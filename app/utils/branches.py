"""Branch parsing helpers."""
from __future__ import annotations

from fnmatch import fnmatch


def normalize_branch(branch: str) -> str:
    """Ensure a branch is prefixed with ``refs/heads``."""

    branch = branch.strip()
    if not branch:
        return branch
    if branch.startswith("refs/"):
        return branch
    return f"refs/heads/{branch}"


def strip_refs_heads(branch: str | None) -> str | None:
    """Remove ``refs/heads`` prefix for display purposes."""

    if branch and branch.startswith("refs/heads/"):
        return branch[len("refs/heads/"):]
    return branch


def branch_has_wildcard(branch: str) -> bool:
    """Return ``True`` when the branch contains wildcard tokens."""

    return any(symbol in branch for symbol in ("*", "?", "[", "]"))


def branch_matches(branch: str, pattern: str) -> bool:
    """Check whether ``branch`` satisfies a wildcard ``pattern``."""

    return fnmatch(branch or "", pattern)
