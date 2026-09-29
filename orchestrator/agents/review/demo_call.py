"""Two-person demo call via Playwright → Outlook web calendar."""

from __future__ import annotations

from typing import Any

from daily_review_agent.alerting import alert_organizer_schedule_failure
from daily_review_agent.config_loader import load_agent_config, readiness_report
from daily_review_agent.preflight import live_schedule_ok, run_preflight
from daily_review_agent.schedule import demo_window, schedule_review_meeting
from teams_schedule import TeamsAttendee


def run_demo_call(*, dry_run: bool = True, minutes_from_now: int = 30, force: bool = False) -> dict[str, Any]:
    cfg = load_agent_config()
    readiness = readiness_report(cfg)

    preflight = run_preflight(cfg, dry_run=dry_run, force=force)
    if not dry_run and not preflight.get("ready"):
        return {
            "status": "preflight_failed",
            "preflight": preflight,
            "readiness": readiness,
        }

    attendees = [{"email": a.email, "name": a.name} for a in cfg.demo_attendees if a.email]
    if len(attendees) < 2:
        return {
            "status": "needs_input",
            "message": (
                "Set MOHAN_DEMO_EMAIL in .env or fill demo.attendees in "
                "orchestrator/agents/review/agent.yaml (need 2 emails for demo)."
            ),
            "readiness": readiness,
            "demo_attendees": [{"name": a.name, "email": a.email or "(missing)"} for a in cfg.demo_attendees],
        }

    start, end = demo_window(cfg, minutes_from_now=minutes_from_now)
    body = (
        "Daily Review Agent — demo call\n\n"
        "Smoke test for Playwright Outlook calendar scheduling. Safe to ignore / delete."
    )
    people = [TeamsAttendee(email=a["email"], name=a.get("name") or "", type="required") for a in attendees]
    schedule = schedule_review_meeting(
        cfg,
        subject=cfg.demo_subject,
        body_html=body.replace("\n", "<br>"),
        start=start,
        end=end,
        attendees=people,
        dry_run=dry_run,
    )

    schedule_ok = live_schedule_ok(schedule if isinstance(schedule, dict) else None, dry_run=dry_run)
    alert: dict[str, Any] = {"ok": True, "skipped": True}
    if not dry_run and not schedule_ok:
        error = str(schedule.get("error") or "missing join_url") if isinstance(schedule, dict) else "schedule failed"
        alert = alert_organizer_schedule_failure(
            cfg,
            error=error,
            subject=cfg.demo_subject,
            dry_run=False,
        )
        return {
            "status": "schedule_failed",
            "dry_run": dry_run,
            "preflight": preflight,
            "readiness": readiness,
            "meeting": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "attendees": attendees,
                "schedule": schedule,
            },
            "alert": alert,
        }

    return {
        "status": "ok",
        "dry_run": dry_run,
        "preflight": preflight,
        "readiness": readiness,
        "meeting": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "attendees": attendees,
            "schedule": schedule,
        },
    }
