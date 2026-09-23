"""Ticket Review fetch — outside-squad exclusion + squad assignee supplement."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


def test_supplement_adds_in_squad_ticket_without_team(monkeypatch):
    from release_mcp import release_ops as ro

    team_issue = {
        "key": "PIC-6027",
        "fields": {
            "summary": "Lift dashboard",
            "status": {"name": "Review"},
            "assignee": {"displayName": "Chanti Kumar Jakkula", "emailAddress": "a@example.com"},
            "parent": {"key": "PIC-6027"},
        },
    }
    missing_team_issue = {
        "key": "PIC-6195",
        "fields": {
            "summary": "Lift ETL royalties",
            "status": {"name": "Review"},
            "assignee": {"displayName": "Chanti Kumar Jakkula", "emailAddress": "a@example.com"},
            "parent": {"key": "PIC-6195"},
        },
    }
    outside_issue = {
        "key": "PIC-5852",
        "fields": {
            "summary": "FIT4MOM dashboard",
            "status": {"name": "Review"},
            "assignee": {"displayName": "Gabriel Barbosa", "emailAddress": "g@example.com"},
            "parent": {"key": "PIC-5852"},
        },
    }

    def fake_get_issues(project_key, statuses, *, jira_team_ids=None):
        if jira_team_ids:
            return [team_issue]
        return [team_issue, missing_team_issue, outside_issue]

    monkeypatch.setattr(ro.jira_client, "get_issues_for_statuses", fake_get_issues)

    rows = [ro.extracted_row_from_jira_issue(team_issue, project_key="PIC")]
    merged, added = ro._supplement_squad_assignee_status_issues(
        "PIC",
        ["Review"],
        team_ids=["team-id"],
        existing_rows=rows,
    )
    keys = [row["ticket"] for row in merged]
    assert keys == ["PIC-6027", "PIC-6195"]
    assert added == ["PIC-6195"]
    assert "PIC-5852" not in keys
