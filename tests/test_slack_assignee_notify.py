"""Tests for Slack assignee DM notifications (release gates)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestSlackAssigneeNotify:
    def test_dry_run_groups_by_assignee(self):
        from release_gates import GateTicket
        from slack_assignee_notify import notify_gate_tickets

        tickets = [
            GateTicket(
                key="PIC-1",
                summary="A",
                status="Open",
                assignee_name="Alice",
                assignee_email="alice@example.com",
                project="PIC",
                reason="not ready",
            ),
            GateTicket(
                key="PIC-2",
                summary="B",
                status="Open",
                assignee_name="Alice",
                assignee_email="alice@example.com",
                project="PIC",
                reason="not ready",
            ),
        ]
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test-token"}):
            out = notify_gate_tickets(
                tickets,
                lambda t: f"msg {t.key}",
                dry_run=True,
            )
        assert out["status"] == "dry_run"
        assert out["recipient_count"] == 1
        assert out["ticket_count"] == 2
        assert "PIC-1" in out["previews"][0]["message_preview"]

    def test_missing_token_returns_error(self, monkeypatch):
        from release_gates import GateTicket
        from slack_assignee_notify import notify_gate_tickets

        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        ticket = GateTicket(
            key="PIC-1",
            summary="A",
            status="Open",
            assignee_name="Alice",
            assignee_email="alice@example.com",
            project="PIC",
            reason="x",
        )
        out = notify_gate_tickets([ticket], lambda t: "hi", dry_run=False)
        assert out["status"] == "error"
        assert "SLACK_BOT_TOKEN" in out["error"]

    def test_gate_slack_status(self):
        from slack_assignee_notify import gate_slack_status

        st = gate_slack_status()
        assert "can_dm_assignees" in st
        assert "scopes_hint" in st
