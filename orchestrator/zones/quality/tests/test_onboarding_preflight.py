"""Onboarding preflight and wizard install path regression tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.paths import DAILY_REVIEW_SETUP_PS1, REQUIREMENTS_MCP_FILE
from release_mcp import beginner_wizard, onboarding_preflight as opf
from release_mcp.mcp_templates import PLAYWRIGHT_MCP_PACKAGE, mcp_node_path_env, starter_mcp_servers


def test_requirements_mcp_file_exists():
    assert REQUIREMENTS_MCP_FILE.is_file()


def test_daily_review_setup_ps1_path_exists():
    assert DAILY_REVIEW_SETUP_PS1.is_file()


def test_starter_playwright_uses_pinned_package_and_path_env():
    servers = starter_mcp_servers(track="release")
    pw = servers["playwright"]
    assert PLAYWRIGHT_MCP_PACKAGE in pw["args"][1]
    assert "latest" not in pw["args"][1]
    assert isinstance(pw.get("env"), dict)


def test_mcp_node_path_env_is_dict():
    assert isinstance(mcp_node_path_env(), dict)


def test_run_preflight_returns_status():
    report = opf.run_preflight(track="release", include_tool_scan=False)
    assert report["status"] in {"ready", "needs_fix", "blocked"}
    assert isinstance(report["checks"], list)


def test_packages_ready_false_without_venv(tmp_path, monkeypatch):
    missing = tmp_path / "missing" / "python.exe"
    monkeypatch.setattr(beginner_wizard, "_VENV_PY", missing)
    assert beginner_wizard._packages_ready() is False


def test_auto_pip_uses_canonical_requirements(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(beginner_wizard.subprocess, "run", _fake_run)
    monkeypatch.setattr(
        beginner_wizard,
        "venv_python",
        lambda repo_root=None: Path("C:/fake/.venv/Scripts/python.exe"),
    )
    monkeypatch.setattr(beginner_wizard, "_VENV_PY", Path("C:/fake/.venv/Scripts/python.exe"))
    with patch.object(Path, "is_file", return_value=True):
        result = beginner_wizard._auto_pip()
    assert result["ok"] is True
    assert any(str(REQUIREMENTS_MCP_FILE) in " ".join(c) for c in calls)


def test_welcome_includes_preflight_once(tmp_path, monkeypatch):
    from release_mcp import mcp_installer, onboarding_store

    onboarding_store.set_state_path_override(tmp_path / "onboarding_state.json")
    monkeypatch.setattr(mcp_installer, "project_mcp_config_path", lambda: tmp_path / "mcp.json")

    def _fake_preflight(*, track: str, force_fix: bool = False) -> dict:
        return {"status": "ready", "checks": [], "next_action": "welcome onboard"}

    monkeypatch.setattr(beginner_wizard, "_run_preflight_onboarding", _fake_preflight)
    onboarding_store.clear_state()
    try:
        with patch.object(beginner_wizard, "_auto_venv", return_value={"ok": True, "detail": "skip"}):
            body = beginner_wizard.process_message("welcome onboard")
        assert "preflight" in body["prompt"].lower() or "Onboarding" in body["prompt"]
    finally:
        onboarding_store.clear_state()
        onboarding_store.set_state_path_override(None)
