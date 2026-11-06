import asyncio
import hashlib
import heapq
import hmac
import math
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from src.domain.errors import DomainError


@dataclass(slots=True)
class Bucket:
    count: int
    expires_at: float


class InMemoryRateLimiter:
    """Bounded fixed windows for ONE API process; state resets on restart."""

    def __init__(
        self,
        secret: str,
        max_keys: int = 10000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be positive")
        self._secret = secret.encode()
        self._max_keys = max_keys
        self._clock = clock
        self._buckets: dict[str, Bucket] = {}
        self._expiry: list[tuple[float, str]] = []
        self._lock = asyncio.Lock()

    async def check(self, scope: str, identity: str, limit: int, seconds: int) -> None:
        if limit < 1 or seconds < 1:
            raise ValueError("limit and seconds must be positive")
        digest = hmac.new(self._secret, identity.encode(), hashlib.sha256).hexdigest()
        key = f"{scope}:{digest}"
        async with self._lock:
            now = self._clock()
            while self._expiry and self._expiry[0][0] <= now:
                _, expired_key = heapq.heappop(self._expiry)
                self._buckets.pop(expired_key, None)
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    raise DomainError(
                        503,
                        "rate_limiter_capacity",
                        "Please retry shortly.",
                        retry_after=60,
                    )
                bucket = Bucket(count=0, expires_at=now + seconds)
                self._buckets[key] = bucket
                heapq.heappush(self._expiry, (bucket.expires_at, key))
            if bucket.count >= limit:
                raise DomainError(
                    429,
                    "rate_limited",
                    "Too many requests. Please try again later.",
                    retry_after=max(1, math.ceil(bucket.expires_at - now)),
                )
            bucket.count += 1
