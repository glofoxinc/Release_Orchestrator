"""MCP tools: sharepoint."""

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
def sharepoint_upload_status() -> dict:
    """Status for SharePoint release-notes upload (Graph backend).

    Safe without credentials. Reports enabled flag, folder/site target readiness,
    and whether MS_GRAPH_* env vars are set. Same backend as the platform UI
    (Release Notes Step 4 upload button).
    """
    return sharepoint_ops.sharepoint_upload_status()


@mcp.tool()
def sharepoint_upload_release_notes(
    local_path: str,
    remote_name: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Upload a release-notes .docx to the configured SharePoint folder.

    Defaults to dry_run=True (preview plan only). Live upload requires
    sharepoint_upload.enabled=true in workspace.yaml and MS_GRAPH_* credentials.
    Returns web_url for Service Ticket / Slack reuse when live upload succeeds.

    Args:
        local_path: Absolute or relative path to the .docx file
        remote_name: Optional SharePoint file name (defaults to local basename)
        dry_run: If true, return the upload plan without calling Graph
    """
    return sharepoint_ops.sharepoint_upload_release_notes(
        local_path,
        remote_name=remote_name,
        dry_run=dry_run,
    )


@mcp.tool()
def sharepoint_download_release_notes(
    web_url: str,
    output_path: str | None = None,
) -> dict:
    """Download a SharePoint Release Notes document and parse deployment rows.

    The parsed rows provide client deployment IDs, dates, and times for the
    post-deployment workflow. ``output_path`` is optional; omit it to avoid
    writing the document locally.
    """
    return sharepoint_ops.sharepoint_download_release_notes(
        web_url,
        output_path=output_path,
    )


@mcp.tool()
def browser_automation_status() -> dict:
    """Playwright + Slack MCP handoff readiness for SharePoint upload and Slack announce.

    Safe without credentials. Use when Graph upload is archived or SLACK_BOT_TOKEN
    is not set — the agent posts via Cursor Playwright MCP and/or Slack MCP instead.
    """
    return enrich_tool_response(
        browser_ops.browser_automation_status(),
        tool="browser_automation_status",
    )


@mcp.tool()
def sharepoint_playwright_handoff(
    local_path: str,
    version_name: str = "",
    remote_name: str | None = None,
) -> dict:
    """Return Playwright MCP steps to upload Release Notes .docx to SharePoint.

    Execute steps via Cursor **Playwright MCP** (user-playwright). Operator must be
    signed in to Microsoft 365 in the Playwright browser profile. After upload,
    paste the document URL into the workflow (sharepoint_url).

    Args:
        local_path: Path to generated Release Notes .docx
        version_name: Fix version for remote file name (e.g. 2026.3.09.14)
        remote_name: Optional override file name on SharePoint
    """
    return enrich_tool_response(
        browser_ops.sharepoint_playwright_handoff(
            local_path,
            version_name=version_name,
            remote_name=remote_name,
        ),
        tool="sharepoint_playwright_handoff",
    )


@mcp.tool()
def slack_playwright_handoff(
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
    message_edits: dict[str, str] | None = None,
) -> dict:
    """Return Playwright MCP steps to post deployment announce to both Slack channels.

    Fallback when Slack MCP is unavailable. Prefer ``slack_preview`` +
    Cursor **Slack MCP** ``slack_send_message`` when connected. Includes both
    #insights-customize-squad and #customize-bi-buddies from workspace.yaml.

    Args:
        ticket_key: SHIPIT key (e.g. SHIPIT-17036)
        summary: Service ticket summary
        ticket_url: Jira browse URL
        version_name: Release version
        sharepoint_url: Release Notes SharePoint link
        deploy_date: ISO date YYYY-MM-DD
        environments: Environment label in message body
        message_edits: Optional per-channel message overrides (key → text)
    """
    return enrich_tool_response(
        browser_ops.slack_playwright_handoff(
            ticket_key=ticket_key,
            summary=summary,
            ticket_url=ticket_url,
            version_name=version_name,
            sharepoint_url=sharepoint_url,
            deploy_date=deploy_date,
            environments=environments,
            message_edits=message_edits,
        ),
        tool="slack_playwright_handoff",
    )


