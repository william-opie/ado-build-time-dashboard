"""FastAPI application that exposes an Azure DevOps build dashboard."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.clients.azure_devops import AzureDevOpsClient, AzureDevOpsError
from app.config import Settings, get_settings
from app.logging_config import configure_logging
from app.rate_limit import RateLimiter
from app.utils import branch_has_wildcard, normalize_branch

configure_logging()
LOGGER = logging.getLogger(__name__)

settings = get_settings()
client = AzureDevOpsClient(settings)
rate_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)

app = FastAPI(title="Azure DevOps Pipeline Runtime Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def apply_rate_limiting(request: Request, call_next):  # type: ignore[override]
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Unhandled exception", extra={"client_ip": client_ip})
        raise exc
    return response


def get_client(settings: Settings = Depends(get_settings)) -> AzureDevOpsClient:
    """Provide a configured Azure DevOps client."""

    return client


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve the dashboard shell."""

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "defaults": {
                "days": settings.default_days,
                "top": settings.default_top,
            },
        },
    )


@app.get("/api/builds")
def get_builds(
    request: Request,
    branch: Optional[str] = Query(None, description="Branch name or wildcard pattern."),
    days: int = Query(settings.default_days, ge=1, le=settings.max_days),
    top: int = Query(settings.default_top, ge=1, le=settings.max_top),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200, alias="pageSize"),
    timezone_name: str = Query("UTC", description="IANA timezone, e.g. 'America/Los_Angeles'."),
    pipeline: Optional[str] = Query(
        None, description="Case-insensitive substring to filter by pipeline name."
    ),
    results: list[str] | None = Query(
        None, description="Build results to include (repeat param for multiples)."
    ),
    azdo_client: AzureDevOpsClient = Depends(get_client),
) -> dict:
    """Fetch builds from Azure DevOps with pagination, caching, and filtering."""

    wildcard_pattern = None
    branch_for_api = None
    if branch:
        normalized = normalize_branch(branch)
        if branch_has_wildcard(branch):
            wildcard_pattern = normalized
        else:
            branch_for_api = normalized

    try:
        raw = azdo_client.fetch_builds(branch=branch_for_api, days=days, top=top)
        builds = azdo_client.transform_builds(
            raw, timezone_name=timezone_name, wildcard_pattern=wildcard_pattern
        )
    except AzureDevOpsError as exc:  # pragma: no cover - simple rethrow
        LOGGER.warning("Azure DevOps error", extra={"detail": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Failed to fetch builds")
        raise HTTPException(status_code=500, detail="Unable to fetch builds.") from exc

    result_filters = {value.lower() for value in (results or []) if value}
    if result_filters:
        builds = [
            build for build in builds if (build.get("result") or "").lower() in result_filters
        ]

    pipeline_filter = (pipeline or "").strip().lower()
    if pipeline_filter:
        builds = [
            build
            for build in builds
            if pipeline_filter in (build.get("pipelineName") or "").lower()
        ]

    if top:
        builds = builds[:top]

    total = len(builds)
    start = (page - 1) * page_size
    end = start + page_size
    paged_builds = builds[start:end]

    return {
        "branch": branch,
        "days": days,
        "top": top,
        "page": page,
        "pageSize": page_size,
        "pipeline": pipeline,
        "timezone": timezone_name,
        "total": total,
        "count": len(paged_builds),
        "builds": paged_builds,
    }
