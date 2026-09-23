"""Tests for fix-version → release notes metadata parsing."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from datetime import date

from release_platform.ui.helpers import (
    clear_release_doc_version_metadata,
    derive_release_doc_metadata,
    parse_fix_version_date,
    parse_fix_version_name,
    release_doc_metadata_fallback_today,
    release_notes_doc_filename,
    release_notes_uses_fix_version,
    sync_release_doc_metadata,
)


class TestParseFixVersionName:
    def test_q3_july_six(self):
        result = parse_fix_version_name("2026.3.07.06")
        assert result == ("v2026.3.07.06", "06-July-2026")

    def test_q2_april_fourteen(self):
        result = parse_fix_version_name("2026.2.04.14")
        assert result == ("v2026.2.04.14", "14-April-2026")

    def test_does_not_use_today(self):
        result = parse_fix_version_name("2026.3.07.08")
        assert result == ("v2026.3.07.08", "08-July-2026")

    def test_invalid_name(self):
        assert parse_fix_version_name("Sprint 42") is None


class TestParseFixVersionDate:
    def test_returns_date(self):
        assert parse_fix_version_date("2026.3.07.06") == date(2026, 7, 6)


class TestReleaseDocMetadataFallbackToday:
    def test_builds_quarter_version_and_date_label(self):
        version, doc_date = release_doc_metadata_fallback_today(on=date(2026, 9, 8))
        assert version == "v2026.3.09.08"
        assert doc_date == "08-September-2026"


class TestDeriveReleaseDocMetadata:
    def test_from_session_releases(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        state = {
            "rn_release_PIC": {"id": "1", "name": "2026.3.07.06"},
            "rn_release_AN": {"id": "2", "name": "2026.3.07.06"},
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        monkeypatch.setattr(helpers.config, "PROJECTS", [
            {"key": "PIC", "name": "PIC"},
            {"key": "AN", "name": "AN"},
        ])

        version, doc_date = derive_release_doc_metadata("rn_")
        assert version == "v2026.3.07.06"
        assert doc_date == "06-July-2026"


class TestReleaseNotesDocFilename:
    def test_dedupes_pic_and_an_same_version(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        state = {
            "stk_release_PIC": {"id": "1", "name": "2026.3.07.29"},
            "stk_release_AN": {"id": "2", "name": "2026.3.07.29"},
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        monkeypatch.setattr(helpers.config, "PROJECTS", [
            {"key": "PIC", "name": "PIC"},
            {"key": "AN", "name": "AN"},
        ])
        assert release_notes_doc_filename("stk_") == "Release Notes 2026.3.07.29.docx"

    def test_prefers_generated_filename(self, monkeypatch):
        import streamlit as st

        monkeypatch.setattr(st, "session_state", {
            "shared_docx_filename": "Release Notes 2026.3.07.29.docx",
        }, raising=False)
        assert release_notes_doc_filename("stk_") == "Release Notes 2026.3.07.29.docx"


class TestSyncReleaseDocMetadata:
    def _patch_projects(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(helpers.config, "PROJECTS", [
            {"key": "PIC", "name": "PIC"},
            {"key": "AN", "name": "AN"},
        ])
        return st, helpers

    def test_heals_stale_q2_default(self, monkeypatch):
        st, helpers = self._patch_projects(monkeypatch)
        state = {
            "rn_release_PIC": {"id": "1", "name": "2026.3.07.08"},
            "rn_release_AN": {"id": "2", "name": "2026.3.07.08"},
            "rn_release_fp": "PIC:1|AN:2",
            "rn_version": "v2026.2.07.06",
            "rn_date": "06-July-2026",
            "_rn_ver": "v2026.2.07.06",
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        sync_release_doc_metadata("rn_")

        assert state["rn_version"] == "v2026.3.07.08"
        assert state["rn_date"] == "08-July-2026"
        assert "_rn_ver" not in state

    def test_respects_user_customization(self, monkeypatch):
        st, helpers = self._patch_projects(monkeypatch)
        state = {
            "rn_release_PIC": {"id": "1", "name": "2026.3.07.08"},
            "rn_release_AN": {"id": "2", "name": "2026.3.07.08"},
            "rn_release_fp": "PIC:1|AN:2",
            "rn_version": "v2026.3.07.08-custom",
            "rn_date": "08-July-2026",
            "rn_metadata_customized": True,
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        sync_release_doc_metadata("rn_")

        assert state["rn_version"] == "v2026.3.07.08-custom"


class TestStatusOnlyReleaseNotesMetadata:
    def test_release_notes_uses_fix_version_from_locked_status(self):
        from release_platform.ui import ticket_source as ts

        ss = {
            "rn_locked_ticket_source": {
                "mode": ts.MODE_STATUS,
                "summary": "PIC: Review",
                "statuses": {"PIC": ["Review"]},
                "releases": {},
            }
        }
        assert not release_notes_uses_fix_version("rn_", ss)

    def test_sync_clears_version_for_status_only(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers
        from release_platform.ui import ticket_source as ts

        state = {
            "rn_version": "v2026.3.07.08",
            "rn_date": "08-July-2026",
            "rn_locked_ticket_source": {
                "mode": ts.MODE_STATUS,
                "summary": "PIC: Review",
                "statuses": {"PIC": ["Review"]},
                "releases": {},
            },
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        monkeypatch.setattr(helpers.config, "PROJECTS", [
            {"key": "PIC", "name": "PIC"},
            {"key": "AN", "name": "AN"},
        ])

        sync_release_doc_metadata("rn_")

        # Status mode now always sets version from deploy date (user requirement: always include version)
        assert "rn_version" in state
        assert "rn_date" in state
        assert state["rn_version"].startswith("v20")

    def test_doc_filename_with_status_derived_version(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import ticket_source as ts

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "rn_locked_ticket_source": {
                    "mode": ts.MODE_STATUS,
                    "summary": "PIC: Review",
                    "statuses": {"PIC": ["Review"]},
                    "releases": {},
                }
            },
            raising=False,
        )
        # Status mode now derives version from today's date (user requirement)
        filename = release_notes_doc_filename("rn_")
        assert filename.startswith("Release Notes ")
        assert filename.endswith(".docx")

    def test_clear_release_doc_version_metadata(self, monkeypatch):
        import streamlit as st

        state = {
            "rn_version": "v2026.3.07.08",
            "rn_date": "08-July-2026",
            "rn_metadata_customized": True,
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        clear_release_doc_version_metadata("rn_")

        assert "rn_version" not in state
        assert "rn_date" not in state
        assert "rn_metadata_customized" not in state

    def test_docx_omits_version_and_release_date(self):
        import io

        from docx import Document

        from generators.release_notes_generator import generate_release_notes_docx

        doc = Document(
            io.BytesIO(
                generate_release_notes_docx(
                    {
                        "version": "",
                        "release_date": "",
                        "dev_team": "BI Team",
                        "release_owner": "Alice",
                        "summary_p1": "Status-only release.",
                    }
                )
            )
        )
        texts = [p.text for p in doc.paragraphs]
        assert not any("Release Date" in t for t in texts)
        assert not any(t.strip().startswith("v2026") for t in texts)
        assert texts[0].strip() == "Release Notes"
