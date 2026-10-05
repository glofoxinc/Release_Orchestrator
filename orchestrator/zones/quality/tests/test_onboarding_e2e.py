"""E2E-style onboarding flow tests (mocked subprocess — no network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from release_mcp import beginner_wizard, mcp_installer, onboarding_store


def test_e2e_mcp_merge_writes_playwright_with_env(tmp_path, monkeypatch):
    onboarding_store.clear_state()
    cfg = tmp_path / "mcp.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mcp_installer, "project_mcp_config_path", lambda: cfg)
    monkeypatch.setattr(
        mcp_installer,
        "load_mcp_config",
        lambda prefer_project=True: {
            "path": str(cfg),
            "source": "project",
            "raw": None,
            "parse_error": None,
            "servers": {},
        },
    )
    result = mcp_installer.merge_starter_servers(track="release", backup=False)
    assert result["ok"] is True
    raw = json.loads(cfg.read_text(encoding="utf-8"))
    pw = raw["mcpServers"]["playwright"]
    assert "0.0.39" in pw["args"][1]
    assert "daily-review-agent" not in raw["mcpServers"]
    onboarding_store.clear_state()


def test_e2e_wizard_pip_step_advances_when_import_ok(monkeypatch):
    from release_mcp import unified_onboarding as uo

    onboarding_store.clear_state()
    onboarding_store.set_track(uo.TRACK_RELEASE)
    onboarding_store.merge_state({"wizard_step_index": 1})

    with patch.object(beginner_wizard, "_auto_venv", return_value={"ok": True, "detail": "ok"}):
        with patch.object(beginner_wizard, "_auto_pip", return_value={"ok": True, "detail": "ok"}):
            with patch.object(beginner_wizard, "_packages_ready", return_value=True):
                body = beginner_wizard.process_message("continue")
    assert body["wizard_index"] >= 2
    onboarding_store.clear_state()


def test_e2e_deprecated_server_detected_in_preflight(tmp_path, monkeypatch):
    from release_mcp import onboarding_preflight as opf

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "daily-review-agent": {"command": "python", "args": []},
                    "release-orchestrator": {"command": "x", "args": ["-m", "release_mcp"]},
                    "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@0.0.39"]},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_installer, "project_mcp_config_path", lambda: cfg)
    monkeypatch.setattr(
        mcp_installer,
        "load_mcp_config",
        lambda prefer_project=True: {
            "path": str(cfg),
            "source": "project",
            "raw": json.loads(cfg.read_text(encoding="utf-8")),
            "parse_error": None,
            "servers": json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"],
        },
    )
    report = opf.run_preflight(track="release", include_tool_scan=False)
    dep = next(c for c in report["checks"] if c["name"] == "deprecated MCP servers")
    assert dep["ok"] is False
    onboarding_store.clear_state()
