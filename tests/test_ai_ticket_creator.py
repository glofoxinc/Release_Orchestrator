"""Tests for AI ticket creator field mapping and Jira submission."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from ai_ticket_creator import build_jira_create_fields, create_ticket_from_nl, parse_ticket_from_nl

SAMPLE = (
    "Bug in the monthly revenue dashboard for Jetts — chart is broken and not working. "
    "Priority: urgent. Production impact."
)


class TestBuildJiraCreateFields:
    def test_includes_priority_description_component_labels(self):
        parsed = parse_ticket_from_nl(SAMPLE, "PIC")
        with patch("jira_client.resolve_component", return_value={"name": "Dashboard"}):
            fields = build_jira_create_fields(parsed, "PIC")

        assert fields["priority"] == {"name": "High"}
        assert fields["description"]["type"] == "doc"
        assert fields["components"] == [{"name": "Dashboard"}]
        assert "ai-bug" in fields["labels"]
        assert "Dashboard" in fields["labels"]
        assert any(label.startswith("triage-") for label in fields["labels"])

    def test_skips_general_component(self):
        parsed = {
            "summary": "Task",
            "description": "Do work",
            "issue_type": "Task",
            "priority": "Medium",
            "component": "General",
            "triage": None,
        }
        fields = build_jira_create_fields(parsed, "PIC")
        assert "components" not in fields
        assert fields["labels"] == ["ai-task"]


class TestCreateTicketFromNl:
    def test_sends_all_mapped_fields_to_jira(self, monkeypatch):
        import jira_client

        jira_client._issue_type_cache.clear()
        jira_client._component_cache.clear()

        created: dict = {}

        def fake_create(project_key, issue_type_id, summary, fields):
            created["project_key"] = project_key
            created["issue_type_id"] = issue_type_id
            created["summary"] = summary
            created["fields"] = fields
            return {"key": "PIC-999"}

        with patch("jira_client.resolve_issue_type_id", return_value="10004"), patch(
            "jira_client.resolve_component", return_value={"name": "Dashboard"}
        ), patch("jira_client.create_issue", side_effect=fake_create):
            result = create_ticket_from_nl(SAMPLE, "PIC")

        assert result["key"] == "PIC-999"
        assert created["project_key"] == "PIC"
        assert created["issue_type_id"] == "10004"
        assert created["fields"]["priority"]["name"] == "High"
        assert created["fields"]["components"] == [{"name": "Dashboard"}]
        assert "labels" in created["fields"]
        assert result["jira_fields"] == created["fields"]

    def test_dry_run_does_not_call_jira(self):
        with patch("jira_client.create_issue") as mock_create:
            result = create_ticket_from_nl(SAMPLE, "PIC", dry_run=True)
        mock_create.assert_not_called()
        assert result["dry_run"] is True
        assert result["fields"]["issue_type"] == "Bug"
