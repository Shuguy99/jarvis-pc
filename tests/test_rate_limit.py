"""Тесты модуля rate_limit."""

from __future__ import annotations

import time
import threading

from jarvis.rate_limit import RateLimiter


def test_first_call_passes_immediately():
    """Первый вызов не блокируется."""
    rl = RateLimiter(per_second=10, burst=1, enabled=True)
    t0 = time.monotonic()
    rl.wait("test")
    elapsed = time.monotonic() - t0
    assert elapsed < 0.05  # should be near-instant


def test_burst_allows_consecutive_calls():
    """burst=3 позволяет 3 вызова подряд без задержки."""
    rl = RateLimiter(per_second=1, burst=3, enabled=True)
    t0 = time.monotonic()
    for _ in range(3):
        rl.wait("test")
    elapsed = time.monotonic() - t0
    assert elapsed < 0.1  # all 3 should be instant


def test_throttle_after_burst():
    """После исчерпания burst — задержка."""
    rl = RateLimiter(per_second=100, burst=1, enabled=True)
    rl.wait("test")  # consumes the only token
    t0 = time.monotonic()
    rl.wait("test")  # should throttle
    elapsed = time.monotonic() - t0
    # At 100/s, wait = (1.0 - ~0)/100 = 0.01s, but time.sleep has overhead
    # so we just check it actually blocked
    assert elapsed >= 0.005


def test_disabled_bypasses():
    """When enabled=False, no throttling."""
    rl = RateLimiter(per_second=0.001, burst=1, enabled=False)
    t0 = time.monotonic()
    for _ in range(10):
        rl.wait("test")
    elapsed = time.monotonic() - t0
    assert elapsed < 0.05  # all instant


def test_separate_groups_independent():
    """Different groups have independent buckets."""
    rl = RateLimiter(per_second=0.01, burst=1, enabled=True)
    rl.wait("group_a")
    rl.wait("group_b")  # different group, should not throttle
    t0 = time.monotonic()
    rl.wait("group_a")  # should throttle
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.005


def test_thread_safety():
    """Multiple threads can call wait() without crashes."""
    rl = RateLimiter(per_second=10, burst=100, enabled=True)
    errors = []

    def worker():
        try:
            for _ in range(20):
                rl.wait(f"thread-{threading.current_thread().ident}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert errors == []


def test_configure_changes_params():
    """configure() updates parameters."""
    rl = RateLimiter(per_second=1, burst=1, enabled=True)
    rl.wait("test")
    rl.configure(enabled=False)
    t0 = time.monotonic()
    rl.wait("test")  # should NOT throttle now
    elapsed = time.monotonic() - t0
    assert elapsed < 0.05


def test_tokens_refill_over_time():
    """Tokens refill based on elapsed time."""
    rl = RateLimiter(per_second=1000, burst=1, enabled=True)
    rl.wait("test")  # consume token
    time.sleep(0.02)  # wait for refill: 0.02 * 1000 = 20 tokens
    t0 = time.monotonic()
    rl.wait("test")  # should NOT throttle (tokens refilled)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.01
