"""MCP tools: teams."""

from __future__ import annotations

from typing import Any

import config
import jira_client
from release_mcp import (
    browser_ops,
    gate_ops,
    release_ops,
    sharepoint_ops,
    slack_mcp_ops,
    slack_ops,
    teams_ops,
    wizard,
)
from release_mcp.operator_guide import enrich_tool_response
from release_mcp.server.bootstrap import logger, mcp

@mcp.tool()
def teams_schedule_status() -> dict:
    """Status for Teams review/deployment meeting scheduling (Graph backend).

    Safe without credentials. Reports enabled flag, organizer, defaults, and
    whether MS_GRAPH_* env vars are set. Same backend as the platform UI
    Teams panels in Ticket Review and Service Ticket.
    """
    return teams_ops.teams_schedule_status()


@mcp.tool()
def teams_schedule_meeting(
    kind: str,
    start: str,
    subject: str = "",
    end: str | None = None,
    timezone_name: str | None = None,
    attendees: list[dict] | None = None,
    body: str = "",
    version: str = "",
    dry_run: bool = True,
) -> dict:
    """Schedule a Teams meeting for ticket review or deployment.

    Defaults to dry_run=True (returns Graph calendar payload only). Live create
    requires teams_schedule.enabled=true, organizer_upn, and MS_GRAPH_* credentials.

    Args:
        kind: 'review' or 'deployment'
        start: ISO datetime (YYYY-MM-DDTHH:MM:SS or with offset)
        subject: Meeting subject (auto-built from kind/version when empty)
        end: Optional ISO end datetime (defaults from workspace durations)
        timezone_name: IANA zone (defaults to teams_schedule.default_timezone)
        attendees: Optional list of {email, name?, type?} (else workspace defaults)
        body: Optional HTML/text body
        version: Optional release version for default subject/body
        dry_run: If true, preview payload without calling Graph
    """
    return teams_ops.teams_schedule_meeting(
        kind=kind,
        start=start,
        subject=subject,
        end=end,
        timezone_name=timezone_name,
        attendees=attendees,
        body=body,
        version=version,
        dry_run=dry_run,
    )


@mcp.tool()
def teams_update_meeting(
    event_id: str,
    kind: str,
    start: str,
    subject: str = "",
    end: str | None = None,
    timezone_name: str | None = None,
    attendees: list[dict] | None = None,
    body: str = "",
    version: str = "",
    dry_run: bool = True,
) -> dict:
    """Update/reschedule an existing Teams meeting (Graph PATCH)."""
    return teams_ops.teams_update_meeting(
        event_id=event_id,
        kind=kind,
        start=start,
        subject=subject,
        end=end,
        timezone_name=timezone_name,
        attendees=attendees,
        body=body,
        version=version,
        dry_run=dry_run,
    )


@mcp.tool()
def teams_cancel_meeting(event_id: str, dry_run: bool = True) -> dict:
    """Cancel/delete a scheduled Teams calendar event."""
    return teams_ops.teams_cancel_meeting(event_id=event_id, dry_run=dry_run)


@mcp.tool()
def teams_playwright_handoff(
    kind: str,
    start: str,
    subject: str = "",
    end: str | None = None,
    timezone_name: str | None = None,
    attendees: list[dict] | None = None,
    body: str = "",
    version: str = "",
) -> dict:
    """Schedule a Teams meeting via Playwright MCP + Outlook web (no MS_GRAPH_* required).

    Use when ``teams_schedule`` Graph backend is archived or credentials are unavailable.
    Execute returned ``steps`` with Playwright MCP, then say **calendar done**.

    Args:
        kind: ``review`` or ``deployment``
        start: ISO datetime for meeting start
        subject: Optional subject (auto-built from kind/version when empty)
        end: Optional ISO end datetime
        timezone_name: IANA zone (default Asia/Kolkata)
        attendees: Optional list of {email, name?}
        body: Optional meeting body
        version: Release version for default subject
    """
    return enrich_tool_response(
        browser_ops.teams_playwright_handoff(
            kind=kind,
            start=start,
            subject=subject,
            end=end,
            timezone_name=timezone_name,
            attendees=attendees,
            body=body,
            version=version,
        ),
        tool="teams_playwright_handoff",
    )


