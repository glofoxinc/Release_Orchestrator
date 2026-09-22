"""Fail-closed scheduling, preflight, alerting, ad-hoc — mocked (no live APIs)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from daily_review_agent.config_loader import AgentConfig, AttendeeSpec, AlertingConfig, load_agent_config
from daily_review_agent.graph_calendar import _extract_join_url
from daily_review_agent.preflight import live_schedule_ok, run_preflight


def test_live_schedule_ok_dry_run_without_join():
    assert live_schedule_ok({"ok": True, "join_url": ""}, dry_run=True) is True


def test_live_schedule_ok_requires_join_url_or_playwright_sent():
    assert live_schedule_ok({"ok": True, "join_url": ""}, dry_run=False) is False
    assert live_schedule_ok({"ok": True, "join_url": "https://teams.microsoft.com/j/abc"}, dry_run=False) is True
    assert live_schedule_ok(
        {"ok": True, "backend": "playwright_outlook", "sent": True, "join_url": ""},
        dry_run=False,
    ) is True
    assert live_schedule_ok({"ok": False, "error": "x"}, dry_run=False) is False


def test_extract_join_url_from_online_meeting():
    body = {"onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/abc"}}
    assert _extract_join_url(body) == "https://teams.microsoft.com/l/meetup-join/abc"


def test_extract_join_url_fallback_online_meeting_url():
    body = {"onlineMeetingUrl": "https://teams.microsoft.com/l/meetup-join/xyz"}
    assert _extract_join_url(body) == "https://teams.microsoft.com/l/meetup-join/xyz"


def test_preflight_dry_run_only_needs_jira(monkeypatch):
    cfg = load_agent_config()
    monkeypatch.setattr(
        "daily_review_agent.preflight.readiness_report",
        lambda c: {
            "hard_blockers_for_jira_fetch": [],
            "hard_blockers_for_live_calendar": ["need graph login"],
            "hard_blockers_for_live_teams": [],
            "teams_mcp": {"authenticated": False},
        },
    )
    report = run_preflight(cfg, dry_run=True, force=False)
    assert report["ready"] is True
    assert report["mode"] == "dry_run"


def test_preflight_live_blocks_calendar(monkeypatch):
    cfg = load_agent_config()
    cfg.enabled = True
    cfg.calendar_backend = "auto"
    monkeypatch.setattr(
        "daily_review_agent.calendar_orchestrator.orchestrator_readiness",
        lambda c: {"can_schedule_any": False, "blockers": ["No calendar backend available"]},
    )
    monkeypatch.setattr(
        "daily_review_agent.preflight.readiness_report",
        lambda c: {
            "hard_blockers_for_jira_fetch": [],
            "hard_blockers_for_live_calendar": [],
            "hard_blockers_for_live_teams": [],
            "teams_mcp": {"authenticated": True},
        },
    )
    monkeypatch.setattr("daily_review_agent.preflight.schedule_is_active", lambda **kw: True)
    report = run_preflight(cfg, dry_run=False, force=True)
    assert report["ready"] is False
    assert "No calendar backend" in report["blockers"][0]


def test_live_run_fails_closed_when_schedule_fails(monkeypatch):
    from daily_review_agent import runner

    cfg = load_agent_config()
    cfg.enabled = True
    cfg.alerting = AlertingConfig(on_schedule_failure=True)

    monkeypatch.setattr("daily_review_agent.runner.load_agent_config", lambda: cfg)
    monkeypatch.setattr(
        "daily_review_agent.runner.run_preflight",
        lambda *a, **k: {"ready": True, "blockers": [], "fix_commands": []},
    )
    monkeypatch.setattr("daily_review_agent.runner.schedule_is_active", lambda **kw: True)
    monkeypatch.setattr(
        "daily_review_agent.runner.resolve_review_issues",
        lambda cfg: {"status": "ok", "total": 1, "errors": [], "by_project": {}, "issues": []},
    )
    monkeypatch.setattr(
        "daily_review_agent.runner.schedule_review_meeting",
        lambda *a, **k: {"ok": False, "error": "Graph HTTP 401"},
    )
    post_mock = MagicMock(return_value={"ok": True})
    monkeypatch.setattr("daily_review_agent.runner.post_summary_via_mcp", post_mock)
    alert_mock = MagicMock(return_value={"ok": True, "dry_run": False})
    monkeypatch.setattr("daily_review_agent.runner.alert_organizer_schedule_failure", alert_mock)

    result = runner.run_daily_agent(dry_run=False, force=True)
    assert result["status"] in {"schedule_failed", "schedule_failed_handoff_available"}
    if result["status"] == "schedule_failed_handoff_available":
        assert result.get("fallback_handoff")
    post_mock.assert_not_called()
    alert_mock.assert_called_once()


def test_live_run_posts_summary_when_schedule_ok(monkeypatch):
    from daily_review_agent import runner

    cfg = load_agent_config()
    cfg.enabled = True

    monkeypatch.setattr("daily_review_agent.runner.load_agent_config", lambda: cfg)
    monkeypatch.setattr(
        "daily_review_agent.runner.run_preflight",
        lambda *a, **k: {"ready": True, "blockers": [], "fix_commands": []},
    )
    monkeypatch.setattr("daily_review_agent.runner.schedule_is_active", lambda **kw: True)
    monkeypatch.setattr(
        "daily_review_agent.runner.resolve_review_issues",
        lambda cfg: {"status": "ok", "total": 0, "errors": [], "by_project": {}, "issues": []},
    )
    monkeypatch.setattr(
        "daily_review_agent.runner.schedule_review_meeting",
        lambda *a, **k: {"ok": True, "join_url": "https://teams.microsoft.com/j/ok"},
    )
    post_mock = MagicMock(return_value={"ok": True})
    monkeypatch.setattr("daily_review_agent.runner.post_summary_via_mcp", post_mock)

    result = runner.run_daily_agent(dry_run=False, force=True)
    assert result["status"] == "ok"
    post_mock.assert_called_once()
    call_text = post_mock.call_args.kwargs.get("text") or post_mock.call_args[1].get("text", "")
    assert "teams.microsoft.com" in call_text


def test_outlook_com_fails_without_join_url(monkeypatch):
    import sys
    import types

    from daily_review_agent import outlook_calendar

    class FakeAppt:
        EntryID = "e1"

        def __init__(self):
            self.Recipients = self._Recipients()

        class _Recipients:
            def Add(self, _):
                return MagicMock()

            def ResolveAll(self):
                return None

        Subject = "Test"
        Body = "body"
        Start = end = Location = ""
        MeetingStatus = 1

        def Save(self):
            return None

        def Send(self):
            return None

        @property
        def MeetingWorkspaceURL(self):
            return ""

        IsOnlineMeeting = True
        OnlineMeetingProvider = 1

    class FakeGencache:
        @staticmethod
        def EnsureDispatch(_):
            return types.SimpleNamespace(CreateItem=lambda _: FakeAppt())

    fake_client = types.SimpleNamespace(gencache=FakeGencache())
    fake_win32com = types.SimpleNamespace(client=fake_client)
    monkeypatch.setitem(sys.modules, "win32com", fake_win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_client)

    result = outlook_calendar.schedule_meeting_via_outlook(
        subject="Test",
        body_text="body",
        start=datetime(2026, 9, 17, 17, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        end=datetime(2026, 9, 17, 17, 30, tzinfo=ZoneInfo("Asia/Kolkata")),
        attendee_emails=[{"email": "a@b.com", "name": "A"}],
    )
    assert result["ok"] is False
    assert "local_outlook_no_teams_link" in result["error"]


def test_alert_format_message():
    from daily_review_agent.alerting import format_schedule_failure_message

    msg = format_schedule_failure_message(run_at="2026-09-17T18:00:00", error="missing join_url", subject="Review")
    assert "FAILED" in msg
    assert "outlook-login" in msg
    assert "Review" in msg


def test_ad_hoc_dry_run(monkeypatch):
    from daily_review_agent.ad_hoc import run_ad_hoc_schedule

    monkeypatch.setattr(
        "daily_review_agent.ad_hoc.run_preflight",
        lambda *a, **k: {"ready": True, "blockers": []},
    )
    result = run_ad_hoc_schedule(
        subject="Demo",
        start_iso="2026-09-17T17:30:00+05:30",
        end_iso="2026-09-17T18:00:00+05:30",
        attendee_emails=["MohanKrishna.Sai@abcfitness.com"],
        dry_run=True,
    )
    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert result["preview"]["subject"] == "Demo"


def test_ad_hoc_preflight_failed(monkeypatch):
    from daily_review_agent.ad_hoc import run_ad_hoc_schedule

    monkeypatch.setattr(
        "daily_review_agent.ad_hoc.run_preflight",
        lambda *a, **k: {"ready": False, "blockers": ["no graph"]},
    )
    result = run_ad_hoc_schedule(
        subject="Demo",
        start_iso="2026-09-17T17:30:00+05:30",
        end_iso="2026-09-17T18:00:00+05:30",
        attendee_emails=["a@b.com"],
        dry_run=False,
    )
    assert result["status"] == "preflight_failed"


def test_alerting_config_loaded():
    cfg = load_agent_config()
    assert cfg.alerting.on_schedule_failure is True
    assert cfg.alerting.channel == "organizer_dm"


def test_graph_schedule_fails_without_join_url(monkeypatch):
    from daily_review_agent import graph_calendar

    monkeypatch.setattr("daily_review_agent.graph_calendar.acquire_graph_token", lambda **k: "token")
    monkeypatch.setattr(
        "teams_schedule.build_meeting_draft",
        lambda *a, **k: MagicMock(),
    )
    monkeypatch.setattr(
        "teams_schedule.build_graph_event_payload",
        lambda draft: {"subject": "x"},
    )
    monkeypatch.setattr(
        "teams_schedule.load_schedule_config",
        lambda section: MagicMock(),
    )

    class FakeResp:
        status_code = 201

        @staticmethod
        def json():
            return {"id": "evt-1", "onlineMeeting": {}}

    monkeypatch.setattr("daily_review_agent.graph_calendar.requests.post", lambda *a, **k: FakeResp())
    monkeypatch.setattr("daily_review_agent.graph_calendar._verify_event_join_url", lambda *a, **k: "")

    result = graph_calendar.schedule_meeting_via_graph(
        subject="T",
        body_text="b",
        start=datetime(2026, 9, 17, 17, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        end=datetime(2026, 9, 17, 17, 30, tzinfo=ZoneInfo("Asia/Kolkata")),
        attendee_emails=[{"email": "a@b.com"}],
        interactive_auth=False,
    )
    assert result["ok"] is False
    assert "join URL missing" in result["error"]


def test_demo_call_schedule_failed(monkeypatch):
    from daily_review_agent.demo_call import run_demo_call

    cfg = load_agent_config()
    cfg.demo_attendees = [
        AttendeeSpec(email="a@a.com", name="A"),
        AttendeeSpec(email="b@b.com", name="B"),
    ]
    monkeypatch.setattr("daily_review_agent.demo_call.load_agent_config", lambda: cfg)
    monkeypatch.setattr(
        "daily_review_agent.demo_call.run_preflight",
        lambda *a, **k: {"ready": True},
    )
    monkeypatch.setattr(
        "daily_review_agent.demo_call.schedule_review_meeting",
        lambda *a, **k: {"ok": False, "error": "no token"},
    )
    alert_mock = MagicMock(return_value={"ok": True})
    monkeypatch.setattr("daily_review_agent.demo_call.alert_organizer_schedule_failure", alert_mock)

    result = run_demo_call(dry_run=False, force=True)
    assert result["status"] == "schedule_failed"
    alert_mock.assert_called_once()
