"""Tests for comprehensive first-time onboarding guide."""

from __future__ import annotations

from release_mcp import guided, onboarding, onboarding_guide


def test_mcp_catalog_lists_required_servers():
    catalog = onboarding_guide.mcp_catalog_payload()
    ids = {item["id"] for item in catalog}
    assert "release-orchestrator" in ids
    assert "slack" in ids
    assert any(item["required"] for item in catalog if item["id"] == "release-orchestrator")


def test_welcome_onboard_intro_mentions_mcps_and_time():
    text = onboarding_guide.format_welcome_onboard_intro()
    assert "15-20" in text or "15" in text
    assert "Release Orchestrator" in text
    assert "Slack" in text
    assert "welcome onboard" in text.lower() or "done" in text.lower()


def test_phrase_cheat_sheet_covers_slack_step():
    text = onboarding_guide.format_phrase_cheat_sheet()
    assert "send slack" in text
    assert "slack done" in text
    assert "upload sharepoint" in text


def test_full_onboarding_guide_payload():
    payload = onboarding.full_onboarding_guide()
    assert payload.get("mcp_catalog")
    assert payload.get("workflow_phrases")
    assert payload.get("phrase_cheat_sheet")
    assert payload.get("setup_checklist")


def test_interactive_onboarding_shows_intro_on_first_step(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.setenv("JIRA_BASE_URL", "")
    assessment = onboarding.assess_setup(from_mcp=True)
    text = onboarding.format_interactive_onboarding_prompt(assessment, show_intro=True)
    assert "Welcome onboard" in text
    assert "MCP" in text


def test_help_phrase_returns_cheat_sheet():
    result = guided.run_guided("help")
    assert result.get("guided") is True
    say = result.get("say_to_user") or ""
    assert "phrase" in say.lower() or "help" in say.lower()
    assert result.get("onboarding_guide") or result.get("help")


def test_welcome_onboard_routes_with_intro():
    plan = guided.interpret_message("welcome onboard")
    assert plan["intent"] == "welcome_onboard"
    assert plan["action"] == "beginner_wizard"
