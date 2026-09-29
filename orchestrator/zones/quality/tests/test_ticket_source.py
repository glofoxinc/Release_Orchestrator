"""Tests for shared ticket_source module."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestTicketSourceDefaults:
    def test_rn_default_statuses(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import ticket_source as ts

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        monkeypatch.setattr(
            ts,
            "load_project_status_options",
            lambda pk: (
                ["Ready for Release", "Review"]
                if pk == "PIC"
                else ["QA(migrated)", "Passed QA", "Done"]
            ),
        )
        ts.apply_default_status_selections("rn_", force=True)
        assert st.session_state["rn_statuses_PIC"] == ["Ready for Release"]
        assert st.session_state["rn_statuses_AN"] == ["QA(migrated)"]

    def test_has_step1_status_selection(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import ticket_source as ts

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "stk_selection_mode": ts.MODE_STATUS,
                "stk_statuses_AN": ["Passed QA"],
            },
            raising=False,
        )
        assert ts.has_step1_selection(prefix="stk_") is True


class TestLockedTicketSource:
    def test_lock_and_apply_status_mode(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import ticket_source as ts

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "rn_selection_mode": ts.MODE_STATUS,
                "rn_statuses_PIC": ["Review"],
                "rn_statuses_AN": ["Passed QA"],
            },
            raising=False,
        )
        locked = ts.lock_ticket_source("rn_")
        assert locked["mode"] == ts.MODE_STATUS
        assert locked["statuses"]["PIC"] == ["Review"]
        assert st.session_state["rn_selection_mode"] == ts.MODE_STATUS

        st.session_state.pop("rn_statuses_PIC", None)
        st.session_state.pop("rn_statuses_AN", None)
        st.session_state["rn_step"] = 2

        ts.apply_locked_ticket_source("rn_")
        assert ts.get_effective_selection_mode("rn_") == ts.MODE_STATUS
        assert st.session_state["rn_statuses_PIC"] == ["Review"]
        assert st.session_state["rn_statuses_AN"] == ["Passed QA"]

    def test_rebuild_locked_from_fingerprint(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import ticket_source as ts

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        fp = "status|PIC:Review|AN:Passed QA|teams:PIC:abc|AN:abc"
        rebuilt = ts.rebuild_locked_from_fingerprint("rn_", fp)
        assert rebuilt is not None
        assert rebuilt["mode"] == ts.MODE_STATUS
        assert rebuilt["statuses"]["PIC"] == ["Review"]
        assert rebuilt["statuses"]["AN"] == ["Passed QA"]

        st.session_state["rn_source_fp"] = fp
        ensured = ts.ensure_locked_ticket_source("rn_")
        assert ensured is not None
        assert ts.get_effective_selection_mode("rn_") == ts.MODE_STATUS

    def test_snapshot_does_not_clobber_locked_source(self, monkeypatch):
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
                },
                "rn_selection_mode": ts.MODE_STATUS,
            },
            raising=False,
        )
        ts.apply_snapshot_selection_context(
            "rn_",
            {
                "selection_mode": ts.MODE_FIX_VERSION,
                "status_filters": {"PIC": ["Done"]},
            },
        )
        assert ts.get_effective_selection_mode("rn_") == ts.MODE_STATUS
        assert st.session_state.get("rn_statuses_PIC") != ["Done"]
