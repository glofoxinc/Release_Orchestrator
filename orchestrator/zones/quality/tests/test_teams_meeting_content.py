"""Tests for rich Teams meeting body and attendee helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


def _sample_issue(key: str, summary: str, status: str, email: str, name: str) -> dict:
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": status},
            "assignee": {"displayName": name, "emailAddress": email},
        },
    }


class TestMeetingContent:
    def test_default_subject_substitutes_version(self, monkeypatch):
        import config
        import teams_meeting_content as tmc

        monkeypatch.setattr(
            config,
            "TEAMS_SCHEDULE",
            {"templates": {"review": {"subject": "Team X Review — {{version}}"}}},
        )
        assert tmc.default_subject("review", "2026.3.09.30") == "Team X Review — 2026.3.09.30"

    def test_default_meeting_window_review_offset(self, monkeypatch):
        import config
        import teams_meeting_content as tmc
        from datetime import date

        monkeypatch.setattr(
            config,
            "TEAMS_SCHEDULE",
            {
                "review_duration_minutes": 30,
                "templates": {"review": {"default_day_offset": -2, "default_time": "14:30"}},
            },
        )
        start, end = tmc.default_meeting_window("review", deploy_date=date(2026, 4, 10))
        assert start.date().isoformat() == "2026-04-08"
        assert start.strftime("%H:%M") == "14:30"

    def test_review_body_includes_tickets(self):
        import teams_meeting_content as tmc

        ctx = tmc.MeetingContext(
            version="2026.3.09.30",
            kind="review",
            base_url="https://jira.example.net",
            tickets=[
                _sample_issue("PIC-1", "Fix dashboard", "In Review", "a@x.com", "Alice"),
            ],
        )
        body = tmc.build_review_meeting_body(ctx)
        assert "PIC-1" in body
        assert "Fix dashboard" in body
        assert "In Review" in body
        assert "Alice" in body

    def test_deployment_body_includes_sharepoint_and_tckt(self):
        import teams_meeting_content as tmc

        ctx = tmc.MeetingContext(
            version="2026.3.09.30",
            kind="deployment",
            sharepoint_url="https://sharepoint.example/doc.docx",
            tckt_key="TCKT-99",
            deploy_window="Thu 10:00–13:00 IST",
            tickets=[
                _sample_issue("PIC-2", "Deploy item", "Done", "b@x.com", "Bob"),
            ],
        )
        body = tmc.build_deployment_meeting_body(ctx)
        assert "sharepoint.example" in body
        assert "TCKT-99" in body
        assert "PIC-2" in body
        assert "Pre-deploy checklist" in body

    def test_collect_assignee_attendees_dedupes(self):
        import teams_meeting_content as tmc

        tickets = [
            _sample_issue("PIC-1", "A", "Open", "same@x.com", "One"),
            _sample_issue("PIC-2", "B", "Open", "same@x.com", "One"),
            _sample_issue("PIC-3", "C", "Open", "other@x.com", "Two"),
        ]
        people = tmc.collect_assignee_attendees(tickets)
        emails = sorted(p.email for p in people)
        assert emails == ["other@x.com", "same@x.com"]

    def test_merge_attendees_required_wins(self):
        import teams_meeting_content as tmc
        from teams_schedule import TeamsAttendee

        merged = tmc.merge_attendees(
            [TeamsAttendee(email="a@x.com", type="optional")],
            [TeamsAttendee(email="a@x.com", type="required")],
        )
        assert len(merged) == 1
        assert merged[0].type == "required"
