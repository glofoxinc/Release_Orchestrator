"""Natural-language `.env` onboarding parser and merge."""

from __future__ import annotations

from pathlib import Path

from release_mcp import env_onboarding as env_ob
from release_mcp import guided


def test_parse_org_slug_and_projects():
    parsed = env_ob.parse_env_from_message("org is abcfinancial and projects pic an")
    assert parsed["JIRA_BASE_URL"] == "https://abcfinancial.atlassian.net"
    assert parsed["DEFAULT_PROJECTS"] == "PIC,AN"


def test_parse_use_glofox_team():
    parsed = env_ob.parse_env_from_message("use glofox")
    assert "DEFAULT_JIRA_TEAM" in parsed
    assert "Glofox" in parsed["DEFAULT_JIRA_TEAM"]
    assert parsed.get("DEFAULT_PROJECTS") == "PIC,AN"


def test_parse_explicit_kv():
    parsed = env_ob.parse_env_from_message(
        "JIRA_EMAIL=test@abcfitness.com JIRA_BASE_URL=https://abcfinancial.atlassian.net"
    )
    assert parsed["JIRA_EMAIL"] == "test@abcfitness.com"
    assert parsed["JIRA_BASE_URL"] == "https://abcfinancial.atlassian.net"


def test_does_not_parse_ticket_key_as_project():
    parsed = env_ob.parse_env_from_message("exclude PIC-6085 from release")
    assert "DEFAULT_PROJECTS" not in parsed


def test_merge_env_updates(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("JIRA_BASE_URL=\nJIRA_EMAIL=\n", encoding="utf-8")
    monkeypatch.setattr(env_ob, "_ENV_FILE", env_file)

    result = env_ob.merge_env_updates({"JIRA_EMAIL": "a@b.com"})
    assert result["ok"] is True
    assert "JIRA_EMAIL" in result["written"]
    text = env_file.read_text(encoding="utf-8")
    assert "JIRA_EMAIL=a@b.com" in text


def test_env_checklist_route():
    plan = guided.interpret_message("env checklist")
    assert plan["action"] == "env_onboard"


def test_email_phrase_route():
    plan = guided.interpret_message("email new.user@abcfitness.com")
    assert plan["action"] == "env_onboard"
