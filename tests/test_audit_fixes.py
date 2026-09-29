"""Regression tests for audit-fix session helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


class TestDeployFilterBlocksProgress:
    def test_blocks_on_missing_from_release(self):
        from release_platform.ui.helpers import deploy_filter_blocks_progress

        assert deploy_filter_blocks_progress({"missing_from_release": ["PIC-1"]}) is True
        assert deploy_filter_blocks_progress({"using_snapshot": True, "removed": ["PIC-2"]}) is False


class TestSnapshotSelectionPending:
    def test_pending_when_differs(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        state = {
            helpers._SNAPSHOT_KEY: {"ticket_keys": ["PIC-1", "PIC-2"]},
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        assert helpers.snapshot_selection_pending({"PIC-1"}) is True
        assert helpers.snapshot_selection_pending({"PIC-1", "PIC-2"}) is False


class TestSyncRnTicketDraft:
    def test_clears_draft_on_selection_change(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        state = {
            "rn_ticket_fp": "PIC-1",
            "rn_summary_p1": "old",
            "rn_change_rows": "old",
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        helpers.sync_rn_ticket_draft({"PIC-1", "PIC-2"})

        assert state["rn_ticket_fp"] == "PIC-1|PIC-2"
        assert "rn_summary_p1" not in state
        assert "rn_change_rows" not in state


class TestValidateWorkspaceProjects:
    def test_rejects_empty_and_duplicate(self):
        from release_platform.ui.helpers import validate_workspace_projects

        assert validate_workspace_projects([]) == ["At least one project is required."]
        errors = validate_workspace_projects([
            {"key": "PIC"},
            {"key": "PIC"},
        ])
        assert any("Duplicate" in e for e in errors)
