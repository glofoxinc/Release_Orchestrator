"""Regression tests for audit-fix helpers."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


class TestMarkHistoryEntryReverted:
    def test_marks_matching_entry(self, tmp_path, monkeypatch):
        from release_platform.ui import helpers

        history_file = tmp_path / ".deployment_history.json"
        history_file.write_text(
            json.dumps([
                {
                    "timestamp": "2026-07-01T12:00:00+00:00",
                    "project": "PIC",
                    "success": 3,
                }
            ]),
            encoding="utf-8",
        )
        monkeypatch.setattr(helpers, "_history_path", lambda: str(history_file))

        helpers.mark_history_entry_reverted("2026-07-01T12:00:00+00:00")

        data = json.loads(history_file.read_text(encoding="utf-8"))
        assert data[0]["reverted"] is True
        assert data[0]["success"] == 0
        assert "reverted_at" in data[0]


class TestResolveIssueTypeId:
    def test_resolves_by_name(self):
        import jira_client

        jira_client._issue_type_cache.clear()
        payload = {
            "projects": [
                {
                    "issuetypes": [
                        {"id": "10002", "name": "Task"},
                        {"id": "10004", "name": "Bug"},
                    ]
                }
            ]
        }
        with patch("jira_client._get", return_value=payload):
            assert jira_client.resolve_issue_type_id("PIC", "Bug") == "10004"

    def test_falls_back_to_task_when_type_missing(self):
        import jira_client

        jira_client._issue_type_cache.clear()
        payload = {"projects": [{"issuetypes": [{"id": "10002", "name": "Task"}]}]}
        with patch("jira_client._get", return_value=payload):
            assert jira_client.resolve_issue_type_id("PIC", "Epic") == "10002"


class TestMockModeGuards:
    def test_post_blocked_in_mock_mode(self, monkeypatch):
        import jira_client
        from jira_client import JiraApiError

        monkeypatch.setenv("MOCK_MODE", "true")
        with pytest.raises(JiraApiError, match="Mock mode"):
            jira_client.create_issue("PIC", "10002", "Summary", {})

    def test_transition_blocked_in_mock_mode(self, monkeypatch):
        import jira_client
        from jira_client import JiraApiError

        monkeypatch.setenv("MOCK_MODE", "true")
        with pytest.raises(JiraApiError, match="Mock mode"):
            jira_client.transition_issue("PIC-1", "21")


class TestInvalidateSnapshotIfSelectionChanged:
    def test_clears_snapshot_when_keys_differ(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        state = {
            helpers._SNAPSHOT_KEY: {"ticket_keys": ["PIC-1", "PIC-2"]},
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        helpers.invalidate_snapshot_if_selection_changed({"PIC-1"})

        assert helpers._SNAPSHOT_KEY not in state

    def test_keeps_snapshot_when_keys_match(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import helpers

        state = {
            helpers._SNAPSHOT_KEY: {"ticket_keys": ["PIC-1", "PIC-2"]},
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)

        helpers.invalidate_snapshot_if_selection_changed({"PIC-1", "PIC-2"})

        assert helpers._SNAPSHOT_KEY in state
