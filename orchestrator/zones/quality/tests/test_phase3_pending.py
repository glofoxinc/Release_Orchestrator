"""Tests for Phase 3: default slots, update meeting, slack/gate templates."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestDefaultMeetingWindow:
    def test_review_three_days_before_deploy(self, monkeypatch):
        import config
        import teams_meeting_content as tmc

        monkeypatch.setattr(
            config,
            "TEAMS_SCHEDULE",
            {
                "review_duration_minutes": 45,
                "templates": {
                    "review": {"default_day_offset": -3, "default_time": "15:00"},
                },
            },
        )
        deploy = date(2026, 3, 30)
        start, end = tmc.default_meeting_window("review", deploy_date=deploy)
        assert start.date() == date(2026, 3, 27)
        assert start.time() == time(15, 0)
        assert (end - start).total_seconds() == 45 * 60

    def test_deployment_uses_deploy_window(self):
        import teams_meeting_content as tmc

        ds = datetime(2026, 3, 30, 10, 0)
        de = datetime(2026, 3, 30, 13, 0)
        start, end = tmc.default_meeting_window(
            "deployment", deploy_start=ds, deploy_end=de
        )
        assert start == ds
        assert end == de


class TestUpdateMeeting:
    def test_update_dry_run(self, monkeypatch):
        import teams_schedule as ts

        cfg = ts.TeamsScheduleConfig(enabled=True, organizer_upn="org@example.com")
        draft = ts.build_meeting_draft(
            cfg,
            kind="review",
            subject="Updated",
            start=datetime(2026, 3, 27, 15, 0),
            version="2026.3.09.30",
        )
        result = ts.update_meeting(cfg, "evt-123", draft, dry_run=True)
        assert result.ok is True
        assert result.dry_run is True
        assert result.updated is True
        assert result.event_id == "evt-123"
        assert result.graph_payload is not None


class TestSlackTemplate:
    def test_template_renders_format(self, monkeypatch):
        import slack_announce as sa
        from datetime import date

        draft = sa.SlackAnnounceDraft(
            ticket_key="TCKT-1",
            ticket_summary="Deploy v2026.3.09.30",
            ticket_url="https://jira/browse/TCKT-1",
            version="v2026.3.09.30",
            deploy_date=date(2026, 3, 30),
            sharepoint_url="https://sp/doc.docx",
            sharepoint_label="Release Notes 2026.3.09.30.docx",
            ticket_count=5,
        )
        ch = sa.default_channels()[0]
        text = sa.build_announce_text(draft, ch, for_preview=True)
        # New short format: date, SharePoint label, ticket key, CC
        assert "Monday, March 30, 2026" in text
        assert "Release Notes 2026.3.09.30.docx" in text
        assert "Deploy v2026.3.09.30" in text
        assert "CC:" in text
        assert "Our upcoming deployment is scheduled for" in text
        assert "Deployment notes and the deployment ticket" in text


class TestGateTemplate:
    def test_pre_review_template(self):
        import release_gates as rg

        ticket = rg.GateTicket(
            key="PIC-1",
            summary="Fix bug",
            status="Open",
            assignee_name="Alice",
            assignee_email="alice@x.com",
            project="PIC",
            reason="not ready",
        )
        msg = rg.build_pre_review_message(ticket, version_name="2026.3.09.30")
        assert "PIC-1" in msg
        assert "Alice" in msg
        assert "2026.3.09.30" in msg


class TestWorkspaceProfile:
    def test_summarize_active_workspace(self):
        import workspace_profile as wp

        profile = wp.summarize_active_workspace()
        assert "workspace_id" in profile
        assert "integrations" in profile
        assert "teams_schedule" in profile["integrations"]
