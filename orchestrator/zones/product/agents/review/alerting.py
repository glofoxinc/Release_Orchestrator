"""Organizer alerts on schedule failure (Teams self-chat / notes DM)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from daily_review_agent.config_loader import AgentConfig
from daily_review_agent.teams_mcp import teams_mcp_call

logger = logging.getLogger(__name__)


def format_schedule_failure_message(
    *,
    run_at: str,
    error: str,
    subject: str = "",
    fallback_phrase: str = "daily review calendar playwright",
) -> str:
    lines = [
        "Daily Review Agent FAILED — meeting not scheduled",
        f"Time: {run_at}",
    ]
    if subject:
        lines.append(f"Subject: {subject}")
    lines.append(f"Error: {error or 'unknown'}")
    lines.extend(
        [
            "",
            "Fix (primary):",
            "  python -m daily_review_agent --outlook-login",
            "  Then in Cursor: daily_review_run_live(force=true)",
            "",
            "Fallback (Playwright MCP in Cursor chat):",
            f"  Say: {fallback_phrase}",
            "  Or MCP: daily_review_calendar_playwright_handoff()",
            "  When invite is sent, say: calendar done",
        ]
    )
    return "\n".join(lines)


def alert_organizer_schedule_failure(
    cfg: AgentConfig,
    *,
    error: str,
    subject: str = "",
    run_at: str | None = None,
    dry_run: bool = False,
    fallback_phrase: str = "daily review calendar playwright",
) -> dict[str, Any]:
    """Send failure alert to organizer via Teams self-chat (requires teams_login)."""
    if not cfg.alerting.on_schedule_failure:
        return {"ok": True, "skipped": True, "reason": "alerting disabled"}

    tz = ZoneInfo(cfg.timezone)
    when = run_at or datetime.now(tz).isoformat()
    content = format_schedule_failure_message(
        run_at=when,
        error=error,
        subject=subject,
        fallback_phrase=fallback_phrase,
    )

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "preview": content,
            "channel": cfg.alerting.channel,
            "organizer_upn": cfg.alerting.organizer_upn or cfg.organizer_upn,
        }

    result = teams_mcp_call("send-self-message", {"content": content})
    return {
        "ok": bool(result.get("ok")),
        "dry_run": False,
        "channel": cfg.alerting.channel,
        "organizer_upn": cfg.alerting.organizer_upn or cfg.organizer_upn,
        "bridge": result,
    }
