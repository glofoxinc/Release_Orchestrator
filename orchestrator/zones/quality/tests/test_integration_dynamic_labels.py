"""Integration tests verifying hardcoded PIC/AN labels are removed.

Ensures project labels are generated dynamically from workspace config.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


class TestProjectLabelDynamic:
    """Verify project_label() derives from PROJECTS config, not hardcoded strings."""

    def test_two_projects_label(self, monkeypatch):
        monkeypatch.setattr(
            config,
            "PROJECTS",
            [{"key": "PROJ1", "name": "Project One"}, {"key": "PROJ2", "name": "Project Two"}],
        )
        assert config.project_label() == "PROJ1 + PROJ2"

    def test_single_project_label(self, monkeypatch):
        monkeypatch.setattr(config, "PROJECTS", [{"key": "ALPHA", "name": "Alpha"}])
        assert config.project_label() == "ALPHA"

    def test_three_projects_label(self, monkeypatch):
        monkeypatch.setattr(
            config,
            "PROJECTS",
            [{"key": "A"}, {"key": "B"}, {"key": "C"}],
        )
        assert config.project_label() == "A + B + C"

    def test_empty_projects_label(self, monkeypatch):
        monkeypatch.setattr(config, "PROJECTS", [])
        assert config.project_label() == ""

    def test_label_never_returns_hardcoded_pic_an(self, monkeypatch):
        monkeypatch.setattr(
            config,
            "PROJECTS",
            [{"key": "FOO", "name": "Foo"}, {"key": "BAR", "name": "Bar"}],
        )
        label = config.project_label()
        assert "PIC" not in label
        assert label == "FOO + BAR"


class TestProjectKeysDynamic:
    """Verify project_keys() returns keys from the active config."""

    def test_project_keys_matches_config(self, monkeypatch):
        monkeypatch.setattr(
            config,
            "PROJECTS",
            [{"key": "X1"}, {"key": "Y2"}, {"key": "Z3"}],
        )
        assert config.project_keys() == ["X1", "Y2", "Z3"]

    def test_project_keys_empty(self, monkeypatch):
        monkeypatch.setattr(config, "PROJECTS", [])
        assert config.project_keys() == []


class TestNoHardcodedLabelsInUI:
    """Scan UI source files at import time — no hardcoded 'PIC + AN' string literals."""

    @pytest.fixture()
    def ui_source_files(self) -> list[str]:
        ui_dir = os.path.join(os.path.dirname(__file__), "..", "ui")
        ui_dir = os.path.normpath(ui_dir)
        files = []
        if os.path.isdir(ui_dir):
            for fname in os.listdir(ui_dir):
                if fname.endswith(".py"):
                    files.append(os.path.join(ui_dir, fname))
        return files

    def test_no_pic_plus_an_string(self, ui_source_files):
        for filepath in ui_source_files:
            with open(filepath, "r", encoding="utf-8") as f:
                contents = f.read()
            lines = contents.splitlines()
            for lineno, line in enumerate(lines, start=1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                assert "PIC + AN" not in line, (
                    f"Hardcoded 'PIC + AN' found in {os.path.basename(filepath)} line {lineno}: {line.strip()}"
                )

    def test_no_pic_an_as_label_literal(self, ui_source_files):
        for filepath in ui_source_files:
            with open(filepath, "r", encoding="utf-8") as f:
                contents = f.read()
            lines = contents.splitlines()
            for lineno, line in enumerate(lines, start=1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                assert '"PIC"' not in line and "'PIC'" not in line, (
                    f"Hardcoded PIC string literal in {os.path.basename(filepath)} line {lineno}"
                )


class TestSessionStateKeysDynamic:
    """Verify session-state key generation is based on project keys."""

    def test_shared_release_keys_use_config(self, monkeypatch):
        monkeypatch.setattr(
            config,
            "PROJECTS",
            [{"key": "PROJ1"}, {"key": "PROJ2"}],
        )
        from release_platform.ui.helpers import _shared_release_keys

        keys = _shared_release_keys()
        assert keys == ["shared_release_PROJ1", "shared_release_PROJ2"]

    def test_shared_release_keys_change_with_config(self, monkeypatch):
        monkeypatch.setattr(config, "PROJECTS", [{"key": "AAA"}])
        from release_platform.ui.helpers import _shared_release_keys

        keys = _shared_release_keys()
        assert keys == ["shared_release_AAA"]
