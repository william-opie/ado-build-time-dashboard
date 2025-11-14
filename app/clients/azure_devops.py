"""Azure DevOps REST API client."""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests
from requests import Response

from app.cache import TTLCache
from app.config import Settings
from app.utils import (
    branch_matches,
    format_duration,
    parse_azdo_time,
    strip_refs_heads,
    to_timezone,
)

LOGGER = logging.getLogger(__name__)


class AzureDevOpsError(RuntimeError):
    """Raised when the Azure DevOps API returns an error."""


class AzureDevOpsClient:
    """Small HTTP client for fetching builds with caching and error handling."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()
        token = base64.b64encode(f":{settings.azdo_pat}".encode("utf-8")).decode("utf-8")
        self._session.headers.update(
            {
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
            }
        )
        self._cache = TTLCache(settings.cache_ttl_seconds)

    def fetch_builds(self, *, branch: Optional[str], days: int, top: int) -> Dict[str, Any]:
        """Return builds from Azure DevOps with caching."""

        cache_key = (branch, days, top)
        cached = self._cache.get(cache_key)
        if cached:
            LOGGER.debug("cache hit", extra={"branch": branch, "top": top})
            return cached

        params = {
            "api-version": "7.1-preview.7",
            "statusFilter": "completed",
            "queryOrder": "finishTimeDescending",
            "top": top,
            "minTime": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(),
        }
        if branch:
            params["branchName"] = branch

        url = f"{self._settings.base_url}/{self._settings.azdo_project}/_apis/build/builds"
        response = self._session.get(url, params=params, timeout=30)
        self._raise_for_status(response)
        payload = response.json()
        self._cache.set(cache_key, payload)
        return payload

    def transform_builds(
        self,
        raw: Dict[str, Any],
        *,
        timezone_name: str,
        wildcard_pattern: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Project raw API builds into dashboard schema."""

        raw_items: Iterable[Dict[str, Any]] = raw.get("value", [])
        if wildcard_pattern:
            raw_items = [
                b
                for b in raw_items
                if branch_matches(b.get("sourceBranch") or "", wildcard_pattern)
            ]
        items = list(raw_items)

        def sort_key(build: Dict[str, Any]) -> datetime:
            finish = parse_azdo_time(build.get("finishTime"))
            start = parse_azdo_time(build.get("startTime"))
            queue = parse_azdo_time(build.get("queueTime"))
            return finish or start or queue or datetime.min.replace(tzinfo=timezone.utc)

        items.sort(key=sort_key, reverse=True)

        builds_out: List[Dict[str, Any]] = []
        for build in items:
            start = parse_azdo_time(build.get("startTime"))
            finish = parse_azdo_time(build.get("finishTime"))
            queue = parse_azdo_time(build.get("queueTime"))
            duration_seconds = format_duration(start, finish)
            web_url = build.get("webUrl")
            if not web_url and (build_id := build.get("id")):
                web_url = (
                    f"https://dev.azure.com/{self._settings.azdo_org}/{self._settings.azdo_project}/"
                    f"_build/results?buildId={build_id}"
                )
            start_timestamp = (start or finish or queue)
            finish_timestamp = finish or start or queue

            builds_out.append(
                {
                    "id": build.get("id"),
                    "buildNumber": build.get("buildNumber"),
                    "pipelineName": (build.get("definition") or {}).get("name"),
                    "sourceBranch": build.get("sourceBranch"),
                    "sourceBranchDisplay": strip_refs_heads(build.get("sourceBranch")),
                    "result": build.get("result"),
                    "status": build.get("status"),
                    "startTime": to_timezone(start, timezone_name),
                    "finishTime": to_timezone(finish, timezone_name),
                    "startTimestamp": start_timestamp.timestamp() if start_timestamp else None,
                    "finishTimestamp": finish_timestamp.timestamp() if finish_timestamp else None,
                    "durationSeconds": duration_seconds,
                    "webUrl": web_url,
                }
            )

        return builds_out

    def _raise_for_status(self, response: Response) -> None:
        """Raise descriptive errors for Azure DevOps responses."""

        if response.ok:
            return
        status = response.status_code
        detail = response.text
        if status == 401:
            message = "Unauthorized: verify AZDO_PAT permissions."
        elif status == 403:
            message = "Forbidden: the PAT lacks Build read permissions."
        elif status == 404:
            message = "Project or organization not found."
        else:
            message = f"Azure DevOps error ({status})."
        LOGGER.error("azdo request failed", extra={"status": status, "detail": detail})
        raise AzureDevOpsError(f"{message} Response: {detail[:200]}")
