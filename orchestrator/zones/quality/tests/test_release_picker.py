"""Tests for shared release picker id normalization and write semantics."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")

from release_platform.ui import helpers


class TestNormalizeVersionId:
    def test_int_and_str_equal(self):
        assert helpers.normalize_version_id(12345) == helpers.normalize_version_id("12345")

    def test_blank(self):
        assert helpers.normalize_version_id(None) == ""
        assert helpers.normalize_version_id("") == ""


class TestWriteSharedRelease:
    def test_same_id_different_type_does_not_clear_snapshot(self, monkeypatch):
        import streamlit as st

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "tr_release_PIC": {"id": 999, "name": "2026.3.09.16"},
                "shared_release_PIC": {"id": 999, "name": "2026.3.09.16"},
                "shared_snapshot": {"ticket_keys": ["PIC-1"]},
            },
            raising=False,
        )
        changed = helpers.write_shared_release(
            "tr_",
            "PIC",
            {"id": "999", "name": "2026.3.09.16"},
        )
        assert changed is False
        assert st.session_state["shared_snapshot"] == {"ticket_keys": ["PIC-1"]}
        assert st.session_state["tr_release_PIC"]["id"] == "999"

    def test_new_version_clears_snapshot(self, monkeypatch):
        import streamlit as st

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "tr_release_PIC": {"id": "111", "name": "old"},
                "shared_snapshot": {"ticket_keys": ["PIC-1"]},
            },
            raising=False,
        )
        changed = helpers.write_shared_release(
            "tr_",
            "PIC",
            {"id": "222", "name": "new"},
        )
        assert changed is True
        assert "shared_snapshot" not in st.session_state


class TestApplyReleaseSelection:
    def test_no_op_when_ids_match_by_value(self, monkeypatch):
        import streamlit as st

        monkeypatch.setattr(
            st,
            "session_state",
            {"tr_release_PIC": {"id": 42, "name": "v1"}},
            raising=False,
        )
        versions = {"42": {"id": "42", "name": "v1"}}
        changed = helpers._apply_release_selection(
            "tr_",
            "PIC",
            "42",
            versions,
            ("tr_grouped",),
        )
        assert changed is False
