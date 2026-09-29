"""Integration tests for workspace path resolution and settings module."""

from __future__ import annotations

import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


def _write_workspace_yaml(path: str, ws_data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"workspace": ws_data}, f, default_flow_style=False)


class TestGetActiveWorkspacePath:
    """Verify get_active_workspace_path() returns the correct YAML path."""

    def test_returns_root_when_no_env(self, tmp_path, monkeypatch):
        root_yaml = str(tmp_path / "workspace.yaml")
        _write_workspace_yaml(root_yaml, {"name": "Root"})

        monkeypatch.setattr(config, "_WS_PATH", root_yaml)
        monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))
        monkeypatch.delenv("JIRA_TOOLKIT_WORKSPACE", raising=False)

        result = config.get_active_workspace_path()
        assert os.path.normpath(result) == os.path.normpath(root_yaml)

    def test_returns_sub_workspace_when_switched(self, tmp_path, monkeypatch):
        root_yaml = str(tmp_path / "workspace.yaml")
        _write_workspace_yaml(root_yaml, {"name": "Root"})

        sub_dir = tmp_path / "workspaces" / "team_x"
        sub_yaml = str(sub_dir / "workspace.yaml")
        _write_workspace_yaml(sub_yaml, {"name": "Team X"})

        monkeypatch.setattr(config, "_WS_PATH", root_yaml)
        monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))
        monkeypatch.setenv("JIRA_TOOLKIT_WORKSPACE", "team_x")

        result = config.get_active_workspace_path()
        assert os.path.normpath(result) == os.path.normpath(sub_yaml)

    def test_falls_back_to_root_when_sub_missing(self, tmp_path, monkeypatch):
        root_yaml = str(tmp_path / "workspace.yaml")
        _write_workspace_yaml(root_yaml, {"name": "Root"})

        monkeypatch.setattr(config, "_WS_PATH", root_yaml)
        monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))
        monkeypatch.setenv("JIRA_TOOLKIT_WORKSPACE", "nonexistent_team")

        result = config.get_active_workspace_path()
        assert os.path.normpath(result) == os.path.normpath(root_yaml)


class TestSwitchWorkspace:
    """Verify switch_workspace toggles the active path."""

    def test_switch_to_sub_then_back(self, tmp_path, monkeypatch):
        root_yaml = str(tmp_path / "workspace.yaml")
        _write_workspace_yaml(root_yaml, {"name": "Root", "projects": []})

        sub_dir = tmp_path / "workspaces" / "alpha"
        sub_yaml = str(sub_dir / "workspace.yaml")
        _write_workspace_yaml(sub_yaml, {"name": "Alpha", "projects": []})

        monkeypatch.setattr(config, "_WS_PATH", root_yaml)
        monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))
        monkeypatch.setattr(config, "_APP_DIR", str(tmp_path))
        monkeypatch.delenv("JIRA_TOOLKIT_WORKSPACE", raising=False)

        assert os.path.normpath(config.get_active_workspace_path()) == os.path.normpath(root_yaml)

        config.switch_workspace("alpha")
        assert os.path.normpath(config.get_active_workspace_path()) == os.path.normpath(sub_yaml)

        config.switch_workspace("")
        assert os.path.normpath(config.get_active_workspace_path()) == os.path.normpath(root_yaml)


class TestSettingsWsPathFix:
    """Verify that the settings module's _ws_path() delegates to config."""

    def test_ws_path_uses_config_get_active(self, tmp_path, monkeypatch):
        root_yaml = str(tmp_path / "workspace.yaml")
        _write_workspace_yaml(root_yaml, {"name": "Root"})

        monkeypatch.setattr(config, "_WS_PATH", root_yaml)
        monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))
        monkeypatch.delenv("JIRA_TOOLKIT_WORKSPACE", raising=False)

        from release_platform.ui.settings import _ws_path

        result = _ws_path()
        expected = config.get_active_workspace_path()
        assert os.path.normpath(result) == os.path.normpath(expected)

    def test_ws_path_follows_workspace_switch(self, tmp_path, monkeypatch):
        root_yaml = str(tmp_path / "workspace.yaml")
        _write_workspace_yaml(root_yaml, {"name": "Root", "projects": []})

        sub_dir = tmp_path / "workspaces" / "beta"
        sub_yaml = str(sub_dir / "workspace.yaml")
        _write_workspace_yaml(sub_yaml, {"name": "Beta", "projects": []})

        monkeypatch.setattr(config, "_WS_PATH", root_yaml)
        monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))
        monkeypatch.setattr(config, "_APP_DIR", str(tmp_path))
        monkeypatch.delenv("JIRA_TOOLKIT_WORKSPACE", raising=False)

        from release_platform.ui.settings import _ws_path

        before = _ws_path()
        assert os.path.normpath(before) == os.path.normpath(root_yaml)

        config.switch_workspace("beta")
        after = _ws_path()
        assert os.path.normpath(after) == os.path.normpath(sub_yaml)

        config.switch_workspace("")


class TestCreateWorkspace:
    """Verify create_workspace produces valid workspace files."""

    def test_creates_yaml_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))

        path = config.create_workspace("new_team", "New Team")
        assert os.path.isfile(path)

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        assert raw["workspace"]["name"] == "New Team"

    def test_does_not_overwrite_existing(self, tmp_path, monkeypatch):
        ws_dir = tmp_path / "workspaces" / "existing"
        ws_dir.mkdir(parents=True)
        existing_yaml = ws_dir / "workspace.yaml"
        _write_workspace_yaml(str(existing_yaml), {"name": "Original"})

        monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))
        config.create_workspace("existing", "Should Not Overwrite")

        with open(str(existing_yaml), "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        assert raw["workspace"]["name"] == "Original"
