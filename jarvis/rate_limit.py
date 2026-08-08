"""Лёгкий rate limiter для внешних вызовов (поиск, Telegram API, HTTP).

Использование::

    from jarvis.rate_limit import rate_limiter

    rate_limiter.wait("web_search")  # блокирует если слишком частые вызовы
    # ... делаем запрос ...

Конфигурация в config.yaml::

  rate_limit:
    enabled: true
    per_second: 1.0    # минимальный интервал между вызовами (секунды)
    burst: 3           # сколько вызовов позволено подряд до throttling
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class _Bucket:
    """Token bucket для одной группы вызовов."""

    tokens: float
    max_tokens: float
    last_refill: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class RateLimiter:
    """Thread-safe token-bucket rate limiter.

    Каждая группа вызовов (например, «web_search») имеет свой bucket.
    При вызове wait() блокируется, пока не будет доступен токен.
    """

    def __init__(self, per_second: float = 1.0, burst: int = 3, enabled: bool = True) -> None:
        self._per_second = per_second
        self._burst = float(burst)
        self._enabled = enabled
        self._buckets: dict[str, _Bucket] = {}
        self._global_lock = threading.Lock()

    def _get_bucket(self, group: str) -> _Bucket:
        with self._global_lock:
            if group not in self._buckets:
                self._buckets[group] = _Bucket(
                    tokens=self._burst,
                    max_tokens=self._burst,
                    last_refill=time.monotonic(),
                )
            return self._buckets[group]

    def wait(self, group: str) -> None:
        """Блокируется, если вызовы слишком частые. Иначе возвращается сразу."""
        if not self._enabled:
            return

        bucket = self._get_bucket(group)
        with bucket.lock:
            now = time.monotonic()
            # Пополнение токенов
            elapsed = now - bucket.last_refill
            bucket.tokens = min(
                bucket.max_tokens,
                bucket.tokens + elapsed * self._per_second,
            )
            bucket.last_refill = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return

            # Сколько ждать до следующего токена
            wait_s = (1.0 - bucket.tokens) / self._per_second
            log.debug(
                "rate_limit[%s]: throttled, wait %.1fs (tokens=%.1f/%.0f)",
                group, wait_s, bucket.tokens, bucket.max_tokens,
            )
            time.sleep(wait_s)
            bucket.tokens = 0.0
            bucket.last_refill = time.monotonic()

    def configure(self, per_second: float | None = None, burst: int | None = None, enabled: bool | None = None) -> None:
        """Обновляет параметры. None = не менять."""
        if per_second is not None:
            self._per_second = per_second
        if burst is not None:
            self._burst = float(burst)
        if enabled is not None:
            self._enabled = enabled


# Глобальный экземпляр.
rate_limiter = RateLimiter()
