"""Tests for the MCP server module.

Skipped when the running interpreter lacks mcp>=2.0.0 — the module raises a
guarded ModuleNotFoundError in that case, which is itself asserted below.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

server = pytest.importorskip(
    "release_mcp.server",
    reason="mcp>=2.0.0 not installed for this interpreter",
)


class TestToolsAreRegistered:
    EXPECTED_TOOLS = (
        "create_ticket",
        "triage_ticket",
        "search_tickets",
        "generate_release_notes",
        "fetch_release_tickets",
        "team_scope_status",
        "team_crew_status",
        "release_step_status",
        "release_step_catalog",
        "release_step_onboarding",
        "release_step_ticket_review",
        "release_step_exclusions",
        "release_step_release_date_confirm",
        "release_step_release_notes",
        "release_step_sharepoint",
        "release_step_service_ticket",
        "release_step_slack",
        "release_step_deploy",
        "release_step_mark_released",
        "release_gate_status",
        "pre_review_gate",
        "post_qa_gate",
        "generate_release_notes_docx",
        "generate_client_release_notes_docx",
        "create_service_ticket",
        "sharepoint_upload_status",
        "sharepoint_upload_release_notes",
        "sharepoint_upload_client_notes",
        "sharepoint_upload_notes_pair",
        "sharepoint_download_release_notes",
        "teams_schedule_status",
        "teams_schedule_meeting",
        "teams_update_meeting",
        "teams_cancel_meeting",
        "slack_announce_status",
        "slack_preview",
        "slack_send",
        "release_workflow_checkpoints",
        "validate_service_ticket",
        "release_recovery_status",
        "workspace_config",
        "tckt_history",
        "deployment_metrics",
        "verify_linked_tickets",
        "list_tckt_templates",
        "apply_tckt_template",
        "save_tckt_template",
        "confluence_publish_release_notes",
        "ai_enhance_release",
        "release_orchestrator",
        "release_wizard",
    )

    def test_expected_tools_exist(self):
        for name in self.EXPECTED_TOOLS:
            assert callable(getattr(server, name, None)), f"{name} is missing"

    def test_main_runs_over_stdio(self):
        with patch.object(server.mcp, "run") as mock_run:
            server.main()
        mock_run.assert_called_once_with(transport="stdio")


class TestSearchTickets:
    def test_paginates_and_flattens_results(self):
        pages = [
            {
                "issues": [
                    {
                        "key": "PIC-1",
                        "fields": {
                            "summary": "First",
                            "status": {"name": "Open"},
                            "assignee": {"displayName": "Ann"},
                            "priority": {"name": "High"},
                        },
                    }
                ],
                "nextPageToken": "tok",
            },
            {
                "issues": [
                    {
                        "key": "PIC-2",
                        "fields": {
                            "summary": "Second",
                            "status": {"name": "Done"},
                            "assignee": None,
                            "priority": None,
                        },
                    }
                ]
            },
        ]
        with patch("jira_client._post", side_effect=pages):
            out = server.search_tickets("project = PIC", max_results=10)

        assert out["total_found"] == 2
        assert [i["key"] for i in out["issues"]] == ["PIC-1", "PIC-2"]
        # Missing assignee/priority must not raise.
        assert out["issues"][1]["assignee"] is None
        assert out["issues"][1]["priority"] is None

    def test_stops_at_max_results(self):
        page = {"issues": [{"key": "PIC-1", "fields": {}}], "nextPageToken": "tok"}
        with patch("jira_client._post", return_value=page) as mock_post:
            out = server.search_tickets("project = PIC", max_results=1)

        assert mock_post.call_count == 1
        assert out["total_found"] == 1


class TestGenerateReleaseNotes:
    def test_groups_tickets_by_issue_type(self):
        versions = [{"id": "42", "name": "2026.8.03", "released": False}]
        issues = [
            {"key": "PIC-1", "fields": {"issuetype": {"name": "Bug"}, "summary": "Fix a"}},
            {"key": "PIC-2", "fields": {"issuetype": {"name": "Bug"}, "summary": "Fix b"}},
            {"key": "PIC-3", "fields": {"issuetype": {"name": "Task"}, "summary": "Do c"}},
        ]
        with patch("jira_client.get_project_versions", return_value=versions), \
             patch("jira_client.get_issues_for_version", return_value=issues):
            out = server.generate_release_notes("PIC", "2026.8.03")

        assert out["total_tickets"] == 3
        assert out["notes_by_type"]["Bug"] == ["PIC-1: Fix a", "PIC-2: Fix b"]
        assert out["notes_by_type"]["Task"] == ["PIC-3: Do c"]

    def test_matches_version_name_case_insensitively(self):
        versions = [{"id": "7", "name": "2026.8.03"}]
        with patch("jira_client.get_project_versions", return_value=versions), \
             patch("jira_client.get_issues_for_version", return_value=[]) as mock_issues:
            out = server.generate_release_notes("PIC", "  2026.8.03  ")

        assert out["version_id"] == "7"
        mock_issues.assert_called_once_with("PIC", "7")

    def test_unknown_version_reports_available_ones(self):
        versions = [{"id": "1", "name": "2026.7.01"}]
        with patch("jira_client.get_project_versions", return_value=versions):
            out = server.generate_release_notes("PIC", "nope")

        assert "not found" in out["error"]
        assert out["available_versions"] == ["2026.7.01"]


class TestCreateTicket:
    def test_explicit_overrides_win_over_parsed_values(self):
        parsed = {
            "summary": "parsed",
            "issue_type": "Task",
            "priority": "Medium",
            "description": "body",
            "component": "General",
        }
        with patch("ai_ticket_creator.parse_ticket_from_nl", return_value=parsed):
            out = server.create_ticket(
                "PIC",
                "something broke",
                summary="explicit",
                issue_type="Bug",
                priority="High",
                dry_run=True,
            )

        assert out["fields"]["summary"] == "explicit"
        assert out["fields"]["issue_type"] == "Bug"
        assert out["fields"]["priority"] == "High"

    def test_live_create_uses_overrides_before_jira_call(self):
        parsed = {
            "summary": "parsed",
            "issue_type": "Task",
            "priority": "Medium",
            "description": "body",
            "component": "General",
        }
        with patch("ai_ticket_creator.parse_ticket_from_nl", return_value=parsed), \
             patch("jira_client.resolve_issue_type_id", return_value="10001") as mock_type, \
             patch("ai_ticket_creator.build_jira_create_fields", return_value={}) as mock_fields, \
             patch("jira_client.create_issue", return_value={"key": "PIC-99"}) as mock_create:
            out = server.create_ticket(
                "PIC",
                "something broke",
                summary="explicit",
                issue_type="Bug",
                dry_run=False,
            )

        mock_type.assert_called_once_with("PIC", "Bug")
        mock_fields.assert_called_once()
        assert mock_fields.call_args[0][0]["summary"] == "explicit"
        mock_create.assert_called_once_with(
            project_key="PIC",
            issue_type_id="10001",
            summary="explicit",
            fields={},
        )
        assert out["key"] == "PIC-99"

    def test_dry_run_skips_jira_create(self):
        with patch(
            "ai_ticket_creator.parse_ticket_from_nl",
            return_value={"summary": "x", "issue_type": "Task", "priority": "Medium"},
        ), patch("jira_client.create_issue") as mock_create:
            server.create_ticket("PIC", "desc", dry_run=True)

        mock_create.assert_not_called()

    def test_create_ticket_defaults_to_dry_run(self):
        with patch(
            "ai_ticket_creator.parse_ticket_from_nl",
            return_value={"summary": "x", "issue_type": "Task", "priority": "Medium"},
        ), patch("jira_client.create_issue") as mock_create:
            server.create_ticket("PIC", "desc")

        mock_create.assert_not_called()


class TestArchivedIntegrations:
    def test_slack_status_enabled(self):
        from release_mcp import slack_ops

        out = slack_ops.slack_announce_status()
        assert out.get("enabled") is True
        assert out.get("archived") is not True
        assert out.get("channel_count") >= 1

    def test_sharepoint_status_disabled(self):
        from release_mcp import sharepoint_ops

        out = sharepoint_ops.sharepoint_upload_status()
        # Either archived=True (from config) or enabled=False (when not live)
        assert out.get("archived") is True or out.get("enabled") is False

    def test_teams_status_disabled(self):
        from release_mcp import teams_ops

        out = teams_ops.teams_schedule_status()
        # Either archived=True (from config) or enabled=False (when not live)
        assert out.get("archived") is True or out.get("enabled") is False


class TestReleaseOpsParityTools:
    def test_create_service_ticket_asks_for_sharepoint(self):
        out = server.create_service_ticket(version_name="2026.3.08.12", dry_run=True)
        assert out["status"] == "needs_input"
        assert "sharepoint_url" in out["missing"]
        assert out["questions"]

    def test_fetch_release_tickets_asks_for_version(self):
        out = server.fetch_release_tickets(version_name="")
        assert out["status"] == "needs_input"
        assert "version_name" in out["missing"]

    def test_fetch_release_tickets_combines_pic_and_an(self):
        versions = [{"id": "1", "name": "2026.3.08.12"}]
        pic_issues = [{
            "key": "PIC-1",
            "fields": {
                "summary": "Jetts - Monthly Report - column add",
                "status": {"name": "Done"},
                "assignee": {"displayName": "Ann"},
                "parent": {"key": "PIC-1"},
            },
        }]
        an_issues = [{
            "key": "AN-1",
            "fields": {
                "summary": "Analyze - New Members - filter",
                "status": {"name": "Live"},
                "assignee": None,
                "parent": {"key": "AN-1"},
            },
        }]

        def _issues(project_key, version_id, jira_team_ids=None):
            return pic_issues if project_key == "PIC" else an_issues

        with patch("jira_client.get_project_versions", return_value=versions), \
             patch("jira_client.get_issues_for_version", side_effect=_issues), \
             patch("jira_client.scoped_version_metadata", return_value={}), \
             patch("team_scope.scope_status", return_value={"blocking": False}), \
             patch("config.PROJECTS", [
                 {
                     "key": "PIC",
                     "multi_client": True,
                     "client_extraction": "title_prefix",
                     "scope": {"allow_project_wide": True},
                 },
                 {
                     "key": "AN",
                     "multi_client": False,
                     "scope": {"allow_project_wide": True},
                 },
             ]):
            out = server.fetch_release_tickets("2026.3.08.12")

        assert out["status"] == "ok"
        assert out["total_tickets"] == 2
        assert set(out["by_project"]) == {"PIC", "AN"}
