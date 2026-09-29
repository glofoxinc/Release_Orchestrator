"""Edge-case tests for workspace.yaml validation and loading."""

from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")

import config


class TestEmptyWorkspaceYaml:
    """Workspace files that are empty or contain only null."""

    def test_empty_file_returns_safe_defaults(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("")
            f.flush()
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["name"] == "My Team"
            assert ws["projects"] == []
            assert ws["apps"] == {}
        finally:
            os.unlink(path)

    def test_null_yaml_returns_safe_defaults(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("null\n")
            f.flush()
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert isinstance(ws, dict)
            assert ws["projects"] == []
        finally:
            os.unlink(path)

    def test_empty_workspace_key_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump({"workspace": None}, f)
            f.flush()
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    with pytest.raises(ValueError, match="must be a YAML mapping"):
                        config._load_workspace()
        finally:
            os.unlink(path)


class TestMissingRequiredFields:
    """Workspace YAML with missing or incomplete sections."""

    def test_missing_jira_section_gets_default(self):
        data = {"workspace": {"name": "Test", "projects": []}}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["jira"] == {}
        finally:
            os.unlink(path)

    def test_missing_projects_gets_empty_list(self):
        data = {"workspace": {"name": "No Projects"}}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["projects"] == []
        finally:
            os.unlink(path)

    def test_missing_apps_gets_empty_dict(self):
        data = {"workspace": {"name": "No Apps", "projects": []}}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["apps"] == {}
        finally:
            os.unlink(path)

    def test_missing_service_desk_gets_empty_dict(self):
        data = {"workspace": {"name": "No SD", "projects": []}}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["service_desk"] == {}
        finally:
            os.unlink(path)


class TestInvalidFieldTypes:
    """Workspace YAML with wrong types for known fields."""

    def test_projects_as_string_raises(self):
        data = {"workspace": {"name": "Bad", "projects": "not-a-list"}}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    with pytest.raises(ValueError, match="'projects' must be a list"):
                        config._validate_config(data["workspace"])
        finally:
            os.unlink(path)

    def test_jira_as_string_raises(self):
        data = {"workspace": {"name": "Bad", "jira": "not-a-dict"}}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with pytest.raises(ValueError, match="'jira' must be a mapping"):
                config._validate_config(data["workspace"])
        finally:
            os.unlink(path)

    def test_apps_as_list_raises(self):
        cfg = {"name": "Bad", "apps": ["not", "a", "dict"]}
        with pytest.raises(ValueError, match="'apps' must be a mapping"):
            config._validate_config(cfg)

    def test_non_dict_root_raises(self):
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            config._validate_config("just a string")

    def test_list_root_raises(self):
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            config._validate_config(["a", "list"])


class TestInvalidProjectKeys:
    """Projects with missing or malformed keys."""

    def test_project_missing_key_field(self):
        data = {"workspace": {
            "name": "Test",
            "projects": [{"name": "Missing Key Project"}],
        }}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert len(ws["projects"]) == 1
            with pytest.raises(KeyError):
                _ = [p["key"] for p in ws["projects"]]
        finally:
            os.unlink(path)

    def test_project_empty_key(self):
        data = {"workspace": {
            "name": "Test",
            "projects": [{"key": "", "name": "Empty Key"}],
        }}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["projects"][0]["key"] == ""
        finally:
            os.unlink(path)

    def test_project_with_special_chars_key(self):
        data = {"workspace": {
            "name": "Test",
            "projects": [{"key": "!@#$%", "name": "Bad Key"}],
        }}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["projects"][0]["key"] == "!@#$%"
        finally:
            os.unlink(path)


class TestDuplicateEntries:
    """Workspace with duplicate project keys or apps."""

    def test_duplicate_project_keys_loaded_as_is(self):
        data = {"workspace": {
            "name": "Dupes",
            "projects": [
                {"key": "PIC", "name": "PIC First"},
                {"key": "PIC", "name": "PIC Second"},
                {"key": "AN", "name": "Analyze"},
            ],
        }}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            keys = [p["key"] for p in ws["projects"]]
            assert keys.count("PIC") == 2
            assert len(ws["projects"]) == 3
        finally:
            os.unlink(path)

    def test_duplicate_app_ids_last_wins(self):
        """YAML merges duplicate mapping keys — last definition wins."""
        yaml_str = (
            "workspace:\n"
            "  name: Dupes\n"
            "  projects: []\n"
            "  apps:\n"
            "    ticket_review:\n"
            "      enabled: true\n"
            "      label: First\n"
            "    ticket_review:\n"
            "      enabled: false\n"
            "      label: Second\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".yaml", mode="w", delete=False, encoding="utf-8",
        ) as f:
            f.write(yaml_str)
            path = f.name
        try:
            with open(path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            ws = raw.get("workspace", raw)
            assert ws["apps"]["ticket_review"]["label"] == "Second"
            assert ws["apps"]["ticket_review"]["enabled"] is False
        finally:
            os.unlink(path)


class TestVeryLongFieldValues:
    """Workspace with extremely long strings for names, keys, URLs."""

    def test_very_long_workspace_name(self):
        long_name = "A" * 5000
        data = {"workspace": {"name": long_name, "projects": []}}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["name"] == long_name
        finally:
            os.unlink(path)

    def test_very_long_project_key(self):
        long_key = "X" * 1000
        data = {"workspace": {
            "name": "Test",
            "projects": [{"key": long_key, "name": "Long Key Project"}],
        }}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["projects"][0]["key"] == long_key
        finally:
            os.unlink(path)

    def test_very_long_jira_url(self):
        long_url = "https://" + "a" * 2000 + ".atlassian.net"
        data = {"workspace": {
            "name": "Long URL",
            "jira": {"base_url": long_url},
            "projects": [],
        }}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["jira"]["base_url"] == long_url
        finally:
            os.unlink(path)

    def test_many_projects_loaded(self):
        projects = [{"key": f"P{i:03d}", "name": f"Project {i}"} for i in range(200)]
        data = {"workspace": {"name": "Many", "projects": projects}}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert len(ws["projects"]) == 200
        finally:
            os.unlink(path)


class TestNonExistentFilePath:
    """Config loading when the workspace file doesn't exist at all."""

    def test_nonexistent_path_returns_defaults(self):
        fake_path = os.path.join(tempfile.gettempdir(), "nonexistent_xyz_42.yaml")
        assert not os.path.exists(fake_path)
        with patch.object(config, "get_active_workspace_path", return_value=fake_path):
            ws = config._load_workspace()
        assert ws["name"] == "My Team"
        assert ws["projects"] == []
        assert ws["apps"] == {}

    def test_nonexistent_path_jira_defaults(self):
        fake_path = os.path.join(tempfile.gettempdir(), "nonexistent_xyz_43.yaml")
        assert not os.path.exists(fake_path)
        with patch.object(config, "get_active_workspace_path", return_value=fake_path):
            ws = config._load_workspace()
        assert ws["jira"] == {}
        assert ws["service_desk"] == {}
        assert ws["deployment"] == {}

    def test_nonexistent_workspace_dir_for_sub(self):
        with patch.object(config, "_WORKSPACES_DIR", "/completely/fake/dir"):
            with patch.dict(os.environ, {"JIRA_TOOLKIT_WORKSPACE": "ghost_team"}):
                path = config.get_active_workspace_path()
                assert "ghost_team" not in path


class TestNumericProjectKeys:
    """Project keys that are purely numeric or start with numbers."""

    def test_numeric_key_loaded(self):
        data = {"workspace": {
            "name": "Numeric",
            "projects": [{"key": "12345", "name": "Numeric Project"}],
        }}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["projects"][0]["key"] == "12345"
        finally:
            os.unlink(path)

    def test_mixed_numeric_alpha_key(self):
        data = {"workspace": {
            "name": "Mixed",
            "projects": [{"key": "123ABC", "name": "Mixed Project"}],
        }}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    ws = config._load_workspace()
            assert ws["projects"][0]["key"] == "123ABC"
        finally:
            os.unlink(path)


class TestCreateWorkspace:
    """Edge cases for create_workspace()."""

    def test_create_workspace_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(config, "_WORKSPACES_DIR", tmpdir):
                path1 = config.create_workspace("team_x", "Team X")
                path2 = config.create_workspace("team_x", "Team X")
                assert path1 == path2
                assert os.path.isfile(path1)

    def test_create_workspace_produces_valid_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(config, "_WORKSPACES_DIR", tmpdir):
                path = config.create_workspace("new_team", "New Team")
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                assert data["workspace"]["name"] == "New Team"
                assert isinstance(data["workspace"]["projects"], list)


class TestSaveWorkspace:
    """Edge cases for save_workspace()."""

    def test_save_preserves_custom_fields(self):
        ws = {
            "name": "Round-trip",
            "jira": {"base_url": "https://test.atlassian.net"},
            "projects": [{"key": "TST", "name": "Test"}],
            "service_desk": {"enabled": True, "custom_data": "preserved"},
            "deployment": {},
            "release_notes": {},
            "apps": {},
        }
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            path = f.name
        try:
            with patch.object(config, "_WS_PATH", path):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
                    config.save_workspace(ws)
                    with open(path, encoding="utf-8") as fh:
                        reloaded = yaml.safe_load(fh)
            assert reloaded["workspace"]["service_desk"]["custom_data"] == "preserved"
            assert reloaded["workspace"]["projects"][0]["key"] == "TST"
        finally:
            os.unlink(path)
