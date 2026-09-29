"""Auto-probes for welcome onboard wizard."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from release_mcp import onboarding_store, onboarding_verify as ob_verify
from release_mcp import unified_onboarding as uo


@pytest.fixture(autouse=True)
def _clear_state(tmp_path):
    state_file = tmp_path / "onboarding_state.json"
    onboarding_store.set_state_path_override(state_file)
    onboarding_store.clear_state()
    yield
    onboarding_store.clear_state()
    onboarding_store.set_state_path_override(None)


def test_probe_mcp_install_auto_confirms(monkeypatch):
    uo.set_track(uo.TRACK_RELEASE)
    with patch(
        "release_mcp.mcp_installer.install_status",
        return_value={"ready": True, "missing": [], "parse_error": None, "config_path": "/p/mcp.json"},
    ), patch(
        "daily_review_agent.setup_mcp.validate_cursor_mcp_config",
        return_value={"parse_error": None, "issues": []},
    ):
        result = ob_verify.probe_step("mcp_install", track=uo.TRACK_RELEASE)
    assert result["ok"] is True
    assert onboarding_store.manual_confirmed("cursor_mcp")


def test_probe_playwright_requires_config_and_signin():
    with patch(
        "browser_automation.playwright_mcp_readiness",
        return_value={"in_mcp_config": True, "can_schedule": False, "blockers": ["Sign in"]},
    ):
        result = ob_verify.probe_step("playwright_signin")
    assert result["ok"] is False
    assert "Sign in" in (result.get("issues") or [""])[0]


def test_setup_complete_false_without_jira(monkeypatch):
    uo.set_track(uo.TRACK_RELEASE)
    with patch(
        "release_mcp.env_onboarding.assess_env_params",
        return_value={"credentials_ready": False, "team_ready": True},
    ), patch(
        "release_mcp.mcp_installer.install_status",
        return_value={"ready": True},
    ), patch(
        "browser_automation.playwright_mcp_readiness",
        return_value={"in_mcp_config": True, "can_schedule": True},
    ):
        assert ob_verify.setup_complete(track=uo.TRACK_RELEASE) is False


def test_setup_complete_true_release_track(monkeypatch):
    uo.set_track(uo.TRACK_RELEASE)
    with patch(
        "release_mcp.unified_onboarding.assess_unified_setup",
        return_value={
            "needs_track_picker": False,
            "required_pending": [],
        },
    ), patch(
        "release_mcp.env_onboarding.assess_env_params",
        return_value={"credentials_ready": True},
    ), patch(
        "release_mcp.mcp_installer.install_status",
        return_value={"ready": True},
    ), patch(
        "browser_automation.playwright_mcp_readiness",
        return_value={"in_mcp_config": True, "can_schedule": True},
    ):
        assert ob_verify.setup_complete(track=uo.TRACK_RELEASE) is True


def test_format_probe_lines_ok_and_fail():
    assert "✅" in ob_verify.format_probe_lines({"ok": True, "detail": "MCP ready"})
    bad = ob_verify.format_probe_lines({"ok": False, "issues": ["missing token"], "fix": "edit .env"})
    assert "❌" in bad
    assert "edit .env" in bad
