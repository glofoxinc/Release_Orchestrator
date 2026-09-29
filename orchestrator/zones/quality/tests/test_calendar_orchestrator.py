"""Calendar orchestrator — fallback chain (mocked)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from daily_review_agent.calendar_orchestrator import resolve_backend_chain, schedule_with_fallback
from daily_review_agent.config_loader import AgentConfig


def test_resolve_auto_chain():
    cfg = AgentConfig(calendar_backend="auto", playwright_mcp_primary_enabled=True)
    chain = resolve_backend_chain(cfg)
    assert chain == ("playwright_mcp",)
    assert "outlook_com" not in chain


def test_playwright_alias_maps_to_playwright_outlook():
    cfg = AgentConfig(calendar_backend="auto", calendar_backends=["playwright", "teams_mcp"])
    chain = resolve_backend_chain(cfg)
    assert chain[0] == "playwright_outlook"


def test_playwright_mcp_in_chain():
    cfg = AgentConfig(calendar_backend="auto", calendar_backends=["playwright_mcp"])
    chain = resolve_backend_chain(cfg)
    assert chain == ("playwright_mcp",)


def test_embedded_fallback_appended_when_enabled():
    cfg = AgentConfig(
        calendar_backend="auto",
        calendar_backends=["playwright_mcp"],
        embedded_playwright_fallback_enabled=True,
    )
    chain = resolve_backend_chain(cfg)
    assert chain == ("playwright_mcp", "playwright_outlook")


def test_schedule_playwright_mcp_returns_handoff():
    cfg = AgentConfig(calendar_backends=["playwright_mcp"])
    start = datetime(2026, 9, 17, 11, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    end = datetime(2026, 9, 17, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    result = schedule_with_fallback(
        cfg,
        subject="Daily review",
        body_text="tickets",
        start=start,
        end=end,
        attendee_emails=[{"email": "a@abcfitness.com", "name": "A"}],
        dry_run=False,
    )
    assert result["ok"] is True
    assert result.get("handoff_required") is True
    assert result.get("backend") == "cursor_playwright_mcp"
    assert result.get("handoff", {}).get("delivery") == "cursor_playwright_mcp"


def test_outlook_without_join_url_not_verified(monkeypatch):
    cfg = AgentConfig(calendar_backends=["outlook_com"], calendar_accept_outlook_without_join_url=False)
    start = datetime(2026, 9, 17, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    end = datetime(2026, 9, 17, 20, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    monkeypatch.setattr(
        "daily_review_agent.outlook_calendar.schedule_meeting_via_outlook",
        lambda **k: {"ok": False, "event_id": "x", "backend": "outlook_com", "error": "no link"},
    )
    result = schedule_with_fallback(
        cfg,
        subject="Test",
        body_text="body",
        start=start,
        end=end,
        attendee_emails=[{"email": "a@x.com"}],
        dry_run=False,
    )
    assert result["ok"] is False


def test_schedule_dry_run():
    cfg = AgentConfig(calendar_backend="auto")
    start = datetime(2026, 9, 17, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    end = datetime(2026, 9, 17, 20, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    result = schedule_with_fallback(
        cfg,
        subject="Test",
        body_text="body",
        start=start,
        end=end,
        attendee_emails=[{"email": "a@x.com", "name": "A"}],
        dry_run=True,
    )
    assert result["ok"] is True
    assert result["dry_run"] is True


def test_fallback_to_browser_after_teams_mcp_fails(monkeypatch):
    cfg = AgentConfig(calendar_backends=["teams_mcp", "teams_browser"])
    start = datetime(2026, 9, 17, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    end = datetime(2026, 9, 17, 20, 10, tzinfo=ZoneInfo("Asia/Kolkata"))

    monkeypatch.setattr(
        "daily_review_agent.calendar_orchestrator._schedule_teams_mcp",
        lambda *a, **k: {"ok": False, "error": "no session"},
    )
    monkeypatch.setattr(
        "daily_review_agent.calendar_orchestrator._schedule_teams_browser",
        lambda *a, **k: {
            "ok": True,
            "backend": "teams_browser",
            "join_url": "https://teams.microsoft.com/l/meetup-join/test",
            "event_id": "evt1",
        },
    )

    result = schedule_with_fallback(
        cfg,
        subject="Test",
        body_text="body",
        start=start,
        end=end,
        attendee_emails=[{"email": "a@x.com"}],
        dry_run=False,
    )
    assert result["ok"] is True
    assert result["backend"] == "teams_browser"
    assert "teams.microsoft.com" in result["join_url"]


def test_playwright_outlook_sent_counts_as_verified(monkeypatch):
    cfg = AgentConfig(calendar_backends=["playwright_outlook"])
    start = datetime(2026, 9, 17, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    end = datetime(2026, 9, 17, 20, 10, tzinfo=ZoneInfo("Asia/Kolkata"))

    monkeypatch.setattr(
        "daily_review_agent.calendar_orchestrator._schedule_playwright_outlook",
        lambda *a, **k: {
            "ok": True,
            "sent": True,
            "backend": "playwright_outlook",
            "join_url": "",
            "subject": "Test",
        },
    )

    result = schedule_with_fallback(
        cfg,
        subject="Test",
        body_text="body",
        start=start,
        end=end,
        attendee_emails=[{"email": "a@x.com"}],
        dry_run=False,
    )
    assert result["ok"] is True
    assert result["backend"] == "playwright_outlook"


def test_batch_playwright_only_no_fallback_on_partial(monkeypatch):
    from daily_review_agent.batch_schedule import build_evening_slots, run_batch_schedule

    slots = build_evening_slots(date_str="2026-09-17", start_hhmm="20:00", count=2, duration_minutes=10)
    monkeypatch.setattr(
        "daily_review_agent.batch_schedule._run_batch_via_playwright",
        lambda **k: {
            "status": "partial",
            "scheduled": 1,
            "total": 2,
            "mode": "playwright_outlook",
            "verified": False,
        },
    )
    monkeypatch.setattr(
        "daily_review_agent.batch_schedule._run_batch_via_browser",
        lambda **k: {"status": "ok", "scheduled": 2, "total": 2, "mode": "batch_browser"},
    )
    result = run_batch_schedule(
        slots=slots,
        attendee_emails=["a@x.com"],
        playwright_only=True,
    )
    assert result["mode"] == "playwright_outlook"
    assert result["scheduled"] == 1
    assert "error" in result


def test_fallback_to_teams_browser_after_playwright_fails(monkeypatch):
    cfg = AgentConfig(calendar_backends=["playwright_outlook", "teams_browser"])
    start = datetime(2026, 9, 17, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    end = datetime(2026, 9, 17, 20, 10, tzinfo=ZoneInfo("Asia/Kolkata"))

    monkeypatch.setattr(
        "daily_review_agent.calendar_orchestrator._schedule_playwright_outlook",
        lambda *a, **k: {"ok": False, "error": "login timeout"},
    )
    monkeypatch.setattr(
        "daily_review_agent.calendar_orchestrator._schedule_teams_browser",
        lambda *a, **k: {
            "ok": True,
            "backend": "teams_browser",
            "join_url": "https://teams.microsoft.com/l/meetup-join/fallback",
        },
    )

    result = schedule_with_fallback(
        cfg,
        subject="Test",
        body_text="body",
        start=start,
        end=end,
        attendee_emails=[{"email": "a@x.com"}],
        dry_run=False,
    )
    assert result["ok"] is True
    assert result["backend"] == "teams_browser"
