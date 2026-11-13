"""Headless Teams scheduling helpers for Release Orchestrator MCP (parity with platform backend)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import config
import teams_schedule as ts
from integration_archive import archived_response, is_archived
from ms_graph import GraphClient
from program_pack import (
    build_program_review_attendees,
    build_review_call_body,
    build_review_call_subject,
    issue_rows_from_jira_issues,
)

_ATTENDEES_REQUIRED_ERROR = (
    "attendees is required for review calls. "
    "Call review_call_prepare(ticket_keys=[...]) or pass explicit attendees "
    "with type required|optional on each row."
)


def _attendees_for_handoff(
    kind: str,
    attendees: list[dict[str, Any]] | None,
) -> list[dict[str, str]] | None:
    if attendees is not None:
        out: list[dict[str, str]] = []
        for item in attendees:
            if isinstance(item, str) and item.strip():
                out.append({"email": item.strip(), "type": "required"})
            elif isinstance(item, dict) and item.get("email"):
                row: dict[str, str] = {"email": str(item["email"]).strip()}
                if item.get("name"):
                    row["name"] = str(item["name"]).strip()
                invite_type = str(item.get("type") or "required").strip().lower()
                row["type"] = invite_type if invite_type in {"required", "optional"} else "required"
                out.append(row)
        return out
    kind_norm = (kind or "review").strip().lower()
    if kind_norm == "review":
        return None
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
    if people is None:
        return {
            "ok": False,
            "error": _ATTENDEES_REQUIRED_ERROR,
            "hint_tool": "review_call_prepare",
        }
    draft = ts.build_meeting_draft(
        cfg,
        kind=kind_norm,  # type: ignore[arg-type]
        subject=subject,
        start=start_dt,
        end=end_dt,
        timezone_name=tz,
        attendees=[
            ts.TeamsAttendee(
                email=p["email"],
                name=p.get("name", ""),
                type=str(p.get("type") or "required"),
            )
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
    return _attach_playwright_validation(handoff, people, draft.start.isoformat(), tz)


def _attach_playwright_validation(
    handoff: dict[str, Any],
    people: list[dict[str, str]],
    start_iso: str,
    timezone_name: str,
) -> dict[str, Any]:
    """Pre-send gate metadata for agents (one send, full crew, date lock)."""
    if not handoff.get("ok"):
        return handoff
    required = [p for p in people if (p.get("type") or "required") == "required"]
    optional = [p for p in people if p.get("type") == "optional"]
    start_date = start_iso[:10] if len(start_iso) >= 10 else ""
    handoff["pre_send_gate"] = {
        "required_count": len(required),
        "optional_count": len(optional),
        "start_date": start_date,
        "rule": (
            "Do not click Send until all required and optional attendees are in compose "
            "and Outlook Start date matches start_date."
        ),
        "required_emails": [p["email"] for p in required],
        "optional_emails": [p["email"] for p in optional],
    }
    handoff["anti_patterns"] = [
        "Sending with required only then patching optional in a second update",
        "Subject/body date different from Outlook Start date combobox",
        "Omitting attendees (never rely on implicit defaults)",
        "Following stale MCP steps after handoff code change without restarting MCP",
    ]
    handoff["timezone_name"] = timezone_name
    return handoff


def review_call_prepare(
    *,
    ticket_keys: list[str],
    start: str,
    end: str | None = None,
    timezone_name: str | None = None,
    program_key: str | None = None,
    subject: str = "",
    body: str = "",
) -> dict[str, Any]:
    """Build review call subject, body, attendees, and Playwright handoff for ticket keys."""
    import jira_client

    keys = [k.strip().upper() for k in ticket_keys if (k or "").strip()]
    if not keys:
        return {"ok": False, "error": "ticket_keys must include at least one Jira key (e.g. AN-5672)"}

    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError as exc:
        return {"ok": False, "error": f"Invalid start datetime: {exc}"}

    cfg = ts.load_schedule_config(config.TEAMS_SCHEDULE)
    tz = timezone_name or cfg.default_timezone or "Asia/Kolkata"

    end_dt: datetime | None = None
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError as exc:
            return {"ok": False, "error": f"Invalid end datetime: {exc}"}
    else:
        from program_pack import load_program

        pack = load_program(program_key)
        review_cfg = pack.get("review_call") or {}
        minutes = int(review_cfg.get("duration_minutes") or 30)
        end_dt = start_dt + timedelta(minutes=minutes)

    jira_issues: list[dict[str, Any]] = []
    errors: list[str] = []
    for key in keys:
        try:
            jira_issues.append(jira_client.get_issue(key))
        except Exception as exc:  # noqa: BLE001 — surface per-key Jira failures
            errors.append(f"{key}: {exc}")

    if errors and not jira_issues:
        return {"ok": False, "error": "Could not fetch any tickets", "details": errors}

    issue_rows = issue_rows_from_jira_issues(jira_issues)
    attendees = build_program_review_attendees(issues=issue_rows, program_key=program_key)
    subj = (subject or "").strip() or build_review_call_subject(start_dt, timezone_name=tz)
    body_text = (body or "").strip() or build_review_call_body(
        issue_rows,
        start_dt,
        end_dt,
        timezone_name=tz,
    )

    handoff = teams_playwright_handoff(
        kind="review",
        start=start_dt.isoformat(),
        end=end_dt.isoformat() if end_dt else None,
        timezone_name=tz,
        subject=subj,
        body=body_text,
        attendees=attendees,
    )
    payload: dict[str, Any] = {
        "ok": handoff.get("ok", False),
        "ticket_keys": keys,
        "issues": issue_rows,
        "attendees": attendees,
        "subject": subj,
        "body": body_text,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat() if end_dt else None,
        "timezone_name": tz,
        "playwright_handoff": handoff,
        "next_step": "Execute playwright_handoff.steps via Playwright MCP, then say calendar done.",
    }
    if errors:
        payload["warnings"] = errors
    if not handoff.get("ok"):
        payload["error"] = handoff.get("error")
    return payload


def _cfg(graph: GraphClient | None = None) -> ts.TeamsScheduleConfig:
    return ts.load_schedule_config(config.TEAMS_SCHEDULE, graph=graph)


def teams_schedule_status() -> dict[str, Any]:
    """Feature/config status — safe without credentials."""
    if is_archived("teams_schedule"):
        base = archived_response("teams_schedule")
        import browser_automation
        from daily_review_agent.calendar_playwright_handoff import (
            HANDOFF_FEATURES,
            HANDOFF_VERSION,
        )

        pw = browser_automation.playwright_mcp_readiness()
        base["playwright_alternative"] = {
            "tool": "teams_playwright_handoff",
            "phrase": "schedule review call",
            "mcp": browser_automation.playwright_mcp(),
            "ready": pw.get("can_schedule") or pw.get("in_mcp_config"),
            "blockers": pw.get("blockers") or [],
        }
        base["playwright_handoff_meta"] = {
            "handoff_version": HANDOFF_VERSION,
            "features": dict(HANDOFF_FEATURES),
            "prepare_tool": "review_call_prepare",
            "restart_hint": "Restart release-orchestrator MCP after handoff code changes.",
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
