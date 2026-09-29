"""Tests for Release Deployer deployment-info helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


class TestDeployFilledHelpers:
    def test_collect_single_project(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "dep_id_single": "uuid-1",
                "dep_date_single": "July 1 2026",
                "dep_time_single": "10:00 AM",
            },
            raising=False,
        )

        filled, skipped = helpers.collect_deploy_filled("AN", multi_client=False)
        assert skipped == []
        assert filled["AN"]["deployment_id"] == "uuid-1"
        assert helpers.deploy_filled_is_valid(filled)

    def test_collect_multi_client_skips_empty_ids(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "wiz_grouped": {"Jetts": [{}], "XPO": [{}]},
                "dep_id_Jetts": "uuid-j",
                "dep_time_Jetts": "9:00 AM",
                "dep_id_XPO": "",
            },
            raising=False,
        )

        filled, skipped = helpers.collect_deploy_filled("PIC", multi_client=True)
        assert list(filled.keys()) == ["Jetts"]
        assert skipped == ["XPO"]

    def test_save_and_read_snapshot(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        state = {
            "dep_id_single": "uuid-1",
            "dep_date_single": "July 1 2026",
            "dep_time_single": "10:00 AM",
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        assert helpers.save_deploy_filled_snapshot("AN", multi_client=False)
        filled, skipped = helpers.get_deploy_filled_snapshot("AN", multi_client=False)
        assert filled["AN"]["deployment_id"] == "uuid-1"
        assert skipped == []
        assert state["wiz_deploy_info_saved"] is True

    def test_invalid_when_missing_time(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(
            st,
            "session_state",
            {
                "dep_id_single": "uuid-1",
                "dep_time_single": "",
            },
            raising=False,
        )

        filled, _ = helpers.collect_deploy_filled("AN", multi_client=False)
        assert not helpers.deploy_filled_is_valid(filled)


class TestApplyDeployIssueFilter:
    def test_filters_to_snapshot_keys(self, monkeypatch):
        from release_platform.ui import helpers

        snap = {
            "release_PIC": {"id": "100", "name": "2026.3.07.08"},
            "ticket_keys": ["PIC-5634", "PIC-9999"],
        }
        issues = [
            {"key": "PIC-5638", "fields": {"summary": "BDGyms - A"}},
            {"key": "PIC-5634", "fields": {"summary": "BDGyms - B"}},
        ]
        with monkeypatch.context() as m:
            m.setattr(helpers, "get_snapshot", lambda: snap)
            filtered, meta = helpers.apply_deploy_issue_filter(
                issues, "PIC", {"id": "100", "name": "2026.3.07.08"}
            )

        assert [i["key"] for i in filtered] == ["PIC-5634"]
        assert meta["removed"] == ["PIC-5638"]
        assert meta["missing_from_release"] == ["PIC-9999"]
