"""Project-first MCP installer."""

from __future__ import annotations

import json
from unittest.mock import patch

from release_mcp import mcp_installer


def test_resolve_mcp_config_prefers_project(tmp_path, monkeypatch):
    project = tmp_path / "mcp.json"
    project.write_text('{"mcpServers": {}}', encoding="utf-8")
    user = tmp_path / "user" / "mcp.json"
    user.parent.mkdir(parents=True)
    user.write_text('{"mcpServers": {"other": {}}}', encoding="utf-8")

    with patch.object(mcp_installer, "project_mcp_config_path", return_value=project), patch.object(
        mcp_installer, "user_mcp_config_path", return_value=user
    ):
        assert mcp_installer.resolve_mcp_config_path(prefer_project=True) == project
        loaded = mcp_installer.load_mcp_config(prefer_project=True)
        assert loaded["source"] == "project"
        assert loaded["path"] == str(project)


def test_merge_starter_servers_writes_project_file(tmp_path, monkeypatch):
    project = tmp_path / ".cursor" / "mcp.json"
    with patch.object(mcp_installer, "project_mcp_config_path", return_value=project), patch.object(
        mcp_installer, "user_mcp_config_path", return_value=tmp_path / "home" / "mcp.json"
    ):
        result = mcp_installer.merge_starter_servers(track="release", backup=False)
    assert result["ok"] is True
    assert project.is_file()
    raw = json.loads(project.read_text(encoding="utf-8"))
    servers = raw.get("mcpServers") or raw.get("servers") or {}
    assert "release-orchestrator" in servers
    assert "playwright" in servers


def test_install_status_ready_when_all_present(tmp_path, monkeypatch):
    project = tmp_path / "mcp.json"
    from release_mcp.mcp_templates import starter_mcp_servers

    starter = starter_mcp_servers(track="release")
    project.write_text(json.dumps({"mcpServers": starter}), encoding="utf-8")
    with patch.object(mcp_installer, "project_mcp_config_path", return_value=project), patch.object(
        mcp_installer, "resolve_mcp_config_path", return_value=project
    ):
        status = mcp_installer.install_status(track="release")
    assert status["ready"] is True
    assert status["missing"] == []
