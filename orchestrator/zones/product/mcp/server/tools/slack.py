"""MCP tools: slack."""

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
def slack_announce_status() -> dict:
    """Status for deployment Slack announce (Bot API backend).

    Safe without credentials. Reports enabled flag, channel targets, CC
    requirements, and whether SLACK_BOT_TOKEN is set. Same backend as the
    Service Ticket Slack panel and release_wizard slack step.
    """
    return slack_ops.slack_announce_status()


@mcp.tool()
def slack_preview(
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
    edits: dict[str, str] | None = None,
    client_sharepoint_url: str = "",
    extracted: list[dict] | None = None,
) -> dict:
    """Build deployment Slack channel previews without sending.

    Args:
        ticket_key: Created TCKT key (e.g. TCKT-123)
        summary: Service ticket summary line
        ticket_url: Browse URL for the TCKT
        version_name: Release version string (e.g. v2026.3.08.05)
        sharepoint_url: Link to Release Notes .docx on SharePoint
        deploy_date: ISO date (YYYY-MM-DD) for the deployment window
        environments: Environment label in the message body
        edits: Optional per-channel body overrides keyed by channel key/name
        client_sharepoint_url: Optional Client Release Notes SharePoint link
        extracted: Optional PIC/AN ticket dicts with ``labels`` for the bold mix line
    """
    preview = slack_ops.build_slack_preview(
        ticket_key=ticket_key,
        summary=summary,
        ticket_url=ticket_url,
        version_name=version_name,
        sharepoint_url=sharepoint_url,
        deploy_date=deploy_date,
        environments=environments,
        client_sharepoint_url=client_sharepoint_url,
        extracted=extracted,
    )
    if edits:
        preview = slack_ops.apply_slack_message_edits(preview, edits)
    return browser_ops.enrich_slack_preview(preview)


@mcp.tool()
def slack_send(
    preview: dict,
    skip_channel_keys: list[str] | None = None,
) -> dict:
    """Send a slack_preview payload to configured channels.

    Requires slack_announce.enabled=true and SLACK_BOT_TOKEN. Use
    skip_channel_keys to retry only failed channels after a partial send.
    """
    return slack_ops.send_slack_preview(preview, skip_channel_keys=skip_channel_keys or [])


@mcp.tool()
def slack_mcp_verify(
    channel_checks: list[dict[str, Any]] | None = None,
    user_checks: list[dict[str, Any]] | None = None,
    refresh_probes: bool = False,
) -> dict:
    """Verify Cursor Slack MCP readiness for Step 6 deployment announce.

    Reports configured channel IDs, CC user IDs, MCP accessibility probes,
    and blockers. Pass ``channel_checks`` / ``user_checks`` after probing with
    Cursor Slack MCP (``slack_read_channel``, ``slack_search_users``).

    Args:
        channel_checks: Optional list of {name, channel_id, accessible, error}
        user_checks: Optional list of {key, name, configured_user_id, resolved_user_id, match}
        refresh_probes: When true, ignore cached probe results (offline config only)
    """
    return enrich_tool_response(
        slack_mcp_ops.slack_mcp_verify(
            channel_checks=channel_checks,
            user_checks=user_checks,
            refresh_probes=refresh_probes,
        ),
        tool="slack_mcp_verify",
    )


@mcp.tool()
def slack_mcp_e2e_handoff(
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
    message_edits: dict[str, str] | None = None,
) -> dict:
    """Full Step 6 E2E: Slack MCP verify + preview + ready-to-post payloads.

    Returns verification blockers, both channel message previews, and
    ``slack_mcp.posts`` for Cursor ``slack_send_message``. Same message copy
    as ``slack_preview``; adds MCP access checklist.
    """
    return enrich_tool_response(
        slack_mcp_ops.slack_mcp_e2e_handoff(
            ticket_key=ticket_key,
            summary=summary,
            ticket_url=ticket_url,
            version_name=version_name,
            sharepoint_url=sharepoint_url,
            deploy_date=deploy_date,
            environments=environments,
            message_edits=message_edits,
        ),
        tool="slack_mcp_e2e_handoff",
    )


