"""Tests for Release Notes step 2 ticket selection helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from release_platform.ui.release_notes import step2_tickets as s2


class TestRnStep2Selection:
    def test_read_selection_from_checkbox_keys(self, monkeypatch):
        import streamlit as st

        extracted = [
            {"ticket": "AN-1"},
            {"ticket": "AN-2"},
            {"ticket": "PIC-3"},
        ]
        state = {
            "rn_selected_keys": {"AN-1", "PIC-3"},
            "rn_chk_AN-1": True,
            "rn_chk_AN-2": False,
            "rn_chk_PIC-3": True,
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        selected = s2._read_ticket_selection(extracted)
        assert selected == {"AN-1", "PIC-3"}

    def test_set_selection_updates_keys(self, monkeypatch):
        import streamlit as st

        extracted = [{"ticket": "AN-1"}, {"ticket": "AN-2"}]
        state: dict = {}
        monkeypatch.setattr(st, "session_state", state, raising=False)

        s2._set_ticket_selection(extracted, {"AN-2"})

        assert state["rn_selected_keys"] == {"AN-2"}
        assert state["rn_chk_AN-1"] is False
        assert state["rn_chk_AN-2"] is True
