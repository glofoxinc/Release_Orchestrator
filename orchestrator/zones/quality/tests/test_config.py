"""Tests for config.py — workspace loading, env-var resolution, helper functions."""

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


class TestEnvVarDefaults:
    """Verify that Jira credentials fall back to env vars."""

    def test_jira_email_from_env(self):
        assert config.JIRA_EMAIL == os.environ.get("JIRA_EMAIL", "")

    def test_jira_api_token_from_env(self):
        assert config.JIRA_API_TOKEN == os.environ.get("JIRA_API_TOKEN", "")

    def test_jira_api_url_ends_with_rest(self):
        assert config.JIRA_API_URL.endswith("/rest/api/3")

    def test_jira_sd_url_ends_with_servicedeskapi(self):
        assert config.JIRA_SD_API_URL.endswith("/rest/servicedeskapi")


class TestAppEnabledAndLabel:
    """Test the app_enabled() and app_label() helper functions."""

    def test_app_enabled_defaults_true_for_unknown(self):
        assert config.app_enabled("nonexistent_app_xyz") is True

    def test_app_label_returns_default_when_missing(self):
        assert config.app_label("nonexistent_app_xyz", "Fallback") == "Fallback"

    def test_app_label_returns_empty_when_no_default(self):
        assert config.app_label("nonexistent_app_xyz") == ""


class TestProjectHelpers:
    """Test project_keys() and project_label()."""

    def test_project_keys_returns_list(self):
        keys = config.project_keys()
        assert isinstance(keys, list)
        for k in keys:
            assert isinstance(k, str)

    def test_project_label_joins_keys(self):
        keys = config.project_keys()
        label = config.project_label()
        if keys:
            assert " + ".join(keys) == label
        else:
            assert label == ""


class TestActiveWorkspacePath:
    """Test get_active_workspace_path with/without JIRA_TOOLKIT_WORKSPACE."""

    def test_returns_root_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
            path = config.get_active_workspace_path()
            assert path.endswith("workspace.yaml")

    def test_returns_subworkspace_when_env_set_and_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws_dir = os.path.join(tmpdir, "team_a")
            os.makedirs(ws_dir)
            ws_file = os.path.join(ws_dir, "workspace.yaml")
            with open(ws_file, "w") as f:
                yaml.dump({"workspace": {"name": "Team A"}}, f)

            with patch.object(config, "_WORKSPACES_DIR", tmpdir):
                with patch.dict(os.environ, {"JIRA_TOOLKIT_WORKSPACE": "team_a"}):
                    path = config.get_active_workspace_path()
                    assert "team_a" in path
                    assert path.endswith("workspace.yaml")


class TestListWorkspaces:
    """Test list_workspaces against a temp directory."""

    def test_returns_empty_when_dir_missing(self):
        with patch.object(config, "_WORKSPACES_DIR", "/nonexistent_path_xyz"):
            assert config.list_workspaces() == []

    def test_finds_subworkspaces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["alpha", "beta"]:
                d = os.path.join(tmpdir, name)
                os.makedirs(d)
                with open(os.path.join(d, "workspace.yaml"), "w") as f:
                    yaml.dump({"workspace": {"name": name}}, f)

            with patch.object(config, "_WORKSPACES_DIR", tmpdir):
                result = config.list_workspaces()
                assert "alpha" in result
                assert "beta" in result

    def test_ignores_dirs_without_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "empty_dir"))
            with patch.object(config, "_WORKSPACES_DIR", tmpdir):
                assert config.list_workspaces() == []


class TestActiveWorkspaceName:
    """Test active_workspace_name() reads from env."""

    def test_returns_empty_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
            assert config.active_workspace_name() == ""

    def test_returns_value_when_set(self):
        with patch.dict(os.environ, {"JIRA_TOOLKIT_WORKSPACE": "my_team"}):
            assert config.active_workspace_name() == "my_team"
