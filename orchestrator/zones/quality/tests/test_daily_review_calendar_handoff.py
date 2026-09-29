"""Tests for Daily Review Playwright MCP calendar fallback handoff."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from daily_review_agent.alerting import format_schedule_failure_message
from daily_review_agent.calendar_playwright_handoff import (
    build_daily_review_calendar_handoff,
    calendar_day_url,
    handoff_from_run_context,
)
from release_mcp import guided


def test_calendar_day_url_from_iso():
    url = calendar_day_url("2026-09-22T11:30:00+05:30")
    assert url.endswith("/2026-09-22")


def test_build_handoff_shape():
    handoff = build_daily_review_calendar_handoff(
        subject="Glofox Customize BI — Daily Ticket Review — 2026-09-22",
        start_iso="2026-09-22T11:30:00+05:30",
        end_iso="2026-09-22T12:00:00+05:30",
        attendees=[
            {"email": "a@abcfitness.com", "name": "A"},
            {"email": "b@abcfitness.com", "name": "B"},
        ],
    )
    assert handoff["ok"] is True
    assert handoff["delivery"] == "cursor_playwright_mcp"
    assert handoff["mcp"] == "playwright"
    assert len(handoff["steps"]) >= 6
    assert handoff["meeting"]["attendees"] == ["a@abcfitness.com", "b@abcfitness.com"]
    assert "calendar done" in handoff["completion"]["user_phrases"]


def test_handoff_from_run_context():
    tz = ZoneInfo("Asia/Kolkata")
    start = datetime(2026, 9, 22, 11, 30, tzinfo=tz)
    end = datetime(2026, 9, 22, 12, 0, tzinfo=tz)
    handoff = handoff_from_run_context(
        subject="Test meeting",
        start=start,
        end=end,
        attendees=[{"email": "x@abcfitness.com"}],
        body_text="ticket summary",
    )
    assert handoff["ok"] is True
    assert handoff["meeting"]["subject"] == "Test meeting"


def test_alert_message_mentions_fallback():
    msg = format_schedule_failure_message(
        run_at="2026-09-21T18:00:00+05:30",
        error="playwright timeout",
        subject="Daily review",
        fallback_phrase="daily review calendar playwright",
    )
    assert "daily review calendar playwright" in msg
    assert "daily_review_calendar_playwright_handoff" in msg


def test_guided_routes_calendar_playwright_phrase():
    plan = guided.interpret_message("daily review calendar playwright")
    assert plan.get("action") == "daily_review_calendar_handoff"
    assert plan.get("intent") == "daily_review_calendar_playwright"


def test_guided_routes_schedule_calendar_playwright_phrase():
    plan = guided.interpret_message("schedule calendar playwright")
    assert plan.get("action") == "daily_review_calendar_handoff"


def test_guided_routes_schedule_review_call_phrase():
    plan = guided.interpret_message("schedule review call")
    assert plan.get("action") == "daily_review_calendar_handoff"
    assert plan.get("intent") == "daily_review_calendar_playwright"


def test_guided_routes_review_call_schedule_phrase():
    plan = guided.interpret_message("review call schedule")
    assert plan.get("action") == "daily_review_calendar_handoff"


def test_runner_includes_fallback_handoff_when_schedule_fails(monkeypatch):
    from daily_review_agent import runner
    from daily_review_agent.config_loader import load_agent_config

    cfg = load_agent_config()
    cfg.enabled = True
    cfg.playwright_mcp_fallback_enabled = True

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
        lambda *a, **k: {"ok": False, "error": "timeout"},
    )
    monkeypatch.setattr(
        "daily_review_agent.runner.alert_organizer_schedule_failure",
        lambda *a, **k: {"ok": True, "dry_run": False},
    )

    result = runner.run_daily_agent(dry_run=False, force=True)
    assert result["status"] == "schedule_failed_handoff_available"
    assert result.get("fallback_handoff", {}).get("delivery") == "cursor_playwright_mcp"


def test_readiness_includes_playwright_fallback_warning():
    from daily_review_agent.config_loader import load_agent_config, readiness_report

    report = readiness_report(load_agent_config())
    assert "playwright_mcp_fallback_enabled" in report
    assert isinstance(report.get("playwright_mcp_fallback_warnings"), list)
