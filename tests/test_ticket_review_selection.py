"""Tests for Ticket Review status-mode JQL and selection helpers."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")

import team_scope
from release_platform.ui.ticket_review.selection import MODE_FIX_VERSION, MODE_STATUS, initial_ticket_selection


class TestInitialTicketSelection:
    def test_empty_when_no_lock_fix_version(self):
        assert initial_ticket_selection([], None, mode=MODE_FIX_VERSION) == set()

    def test_locked_intersection_only(self):
        issues = [{"key": "PIC-1"}, {"key": "PIC-2"}, {"key": "PIC-3"}]
        assert initial_ticket_selection(
            issues,
            {"PIC-1", "PIC-99"},
            mode=MODE_FIX_VERSION,
        ) == {"PIC-1"}

    def test_status_mode_selects_all_when_no_lock(self):
        issues = [
            {"key": "PIC-1", "fields": {"status": {"name": "Review"}}},
            {"key": "PIC-2", "fields": {"status": {"name": "In Progress"}}},
            {"key": "AN-1", "fields": {"status": {"name": "Passed QA"}}},
            {"key": "AN-2", "fields": {"status": {"name": "Review"}}},
        ]
        assert initial_ticket_selection(issues, None, mode=MODE_STATUS) == {
            "PIC-1",
            "PIC-2",
            "AN-1",
            "AN-2",
        }


class TestScopedStatusJql:
    def test_build_scoped_status_jql_with_board_filter(self):
        scope = team_scope.TeamScope(board_id="490")
        jql = team_scope.build_scoped_status_jql(
            "PIC",
            ["In Progress", "In Review"],
            scope,
            resolved_filter_id="12345",
        )
        assert "project = PIC" in jql
        assert 'status in ("In Progress", "In Review")' in jql
        assert "filter = 12345" in jql
        assert "ORDER BY updated DESC" in jql

    def test_build_scoped_status_jql_requires_status(self):
        scope = team_scope.TeamScope(allow_project_wide=True)
        with pytest.raises(team_scope.TeamScopeError):
            team_scope.build_scoped_status_jql("AN", [], scope)
