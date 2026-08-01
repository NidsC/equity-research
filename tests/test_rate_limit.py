"""Rate limiter tests. No network — the limiter is exercised directly."""

from __future__ import annotations

import time

import pytest

from equity_research.ingest.edgar import (
    SUSTAINED_REQUESTS,
    SUSTAINED_WINDOW_SECONDS,
    RateLimitTripwire,
    _RateLimiter,
)


def test_burst_up_to_capacity_is_immediate():
    limiter = _RateLimiter()
    start = time.monotonic()
    for _ in range(SUSTAINED_REQUESTS):
        limiter.acquire()
    assert time.monotonic() - start < 0.1


def test_request_beyond_burst_waits_for_refill():
    limiter = _RateLimiter()
    for _ in range(SUSTAINED_REQUESTS):
        limiter.acquire()

    start = time.monotonic()
    limiter.acquire()
    elapsed = time.monotonic() - start

    # Refill is SUSTAINED_REQUESTS tokens per SUSTAINED_WINDOW_SECONDS, so one
    # token costs window/capacity seconds.
    expected = SUSTAINED_WINDOW_SECONDS / SUSTAINED_REQUESTS
    assert elapsed >= expected * 0.8


def test_sustained_rate_stays_under_four_per_two_seconds():
    limiter = _RateLimiter()
    start = time.monotonic()
    for _ in range(8):
        limiter.acquire()
    elapsed = time.monotonic() - start

    # 8 requests at 4-per-2s, minus the initial burst of 4, must take at least
    # two more seconds of refill.
    assert elapsed >= 1.6


def test_tripwire_latches_and_stays_latched():
    # Refill fast enough that the bucket never throttles, so grants pile into
    # one second and the tripwire is reachable.
    limiter = _RateLimiter(capacity=50, window_seconds=0.001, tripwire_per_second=8)

    with pytest.raises(RateLimitTripwire):
        for _ in range(20):
            limiter.acquire()

    assert limiter.tripped

    # Latched: every subsequent acquire fails, even after the window passes.
    with pytest.raises(RateLimitTripwire):
        limiter.acquire()


def test_tripwire_is_not_an_exception_subclass():
    """A broad `except Exception` in a retry loop must not swallow the tripwire."""
    assert issubclass(RateLimitTripwire, BaseException)
    assert not issubclass(RateLimitTripwire, Exception)


def test_reset_clears_the_latch():
    limiter = _RateLimiter(capacity=50, window_seconds=0.001, tripwire_per_second=8)
    with pytest.raises(RateLimitTripwire):
        for _ in range(20):
            limiter.acquire()

    limiter.reset()
    assert not limiter.tripped
    limiter.acquire()


def test_default_limiter_sits_well_under_the_sec_ceiling():
    limiter = _RateLimiter()
    assert limiter._refill_per_second == SUSTAINED_REQUESTS / SUSTAINED_WINDOW_SECONDS
    assert limiter._refill_per_second <= 2.0  # SEC ceiling is 10/s
