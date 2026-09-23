"""Tests for Release Deployer quick-start flow routing."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


class TestDeployerFlow:
    def test_full_flow_labels_and_back_steps(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import deployer_flow

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        assert deployer_flow.step_count() == 6
        assert "Exclude Tickets" in deployer_flow.step_labels()
        assert deployer_flow.back_from_deploy_info() == 3
        assert deployer_flow.back_from_review() == 4
        assert deployer_flow.back_from_execute() == 5

    def test_quick_start_labels_and_back_steps(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import deployer_flow, workflow

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        workflow.enable_deployer_standalone()
        assert deployer_flow.is_quick_start() is True
        assert deployer_flow.step_count() == 5
        assert deployer_flow.step_labels()[1] == "Select Tickets"
        assert "Exclude Tickets" not in deployer_flow.step_labels()
        assert deployer_flow.back_from_deploy_info() == 2
        assert deployer_flow.back_from_review() == 3
        assert deployer_flow.back_from_execute() == 4

    def test_init_deploy_ticket_selection_respects_allowed_keys(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import deployer_flow

        state: dict = {}
        monkeypatch.setattr(st, "session_state", state, raising=False)
        candidates = [{"key": "PIC-1"}, {"key": "PIC-2"}, {"key": "PIC-3"}]
        deployer_flow.init_deploy_ticket_selection(
            candidates,
            allowed_keys={"PIC-1", "PIC-3"},
        )
        assert state["wiz_deploy_selected_keys"] == {"PIC-1", "PIC-3"}
        assert state["wiz_dep_chk_PIC-1"] is True
        assert state["wiz_dep_chk_PIC-2"] is False

    def test_read_deploy_ticket_selection(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import deployer_flow

        state = {
            "wiz_deploy_selected_keys": {"PIC-1"},
            "wiz_dep_chk_PIC-1": True,
            "wiz_dep_chk_PIC-2": False,
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        candidates = [{"key": "PIC-1"}, {"key": "PIC-2"}]
        assert deployer_flow.read_deploy_ticket_selection(candidates) == {"PIC-1"}
