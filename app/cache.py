"""Simple TTL cache implementation."""
from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Hashable


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """Thread-safe TTL cache for API responses."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: Dict[Hashable, CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry.expires_at < time.time():
                self._store.pop(key, None)
                return None
            return entry.value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._store[key] = CacheEntry(value=value, expires_at=time.time() + self._ttl)
