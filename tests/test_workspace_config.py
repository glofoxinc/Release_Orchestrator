"""Integration tests for multi-workspace configuration lifecycle.

Covers workspace.yaml loading, default selection, switching, creation,
and behaviour with missing or invalid config files.
"""

from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import patch

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")

import config


def _write_workspace(directory: str, name: str, **extra: object) -> str:
    """Helper: write a minimal workspace.yaml into *directory* and return the path."""
    ws_path = os.path.join(directory, "workspace.yaml")
    data: dict = {
        "workspace": {
            "name": name,
            "jira": {"base_url": "https://test.atlassian.net"},
            "projects": [],
            **extra,
        }
    }
    with open(ws_path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh)
    return ws_path


class TestWorkspaceLoading:
    """Verify _load_workspace reads the active workspace correctly."""

    def test_load_returns_dict(self):
        ws = config._load_workspace()
        assert isinstance(ws, dict)

    def test_load_contains_name_key(self):
        ws = config._load_workspace()
        assert "name" in ws

    def test_load_from_custom_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_workspace(tmpdir, "Custom Team")
            fake_path = os.path.join(tmpdir, "workspace.yaml")
            with patch.object(config, "get_active_workspace_path", return_value=fake_path):
                ws = config._load_workspace()
                assert ws["name"] == "Custom Team"


class TestDefaultWorkspaceSelection:
    """The root workspace.yaml is the default when no env var is set."""

    def test_default_path_is_root(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
            path = config.get_active_workspace_path()
            assert os.path.basename(path) == "workspace.yaml"
            assert "workspaces" not in path

    def test_default_name_is_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
            assert config.active_workspace_name() == ""


class TestWorkspaceSwitching:
    """Verify switch_workspace toggles the active workspace."""

    def test_switch_sets_env_and_reloads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            team_dir = os.path.join(tmpdir, "team_x")
            os.makedirs(team_dir)
            _write_workspace(team_dir, "Team X")

            with patch.object(config, "_WORKSPACES_DIR", tmpdir):
                config.switch_workspace("team_x")
                assert config.active_workspace_name() == "team_x"
                assert config.WORKSPACE_NAME == "Team X"

                config.switch_workspace("")
                assert config.active_workspace_name() == ""

    def test_switch_to_nonexistent_falls_back_to_root(self):
        with patch.object(config, "_WORKSPACES_DIR", "/nonexistent_xyz"):
            config.switch_workspace("does_not_exist")
            path = config.get_active_workspace_path()
            assert "does_not_exist" not in path
            config.switch_workspace("")


class TestMissingInvalidConfig:
    """Edge cases: missing directory, empty YAML, corrupt YAML."""

    def test_missing_workspaces_dir_returns_empty_list(self):
        with patch.object(config, "_WORKSPACES_DIR", "/no_such_dir_xyz"):
            assert config.list_workspaces() == []

    def test_empty_yaml_returns_validated_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws_path = os.path.join(tmpdir, "workspace.yaml")
            with open(ws_path, "w", encoding="utf-8") as fh:
                fh.write("")
            with patch.object(config, "get_active_workspace_path", return_value=ws_path):
                ws = config._load_workspace()
                assert ws["name"] == "My Team"
                assert ws["jira"] == {}
                assert ws["projects"] == []

    def test_yaml_without_workspace_key_uses_raw(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws_path = os.path.join(tmpdir, "workspace.yaml")
            with open(ws_path, "w", encoding="utf-8") as fh:
                yaml.dump({"name": "Flat Config", "projects": []}, fh)
            with patch.object(config, "get_active_workspace_path", return_value=ws_path):
                ws = config._load_workspace()
                assert ws.get("name") == "Flat Config"


class TestListAllTeams:
    """Verify list_all_teams aggregates root + sub-workspaces."""

    def test_includes_root_workspace(self):
        teams = config.list_all_teams()
        assert any(t["id"] == "" for t in teams)

    def test_includes_sub_workspaces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for folder in ["alpha", "beta"]:
                d = os.path.join(tmpdir, folder)
                os.makedirs(d)
                _write_workspace(d, folder.title())

            with patch.object(config, "_WORKSPACES_DIR", tmpdir):
                teams = config.list_all_teams()
                ids = [t["id"] for t in teams]
                assert "alpha" in ids
                assert "beta" in ids
