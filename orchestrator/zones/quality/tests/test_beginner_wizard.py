"""Beginner onboarding wizard — linear steps."""

from __future__ import annotations

from unittest.mock import patch

from release_mcp import beginner_wizard, guided, onboarding_store
from release_mcp.mcp_templates import starter_mcp_servers


def test_starter_template_uses_placeholders():
    import json
    from pathlib import Path

    from orchestrator.paths import TEMPLATES_DIR

    raw = json.loads(
        (TEMPLATES_DIR / "cursor-mcp.starter.json").read_text(encoding="utf-8")
    )
    blob = json.dumps(raw)
    assert "{{PYTHON_EXE}}" in blob
    assert "{{REPO_ROOT}}" in blob
    assert "lyal01" not in blob.lower()


def test_starter_servers_include_core_keys():
    servers = starter_mcp_servers(track="release")
    assert "release-orchestrator" in servers
    assert "playwright" in servers


def test_welcome_onboard_routes_to_beginner_wizard():
    plan = guided.interpret_message("welcome onboard")
    assert plan["action"] == "beginner_wizard"


def test_wizard_welcome_step(monkeypatch):
    onboarding_store.clear_state()
    with patch.object(beginner_wizard, "_auto_venv", return_value={"ok": True, "detail": "skip"}):
        body = beginner_wizard.process_message("welcome onboard")
    assert body["wizard_step"] == "welcome"
    assert "continue" in body["prompt"].lower()


def test_continue_advances_after_track(monkeypatch):
    onboarding_store.clear_state()
    beginner_wizard.process_message("welcome onboard")
    onboarding_store.set_track("release")
    onboarding_store.merge_state({"wizard_step_index": 0})
    with patch.object(beginner_wizard, "_auto_venv", return_value={"ok": True, "detail": "ok"}):
        body = beginner_wizard.process_message("continue")
    assert body["wizard_index"] >= 1


def test_welcome_defaults_release_track():
    onboarding_store.clear_state()
    with patch.object(beginner_wizard, "_auto_venv", return_value={"ok": True, "detail": "skip"}):
        body = beginner_wizard.process_message("welcome onboard")
    assert body["track"] == "release"
    assert "daily release" in body["prompt"].lower()


def test_verify_step_uses_setup_complete_not_production_ready():
    onboarding_store.clear_state()
    onboarding_store.set_track("release")
    steps = beginner_wizard.wizard_steps(track="release")
    verify = next(s for s in steps if s["id"] == "verify")
    with patch(
        "release_mcp.onboarding_verify.setup_complete",
        return_value=True,
    ):
        assert verify["check"]() is True
