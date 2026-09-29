"""Regression tests for final cleanup: drift fail-closed and deploy cache."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


class TestDriftFailClosed:
    def test_api_error_returns_error_status(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        def boom(_pk, _rid):
            raise RuntimeError("Jira unavailable")

        state = {
            helpers._SNAPSHOT_KEY: {
                "ticket_keys": ["PIC-1"],
                "release_PIC": {"id": "100", "name": "2026.3.07.15"},
            },
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        monkeypatch.setattr(helpers, "fetch_issues_for_snapshot", lambda _s: (_ for _ in ()).throw(RuntimeError("Jira unavailable")))

        result = helpers.check_snapshot_drift()
        assert result is not None
        assert result["status"] == "error"
        assert "Jira unavailable" in result["message"]
        assert helpers.drift_blocks_proceed(result) is True
        assert helpers.drift_has_changes(result) is False

    def test_no_drift_returns_ok(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(
            helpers,
            "fetch_issues_for_snapshot",
            lambda _s: [{"key": "PIC-1"}, {"key": "PIC-2"}],
        )
        state = {
            helpers._SNAPSHOT_KEY: {
                "ticket_keys": ["PIC-1", "PIC-2"],
                "release_PIC": {"id": "100", "name": "2026.3.07.15"},
            },
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        result = helpers.check_snapshot_drift()
        assert result == {"status": "ok", "added": [], "removed": []}
        assert helpers.drift_blocks_proceed(result) is False

    def test_drift_detected(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(
            helpers,
            "fetch_issues_for_snapshot",
            lambda _s: [{"key": "PIC-1"}, {"key": "PIC-3"}],
        )
        state = {
            helpers._SNAPSHOT_KEY: {
                "ticket_keys": ["PIC-1", "PIC-2"],
                "release_PIC": {"id": "100", "name": "2026.3.07.15"},
            },
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        result = helpers.check_snapshot_drift()
        assert result["status"] == "drift"
        assert result["added"] == ["PIC-3"]
        assert result["removed"] == ["PIC-2"]
        assert helpers.drift_has_changes(result) is True


class TestDeselectedTicketsAreNotDrift:
    def test_excluded_tickets_do_not_report_as_added(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(
            helpers,
            "fetch_issues_for_snapshot",
            lambda _s: [{"key": "PIC-1"}, {"key": "PIC-2"}, {"key": "PIC-3"}],
        )
        state = {
            helpers._SNAPSHOT_KEY: {
                "ticket_keys": ["PIC-1"],
                "excluded_keys": ["PIC-2", "PIC-3"],
                "release_PIC": {"id": "100", "name": "2026.3.08.12"},
            },
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        assert helpers.check_snapshot_drift() == {"status": "ok", "added": [], "removed": []}

    def test_genuinely_new_ticket_still_reports_as_drift(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(
            helpers,
            "fetch_issues_for_snapshot",
            lambda _s: [{"key": "PIC-1"}, {"key": "PIC-2"}, {"key": "PIC-9"}],
        )
        state = {
            helpers._SNAPSHOT_KEY: {
                "ticket_keys": ["PIC-1"],
                "excluded_keys": ["PIC-2"],
                "release_PIC": {"id": "100", "name": "2026.3.08.12"},
            },
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        result = helpers.check_snapshot_drift()
        assert result["status"] == "drift"
        assert result["added"] == ["PIC-9"]

    def test_create_snapshot_records_deselected_keys(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        monkeypatch.setattr(helpers.config, "PROJECTS", [{"key": "PIC"}], raising=False)

        snap = helpers.create_snapshot(
            [{"key": "PIC-1"}],
            candidate_keys={"PIC-1", "PIC-2"},
        )
        assert snap["ticket_keys"] == ["PIC-1"]
        assert snap["excluded_keys"] == ["PIC-2"]

    def test_legacy_snapshot_recovers_exclusions_from_session_cache(self, monkeypatch):
        import streamlit as st
        import team_scope

        from release_platform.ui import helpers

        monkeypatch.setattr(
            helpers,
            "fetch_issues_for_snapshot",
            lambda _s: [{"key": "PIC-1"}, {"key": "PIC-2"}],
        )
        fp = team_scope.scope_fingerprint(
            "PIC", team_scope.parse_scope({"allow_project_wide": True}),
        )
        state = {
            helpers._SNAPSHOT_KEY: {
                "ticket_keys": ["PIC-1"],
                "release_PIC": {"id": "100", "name": "2026.3.08.12"},
            },
            "shared_release_PIC": {"id": "100", "name": "2026.3.08.12"},
            f"_tr_issues_PIC_100_{fp}": [{"key": "PIC-1"}, {"key": "PIC-2"}],
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        monkeypatch.setattr(
            helpers.config,
            "PROJECTS",
            [{"key": "PIC", "scope": {"allow_project_wide": True}}],
            raising=False,
        )

        assert helpers.check_snapshot_drift() == {"status": "ok", "added": [], "removed": []}

    def test_relock_keeps_deselected_tickets_out(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        state = {
            helpers._SNAPSHOT_KEY: {
                "ticket_keys": ["PIC-1"],
                "excluded_keys": ["PIC-2"],
                "release_PIC": {"id": "100", "name": "2026.3.08.12"},
            },
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        monkeypatch.setattr(helpers.config, "PROJECTS", [{"key": "PIC"}], raising=False)
        monkeypatch.setattr(
            helpers.jira_client,
            "get_issues_for_version",
            lambda _pk, _rid, jira_team_ids=None: [
                {"key": "PIC-1"},
                {"key": "PIC-2"},
                {"key": "PIC-9"},
            ],
        )

        snap = helpers.relock_snapshot()
        assert snap["ticket_keys"] == ["PIC-1", "PIC-9"]
        assert snap["excluded_keys"] == ["PIC-2"]


class TestDeployResultsCache:
    def test_fingerprint_changes_when_selection_changes(self):
        from release_platform.ui.helpers import compute_deploy_run_fingerprint

        filled = {"Analyze": {"deployment_id": "DEP-1", "deployment_date": "01-July-2026"}}
        fp1 = compute_deploy_run_fingerprint("rel-1", {"PIC-1"}, filled)
        fp2 = compute_deploy_run_fingerprint("rel-1", {"PIC-1", "PIC-2"}, filled)
        assert fp1 != fp2

    def test_fingerprint_changes_when_force_deploy_toggles(self):
        from release_platform.ui.helpers import compute_deploy_run_fingerprint

        filled = {"Analyze": {"deployment_id": "DEP-1"}}
        fp1 = compute_deploy_run_fingerprint("rel-1", {"PIC-1"}, filled, force_deploy=False)
        fp2 = compute_deploy_run_fingerprint("rel-1", {"PIC-1"}, filled, force_deploy=True)
        assert fp1 != fp2

    def test_clear_deploy_results_cache_scoped(self, monkeypatch):
        import streamlit as st

        from release_platform.ui.helpers import clear_deploy_results_cache

        state = {
            "wiz_results_1": {"success": 1},
            "wiz_results_fp_1": "abc",
            "wiz_results_2": {"success": 2},
            "wiz_results_fp_2": "def",
            "wiz_undo_data": [],
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        clear_deploy_results_cache("1")
        assert "wiz_results_1" not in state
        assert "wiz_results_fp_1" not in state
        assert "wiz_results_2" in state
        assert "wiz_undo_data" not in state
