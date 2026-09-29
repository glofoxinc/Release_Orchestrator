"""Tests for default status selection on Ticket Review Step 1."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestDefaultStatusSelections:
    def test_apply_defaults_pic_and_an(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_review import selection as sel

        monkeypatch.setattr(
            st,
            "session_state",
            {},
            raising=False,
        )

        def fake_options(project_key: str) -> list[str]:
            if project_key == "PIC":
                return ["Review", "In Progress", "Done"]
            return ["Review", "In Progress", "In Review", "Passed QA"]

        monkeypatch.setattr(sel.ts, "load_project_status_options", fake_options)
        sel.apply_default_status_selections(force=True)

        assert "Review" in st.session_state["tr_statuses_PIC"]
        assert "Review" in st.session_state["tr_statuses_AN"]
        assert "Passed QA" not in st.session_state["tr_statuses_AN"]

    def test_does_not_overwrite_existing_without_force(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_review import selection as sel

        monkeypatch.setattr(
            st,
            "session_state",
            {"tr_statuses_PIC": ["In Progress"]},
            raising=False,
        )
        monkeypatch.setattr(
            sel.ts,
            "load_project_status_options",
            lambda pk: ["Review", "In Progress"],
        )
        sel.apply_default_status_selections(force=False)
        assert st.session_state["tr_statuses_PIC"] == ["In Progress"]

    def test_restore_from_snapshot(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_review import selection as sel

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        sel.apply_snapshot_selection_context(
            {
                "selection_mode": sel.MODE_STATUS,
                "status_filters": {
                    "PIC": ["Review"],
                    "AN": ["Passed QA"],
                },
            }
        )
        assert st.session_state[sel.MODE_SESSION_KEY] == sel.MODE_STATUS
        assert st.session_state["tr_statuses_PIC"] == ["Review"]
        assert st.session_state["tr_statuses_AN"] == ["Passed QA"]
