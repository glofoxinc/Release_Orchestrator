"""MCP tools: jira."""

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
def create_ticket(
    project_key: str,
    description: str,
    summary: str | None = None,
    issue_type: str | None = None,
    priority: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Create a Jira ticket from a natural-language description.

    Parses the description to extract summary, type, priority, and component.
    Set dry_run=True to preview without creating in Jira.

    Args:
        project_key: Jira project key (e.g. PIC, AN, TCKT)
        description: Natural-language description of the ticket to create
        summary: Optional explicit summary (overrides NL parsing)
        issue_type: Optional issue type override (Bug, Task, Story)
        priority: Optional priority override (Highest, High, Medium, Low, Lowest)
        dry_run: If true, parse only without creating in Jira
    """
    from ai_ticket_creator import build_jira_create_fields, parse_ticket_from_nl

    parsed = parse_ticket_from_nl(description, project_key)
    if summary:
        parsed["summary"] = summary
    if issue_type:
        parsed["issue_type"] = issue_type
    if priority:
        parsed["priority"] = priority

    if dry_run:
        return {
            "key": None,
            "url": None,
            "fields": parsed,
            "dry_run": True,
            "triage": parsed.get("triage"),
        }

    resolved_type_id = jira_client.resolve_issue_type_id(
        project_key,
        parsed["issue_type"],
    )
    create_fields = build_jira_create_fields(parsed, project_key)
    created = jira_client.create_issue(
        project_key=project_key,
        issue_type_id=resolved_type_id,
        summary=parsed["summary"],
        fields=create_fields,
    )
    ticket_key = created.get("key", "")
    base_url = config.JIRA_BASE_URL.rstrip("/")
    return {
        "key": ticket_key,
        "url": f"{base_url}/browse/{ticket_key}" if ticket_key else "",
        "fields": parsed,
        "jira_fields": create_fields,
        "triage": parsed.get("triage"),
    }


@mcp.tool()
def triage_ticket(ticket_text: str, project_key: str) -> dict:
    """Classify a ticket by component, priority, and suggest an assignee.

    Uses rule-based keyword matching as primary engine. Enhances with LLM
    when OPENAI_API_KEY or AZURE_OPENAI_API_KEY is configured.

    Args:
        ticket_text: The ticket summary and/or description text to classify
        project_key: Jira project key for context
    """
    from ai_triage import triage_ticket

    return triage_ticket(ticket_text, project_key)


@mcp.tool()
def search_tickets(
    jql: str,
    max_results: int = 50,
    fields: list[str] | None = None,
) -> dict:
    """Search Jira tickets using JQL query syntax.

    Args:
        jql: JQL query string (e.g. "project = PIC AND status = Open")
        max_results: Maximum number of results (default 50)
        fields: Fields to return (default: summary, status, assignee, priority)
    """
    if fields is None:
        fields = ["summary", "status", "assignee", "priority"]

    all_issues: list[dict] = []
    next_token: str | None = None

    while len(all_issues) < max_results:
        body: dict[str, Any] = {
            "jql": jql,
            "maxResults": min(100, max_results - len(all_issues)),
            "fields": fields,
        }
        if next_token:
            body["nextPageToken"] = next_token

        data = jira_client._post("/search/jql", body)
        all_issues.extend(data.get("issues", []))

        next_token = data.get("nextPageToken")
        if not next_token:
            break

    return {
        "total_found": len(all_issues),
        "issues": [
            {
                "key": iss.get("key"),
                "summary": iss.get("fields", {}).get("summary"),
                "status": iss.get("fields", {}).get("status", {}).get("name"),
                "assignee": (iss.get("fields", {}).get("assignee") or {}).get("displayName"),
                "priority": (iss.get("fields", {}).get("priority") or {}).get("name"),
            }
            for iss in all_issues
        ],
    }


