"""Ad-hoc meeting scheduling via Playwright → Outlook web."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from daily_review_agent.config_loader import load_agent_config, readiness_report
from daily_review_agent.calendar_orchestrator import schedule_with_fallback
from daily_review_agent.preflight import live_schedule_ok, run_preflight


def _parse_iso(raw: str, tz_name: str) -> datetime:
    text = (raw or "").strip()
    if not text:
        raise ValueError("start_iso and end_iso are required")
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt


def run_ad_hoc_schedule(
    *,
    subject: str,
    start_iso: str,
    end_iso: str,
    attendee_emails: list[str],
    dry_run: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Schedule an arbitrary meeting via Playwright Outlook web."""
    cfg = load_agent_config()
    readiness = readiness_report(cfg)

    preflight = run_preflight(cfg, dry_run=dry_run, force=force)
    if not dry_run and not preflight.get("ready"):
        return {
            "status": "preflight_failed",
            "preflight": preflight,
            "readiness": readiness,
        }

    people = [{"email": e.strip(), "name": ""} for e in attendee_emails if (e or "").strip()]
    if len(people) < 1:
        return {
            "status": "needs_input",
            "message": "Provide at least one attendee email",
            "readiness": readiness,
        }

    try:
        start = _parse_iso(start_iso, cfg.timezone)
        end = _parse_iso(end_iso, cfg.timezone)
    except ValueError as exc:
        return {"status": "error", "message": str(exc), "readiness": readiness}

    if end <= start:
        return {"status": "error", "message": "end_iso must be after start_iso", "readiness": readiness}

    body = f"Ad-hoc meeting scheduled by Daily Review Agent.\n{subject}"
    preview = {
        "backend": "playwright_outlook",
        "subject": subject,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "attendees": people,
    }

    if dry_run:
        return {
            "status": "ok",
            "dry_run": True,
            "preview": preview,
            "readiness": readiness,
            "preflight": preflight,
        }

    schedule = schedule_with_fallback(
        cfg,
        subject=subject,
        body_text=body,
        start=start,
        end=end,
        attendee_emails=people,
        dry_run=False,
    )

    if not live_schedule_ok(schedule, dry_run=False):
        from daily_review_agent.alerting import alert_organizer_schedule_failure

        alert = alert_organizer_schedule_failure(
            cfg,
            error=str(schedule.get("error") or "missing join_url"),
            subject=subject,
            dry_run=False,
        )
        return {
            "status": "schedule_failed",
            "dry_run": False,
            "meeting": {"schedule": schedule, "preview": preview},
            "alert": alert,
            "readiness": readiness,
        }

    return {
        "status": "ok",
        "dry_run": False,
        "meeting": {"schedule": schedule, "preview": preview},
        "readiness": readiness,
    }
