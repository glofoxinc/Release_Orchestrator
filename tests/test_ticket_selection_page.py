"""Tests for ticket selection page helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")


class TestShouldAutoBackToStep1:
    def test_stays_when_step2_loaded(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_selection_page import should_auto_back_to_step1

        monkeypatch.setattr(
            st,
            "session_state",
            {"rn_step2_loaded": True},
            raising=False,
        )
        assert not should_auto_back_to_step1(
            "rn_",
            has_source_selection=False,
        )

    def test_back_when_never_loaded_and_no_source(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_selection_page import should_auto_back_to_step1

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        assert should_auto_back_to_step1(
            "rn_",
            has_source_selection=False,
        )

    def test_stays_with_cached_tickets(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_selection_page import should_auto_back_to_step1

        monkeypatch.setattr(
            st,
            "session_state",
            {"rn_all_extracted": [{"ticket": "AN-1"}]},
            raising=False,
        )
        assert not should_auto_back_to_step1(
            "rn_",
            has_source_selection=False,
            has_cached_tickets=True,
        )


class TestSelectionFingerprintStability:
    def test_fix_version_id_normalized_same_fingerprint(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import ticket_source as ts

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "rn_selection_mode": "fix_version",
                "rn_release_PIC": {"id": 12345, "name": "2026.3.09.08"},
                "rn_release_AN": {},
            },
            raising=False,
        )
        fp_int = ts.selection_fingerprint("rn_")
        st.session_state["rn_release_PIC"] = {"id": "12345", "name": "2026.3.09.08"}
        fp_str = ts.selection_fingerprint("rn_")
        assert fp_int == fp_str
