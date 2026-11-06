import asyncio

import pytest

from src.domain.errors import DomainError
from src.infrastructure.rate_limit import InMemoryRateLimiter


async def test_limit_and_exact_expiry():
    clock = [100.0]
    limiter = InMemoryRateLimiter("test-secret", clock=lambda: clock[0])
    await limiter.check("login", "user@example.com", 1, 60)
    with pytest.raises(DomainError) as error:
        await limiter.check("login", "user@example.com", 1, 60)
    assert error.value.status == 429
    assert error.value.retry_after == 60
    assert "user@example.com" not in repr(limiter._buckets)
    clock[0] += 60
    await limiter.check("login", "user@example.com", 1, 60)


async def test_simultaneous_calls_cannot_exceed_limit():
    limiter = InMemoryRateLimiter("test-secret")

    async def attempt():
        try:
            await limiter.check("login", "same-user", 3, 60)
            return True
        except DomainError as exc:
            assert exc.status == 429
            return False

    assert sum(await asyncio.gather(*(attempt() for _ in range(20)))) == 3


async def test_capacity_is_bounded_and_expired_keys_reclaimed():
    clock = [100.0]
    limiter = InMemoryRateLimiter("test-secret", max_keys=2, clock=lambda: clock[0])
    await limiter.check("login", "a", 1, 60)
    await limiter.check("login", "b", 1, 60)
    with pytest.raises(DomainError) as error:
        await limiter.check("login", "c", 1, 60)
    assert error.value.status == 503
    assert len(limiter._buckets) == len(limiter._expiry) == 2
    clock[0] += 60
    await limiter.check("login", "c", 1, 60)
    assert len(limiter._buckets) == len(limiter._expiry) == 1


async def test_scopes_are_independent():
    limiter = InMemoryRateLimiter("test-secret")
    await limiter.check("login", "user", 1, 60)
    await limiter.check("assistant", "user", 1, 60)
