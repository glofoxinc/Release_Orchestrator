"""Headless Teams scheduling helpers for Release Orchestrator MCP (parity with platform backend)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import config
import teams_schedule as ts
from integration_archive import archived_response, is_archived
from ms_graph import GraphClient


def _cfg(graph: GraphClient | None = None) -> ts.TeamsScheduleConfig:
    return ts.load_schedule_config(config.TEAMS_SCHEDULE, graph=graph)


def teams_schedule_status() -> dict[str, Any]:
    """Feature/config status — safe without credentials."""
    if is_archived("teams_schedule"):
        return archived_response("teams_schedule")
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
        return archived_response("teams_schedule")
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
    return result.to_dict()
