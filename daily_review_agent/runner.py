"""Daily Review Agent — 6 PM fetch + schedule next-day 11:30 Teams review."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from daily_review_agent.alerting import alert_organizer_schedule_failure
from daily_review_agent.config_loader import AgentConfig, load_agent_config, readiness_report
from daily_review_agent.preflight import live_schedule_ok, run_preflight
from daily_review_agent.report import format_html_report, format_text_report
from daily_review_agent.meeting_attendees import attendee_policy_summary
from daily_review_agent.schedule import collect_meeting_attendees, meeting_window, schedule_review_meeting
from daily_review_agent.schedule_registry import schedule_is_active
from daily_review_agent.slack_notify import run_slack_delivery
from daily_review_agent.teams_delivery import post_summary_via_mcp
from daily_review_agent.ticket_pipeline import resolve_review_issues
from daily_review_agent.ticket_fetch import ticket_rows

logger = logging.getLogger(__name__)
_STATE_PATH = Path(__file__).resolve().parent / ".state" / "last_run.json"


def _save_state(payload: dict[str, Any]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _append_join_link(text: str, join_url: str) -> str:
    url = (join_url or "").strip()
    if not url:
        return text
    return f"{text.rstrip()}\n\nTeams join: {url}"


def run_daily_agent(*, dry_run: bool = True, force: bool = False) -> dict[str, Any]:
    """Fetch tickets and schedule review meeting (single 6 PM job)."""
    cfg = load_agent_config()
    readiness = readiness_report(cfg)
    run_at = datetime.now(ZoneInfo(cfg.timezone)).isoformat()

    preflight = run_preflight(cfg, dry_run=dry_run, force=force)
    if not dry_run and not preflight.get("ready"):
        return {
            "status": "preflight_failed",
            "dry_run": dry_run,
            "run_at": run_at,
            "message": "Fix blockers before live run",
            "preflight": preflight,
            "readiness": readiness,
        }

    if not cfg.enabled and not force:
        return {
            "status": "disabled",
            "message": "daily_review_agent.enabled is false — use --force or set enabled: true",
            "readiness": readiness,
        }

    if not force and not schedule_is_active(timezone=cfg.timezone):
        return {
            "status": "outside_schedule_window",
            "message": "Today is outside active_from/active_until — use daily_review_schedule or --force",
            "readiness": readiness,
        }

    fetch = resolve_review_issues(cfg)
    issues = fetch.get("issues") or []
    rows = ticket_rows(issues)
    start, end = meeting_window(cfg)
    meeting_date = start.strftime("%Y-%m-%d")
    subject = f"{cfg.meeting_subject} — {meeting_date}"
    body_html = format_html_report(rows, team_name=cfg.jira_team_name, meeting_date=meeting_date)
    text_report = format_text_report(rows, team_name=cfg.jira_team_name, by_project=fetch.get("by_project") or {})

    attendees = collect_meeting_attendees(cfg, issues)
    invite_policy = attendee_policy_summary(cfg, issues)
    schedule = schedule_review_meeting(
        cfg,
        subject=subject,
        body_html=body_html,
        start=start,
        end=end,
        attendees=attendees,
        dry_run=dry_run,
    )

    handoff_required = bool(isinstance(schedule, dict) and schedule.get("handoff_required"))
    playwright_handoff = (
        schedule.get("handoff") if isinstance(schedule, dict) and handoff_required else None
    )
    schedule_ok = live_schedule_ok(schedule if isinstance(schedule, dict) else None, dry_run=dry_run)
    teams_join = str(schedule.get("join_url") or "") if isinstance(schedule, dict) else ""

    teams_post: dict[str, Any] = {"ok": True, "skipped": True, "reason": "schedule not confirmed"}
    slack: dict[str, Any] = {"ok": True, "skipped": True, "reason": "schedule not confirmed"}
    alert: dict[str, Any] = {"ok": True, "skipped": True}

    if schedule_ok:
        summary_text = _append_join_link(text_report, teams_join) if not dry_run else text_report
        teams_post = (
            post_summary_via_mcp(cfg, text=summary_text, dry_run=dry_run)
            if cfg.teams_mcp_enabled and cfg.teams_post_summary
            else {"ok": True, "skipped": True, "reason": "teams post disabled"}
        )
        slack = (
            run_slack_delivery(
                cfg.slack,
                text_report=summary_text,
                meeting_start=start,
                meeting_end=end,
                teams_join_url=teams_join,
                dry_run=dry_run,
            )
            if cfg.slack and cfg.slack.enabled
            else {"ok": True, "skipped": True, "reason": "slack disabled"}
        )
    fallback_handoff: dict[str, Any] | None = None
    if not dry_run and handoff_required and playwright_handoff:
        status = "schedule_handoff_required"
    elif not dry_run and not schedule_ok:
        error = str(schedule.get("error") or "missing join_url") if isinstance(schedule, dict) else "schedule failed"
        fallback_phrase = "daily review calendar playwright"
        if cfg.playwright_mcp_fallback_enabled and not handoff_required:
            from daily_review_agent.calendar_playwright_handoff import handoff_from_run_context

            fallback_handoff = handoff_from_run_context(
                subject=subject,
                start=start,
                end=end,
                attendees=attendees,
                body_text=text_report,
                timezone=cfg.timezone,
            )
            fallback_phrase = fallback_handoff.get("fallback_phrase") or fallback_phrase
        alert = alert_organizer_schedule_failure(
            cfg,
            error=error,
            subject=subject,
            run_at=run_at,
            dry_run=False,
            fallback_phrase=fallback_phrase,
        )
        status = "schedule_failed_handoff_available" if fallback_handoff else "schedule_failed"
    else:
        status = "ok"

    result: dict[str, Any] = {
        "status": status,
        "dry_run": dry_run,
        "run_at": run_at,
        "readiness": readiness,
        "preflight": preflight,
        "teams_post": teams_post,
        "slack": slack,
        "alert": alert,
        "fetch": {
            "status": fetch.get("status"),
            "total": fetch.get("total"),
            "errors": fetch.get("errors"),
            "by_project": {
                pk: {"statuses": info.get("statuses"), "count": info.get("count")}
                for pk, info in (fetch.get("by_project") or {}).items()
                if isinstance(info, dict)
            },
        },
        "meeting": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "attendee_count": len(attendees),
            "invite_policy": invite_policy,
            "schedule": schedule,
        },
        "text_report": text_report,
    }
    if playwright_handoff is not None:
        result["playwright_handoff"] = playwright_handoff
    if fallback_handoff is not None:
        result["fallback_handoff"] = fallback_handoff

    if not dry_run and schedule_ok:
        _save_state(
            {
                "last_run": result["run_at"],
                "event_id": schedule.get("event_id") if isinstance(schedule, dict) else None,
                "join_url": teams_join,
                "ticket_count": len(rows),
            }
        )

    return result
