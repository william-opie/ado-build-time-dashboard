"""Simple in-memory IP rate limiter."""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict


class RateLimiter:
    """Tracks requests per client IP within a sliding window."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._requests: Dict[str, Deque[float]] = {}

    def allow(self, client_ip: str) -> bool:
        now = time.time()
        q = self._requests.setdefault(client_ip, deque())
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
