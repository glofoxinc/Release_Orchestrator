"""MCP-facing browser automation handoffs (Playwright + Slack MCP)."""

from __future__ import annotations

from typing import Any

import browser_automation
from release_mcp import slack_ops


def browser_automation_status() -> dict[str, Any]:
    """SharePoint + Slack browser/MCP handoff readiness (no credentials required)."""
    base = browser_automation.status()
    slack_mode = slack_ops.slack_delivery_mode()
    base["slack_delivery_mode"] = slack_mode
    if browser_automation.prefer_playwright_slack():
        base["recommended_slack_path"] = "playwright"
    elif slack_mode == "cursor_slack_mcp" and browser_automation.prefer_slack_mcp():
        base["recommended_slack_path"] = "slack_mcp"
    else:
        base["recommended_slack_path"] = "playwright_or_bot"
    return base


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
    """Return Playwright MCP steps to schedule a Teams meeting via Outlook web."""
    from release_mcp import teams_ops

    return teams_ops.teams_playwright_handoff(
        kind=kind,
        start=start,
        subject=subject,
        end=end,
        timezone_name=timezone_name,
        attendees=attendees,
        body=body,
        version=version,
    )


def sharepoint_playwright_handoff(
    local_path: str,
    *,
    version_name: str = "",
    remote_name: str | None = None,
) -> dict[str, Any]:
    """Return Playwright MCP steps to upload Release Notes .docx to SharePoint."""
    return browser_automation.build_sharepoint_upload_handoff(
        local_path,
        version_name=version_name,
        remote_name=remote_name,
    )


def slack_playwright_handoff(
    *,
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
    message_edits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return Playwright MCP steps for both Slack channels (browser fallback)."""
    preview = slack_ops.build_slack_preview(
        ticket_key=ticket_key,
        summary=summary,
        ticket_url=ticket_url,
        version_name=version_name,
        sharepoint_url=sharepoint_url,
        deploy_date=deploy_date,
        environments=environments,
    )
    preview = slack_ops.apply_slack_message_edits(preview, message_edits)
    handoff = browser_automation.build_slack_announce_handoff(preview)
    handoff["slack_mcp"] = slack_ops.handoff_for_slack_mcp(preview)
    handoff["preview"] = preview
    return handoff


def enrich_sharepoint_preview(preview: dict[str, Any], *, local_path: str, version_name: str) -> dict[str, Any]:
    """Attach Playwright upload handoff when Graph upload is unavailable."""
    enriched = dict(preview)
    handoff = browser_automation.build_sharepoint_upload_handoff(
        local_path,
        version_name=version_name,
    )
    enriched["playwright_upload"] = handoff
    enriched["can_upload_via_playwright"] = bool(handoff.get("ok"))
    enriched["delivery_modes"] = _sharepoint_delivery_modes(handoff)
    return enriched


def enrich_slack_preview(preview: dict[str, Any]) -> dict[str, Any]:
    """Attach Slack MCP + Playwright handoffs to a Slack step preview."""
    enriched = slack_ops.enrich_preview_with_delivery(preview)
    pw = browser_automation.build_slack_announce_handoff(preview)
    enriched["playwright_slack"] = pw
    enriched["can_post_via_playwright"] = bool(pw.get("channels"))
    enriched["delivery_modes"] = _slack_delivery_modes(enriched)
    return enriched


def _sharepoint_delivery_modes(handoff: dict[str, Any]) -> list[dict[str, str]]:
    modes = [
        {"id": "manual_url", "label": "Paste SharePoint URL after manual upload"},
    ]
    if handoff.get("ok"):
        modes.insert(0, {
            "id": "playwright",
            "label": "Playwright MCP upload (no Graph credentials)",
            "mcp": browser_automation.playwright_mcp(),
        })
    return modes


def _slack_delivery_modes(preview: dict[str, Any]) -> list[dict[str, str]]:
    modes: list[dict[str, str]] = []
    pw_first = browser_automation.prefer_playwright_slack()
    if preview.get("can_post_via_playwright"):
        modes.append({
            "id": "playwright",
            "label": "Playwright MCP browser post (recommended for Glofox private channels)",
            "mcp": browser_automation.playwright_mcp(),
        })
    if preview.get("can_post_via_slack_mcp"):
        modes.append({
            "id": "slack_mcp",
            "label": "Slack MCP slack_send_message"
            + ("" if pw_first else " (recommended)"),
            "mcp": "plugin-slack-slack",
        })
    if preview.get("can_send"):
        modes.append({
            "id": "bot_token",
            "label": "Auto-send via SLACK_BOT_TOKEN",
        })
    if pw_first and modes and modes[0]["id"] == "playwright":
        return modes + [{"id": "manual", "label": "Post manually → say slack done"}]
    modes.append({"id": "manual", "label": "Post manually → say slack done"})
    return modes
