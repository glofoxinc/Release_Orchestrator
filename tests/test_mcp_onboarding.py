"""Tests for first-time MCP onboarding / setup checklist."""

from __future__ import annotations

from unittest.mock import patch

from release_mcp import guided, onboarding, welcome


def test_assess_setup_flags_missing_jira(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.setenv("JIRA_BASE_URL", "")
    result = onboarding.assess_setup(from_mcp=True)
    assert result["jira_ready"] is False
    assert result["next_setup_step"] is not None
    assert any(i["id"] == "jira_api_token" for i in result["items"])


def test_setup_guide_mentions_atlassian_token_url(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setenv("JIRA_EMAIL", "")
    assessment = onboarding.assess_setup(from_mcp=True)
    all_text = onboarding.format_setup_guide(assessment)
    all_text += " ".join(
        str(i.get("instructions") or "") + str(i.get("where") or "")
        for i in assessment["items"]
    )
    assert "atlassian.com" in all_text.lower()


def test_welcome_blocked_without_credentials(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.setenv("JIRA_BASE_URL", "")
    with patch.object(welcome.config, "JIRA_EMAIL", ""), patch.object(
        welcome.config, "JIRA_API_TOKEN", ""
    ), patch.object(welcome.config, "JIRA_BASE_URL", ""):
        result = welcome.build_welcome({"onboarding": True, "interactive_onboarding": True})
    assert result["step"] == "onboarding"
    assert result["status"] == "setup"
    assert result.get("setup_checklist")
    assert "setup_guide" in result["env"] or result["prompt"]


def test_onboarding_phrase_routes_to_setup_guide():
    plan = guided.interpret_message("onboarding")
    assert plan["intent"] == "onboarding"
    assert plan["inputs"].get("onboarding") is True


def test_run_guided_onboarding_without_env(monkeypatch):
    from release_mcp import onboarding_store

    onboarding_store.clear_state()
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.setenv("JIRA_BASE_URL", "")
    with patch.object(welcome.config, "JIRA_EMAIL", ""), patch.object(
        welcome.config, "JIRA_API_TOKEN", ""
    ), patch.object(welcome.config, "JIRA_BASE_URL", ""):
        result = guided.run_guided("welcome onboard")
    assert result.get("step") == "onboarding"
    say = result.get("say_to_user", "").lower()
    assert "onboard" in say or "continue" in say or "welcome" in say
    assert "continue" in result.get("user_can_say", [])


def test_welcome_ready_includes_whats_next():
    from release_mcp import onboarding_store

    onboarding_store.clear_state()
    with patch.object(welcome.config, "JIRA_EMAIL", "a@x.com"), patch.object(
        welcome.config, "JIRA_API_TOKEN", "tok"
    ), patch.object(welcome.config, "JIRA_BASE_URL", "https://abcfinancial.atlassian.net"):
        result = guided.run_guided("welcome")
    assert result["status"] == "ok"
    assert result.get("step") == "start_menu"
    assert "full release" in result.get("say_to_user", "").lower()
    assert result.get("whats_next")
