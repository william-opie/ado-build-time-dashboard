"""Application settings and environment loading utilities."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _validate_non_empty(value: Optional[str], name: str) -> str:
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    """Runtime configuration derived from environment variables."""

    azdo_org: str
    azdo_project: str
    azdo_pat: str
    default_days: int = 7
    max_days: int = 365
    default_top: int = 200
    max_top: int = 1000
    cache_ttl_seconds: int = 60
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    @property
    def base_url(self) -> str:
        return f"https://dev.azure.com/{self.azdo_org}"

    @classmethod
    def from_env(cls) -> "Settings":
        org = _validate_non_empty(os.getenv("AZDO_ORG"), "AZDO_ORG")
        project = _validate_non_empty(os.getenv("AZDO_PROJECT"), "AZDO_PROJECT")
        pat = _validate_non_empty(os.getenv("AZDO_PAT"), "AZDO_PAT")

        cache_ttl = int(os.getenv("AZDO_CACHE_TTL_SECONDS", "60"))
        rate_limit_requests = int(os.getenv("AZDO_RATE_LIMIT_REQUESTS", "60"))
        rate_limit_window = int(os.getenv("AZDO_RATE_LIMIT_WINDOW_SECONDS", "60"))

        return cls(
            azdo_org=org,
            azdo_project=project,
            azdo_pat=pat,
            cache_ttl_seconds=cache_ttl,
            rate_limit_requests=rate_limit_requests,
            rate_limit_window_seconds=rate_limit_window,
        )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings.from_env()
