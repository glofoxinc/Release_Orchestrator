"""Tests for team + crew one-time onboarding."""

from __future__ import annotations

from pathlib import Path

import team_crew as tc
from release_mcp import guided, onboarding_store, onboarding_team_flow


def test_glofox_profile_has_crew():
    profile = tc.load_team_profile("glofox")
    assert profile is not None
    assert profile.default_projects == ["PIC", "AN"]
    assert len(profile.squad) >= 5
    assert len(profile.leadership) >= 2
    assert len(profile.qa) >= 2
    assert len(profile.exclude) >= 2


def test_build_env_snippet_glofox():
    draft = tc.draft_from_profile("glofox")
    assert draft is not None
    snippet = tc.build_env_snippet(draft)
    assert "DEFAULT_JIRA_TEAM=Glofox Insights Customize" in snippet
    assert "DEFAULT_PROJECTS=PIC,AN" in snippet
    assert "TEAM_CREW_SQUAD=" in snippet
    assert "TEAM_CREW_LEADERSHIP=" in snippet
    assert "Sushma Bhamidipati" in snippet
    assert "TEAM_CREW_QA=" in snippet
    assert "Akhil Sree Kumar" in snippet
    assert "TEAM_CREW_EXCLUDE=" in snippet
    assert "gabriel.barbosa@abcfitness.com" in snippet


def test_crew_exclude():
    draft = tc.draft_from_profile("glofox")
    assert draft is not None
    draft.exclude_emails.add("soumyakant.mishra@abcfitness.com")
    release = tc.apply_exclusions(draft.release, draft.exclude_emails)
    emails = {p.email_lower() for p in release}
    assert "soumyakant.mishra@abcfitness.com" not in emails


def test_interpret_use_glofox(tmp_path):
    onboarding_store.set_state_path_override(tmp_path / "state.json")
    onboarding_store.clear_state()
    updates = onboarding_team_flow.interpret_team_onboard_message("use glofox", {})
    assert updates.get("team_selected") == "glofox"
    draft = updates.get("team_crew_draft") or {}
    assert draft.get("team_name") == "Glofox Insights Customize"
    onboarding_store.set_state_path_override(None)


def test_onboarding_store_persists(tmp_path):
    onboarding_store.set_state_path_override(tmp_path / "state.json")
    onboarding_store.merge_state({"team_crew_draft": {"team_key": "glofox"}})
    assert onboarding_store.load_state().get("team_crew_draft", {}).get("team_key") == "glofox"
    onboarding_store.set_state_path_override(None)


def test_guided_use_glofox_during_onboard(tmp_path, monkeypatch):
    onboarding_store.set_state_path_override(tmp_path / "state.json")
    onboarding_store.clear_state()
    monkeypatch.delenv("DEFAULT_JIRA_TEAM", raising=False)
    monkeypatch.delenv("TEAM_CREW_REVIEW", raising=False)
    plan = guided.interpret_message("use glofox")
    assert plan["intent"] == "team_onboard"
    assert plan["inputs"].get("team_inputs")
    onboarding_store.set_state_path_override(None)


def test_crew_done_marks_confirmed(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("JIRA_EMAIL=test@x.com\n", encoding="utf-8")
    draft = tc.draft_from_profile("glofox")
    state = {"team_crew_draft": onboarding_team_flow._draft_to_dict(draft)}  # noqa: SLF001
    original_apply = tc.apply_crew_to_env

    def _apply(d, env_path=None):
        return original_apply(d, env_path=env)

    monkeypatch.setattr(tc, "apply_crew_to_env", _apply)
    updates = onboarding_team_flow.interpret_team_onboard_message("crew done", state)
    assert updates.get("team_crew_confirmed") is True
    assert updates.get("team_crew_locked") is True
    assert "DEFAULT_JIRA_TEAM=Glofox" in env.read_text(encoding="utf-8")


def test_lock_crew_from_profile(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("JIRA_EMAIL=a@b.com\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = tc.lock_crew_from_profile("glofox", env_path=env)
    assert result.get("ok") is True
    text = env.read_text(encoding="utf-8")
    assert "akhil.sreekumar@abcfitness.com" in text
    assert "JIRA_EMAIL=a@b.com" in text


def test_crew_to_teams_attendees_from_env(monkeypatch):
    draft = tc.draft_from_profile("glofox")
    assert draft is not None
    monkeypatch.setenv("DEFAULT_JIRA_TEAM", draft.team_name)
    monkeypatch.setenv("DEFAULT_PROJECTS", "PIC,AN")
    snippet = tc.build_env_snippet(draft)
    for line in snippet.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, val = line.partition("=")
            monkeypatch.setenv(key.strip(), val.strip())
    review = tc.crew_to_teams_attendees("review")
    deploy = tc.crew_to_teams_attendees("deployment")
    assert len(review) >= 2
    assert all(a.email for a in review)


def test_teams_schedule_uses_env_crew_when_yaml_empty(monkeypatch):
    import teams_schedule as ts

    draft = tc.draft_from_profile("glofox")
    assert draft is not None
    monkeypatch.setenv("DEFAULT_JIRA_TEAM", draft.team_name)
    monkeypatch.setenv("DEFAULT_PROJECTS", "PIC,AN")
    for line in tc.build_env_snippet(draft).splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, val = line.partition("=")
            monkeypatch.setenv(key.strip(), val.strip())
    cfg = ts.load_schedule_config({})
    assert len(cfg.attendees_for_kind("review")) >= 2


def test_guided_crew_status_phrase():
    plan = guided.interpret_message("crew status")
    assert plan["action"] == "team_crew_status"
