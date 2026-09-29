"""Tests for ui.tckt_history filtering + formatting."""

from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

import config
from release_platform.ui.tckt_history import _format_approvers, _matches_filters


def _t(key, created, summary="S", status="Done", approvers=None):
    cf = (config.TCKT_FIELDS or {}).get("approvers", "") or "cf_approvers"
    fields = {
        "summary": summary,
        "created": created,
        "status": {"name": status},
    }
    if approvers is not None:
        fields[cf] = [{"displayName": n} for n in approvers]
    return {"key": key, "fields": fields}


class TestFormatApprovers:
    def test_empty_when_no_cf(self):
        with patch.object(config, "TCKT_FIELDS", {}):
            assert _format_approvers({"cf_approvers": [{"displayName": "X"}]}) == []

    def test_extracts_display_names(self):
        with patch.object(config, "TCKT_FIELDS", {"approvers": "cf_approvers"}):
            names = _format_approvers({"cf_approvers": [
                {"displayName": "Alice"}, {"accountId": "x"},
            ]})
        assert names == ["Alice", "x"]

    def test_single_dict_accepted(self):
        with patch.object(config, "TCKT_FIELDS", {"approvers": "cf_approvers"}):
            names = _format_approvers({"cf_approvers": {"displayName": "Alice"}})
        assert names == ["Alice"]


class TestMatchesFilters:
    def _ticket(self):
        with patch.object(config, "TCKT_FIELDS", {"approvers": "cf_approvers"}):
            return _t(
                "TCKT-1", "2026-04-14T10:00:00.000+0000",
                summary="Glofox release", status="Done",
                approvers=["Alice"],
            )

    def test_query_match_summary(self):
        t = self._ticket()
        assert _matches_filters(
            t, query="Glofox", status_filter="All",
            date_from=None, date_to=None, approver_filter="All",
        )

    def test_query_match_key(self):
        t = self._ticket()
        assert _matches_filters(
            t, query="TCKT-1", status_filter="All",
            date_from=None, date_to=None, approver_filter="All",
        )

    def test_query_no_match(self):
        t = self._ticket()
        assert not _matches_filters(
            t, query="nothing", status_filter="All",
            date_from=None, date_to=None, approver_filter="All",
        )

    def test_status_filter(self):
        t = self._ticket()
        assert not _matches_filters(
            t, query="", status_filter="Open",
            date_from=None, date_to=None, approver_filter="All",
        )

    def test_date_range_inside(self):
        t = self._ticket()
        assert _matches_filters(
            t, query="", status_filter="All",
            date_from=date(2026, 4, 1), date_to=date(2026, 4, 30),
            approver_filter="All",
        )

    def test_date_range_before(self):
        t = self._ticket()
        assert not _matches_filters(
            t, query="", status_filter="All",
            date_from=date(2026, 5, 1), date_to=None,
            approver_filter="All",
        )

    def test_approver_filter_match(self):
        with patch.object(config, "TCKT_FIELDS", {"approvers": "cf_approvers"}):
            t = self._ticket()
            assert _matches_filters(
                t, query="", status_filter="All",
                date_from=None, date_to=None,
                approver_filter="Alice",
            )

    def test_approver_filter_no_match(self):
        with patch.object(config, "TCKT_FIELDS", {"approvers": "cf_approvers"}):
            t = self._ticket()
            assert not _matches_filters(
                t, query="", status_filter="All",
                date_from=None, date_to=None,
                approver_filter="Bob",
            )

    def test_missing_created_with_date_filter_rejected(self):
        t = {"key": "X", "fields": {"summary": "s", "status": {"name": "Done"}}}
        assert not _matches_filters(
            t, query="", status_filter="All",
            date_from=date(2026, 1, 1), date_to=None,
            approver_filter="All",
        )
