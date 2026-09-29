"""Daily Review Agent — unit tests (no live Jira / Graph)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from daily_review_agent.config_loader import AttendeeSpec, AgentConfig, load_agent_config, readiness_report
from daily_review_agent.report import format_html_report, format_text_report
from daily_review_agent.schedule import (
    collect_meeting_attendees,
    demo_window,
    meeting_window,
    next_business_day,
)


def test_load_agent_config_defaults():
    cfg = load_agent_config()
    assert cfg.jira_team_id == "317996a7-118a-4cf3-a3c6-04163516ed32"
    assert "PIC" in cfg.projects and "AN" in cfg.projects
    assert cfg.enabled is False
    assert len(cfg.required_attendees) >= 2
    assert cfg.ticket_scope is not None
    assert cfg.ticket_scope.include_outside_squad_assignees is False


def test_next_business_day_skips_weekend():
    friday = date(2026, 9, 11)  # Thursday in user's TZ context — check: Sep 11 2026 is Friday
    assert friday.weekday() == 4
    nxt = next_business_day(friday, skip_weekends=True)
    assert nxt.weekday() < 5
    assert nxt == date(2026, 9, 14)  # Monday


def test_meeting_window_ist():
    cfg = load_agent_config()
    run_at = datetime(2026, 9, 10, 18, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    start, end = meeting_window(cfg, run_at=run_at)
    assert start.hour == 11 and start.minute == 30
    assert end.hour == 12 and end.minute == 0
    assert start.date() > run_at.date()


def test_collect_meeting_attendees_dedupes_assignee(monkeypatch):
    """Legacy path when crew is not in .env — required attendee deduped with assignee."""
    monkeypatch.setattr(
        "daily_review_agent.meeting_attendees.load_crew_from_env",
        lambda: None,
    )
    cfg = AgentConfig(
        required_attendees=[AttendeeSpec(email="a@x.com", name="A")],
        assignee_invite_type="required",
    )
    issues = [
        {
            "fields": {
                "assignee": {"displayName": "Bob", "emailAddress": "a@x.com"},
            }
        },
        {
            "fields": {
                "assignee": {"displayName": "Bharathi Dev", "emailAddress": "c@x.com"},
            }
        },
    ]
    attendees = collect_meeting_attendees(cfg, issues)
    emails = [a.email.lower() for a in attendees]
    assert emails.count("a@x.com") == 1
    assert "c@x.com" in emails


def test_format_reports():
    rows = [
        {
            "key": "PIC-1",
            "status": "Review",
            "assignee": "Dev",
            "summary": "Fix thing",
            "link": "https://jira/browse/PIC-1",
        }
    ]
    text = format_text_report(rows, team_name="Glofox", by_project={"PIC": {"statuses": ["Review"], "count": 1}})
    assert "PIC-1" in text
    html = format_html_report(rows, team_name="Glofox", meeting_date="2026-09-11")
    assert "PIC-1" in html and "<table" in html


def test_readiness_report_structure():
    cfg = load_agent_config()
    report = readiness_report(cfg)
    assert "agent_enabled" in report
    assert "PIC" in report.get("projects", [])


def test_runner_disabled_without_force(monkeypatch):
    from daily_review_agent import runner

    cfg = load_agent_config()
    assert cfg.enabled is False
    result = runner.run_daily_agent(dry_run=True, force=False)
    assert result["status"] == "disabled"


def test_runner_dry_run_with_force(monkeypatch):
    from daily_review_agent import runner

    monkeypatch.setattr(
        "daily_review_agent.runner.resolve_review_issues",
        lambda cfg: {
            "status": "ok",
            "total": 1,
            "errors": [],
            "by_project": {"PIC": {"statuses": ["Review"], "count": 1}},
            "issues": [
                {
                    "key": "PIC-99",
                    "fields": {
                        "summary": "Test",
                        "status": {"name": "Review"},
                        "assignee": None,
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        "daily_review_agent.schedule.schedule_review_meeting",
        lambda *a, **k: {"ok": True, "dry_run": True, "join_url": None},
    )
    monkeypatch.setattr(
        "daily_review_agent.runner.run_slack_delivery",
        lambda *a, **k: {"ok": True, "skipped": True},
    )
    monkeypatch.setattr(
        "daily_review_agent.runner.run_preflight",
        lambda *a, **k: {"ready": True, "blockers": [], "fix_commands": []},
    )
    monkeypatch.setattr(
        "daily_review_agent.runner.post_summary_via_mcp",
        lambda *a, **k: {"ok": True, "dry_run": True},
    )
    result = runner.run_daily_agent(dry_run=True, force=True)
    assert result["status"] == "ok"
    assert result["fetch"]["total"] == 1


def test_demo_call_needs_mohan_email(monkeypatch):
    from daily_review_agent.demo_call import run_demo_call

    cfg = load_agent_config()
    cfg.demo_attendees = [AttendeeSpec(email="lakshmi@abc.com", name="Lakshmi")]
    monkeypatch.setattr("daily_review_agent.demo_call.load_agent_config", lambda: cfg)
    result = run_demo_call(dry_run=True)
    assert result["status"] == "needs_input"


def test_demo_window():
    cfg = load_agent_config()
    start, end = demo_window(cfg, minutes_from_now=30)
    assert end > start


def test_slack_config_loaded():
    cfg = load_agent_config()
    assert cfg.slack is not None
    assert cfg.slack.channel_name == "insights-customize-squad"
    assert cfg.slack.channel_id == "C08HB93PEVD"


def test_slack_message_format():
    from daily_review_agent.slack_notify import build_huddle_url, format_slack_review_message
    from daily_review_agent.schedule import meeting_window

    cfg = load_agent_config()
    start, end = meeting_window(cfg)
    text = format_slack_review_message(
        text_report="PIC-1 | Review | Dev | Test",
        meeting_start=start,
        meeting_end=end,
        teams_join_url="https://teams.example/join",
        huddle_url=build_huddle_url(team_id="T123", channel_id="C456"),
        include_huddle=True,
        mentions="<@U1>",
    )
    assert "Daily ticket review" in text
    assert "teams.example" in text
    assert "app.slack.com/huddle/T123/C456" in text


def test_review_filter_comment_match():
    from daily_review_agent.review_filter import ReviewFilterConfig, comment_indicates_review_done

    hit = comment_indicates_review_done("QA review done — moving to deploy", ["review done"])
    assert hit == "review done"
    assert comment_indicates_review_done("still in progress", ["review done"]) is None


def test_review_filter_skips_issue(monkeypatch):
    from daily_review_agent.review_filter import ReviewFilterConfig, filter_already_reviewed

    monkeypatch.setattr(
        "daily_review_agent.review_filter.issue_has_review_done_comment",
        lambda key, cfg: "reviewed" if key == "PIC-1" else None,
    )
    issues = [{"key": "PIC-1"}, {"key": "PIC-2"}]
    kept, skipped = filter_already_reviewed(issues, ReviewFilterConfig())
    assert len(kept) == 1 and kept[0]["key"] == "PIC-2"
    assert skipped[0]["key"] == "PIC-1"


def test_meeting_location_config():
    cfg = load_agent_config()
    assert cfg.meeting_location == "Cross Fit"


def test_onboarding_report_structure():
    from daily_review_agent.onboarding import run_onboarding

    report = run_onboarding()
    assert "steps" in report
    assert "ready_for_dry_run" in report
    assert any(s["name"] == "Jira credentials" for s in report["steps"])


def test_graph_calendar_ready_without_cache():
    from daily_review_agent.graph_calendar import graph_calendar_ready

    status = graph_calendar_ready()
    assert "blockers" in status
    assert "can_schedule" in status


def test_calendar_backend_default_auto():
    cfg = load_agent_config()
    assert cfg.calendar_backend == "auto"
    assert cfg.calendar_backends == ["playwright_mcp"]
    assert cfg.playwright_mcp_primary_enabled is True
    assert "outlook_com" not in cfg.calendar_backends
    assert "teams_browser" not in cfg.calendar_backends


def test_slack_dry_run_delivery():
    from daily_review_agent.slack_notify import SlackDeliveryConfig, run_slack_delivery

    cfg = SlackDeliveryConfig(enabled=True, channel_name="test-channel", channel_id="C1")
    start, end = meeting_window(load_agent_config())
    result = run_slack_delivery(
        cfg,
        text_report="ticket list",
        meeting_start=start,
        meeting_end=end,
        dry_run=True,
    )
    assert result.get("ok") is True
    assert result["post"]["dry_run"] is True
