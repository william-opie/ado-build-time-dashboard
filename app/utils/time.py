"""Time helpers."""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_azdo_time(ts: str | None) -> datetime | None:
    """Parse the Azure DevOps timestamp into a timezone-aware datetime."""

    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def format_duration(start: datetime | None, finish: datetime | None) -> float | None:
    """Return build duration in seconds."""

    if not start or not finish:
        return None
    return (finish - start).total_seconds()


def to_timezone(value: datetime | None, tz_name: str) -> str | None:
    """Convert a datetime to the requested timezone and display string."""

    if value is None:
        return None
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = UTC
    localized = value.astimezone(tz)
    hour_24 = localized.hour
    hour_12 = hour_24 % 12 or 12
    meridiem = "AM" if hour_24 < 12 else "PM"
    return f"{localized.month}/{localized.day}/{localized.year} {hour_12}:{localized.minute:02d} {meridiem}"
