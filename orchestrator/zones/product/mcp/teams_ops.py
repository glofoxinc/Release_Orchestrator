"""Headless Teams scheduling helpers for Release Orchestrator MCP (parity with platform backend)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import config
import teams_schedule as ts
from integration_archive import archived_response, is_archived
from ms_graph import GraphClient


def _attendees_for_handoff(
    kind: str,
    attendees: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    if attendees is not None:
        out: list[dict[str, str]] = []
        for item in attendees:
            if isinstance(item, str) and item.strip():
                out.append({"email": item.strip()})
            elif isinstance(item, dict) and item.get("email"):
                row: dict[str, str] = {"email": str(item["email"]).strip()}
                if item.get("name"):
                    row["name"] = str(item["name"]).strip()
                out.append(row)
        return out
    cfg = ts.load_schedule_config(config.TEAMS_SCHEDULE)
    kind_norm = (kind or "review").strip().lower()
    return [
        {"email": a.email, "name": a.name}
        for a in cfg.attendees_for_kind(kind_norm)  # type: ignore[arg-type]
        if a.email
    ]


def teams_playwright_handoff(
    *,
    kind: str,
    start: str,
    subject: str = "",
    end: str | None = None,
    timezone_name: str | None = None,
    attendees: list[dict[str, Any]] | None = None,
    body: str = "",
    version: str = "",
) -> dict[str, Any]:
    """Return Playwright MCP steps to schedule a Teams meeting via Outlook web (no Graph)."""
    from daily_review_agent.calendar_playwright_handoff import build_daily_review_calendar_handoff

    kind_norm = (kind or "review").strip().lower()
    if kind_norm not in ("review", "deployment"):
        return {"ok": False, "error": f"kind must be 'review' or 'deployment' (got {kind!r})"}

    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError as exc:
        return {"ok": False, "error": f"Invalid start datetime: {exc}"}

    end_dt: datetime | None = None
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError as exc:
            return {"ok": False, "error": f"Invalid end datetime: {exc}"}

    cfg = ts.load_schedule_config(config.TEAMS_SCHEDULE)
    tz = timezone_name or cfg.default_timezone or "Asia/Kolkata"
    people = _attendees_for_handoff(kind_norm, attendees)
    draft = ts.build_meeting_draft(
        cfg,
        kind=kind_norm,  # type: ignore[arg-type]
        subject=subject,
        start=start_dt,
        end=end_dt,
        timezone_name=tz,
        attendees=[
            ts.TeamsAttendee(email=p["email"], name=p.get("name", ""))
            for p in people
        ],
        body=body,
        version=version,
    )
    end_iso = (draft.end or start_dt).isoformat()
    handoff = build_daily_review_calendar_handoff(
        subject=draft.subject,
        start_iso=draft.start.isoformat(),
        end_iso=end_iso,
        attendees=people,
        body_text=draft.body or body,
        timezone=tz,
        primary=True,
    )
    handoff["kind"] = kind_norm
    handoff["version"] = version
    handoff["graph_archived"] = is_archived("teams_schedule")
    handoff["user_phrases"] = ["schedule review call", "calendar done", "meeting scheduled"]
    return handoff


def _cfg(graph: GraphClient | None = None) -> ts.TeamsScheduleConfig:
    return ts.load_schedule_config(config.TEAMS_SCHEDULE, graph=graph)


def teams_schedule_status() -> dict[str, Any]:
    """Feature/config status — safe without credentials."""
    if is_archived("teams_schedule"):
        base = archived_response("teams_schedule")
        import browser_automation

        pw = browser_automation.playwright_mcp_readiness()
        base["playwright_alternative"] = {
            "tool": "teams_playwright_handoff",
            "phrase": "schedule review call",
            "mcp": browser_automation.playwright_mcp(),
            "ready": pw.get("can_schedule") or pw.get("in_mcp_config"),
            "blockers": pw.get("blockers") or [],
        }
        return base
    return ts.status(_cfg())


def teams_update_meeting(
    *,
    event_id: str,
    kind: str,
    start: str,
    subject: str = "",
    end: str | None = None,
    timezone_name: str | None = None,
    attendees: list[dict[str, Any]] | None = None,
    body: str = "",
    version: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Update an existing Teams meeting (PATCH) — same fields as teams_schedule_meeting."""
    if is_archived("teams_schedule"):
        return archived_response("teams_schedule")
    cfg = _cfg()
    kind_norm = (kind or "review").strip().lower()
    if kind_norm not in ("review", "deployment"):
        return {
            "ok": False,
            "error": f"kind must be 'review' or 'deployment' (got {kind!r})",
            "dry_run": dry_run,
        }
    if not (event_id or "").strip():
        return {"ok": False, "error": "event_id is required", "dry_run": dry_run}

    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError as exc:
        return {"ok": False, "error": f"Invalid start datetime: {exc}", "dry_run": dry_run}

    end_dt = None
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError as exc:
            return {"ok": False, "error": f"Invalid end datetime: {exc}", "dry_run": dry_run}

    people = None
    if attendees is not None:
        people = []
        for item in attendees:
            if isinstance(item, str):
                people.append(ts.TeamsAttendee(email=item.strip()))
            elif isinstance(item, dict) and item.get("email"):
                people.append(
                    ts.TeamsAttendee(
                        email=str(item["email"]).strip(),
                        name=str(item.get("name") or "").strip(),
                        type=str(item.get("type") or "required").strip() or "required",
                    )
                )

    draft = ts.build_meeting_draft(
        cfg,
        kind=kind_norm,  # type: ignore[arg-type]
        subject=subject,
        start=start_dt,
        end=end_dt,
        timezone_name=timezone_name,
        attendees=people,
        body=body,
        version=version,
    )
    result = ts.update_meeting(cfg, event_id.strip(), draft, dry_run=dry_run)
    return result.to_dict()


def teams_cancel_meeting(
    *,
    event_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Cancel/delete a scheduled Teams meeting."""
    if is_archived("teams_schedule"):
        return archived_response("teams_schedule")
    cfg = _cfg()
    if not (event_id or "").strip():
        return {"ok": False, "error": "event_id is required", "dry_run": dry_run}
    result = ts.cancel_meeting(cfg, event_id.strip(), dry_run=dry_run)
    return result.to_dict()


def teams_schedule_meeting(
    *,
    kind: str,
    start: str,
    subject: str = "",
    end: str | None = None,
    timezone_name: str | None = None,
    attendees: list[dict[str, Any]] | None = None,
    body: str = "",
    version: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Schedule (or dry-run preview) a Teams review/deployment meeting.

    ``start`` / ``end`` are ISO-8601 datetimes (``YYYY-MM-DDTHH:MM:SS`` or with offset).
    ``kind`` is ``review`` or ``deployment``.
    """
    if is_archived("teams_schedule"):
        handoff = teams_playwright_handoff(
            kind=kind,
            start=start,
            subject=subject,
            end=end,
            timezone_name=timezone_name,
            attendees=attendees,
            body=body,
            version=version,
        )
        if not handoff.get("ok"):
            return {**handoff, "dry_run": dry_run, "delivery": "playwright_mcp"}
        return {
            **archived_response("teams_schedule"),
            "dry_run": True,
            "delivery": "playwright_mcp",
            "playwright_handoff": handoff,
            "hint": "Graph archived — execute playwright_handoff.steps via Playwright MCP, then say calendar done.",
        }
    cfg = _cfg()
    kind_norm = (kind or "review").strip().lower()
    if kind_norm not in ("review", "deployment"):
        return {
            "ok": False,
            "error": f"kind must be 'review' or 'deployment' (got {kind!r})",
            "dry_run": dry_run,
        }

    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError as exc:
        return {"ok": False, "error": f"Invalid start datetime: {exc}", "dry_run": dry_run}

    end_dt = None
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError as exc:
            return {"ok": False, "error": f"Invalid end datetime: {exc}", "dry_run": dry_run}

    people = None
    if attendees is not None:
        people = []
        for item in attendees:
            if isinstance(item, str):
                people.append(ts.TeamsAttendee(email=item.strip()))
            elif isinstance(item, dict) and item.get("email"):
                people.append(
                    ts.TeamsAttendee(
                        email=str(item["email"]).strip(),
                        name=str(item.get("name") or "").strip(),
                        type=str(item.get("type") or "required").strip() or "required",
                    )
                )

    draft = ts.build_meeting_draft(
        cfg,
        kind=kind_norm,  # type: ignore[arg-type]
        subject=subject,
        start=start_dt,
        end=end_dt,
        timezone_name=timezone_name,
        attendees=people,
        body=body,
        version=version,
    )
    result = ts.schedule_meeting(cfg, draft, dry_run=dry_run)
    payload = result.to_dict()
    if kind_norm == "review":
        payload["next_notify"] = {
            "tool": "notify_review_call",
            "version": version,
            "when": start,
            "hint": "Call notify_review_call for testers and main assignees (not optional attendees). dry_run=true first.",
        }
    if dry_run:
        payload["playwright_handoff"] = teams_playwright_handoff(
            kind=kind,
            start=start,
            subject=subject or draft.subject,
            end=end or (draft.end.isoformat() if draft.end else None),
            timezone_name=timezone_name,
            attendees=attendees,
            body=body or draft.body,
            version=version,
        )
    return payload
