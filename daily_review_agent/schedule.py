"""Meeting window math + Teams scheduling via existing teams_schedule backend."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import teams_schedule
from teams_meeting_content import merge_attendees
from teams_schedule import TeamsAttendee, TeamsScheduleConfig

from daily_review_agent.config_loader import AgentConfig
from daily_review_agent.meeting_attendees import collect_crew_aware_attendees


def _parse_hhmm(raw: str) -> time:
    text = (raw or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return time(11, 30)


def next_business_day(from_day: date, *, skip_weekends: bool) -> date:
    candidate = from_day + timedelta(days=1)
    if not skip_weekends:
        return candidate
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def meeting_window(cfg: AgentConfig, *, run_at: datetime | None = None) -> tuple[datetime, datetime]:
    """Next review meeting start/end in cfg.timezone."""
    tz = ZoneInfo(cfg.timezone)
    now = run_at.astimezone(tz) if run_at and run_at.tzinfo else datetime.now(tz)
    target_day = now.date()
    for _ in range(max(1, cfg.meeting_day_offset)):
        target_day = next_business_day(target_day, skip_weekends=cfg.skip_weekends)
    start = datetime.combine(target_day, _parse_hhmm(cfg.meeting_start), tzinfo=tz)
    end = datetime.combine(target_day, _parse_hhmm(cfg.meeting_end), tzinfo=tz)
    if end <= start:
        end = start + timedelta(minutes=30)
    return start, end


def demo_window(cfg: AgentConfig, *, minutes_from_now: int = 30) -> tuple[datetime, datetime]:
    tz = ZoneInfo(cfg.timezone)
    start = datetime.now(tz) + timedelta(minutes=max(5, minutes_from_now))
    end = start + timedelta(minutes=max(5, cfg.demo_duration_minutes))
    return start, end


def _to_teams_attendees(specs: list) -> list[TeamsAttendee]:
    out: list[TeamsAttendee] = []
    for spec in specs:
        out.append(
            TeamsAttendee(
                email=spec.email,
                name=spec.name,
                type=spec.type or "required",
            )
        )
    return out


def collect_meeting_attendees(cfg: AgentConfig, issues: list[dict]) -> list[TeamsAttendee]:
    """Crew from welcome onboard + squad assignees (see meeting_attendees.py)."""
    return collect_crew_aware_attendees(cfg, issues)


def build_teams_config(cfg: AgentConfig) -> TeamsScheduleConfig:
    section = dict(cfg.teams_schedule_section)
    section.setdefault("enabled", True)
    section["organizer_upn"] = cfg.organizer_upn or section.get("organizer_upn") or ""
    section["default_timezone"] = cfg.timezone
    return teams_schedule.load_schedule_config(section)


def schedule_review_meeting(
    cfg: AgentConfig,
    *,
    subject: str,
    body_html: str,
    start: datetime,
    end: datetime,
    attendees: list[TeamsAttendee],
    dry_run: bool = True,
) -> dict[str, Any]:
    plain = body_html.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n")
    people = [{"email": a.email, "name": a.name} for a in attendees if a.email]
    backend = (cfg.calendar_backend or "auto").strip().lower()

    if backend == "auto":
        from daily_review_agent.calendar_orchestrator import resolve_backend_chain, schedule_with_fallback

        preview = {
            "backend": "auto",
            "chain": list(resolve_backend_chain(cfg)),
            "subject": subject,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "attendees": people,
        }
        if dry_run:
            return {"ok": True, "dry_run": True, "preview": preview}
        return schedule_with_fallback(
            cfg,
            subject=subject,
            body_text=plain,
            start=start,
            end=end,
            attendee_emails=people,
            dry_run=False,
        )

    if backend == "graph_delegated":
        from daily_review_agent.graph_calendar import schedule_meeting_via_graph

        preview = {
            "backend": "graph_delegated",
            "subject": subject,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "attendees": people,
        }
        if dry_run:
            return {"ok": True, "dry_run": True, "preview": preview}
        graph_result = schedule_meeting_via_graph(
            subject=subject,
            body_text=plain,
            start=start,
            end=end,
            attendee_emails=people,
            timezone_name=cfg.timezone,
            location=cfg.meeting_location or "Microsoft Teams Meeting",
            organizer_upn=cfg.organizer_upn,
            interactive_auth=False,
        )
        if graph_result.get("ok"):
            return graph_result
        err = str(graph_result.get("error") or "")
        if "AADSTS65002" in err or "Graph sign-in required" in err:
            if cfg.teams_mcp_enabled:
                from daily_review_agent.teams_delivery import schedule_meeting_via_mcp

                fallback = schedule_meeting_via_mcp(
                    cfg,
                    subject=subject,
                    body_text=plain,
                    start=start,
                    end=end,
                    attendee_emails=people,
                    dry_run=False,
                )
                if fallback.get("ok"):
                    fallback["fallback_from"] = "graph_delegated"
                    return fallback
        return graph_result

    if backend == "outlook_com":
        from daily_review_agent.outlook_calendar import schedule_meeting_via_outlook

        preview = {
            "backend": "outlook_com",
            "subject": subject,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "attendees": people,
        }
        if dry_run:
            return {"ok": True, "dry_run": True, "preview": preview}
        return schedule_meeting_via_outlook(
            subject=subject,
            body_text=plain,
            start=start,
            end=end,
            attendee_emails=people,
            location=cfg.meeting_location or "Microsoft Teams Meeting",
        )

    if backend == "teams_mcp" and cfg.teams_mcp_enabled:
        from daily_review_agent.teams_delivery import schedule_meeting_via_mcp

        return schedule_meeting_via_mcp(
            cfg,
            subject=subject,
            body_text=plain,
            start=start,
            end=end,
            attendee_emails=people,
            dry_run=dry_run,
        )

    teams_cfg = build_teams_config(cfg)
    teams_cfg.enabled = True
    people = list(attendees)
    if cfg.meeting_room_email:
        people.append(
            TeamsAttendee(
                email=cfg.meeting_room_email,
                name=cfg.meeting_location or "Cross Fit",
                type="resource",
            )
        )
    location = cfg.meeting_location or "Cross Fit"
    draft = teams_schedule.build_meeting_draft(
        teams_cfg,
        kind="review",
        subject=subject,
        start=start,
        end=end,
        timezone_name=cfg.timezone,
        attendees=people,
        body=body_html,
        location=location,
    )
    result = teams_schedule.schedule_meeting(teams_cfg, draft, dry_run=dry_run)
    return result.to_dict()
