"""Tests for release notes built-in vs external generator detection."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


class TestExternalGeneratorDetection:
    def test_builtin_generator_is_not_external(self, monkeypatch):
        from release_platform.ui.release_notes import step4_generate as s4

        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        builtin = os.path.join(app_dir, "orchestrator", "generators", "release_notes_generator.py")
        monkeypatch.setattr(
            "config._ws",
            {"release_notes": {"generator_script": "generators/release_notes_generator.py"}},
        )
        monkeypatch.setattr("config.RELEASE_NOTES_GENERATOR", builtin)

        assert os.path.isfile(builtin)
        assert s4._has_external_generator() is False

    def test_legacy_engine_script_is_external(self, tmp_path, monkeypatch):
        from release_platform.ui.release_notes import step4_generate as s4

        legacy = tmp_path / "legacy_gen.py"
        legacy.write_text(
            "# header\nENGINE \u2014 DO NOT EDIT BELOW\nprint('ok')\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "config._ws",
            {"release_notes": {"generator_script": str(legacy)}},
        )
        monkeypatch.setattr("config.RELEASE_NOTES_GENERATOR", str(legacy))

        assert s4._has_external_generator() is True
