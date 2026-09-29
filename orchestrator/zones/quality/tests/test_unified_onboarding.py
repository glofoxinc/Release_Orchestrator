"""Unified onboarding — release, daily review, or both."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from release_mcp import guided, onboarding, onboarding_store, unified_onboarding as uo


@pytest.fixture(autouse=True)
def _clear_onboarding_state(tmp_path, monkeypatch):
    state_file = tmp_path / "onboarding_state.json"
    onboarding_store.set_state_path_override(state_file)
    onboarding_store.clear_state()
    yield
    onboarding_store.clear_state()
    onboarding_store.set_state_path_override(None)


def test_needs_track_picker_without_stored_track():
    result = uo.assess_unified_setup(from_mcp=True, require_track=True)
    assert result["needs_track_picker"] is True
    assert result["next_setup_step"]["id"] == "onboarding_track"
    assert "release only" in result["next_setup_step"]["instructions"].lower()


def test_set_track_both_includes_daily_review_steps():
    uo.set_track(uo.TRACK_BOTH)
    result = uo.assess_unified_setup(from_mcp=True)
    ids = [i["id"] for i in result["items"]]
    assert "team_and_projects" in ids
    assert "teams_mcp" in ids
    assert "outlook_playwright" in ids


def test_daily_review_only_skips_release_team_steps():
    uo.set_track(uo.TRACK_DAILY_REVIEW)
    result = uo.assess_unified_setup(from_mcp=True)
    ids = [i["id"] for i in result["items"]]
    assert "team_and_projects" not in ids
    assert "slack_plugin" not in ids
    assert "teams_mcp" in ids


def test_resolve_track_phrase_variants():
    assert uo.resolve_track_phrase("I want both") == uo.TRACK_BOTH
    assert uo.resolve_track_phrase("release only please") == uo.TRACK_RELEASE
    assert uo.resolve_track_phrase("daily review only") == uo.TRACK_DAILY_REVIEW


def test_apply_progress_records_manual_confirm():
    uo.set_track(uo.TRACK_RELEASE)
    assessment = uo.assess_unified_setup(from_mcp=True)
    next_id = str((assessment.get("next_setup_step") or {}).get("id") or "")
    if next_id:
        onboarding_store.record_manual_confirm(next_id)
    uo.apply_progress_from_message("mcp configured")
    assert onboarding_store.manual_confirmed("cursor_mcp")


def test_guided_both_sets_track():
    plan = guided.interpret_message("both")
    assert plan["intent"] == "onboarding_track"
    assert plan["action"] == "beginner_wizard"
    assert onboarding_store.get_track() == uo.TRACK_BOTH


def test_welcome_onboard_defaults_release_track(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    with patch.object(onboarding, "_env_file_exists", return_value=False):
        result = guided.run_guided("welcome onboard")
    assert onboarding_store.get_track() == uo.TRACK_RELEASE
    say = result.get("say_to_user", "").lower()
    assert "daily release" in say or "defaulting" in say


def test_track_labels():
    assert uo.track_label(uo.TRACK_RELEASE) == "Daily release (PIC + AN)"
    assert "on demand" in uo.track_label(uo.TRACK_DAILY_REVIEW).lower()


def test_setup_complete_delegates_to_verify():
    with patch("release_mcp.onboarding_verify.setup_complete", return_value=True) as mock_sc:
        assert uo.setup_complete(track=uo.TRACK_RELEASE) is True
    mock_sc.assert_called_once()


def test_welcome_onboard_both_skips_picker(monkeypatch):
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    with patch.object(onboarding, "_env_file_exists", return_value=False):
        result = guided.run_guided("welcome onboard both")
    assert onboarding_store.get_track() == uo.TRACK_BOTH
    say = result.get("say_to_user", "").lower()
    assert "pick your setup path" not in say


def test_format_interactive_prompt_needs_track_picker():
    assessment = uo.assess_unified_setup(from_mcp=True, require_track=True)
    text = onboarding.format_interactive_onboarding_prompt(assessment)
    assert "both" in text.lower()


def test_completion_message_varies_by_track():
    release_msg = uo.completion_message(uo.TRACK_RELEASE)
    dr_msg = uo.completion_message(uo.TRACK_DAILY_REVIEW)
    assert "full release" in release_msg.lower()
    assert "daily review" in dr_msg.lower()
    assert "full release" not in dr_msg.lower()
