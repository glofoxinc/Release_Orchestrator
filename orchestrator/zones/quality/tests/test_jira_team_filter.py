"""Tests for Jira Team filter session helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")

import pytest

pytestmark = pytest.mark.real_scope


class TestTeamFilterCacheSuffix:
    def test_all_teams_when_empty(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_review import jira_team_filter as jtf

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        assert jtf.team_filter_cache_suffix("PIC") == "allteams"

    def test_differs_when_team_selected(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_review import jira_team_filter as jtf

        monkeypatch.setattr(
            st,
            "session_state",
            {"tr_jira_teams_sel_PIC": ["317996a7-118a-4cf3-a3c6-04163516ed32"]},
            raising=False,
        )
        suffix = jtf.team_filter_cache_suffix("PIC")
        assert suffix.startswith("teams_")
        assert suffix != "allteams"


class TestSnapshotTeamFilterSummary:
    def test_all_teams_when_missing(self):
        from release_platform.ui.ticket_review.jira_team_filter import format_snapshot_team_filters

        assert format_snapshot_team_filters({}) == "All teams (no Team filter)"
        assert format_snapshot_team_filters(None) == ""

    def test_formats_per_project(self):
        from release_platform.ui.ticket_review.jira_team_filter import format_snapshot_team_filters

        snap = {
            "jira_team_filters": {
                "PIC": [{"id": "abc", "name": "Glofox Insights Customize"}],
                "AN": [{"id": "def", "name": "Glofox Insights Customize"}],
            }
        }
        text = format_snapshot_team_filters(snap)
        assert "PIC: Glofox Insights Customize" in text
        assert "AN: Glofox Insights Customize" in text


class TestSessionWideTeamLock:
    def test_lock_propagates_to_all_apps(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import jira_team_filter as jtf

        monkeypatch.setattr(
            st,
            "session_state",
            {"tr_jira_teams_sel_PIC": ["team-a"]},
            raising=False,
        )
        monkeypatch.setattr(
            jtf,
            "load_team_catalog",
            lambda pk: [{"id": "team-a", "name": "Customize"}],
        )
        jtf.lock_team_filter("tr_")
        assert st.session_state[jtf.SHARED_LOCK_KEY] is True
        assert jtf.is_team_filter_locked("rn_")
        assert jtf.get_selected_team_ids("stk_", "PIC") == ["team-a"]

    def test_unlock_clears_session_lock(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import jira_team_filter as jtf

        monkeypatch.setattr(
            st,
            "session_state",
            {
                jtf.SHARED_LOCK_KEY: True,
                jtf.SHARED_LOCKED_VALUES_KEY: {
                    "PIC": [{"id": "team-a", "name": "Customize"}],
                },
                "tr_jira_teams_locked": True,
                "rn_jira_teams_locked": True,
            },
            raising=False,
        )
        jtf.unlock_team_filter("tr_")
        assert jtf.SHARED_LOCK_KEY not in st.session_state
        assert not jtf.is_team_filter_locked("rn_")

    def test_ensure_locks_on_continue_when_teams_selected(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import jira_team_filter as jtf

        monkeypatch.setattr(
            st,
            "session_state",
            {"rn_jira_teams_sel_AN": ["team-b"]},
            raising=False,
        )
        monkeypatch.setattr(
            jtf,
            "load_team_catalog",
            lambda pk: [{"id": "team-b", "name": "Ignite"}],
        )
        jtf.ensure_team_filter_locked("rn_")
        assert st.session_state[jtf.SHARED_LOCK_KEY] is True
        assert jtf.is_team_filter_locked("tr_")


class TestSnapshotTeamMatch:
    def test_match_and_mismatch(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_review import jira_team_filter as jtf

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "shared_snapshot": {
                    "jira_team_filters": {
                        "PIC": [{"id": "abc", "name": "Glofox"}],
                    }
                }
            },
            raising=False,
        )
        assert jtf.snapshot_team_filter_matches(
            {"PIC": [{"id": "abc", "name": "Glofox"}]},
        )
        assert not jtf.snapshot_team_filter_matches(
            {"PIC": [{"id": "other", "name": "Ignite"}]},
        )
