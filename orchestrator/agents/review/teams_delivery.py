"""Teams calendar + chat delivery via browser-session MCP (no Graph app)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from daily_review_agent.config_loader import AgentConfig
from daily_review_agent.teams_mcp import teams_mcp_call


def _to_utc_z(dt: datetime) -> str:
    from datetime import timezone

    if dt.tzinfo is None:
        aware = dt.replace(tzinfo=timezone.utc)
    else:
        aware = dt.astimezone(timezone.utc)
    return aware.strftime("%Y-%m-%dT%H:%M:%SZ")


def schedule_meeting_via_mcp(
    cfg: AgentConfig,
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    attendee_emails: list[dict[str, str]],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Create Teams meeting using logged-in browser session."""
    attendees = [{"email": a["email"], "name": a.get("name") or ""} for a in attendee_emails if a.get("email")]
    preview = {
        "backend": "teams_mcp",
        "subject": subject,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "location": cfg.meeting_location,
        "attendees": attendees,
        "body_preview": body_text[:500],
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "preview": preview}

    payload = {
        "subject": subject,
        "startTime": _to_utc_z(start),
        "endTime": _to_utc_z(end),
        "attendees": attendees,
        "body": body_text,
        "isOnlineMeeting": True,
        "location": cfg.meeting_location or "Cross Fit",
    }
    result = teams_mcp_call("create-meeting", payload)
    if not result.get("ok"):
        return {
            "ok": False,
            "dry_run": False,
            "error": result.get("error"),
            "preview": preview,
            "bridge": result,
        }
    return {
        "ok": True,
        "dry_run": False,
        "event_id": result.get("event_id"),
        "join_url": result.get("join_url"),
        "preview": preview,
    }


def post_summary_via_mcp(
    cfg: AgentConfig,
    *,
    text: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Post daily summary to configured Teams conversation."""
    conv = (cfg.teams_summary_conversation_id or "").strip()
    if not conv:
        return {"ok": False, "skipped": True, "reason": "teams.summary_conversation_id not set"}
    if dry_run:
        return {"ok": True, "dry_run": True, "conversation_id": conv, "preview": text[:400]}
    result = teams_mcp_call("send-message", {"conversationId": conv, "content": text})
    return {"ok": bool(result.get("ok")), "dry_run": False, "conversation_id": conv, "bridge": result}
