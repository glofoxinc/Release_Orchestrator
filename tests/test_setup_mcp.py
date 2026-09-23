"""Setup MCP — validation and snippet generation (no live install)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daily_review_agent.setup_mcp import (
    generate_mcp_snippets,
    project_root,
    validate_cursor_mcp_config,
    _validate_server_entry,
)


def test_generate_mcp_snippets_has_both_servers():
    snippets = generate_mcp_snippets()
    servers = snippets["mcpServers"]
    assert "release-orchestrator" in servers
    assert "teams" in servers
    ro = servers["release-orchestrator"]
    assert ro["args"] == ["-m", "release_mcp"]
    assert project_root().as_posix() in ro["cwd"].replace("\\", "/")
    assert "TEAMS_MCP_ROOT" in ro["env"]


def test_validate_missing_mcp_json(tmp_path, monkeypatch):
    missing = tmp_path / "no-mcp.json"
    monkeypatch.setenv("CURSOR_MCP_CONFIG", str(missing))
    result = validate_cursor_mcp_config()
    assert result["config_exists"] is False
    assert "release-orchestrator" in result["missing_servers"]
    assert "teams" in result["missing_servers"]


def test_validate_good_mcp_json(tmp_path, monkeypatch):
    snippets = generate_mcp_snippets()
    cfg_path = tmp_path / "mcp.json"
    cfg_path.write_text(
        json.dumps({"mcpServers": snippets["mcpServers"]}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setenv("CURSOR_MCP_CONFIG", str(cfg_path))
    result = validate_cursor_mcp_config()
    assert result["config_exists"] is True
    assert result["parse_error"] is None
    assert "release-orchestrator" not in result["missing_servers"]
    assert "teams" not in result["missing_servers"]


def test_validate_disabled_server(tmp_path, monkeypatch):
    snippets = generate_mcp_snippets()
    servers = dict(snippets["mcpServers"])
    servers["teams"] = {**servers["teams"], "disabled": True}
    cfg_path = tmp_path / "mcp.json"
    cfg_path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    monkeypatch.setenv("CURSOR_MCP_CONFIG", str(cfg_path))
    result = validate_cursor_mcp_config()
    assert any("disabled" in i.lower() for i in result["issues"])


def test_validate_server_entry_bad_args():
    issues = _validate_server_entry(
        "release-orchestrator",
        {"command": "python.exe", "args": ["-m", "wrong"], "cwd": "/x"},
        expected={"command": "python.exe"},
    )
    assert any("mcp" in i for i in issues)


def test_validate_warns_deprecated_daily_review_agent(tmp_path, monkeypatch):
    snippets = generate_mcp_snippets()
    servers = dict(snippets["mcpServers"])
    servers["daily-review-agent"] = {
        "type": "stdio",
        "command": "python.exe",
        "args": ["-m", "mcp_server"],
        "cwd": "/old/daily-review-agent",
    }
    cfg_path = tmp_path / "mcp.json"
    cfg_path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    monkeypatch.setenv("CURSOR_MCP_CONFIG", str(cfg_path))
    result = validate_cursor_mcp_config()
    assert any("daily-review-agent" in i and "Deprecated" in i for i in result["issues"])


def test_run_setup_returns_first_run_order():
    from daily_review_agent.setup_mcp import run_setup

    report = run_setup(install=False)
    assert "steps" in report
    assert "first_run_order" in report
    assert len(report["first_run_order"]) >= 6
    assert report.get("mcp_snippets")
