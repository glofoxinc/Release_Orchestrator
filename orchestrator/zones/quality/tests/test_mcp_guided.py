"""Tests for conversational release_orchestrator MCP entry point."""

from __future__ import annotations

from unittest.mock import patch

from release_mcp import guided, welcome, wizard, wizard_store


def test_interpret_welcome_message():
    plan = guided.interpret_message("welcome")
    assert plan["action"] == "welcome"
    assert plan["intent"] == "welcome"


def test_interpret_yes_without_workflow_starts_fetch_path():
    plan = guided.interpret_message("yes")
    assert plan["action"] == "welcome"
    assert plan["inputs"]["start_path"] == "fetch_review_tickets"


def test_interpret_ignite_team():
    plan = guided.interpret_message("use Ignite instead")
    assert plan["action"] == "welcome"
    assert plan["intent"] == "team_onboard"
    assert plan["inputs"].get("interactive_onboarding") is True
    draft = plan["inputs"].get("team_inputs", {}).get("team_crew_draft", {})
    assert "Ignite" in draft.get("team_name", "")


def test_enrich_adds_say_to_user():
    with patch.object(welcome.config, "JIRA_EMAIL", "a@x.com"), patch.object(
        welcome.config, "JIRA_API_TOKEN", "tok"
    ), patch.object(welcome.config, "JIRA_BASE_URL", "https://abcfinancial.atlassian.net"), patch(
        "release_mcp.onboarding_verify.setup_complete", return_value=True
    ):
        body = welcome.build_welcome()
        enriched = guided.enrich_response(body, user_message="welcome")
    assert enriched["guided"] is True
    assert "full release" in enriched["say_to_user"].lower()
    assert enriched["user_can_say"]


def test_run_guided_help():
    with patch.object(welcome.config, "JIRA_EMAIL", "a@x.com"), patch.object(
        welcome.config, "JIRA_API_TOKEN", "tok"
    ), patch.object(welcome.config, "JIRA_API_TOKEN", "tok"), patch.object(
        welcome.config, "JIRA_BASE_URL", "https://jira.example"
    ):
        result = guided.run_guided("help")
    assert result.get("help")
    assert result["say_to_user"]


def test_interpret_onboarding():
    plan = guided.interpret_message("onboarding")
    assert plan["action"] == "beginner_wizard"
    assert plan["intent"] == "onboarding"


def test_interpret_welcome_onboard():
    plan = guided.interpret_message("welcome onboard")
    assert plan["intent"] == "welcome_onboard"
    assert plan["action"] == "beginner_wizard"
    assert plan["inputs"].get("message") == "welcome onboard"


def test_interpret_start_shows_menu():
    plan = guided.interpret_message("start")
    assert plan["intent"] == "start_menu"
    assert plan["inputs"].get("show_start_menu") is True


def test_interpret_start_path_release_notes():
    plan = guided.interpret_message("start with release notes")
    assert plan["inputs"]["start_path"] == "release_notes"


def test_interpret_create_release_notes_start_path():
    plan = guided.interpret_message("create release notes")
    assert plan["inputs"]["start_path"] == "release_notes"


def test_interpret_create_release_notes_confirms_at_step(tmp_path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_RELEASE_NOTES,
    )
    wizard_store.update_session(
        session["id"],
        confirmations={
            wizard.STEP_RELEASE_NOTES: {"token": "tok-rn", "status": "pending"},
        },
    )
    plan = guided.interpret_message("create release notes", workflow_id=session["id"])
    assert plan["action"] == "confirm"
    assert plan["confirmation_token"] == "tok-rn"


def test_interpret_start_path_shipit():
    plan = guided.interpret_message("create SHIPIT ticket")
    assert plan["inputs"]["start_path"] == "shipit"


def test_interpret_create_shipit_start_path():
    plan = guided.interpret_message("create shipit")
    assert plan["inputs"]["start_path"] == "shipit"


def test_interpret_create_shipit_confirms_at_step(tmp_path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_SERVICE_TICKET,
    )
    wizard_store.update_session(
        session["id"],
        confirmations={
            wizard.STEP_SERVICE_TICKET: {"token": "tok-shipit", "status": "pending"},
        },
    )
    plan = guided.interpret_message("create shipit", workflow_id=session["id"])
    assert plan["action"] == "confirm"
    assert plan["confirmation_token"] == "tok-shipit"


def test_interpret_onboarding_done():
    plan = guided.interpret_message("done")
    assert plan["intent"] == "onboarding_progress"


def test_interpret_lets_go():
    plan = guided.interpret_message("let's go")
    assert plan["action"] == "welcome"
    assert plan["intent"] == "full_release"
    assert plan["inputs"]["start_path"] == "fetch_review_tickets"


def test_interpret_send_slack():
    plan = guided.interpret_message("send slack", workflow_id="wf-1")
    assert plan["action"] == "update"
    assert plan["inputs"]["slack_decision"] in {"send", "playwright"}
    if plan["inputs"]["slack_decision"] == "playwright":
        assert plan["inputs"].get("slack_via_playwright") is True


def test_interpret_send_slack_mcp_explicit():
    plan = guided.interpret_message("send slack mcp", workflow_id="wf-1")
    assert plan["inputs"]["slack_decision"] == "send"
    assert "slack_via_playwright" not in plan["inputs"]


def test_interpret_skip_slack():
    plan = guided.interpret_message("skip slack", workflow_id="wf-1")
    assert plan["inputs"]["slack_decision"] == "skip"


def test_interpret_release_notes_include_phrase():
    plan = guided.interpret_message("include PIC-5966 for release notes", workflow_id="wf-1")
    assert plan["action"] == "update"
    assert plan["inputs"]["release_notes_include_ticket_keys"] == ["PIC-5966"]
    assert "selected_ticket_keys" not in plan["inputs"]


def test_interpret_release_notes_include_at_release_notes_step(tmp_path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_RELEASE_NOTES,
        inputs={"selection_mode": "status"},
    )
    plan = guided.interpret_message("include PIC-6057", workflow_id=session["id"])
    assert plan["action"] == "update"
    assert plan["inputs"]["release_notes_include_ticket_keys"] == ["PIC-6057"]


def test_run_guided_welcome(tmp_path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    with patch.object(welcome.config, "JIRA_EMAIL", "a@x.com"), patch.object(
        welcome.config, "JIRA_API_TOKEN", "tok"
    ), patch.object(welcome.config, "JIRA_BASE_URL", "https://abcfinancial.atlassian.net"), patch(
        "release_mcp.onboarding_verify.setup_complete", return_value=True
    ):
        result = guided.run_guided("welcome")
    assert result["guided"] is True
    assert result.get("step") == "start_menu"
    assert "full release" in result["say_to_user"].lower()


def test_run_guided_start_menu(tmp_path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    with patch.object(welcome.config, "JIRA_EMAIL", "a@x.com"), patch.object(
        welcome.config, "JIRA_API_TOKEN", "tok"
    ), patch.object(welcome.config, "JIRA_BASE_URL", "https://abcfinancial.atlassian.net"), patch(
        "release_mcp.onboarding_verify.setup_complete", return_value=True
    ):
        result = guided.run_guided("start")
    assert result.get("step") == "start_menu"
    assert "release notes" in result["say_to_user"].lower()
    assert "shipit" in result["say_to_user"].lower()
