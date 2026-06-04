from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from app.config import settings


class FixedWindowRateLimiter:
    """进程内演示限流器；生产多实例部署应替换为 Redis 等共享存储。"""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        max_keys: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._attempts: dict[str, tuple[float, int, float]] = {}
        self._lock = threading.Lock()

    def _cleanup_expired(self, now: float) -> None:
        expired = [
            key
            for key, (started_at, _, _) in self._attempts.items()
            if now - started_at >= self.window_seconds
        ]
        for key in expired:
            self._attempts.pop(key, None)

    def _make_room(self) -> None:
        if len(self._attempts) < self.max_keys:
            return
        oldest_key = min(
            self._attempts,
            key=lambda key: (self._attempts[key][0], self._attempts[key][2]),
        )
        self._attempts.pop(oldest_key, None)

    def retry_after(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            self._cleanup_expired(now)
            attempt = self._attempts.get(key)
            if attempt is None:
                return 0
            started_at, count, _ = attempt
            self._attempts[key] = (started_at, count, now)
            remaining = self.window_seconds - (now - started_at)
            return math.ceil(remaining) if count >= self.limit else 0

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            self._cleanup_expired(now)
            attempt = self._attempts.get(key)
            if attempt is None:
                self._make_room()
                started_at, count = now, 0
            else:
                started_at, count, _ = attempt
            self._attempts[key] = (started_at, count + 1, now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()


customer_auth_limiter = FixedWindowRateLimiter(
    limit=settings.customer_auth_rate_limit_attempts,
    window_seconds=settings.customer_auth_rate_limit_window_minutes * 60,
    max_keys=settings.customer_auth_rate_limit_max_keys,
)
