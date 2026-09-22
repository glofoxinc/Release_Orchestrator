"""Tests for the retry helpers."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from common.retry import (
    RetryError,
    RetryLog,
    compute_backoff,
    retry,
    should_retry,
)


class TestComputeBackoff:
    def test_first_attempt_base_delay_no_jitter(self):
        assert compute_backoff(1, base_delay=1.0, max_delay=10.0, jitter=False) == 1.0

    def test_second_attempt_doubled(self):
        assert compute_backoff(2, base_delay=1.0, max_delay=10.0, jitter=False) == 2.0

    def test_multiplier_respected(self):
        assert compute_backoff(3, base_delay=1.0, max_delay=100.0, multiplier=3.0, jitter=False) == 9.0

    def test_capped_at_max_delay(self):
        assert compute_backoff(10, base_delay=1.0, max_delay=5.0, jitter=False) == 5.0

    def test_attempt_floor_at_one(self):
        assert compute_backoff(0, base_delay=1.0, max_delay=10.0, jitter=False) == 1.0
        assert compute_backoff(-5, base_delay=1.0, max_delay=10.0, jitter=False) == 1.0

    def test_jitter_scales_by_rand(self):
        assert compute_backoff(2, base_delay=1.0, max_delay=10.0, jitter=True, rand=lambda: 0.5) == 1.0


class TestShouldRetry:
    def test_retries_on_matching_exception(self):
        assert should_retry(ValueError("x"), (ValueError,), None) is True

    def test_skips_on_non_matching_exception(self):
        assert should_retry(RuntimeError("x"), (ValueError,), None) is False

    def test_predicate_can_veto(self):
        assert should_retry(ValueError("skip"), (ValueError,), lambda e: "retry" in str(e)) is False

    def test_predicate_allows(self):
        assert should_retry(ValueError("retry please"), (ValueError,), lambda e: "retry" in str(e)) is True


class TestRetryDecorator:
    def test_returns_on_success(self):
        @retry(max_attempts=3, base_delay=0, jitter=False, sleep=lambda s: None)
        def ok():
            return 7

        assert ok() == 7

    def test_retries_transient_errors(self):
        calls = {"n": 0}

        @retry(max_attempts=3, base_delay=0, jitter=False, sleep=lambda s: None)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("boom")
            return "ok"

        assert flaky() == "ok"
        assert calls["n"] == 3

    def test_gives_up_after_max_attempts(self):
        @retry(max_attempts=2, base_delay=0, jitter=False, sleep=lambda s: None)
        def always_fail():
            raise RuntimeError("nope")

        with pytest.raises(RetryError) as exc:
            always_fail()
        assert exc.value.attempts == 2

    def test_non_retriable_exception_raises_immediately(self):
        calls = {"n": 0}

        @retry(max_attempts=3, base_delay=0, retry_on=(ValueError,), jitter=False, sleep=lambda s: None)
        def bad():
            calls["n"] += 1
            raise RuntimeError("never retried")

        with pytest.raises(RuntimeError):
            bad()
        assert calls["n"] == 1

    def test_predicate_filters_retries(self):
        @retry(
            max_attempts=3,
            base_delay=0,
            retry_on=(ValueError,),
            predicate=lambda e: "retry" in str(e),
            jitter=False,
            sleep=lambda s: None,
        )
        def sometimes():
            raise ValueError("skip me")

        with pytest.raises(ValueError):
            sometimes()

    def test_audit_records_attempts(self):
        log = RetryLog()

        @retry(max_attempts=3, base_delay=0, jitter=False, sleep=lambda s: None, audit=log)
        def ok():
            return "x"

        assert ok() == "x"
        assert log.succeeded is True

    def test_audit_records_failures(self):
        log = RetryLog()

        @retry(max_attempts=2, base_delay=0, jitter=False, sleep=lambda s: None, audit=log)
        def fail():
            raise RuntimeError("bad")

        with pytest.raises(RetryError):
            fail()
        assert len(log.attempts) >= 1
        d = log.to_dict()
        assert d["succeeded"] is False
        assert d["attempts"]


class TestRetryError:
    def test_has_attempts_and_last_error(self):
        e = RetryError(4, ValueError("x"))
        assert e.attempts == 4
        assert isinstance(e.last_error, ValueError)
        assert "4" in str(e)
