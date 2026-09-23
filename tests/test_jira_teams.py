"""Tests for Jira Team field JQL helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")

import jira_teams


class TestJiraTeamsJql:
    def test_single_team(self):
        clause = jira_teams.build_team_jql_clause(
            ["317996a7-118a-4cf3-a3c6-04163516ed32"],
        )
        assert clause == 'cf[10700] = "317996a7-118a-4cf3-a3c6-04163516ed32"'

    def test_multiple_teams(self):
        clause = jira_teams.build_team_jql_clause(
            [
                "317996a7-118a-4cf3-a3c6-04163516ed32",
                "9b5dc24e-0a1b-4634-98ac-9a1a43bcec4e",
            ],
        )
        assert "cf[10700] in (" in clause
        assert "317996a7" in clause
        assert "9b5dc24e" in clause

    def test_append_filter_before_order_by(self):
        jql = jira_teams.append_issue_team_filter(
            "project = PIC AND fixVersion = 123 ORDER BY key ASC",
            ["9b5dc24e-0a1b-4634-98ac-9a1a43bcec4e"],
        )
        assert "ORDER BY key ASC" in jql
        assert jql.index("AND (cf[10700]") < jql.index("ORDER BY")

    def test_normalize_display_name(self):
        assert jira_teams.normalize_team_display_name(
            "\U0001f512\ufe0e Glofox Insights Customize",
        ) == "Glofox Insights Customize"
