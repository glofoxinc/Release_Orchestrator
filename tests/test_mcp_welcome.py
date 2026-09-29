"""Tests for MCP guided welcome flow."""

from __future__ import annotations

from unittest.mock import patch

from release_mcp import welcome, wizard, wizard_store


def test_welcome_returns_greeting_and_roadmap():
    with patch.object(welcome.config, "JIRA_EMAIL", "a@x.com"), patch.object(
        welcome.config, "JIRA_API_TOKEN", "tok"
    ), patch.object(welcome.config, "JIRA_BASE_URL", "https://abcfinancial.atlassian.net"):
        result = welcome.build_welcome()
    assert result["status"] == "ok"
    assert "Welcome" in result["greeting"]
    assert len(result["step_roadmap"]) >= 5
    assert "PIC" in result["suggested_defaults"]["projects"]
    assert result["step"] == "start_menu"
    assert result["next_actions"]["fetch_review_tickets"]["action"] == "start"


def test_welcome_resolves_glofox_team_by_default():
    result = welcome.resolve_team("")
    assert result["status"] == "ok"
    assert "glofox" in result["team"]["name"].lower()


def test_welcome_resolve_ignite_partial():
    result = welcome.resolve_team("Ignite")
    assert result["status"] == "ok"
    assert "ignite" in result["team"]["name"].lower()


def test_build_start_inputs_status_mode():
    inputs = welcome.build_start_inputs({"team_name": "Glofox Insights Customize"})
    assert inputs["selection_mode"] == "status"
    assert "PIC" in inputs["projects"]
    assert inputs.get("jira_team_ids_by_project")


def test_wizard_welcome_action():
    wizard_store.set_sessions_dir_override(None)
    with patch.object(welcome.config, "JIRA_EMAIL", "a@x.com"), patch.object(
        welcome.config, "JIRA_API_TOKEN", "tok"
    ), patch.object(welcome.config, "JIRA_BASE_URL", "https://abcfinancial.atlassian.net"):
        result = wizard.run_wizard("welcome")
    assert result["status"] == "ok"
    assert result["step"] == "start_menu"
    assert result.get("start_menu_options")


def test_wizard_welcome_confirm_starts_session(tmp_path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    fetch = {
        "status": "ok",
        "projects": ["PIC", "AN"],
        "total_tickets": 1,
        "extracted": [
            {
                "ticket": "PIC-1",
                "summary": "Test",
                "status": "Review",
                "type": "Custom",
                "client": "Jetts",
                "report": "R",
                "description": "d",
                "assignee": "A",
                "parent": "PIC-1",
                "project": "PIC",
                "fix_version": "",
                "link": "https://x/PIC-1",
            }
        ],
        "by_project": {
            "PIC": {"count": 1, "tickets": [{"key": "PIC-1", "summary": "Test", "status": "Review"}]},
            "AN": {"count": 0, "tickets": []},
        },
    }
    with patch.object(welcome.config, "JIRA_EMAIL", "a@x.com"), patch.object(
        welcome.config, "JIRA_API_TOKEN", "tok"
    ), patch.object(welcome.config, "JIRA_BASE_URL", "https://jira.example"), patch(
        "release_mcp.wizard.release_ops.fetch_release_tickets",
        return_value=fetch,
    ):
        result = wizard.run_wizard("welcome", inputs={"confirm_defaults": "yes"})
    assert "workflow_id" in result
    assert result["step"] == wizard.STEP_TICKET_REVIEW
