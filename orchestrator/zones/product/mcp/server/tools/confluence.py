"""MCP tools: confluence."""

from __future__ import annotations

import os
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
def confluence_publish_release_notes(
    ticket_key: str,
    summary: str,
    sharepoint_url: str = "",
    extracted: list[dict[str, Any]] | None = None,
    space_key: str = "",
    parent_id: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Publish release notes to Confluence as a wiki page.

    Generates a formatted Confluence page with ticket details, affected clients,
    dashboards, plans, and source tickets.

    Args:
        ticket_key: The TCKT ticket key (e.g. TCKT-1234)
        summary: Ticket summary line
        sharepoint_url: URL to SharePoint release notes document
        extracted: List of extracted ticket dicts for the release
        space_key: Confluence space key (defaults to CONFLUENCE_SPACE env var)
        parent_id: Parent page ID (optional, defaults to CONFLUENCE_PARENT_ID env var)
        dry_run: If true, generate body but don't publish (preview mode)
    """
    import confluence_publisher

    space = space_key or os.environ.get("CONFLUENCE_SPACE", "")
    parent = parent_id or os.environ.get("CONFLUENCE_PARENT_ID") or None

    if not space:
        return enrich_tool_response({
            "status": "error",
            "error": "No Confluence space key provided. Set space_key or CONFLUENCE_SPACE env var.",
        }, tool="confluence_publish_release_notes")

    ticket_data = {
        "ticket_key": ticket_key,
        "summary": summary,
        "sharepoint_url": sharepoint_url,
        "extracted": extracted or [],
    }

    body = confluence_publisher.generate_page_body(ticket_data)
    title = confluence_publisher.default_title(ticket_data)

    if dry_run:
        return enrich_tool_response({
            "status": "preview",
            "title": title,
            "space": space,
            "parent_id": parent,
            "body_preview": body[:2000] + ("..." if len(body) > 2000 else ""),
            "body_length": len(body),
        }, tool="confluence_publish_release_notes")

    result = confluence_publisher.publish_page(space, parent, body, title=title)
    return enrich_tool_response({
        "status": "ok" if result.ok else "error",
        "page_id": result.page_id,
        "url": result.url,
        "error": result.error,
    }, tool="confluence_publish_release_notes")


@mcp.tool()
def ai_enhance_release(
    extracted: list[dict[str, Any]],
    options: dict[str, bool] | None = None,
) -> dict:
    """Generate AI-enhanced insights for a release ticket set.

    Returns an executive summary, risk assessment, and optionally acceptance
    criteria suggestions based on the extracted ticket data.

    Args:
        extracted: List of extracted ticket dicts (from ticket snapshot)
        options: Optional dict with keys:
            - include_summary (bool, default True): Generate executive summary
            - include_risk (bool, default True): Generate risk assessment
            - include_criteria (bool, default False): Generate acceptance criteria
    """
    import ai_enhancer

    opts = options or {}
    include_summary = opts.get("include_summary", True)
    include_risk = opts.get("include_risk", True)
    include_criteria = opts.get("include_criteria", False)

    result: dict[str, Any] = {"status": "ok"}

    if include_summary:
        try:
            result["summary"] = ai_enhancer.summarize_ticket_set(extracted)
        except Exception as exc:
            result["summary_error"] = str(exc)

    if include_risk:
        try:
            risk = ai_enhancer.rate_release_risk(extracted)
            result["risk"] = risk.to_dict()
        except Exception as exc:
            result["risk_error"] = str(exc)

    if include_criteria:
        try:
            criteria = []
            for ticket in (extracted or [])[:5]:
                ticket_criteria = ai_enhancer.generate_acceptance_criteria_for_ticket(ticket)
                criteria.append({
                    "ticket_key": ticket.get("key", "unknown"),
                    "criteria": ticket_criteria,
                })
            result["acceptance_criteria"] = criteria
        except Exception as exc:
            result["criteria_error"] = str(exc)

    return enrich_tool_response(result, tool="ai_enhance_release")


