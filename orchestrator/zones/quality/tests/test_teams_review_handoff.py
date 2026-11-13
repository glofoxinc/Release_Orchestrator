"""Review call Playwright handoff — fail-closed attendees and step shape."""

from __future__ import annotations

from daily_review_agent.calendar_playwright_handoff import (
    HANDOFF_VERSION,
    build_daily_review_calendar_handoff,
)
from release_mcp import teams_ops


def test_review_handoff_requires_attendees():
    out = teams_ops.teams_playwright_handoff(
        kind="review",
        start="2026-11-13T11:30:00+05:30",
        end="2026-11-13T12:00:00+05:30",
    )
    assert out["ok"] is False
    assert "attendees" in out["error"].lower()
    assert out.get("hint_tool") == "review_call_prepare"


def test_review_handoff_pre_send_gate():
    attendees = [
        {"email": "a@abcfitness.com", "type": "required"},
        {"email": "b@abcfitness.com", "type": "optional"},
    ]
    out = teams_ops.teams_playwright_handoff(
        kind="review",
        start="2026-11-13T11:30:00+05:30",
        end="2026-11-13T12:00:00+05:30",
        subject="Review call 11/13/2026",
        attendees=attendees,
        body="AN-5672",
    )
    assert out["ok"] is True
    gate = out["pre_send_gate"]
    assert gate["required_count"] == 1
    assert gate["optional_count"] == 1
    assert gate["start_date"] == "2026-11-13"
    assert out["handoff_version"] == HANDOFF_VERSION


def test_handoff_optional_uses_optional_field_in_steps():
    handoff = build_daily_review_calendar_handoff(
        subject="Review call 11/13/2026",
        start_iso="2026-11-13T11:30:00+05:30",
        end_iso="2026-11-13T12:00:00+05:30",
        attendees=[
            {"email": "req@abcfitness.com", "type": "required"},
            {"email": "opt@abcfitness.com", "type": "optional"},
        ],
        body_text="ticket body",
    )
    codes = [
        s.get("arguments", {}).get("code", "")
        for s in handoff["steps"]
        if s.get("mcp_tool") == "browser_run_code_unsafe"
    ]
    optional_steps = [c for c in codes if "Invite optional attendees" in c]
    assert optional_steps, "expected optional attendee step"
    assert not any("opt@abcfitness.com" in c and "Invite required attendees" in c for c in codes)
    assert any("Start date" in (s.get("title") or "") for s in handoff["steps"])
    assert any("agenda" in (s.get("title") or "").lower() for s in handoff["steps"])
    assert handoff["meeting"]["start_date"] == "11/13/2026"


def test_teams_schedule_status_includes_handoff_meta():
    status = teams_ops.teams_schedule_status()
    meta = status.get("playwright_handoff_meta") or {}
    assert meta.get("handoff_version") == HANDOFF_VERSION
    assert meta.get("features", {}).get("optional_row") is True
