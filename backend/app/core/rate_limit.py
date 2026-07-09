"""Sliding-window request rate limiting."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


@dataclass
class RateLimitConfig:
    max_requests: int
    window_seconds: int

    @classmethod
    def parse(cls, value: str) -> RateLimitConfig:
        count, _, unit = value.partition("/")
        count = int(count.strip())
        unit = unit.strip()
        seconds = {
            "second": 1,
            "sec": 1,
            "s": 1,
            "minute": 60,
            "min": 60,
            "m": 60,
            "hour": 3600,
            "h": 3600,
        }.get(unit, 60)
        return cls(max_requests=count, window_seconds=seconds)


class RateLimitStore(Protocol):
    def check(self, key: str, config: RateLimitConfig) -> None: ...

    def reset(self) -> None: ...


class InMemoryRateLimitStore:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, config: RateLimitConfig) -> None:
        now = time.monotonic()
        cutoff = now - config.window_seconds
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= config.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {key}",
                )
            bucket.append(now)

    def reset(self) -> None:
        """Clear all rate-limit state. Intended for tests."""
        with self._lock:
            self._buckets.clear()


class RedisRateLimitStore:
    def __init__(
        self,
        redis_client: Any,
        *,
        namespace: str = "transcriber:rate-limit",
        clock=time.time,
    ) -> None:
        self.redis = redis_client
        self.namespace = namespace.rstrip(":")
        self.clock = clock

    def check(self, key: str, config: RateLimitConfig) -> None:
        redis_key = f"{self.namespace}:{key}"
        now = self.clock()
        cutoff = now - config.window_seconds
        try:
            self.redis.zremrangebyscore(redis_key, 0, cutoff)
            if int(self.redis.zcard(redis_key)) >= config.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {key}",
                )
            self.redis.zadd(redis_key, {f"{now}:{uuid.uuid4()}": now})
            self.redis.expire(redis_key, config.window_seconds)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limit storage is unavailable",
            ) from error

    def reset(self) -> None:
        pattern = f"{self.namespace}:*"
        keys = list(self.redis.scan_iter(pattern))
        if keys:
            self.redis.delete(*keys)


class RateLimiter:
    def __init__(self) -> None:
        self._store: RateLimitStore | None = None
        self._lock = threading.Lock()

    def check(self, key: str, config: RateLimitConfig) -> None:
        self._get_store().check(key, config)

    def reset(self) -> None:
        with self._lock:
            if self._store is not None:
                self._store.reset()
            self._store = None

    def _get_store(self) -> RateLimitStore:
        with self._lock:
            if self._store is None:
                self._store = _build_store()
            return self._store


def _build_store() -> RateLimitStore:
    settings = get_settings()
    if settings.rate_limit_storage == "memory":
        return InMemoryRateLimitStore()

    from redis import Redis

    client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    return RedisRateLimitStore(client, namespace=settings.rate_limit_namespace)


limiter = RateLimiter()


def rate_limit(bucket: str, config_value: str):
    """FastAPI dependency factory enforcing a rate limit per client IP."""
    config = RateLimitConfig.parse(config_value)

    async def dependency(request: Request) -> None:
        client = request.client.host if request.client else "anonymous"
        limiter.check(f"{bucket}:{client}", config)

    return dependency
