"""Tests for release_stats.compute_quick_stats + caching."""

from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

import config
from release_stats import (
    _CACHE_TTL_SECONDS,
    QuickStats,
    _month_start,
    _quarter_start,
    compute_quick_stats,
    get_cached_stats,
    record_draft_timing,
)


def _issue(key, created, approvers=None):
    fields = {"created": created}
    cf = (config.TCKT_FIELDS or {}).get("approvers", "")
    if cf and approvers:
        fields[cf] = [{"displayName": n} for n in approvers]
    return {"key": key, "fields": fields}


class TestQuarterMonthHelpers:
    def test_quarter_start(self):
        assert _quarter_start(date(2026, 5, 15)) == date(2026, 4, 1)
        assert _quarter_start(date(2026, 1, 1)) == date(2026, 1, 1)
        assert _quarter_start(date(2026, 12, 31)) == date(2026, 10, 1)

    def test_month_start(self):
        assert _month_start(date(2026, 4, 20)) == date(2026, 4, 1)


class TestComputeQuickStats:
    def test_empty(self):
        out = compute_quick_stats([])
        assert out.total == 0
        assert out.last_release_date == ""
        assert out.most_used_approver == ""

    def test_totals_and_last_date(self):
        today = date(2026, 4, 20)
        issues = [
            _issue("TCKT-1", "2026-04-18T10:00:00.000+0000"),
            _issue("TCKT-2", "2026-04-10T10:00:00.000+0000"),
            _issue("TCKT-3", "2025-12-01T10:00:00.000+0000"),
        ]
        stats = compute_quick_stats(issues, today=today)
        assert stats.total == 3
        assert stats.this_month == 2
        assert stats.this_quarter == 2
        assert stats.last_release_date == "2026-04-18"

    def test_avg_draft_minutes(self):
        stats = compute_quick_stats([], draft_timings=[60.0, 120.0])
        assert stats.avg_draft_to_create_minutes == 1.5

    def test_draft_timings_filters_non_positive(self):
        stats = compute_quick_stats([], draft_timings=[0, -10, 300])
        assert stats.avg_draft_to_create_minutes == 5.0

    def test_most_used_approver(self):
        with patch.object(config, "TCKT_FIELDS", {"approvers": "cf_approvers"}):
            issues = [
                _issue("TCKT-1", "2026-04-18T10:00:00.000+0000", approvers=["Alice"]),
                _issue("TCKT-2", "2026-04-19T10:00:00.000+0000", approvers=["Alice", "Bob"]),
                _issue("TCKT-3", "2026-04-20T10:00:00.000+0000", approvers=["Bob"]),
            ]
            stats = compute_quick_stats(issues, today=date(2026, 4, 20))
        assert stats.most_used_approver in ("Alice", "Bob")
        assert stats.approver_counts.get("Alice") == 2
        assert stats.approver_counts.get("Bob") == 2

    def test_malformed_created_ignored(self):
        stats = compute_quick_stats([_issue("T-1", "not-a-date")])
        assert stats.total == 1
        assert stats.last_release_date == ""

    def test_to_dict(self):
        stats = compute_quick_stats([_issue("T", "2026-04-18T10:00:00.000+0000")])
        d = stats.to_dict()
        assert d["total"] == 1
        assert "last_release_date" in d


class TestCaching:
    def test_cache_hit(self):
        cache: dict = {}
        count = {"n": 0}

        def fetch():
            count["n"] += 1
            return []

        get_cached_stats(fetch, cache=cache)
        get_cached_stats(fetch, cache=cache)
        assert count["n"] == 1

    def test_cache_expired(self):
        cache: dict = {}
        count = {"n": 0}

        def fetch():
            count["n"] += 1
            return []

        with patch("release_stats.time.time", return_value=1000.0):
            get_cached_stats(fetch, cache=cache, now=lambda: 1000.0)
        get_cached_stats(fetch, cache=cache, now=lambda: 1000.0 + _CACHE_TTL_SECONDS + 1)
        assert count["n"] == 2

    def test_fetch_failure_returns_empty_stats(self):
        def raiser():
            raise RuntimeError("no net")

        stats = get_cached_stats(raiser)
        assert stats.total == 0

    def test_record_draft_timing(self):
        cache: dict = {}
        record_draft_timing(cache, 45.5)
        record_draft_timing(cache, 30.0)
        assert cache["_release_stats_timings"] == [45.5, 30.0]


class TestQuickStatsDataclass:
    def test_defaults(self):
        q = QuickStats()
        assert q.total == 0
        assert q.approver_counts == {}
