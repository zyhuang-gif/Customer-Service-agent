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
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            attempt = self._attempts.get(key)
            if attempt is None:
                return 0
            started_at, count = attempt
            remaining = self.window_seconds - (now - started_at)
            if remaining <= 0:
                self._attempts.pop(key, None)
                return 0
            return math.ceil(remaining) if count >= self.limit else 0

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            started_at, count = self._attempts.get(key, (now, 0))
            if now - started_at >= self.window_seconds:
                started_at, count = now, 0
            self._attempts[key] = (started_at, count + 1)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()


customer_auth_limiter = FixedWindowRateLimiter(
    limit=settings.customer_auth_rate_limit_attempts,
    window_seconds=settings.customer_auth_rate_limit_window_minutes * 60,
)
