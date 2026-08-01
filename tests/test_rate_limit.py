"""Rate limiter tests. No network — the limiters are exercised directly."""

from __future__ import annotations

import time

import pytest

from equity_research.ingest.edgar import (
    LOCK_FILENAME,
    SUSTAINED_REQUESTS,
    SUSTAINED_WINDOW_SECONDS,
    RateLimitTripwire,
    _CrossProcessGate,
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


# ---- cross-process gate ------------------------------------------------
#
# Separate gate instances over one ledger file stand in for separate worker
# processes: all of the shared state lives in the file, so two instances are
# indistinguishable from two interpreters.


def _gate(tmp_path, **kw):
    return _CrossProcessGate(tmp_path / LOCK_FILENAME, **kw)


def test_gate_paces_a_second_process_that_did_not_spend_the_budget(tmp_path):
    """The whole point: worker B is throttled by worker A's traffic."""
    a = _gate(tmp_path, capacity=2, window_seconds=1.0)
    b = _gate(tmp_path, capacity=2, window_seconds=1.0)

    a.acquire()
    a.acquire()

    # B has its own in-process budget but shares the ledger, so it must wait.
    start = time.monotonic()
    b.acquire()
    assert time.monotonic() - start >= 0.5


def test_independent_gates_on_separate_ledgers_do_not_interfere(tmp_path):
    """Different cache dirs are different SEC conversations; no shared pacing."""
    one = (tmp_path / "one").resolve()
    two = (tmp_path / "two").resolve()
    one.mkdir()
    two.mkdir()

    a = _gate(one, capacity=2, window_seconds=1.0)
    b = _gate(two, capacity=2, window_seconds=1.0)

    a.acquire()
    a.acquire()

    start = time.monotonic()
    b.acquire()
    assert time.monotonic() - start < 0.1


def test_gate_tripwire_measures_the_aggregate(tmp_path):
    # Capacity high enough that the bucket never throttles, so grants pile up
    # inside the observation window and the tripwire becomes reachable.
    gate = _gate(tmp_path, capacity=50, window_seconds=2.0, tripwire_per_second=4)

    with pytest.raises(RateLimitTripwire, match="across all processes"):
        for _ in range(10):
            gate.acquire()


def test_gate_tripwire_fires_on_traffic_it_did_not_issue(tmp_path):
    """A gate must trip on the ledger's total, not just its own grants."""
    noisy = _gate(tmp_path, capacity=50, window_seconds=2.0, tripwire_per_second=4)
    quiet = _gate(tmp_path, capacity=50, window_seconds=2.0, tripwire_per_second=4)

    for _ in range(3):
        noisy.acquire()

    # `quiet` has issued nothing, but the shared ledger is already at the line.
    with pytest.raises(RateLimitTripwire):
        quiet.acquire()


def test_gate_survives_a_corrupt_ledger(tmp_path):
    ledger = tmp_path / LOCK_FILENAME
    ledger.write_text("{not json at all")

    gate = _gate(tmp_path, capacity=2, window_seconds=1.0)
    gate.acquire()  # must not raise

    assert ledger.read_text().startswith("[")


def test_client_gate_points_at_its_own_cache_dir(tmp_path, monkeypatch):
    from equity_research.ingest.edgar import EdgarClient

    monkeypatch.setenv("EDGAR_USER_AGENT", "Test test@example.com")
    with EdgarClient(cache_dir=tmp_path) as client:
        assert client._gate._path == tmp_path / LOCK_FILENAME
