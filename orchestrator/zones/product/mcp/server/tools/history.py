"""MCP tools: history."""

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
def tckt_history(
    limit: int = 50,
    search: str | None = None,
    status: str | None = None,
) -> dict:
    """Query TCKT deployment ticket history for the current user.

    Args:
        limit: Maximum number of tickets to return (default 50)
        search: Optional search term to filter by summary
        status: Optional status filter (e.g. "Resolved", "Closed")
    """
    if not config.TCKT_PROJECT_KEY:
        return enrich_tool_response({
            "status": "error",
            "error": "TCKT project not configured. Set TCKT_PROJECT_KEY in workspace.yaml.",
        }, tool="tckt_history")

    try:
        tickets = jira_client.search_my_service_desk_tickets(
            config.TCKT_PROJECT_KEY, max_results=limit
        )
    except Exception as exc:
        return enrich_tool_response({
            "status": "error",
            "error": f"Failed to fetch TCKT history: {exc}",
        }, tool="tckt_history")

    results = []
    for ticket in tickets:
        fields = ticket.get("fields", {})
        summary = fields.get("summary", "")
        status_name = fields.get("status", {}).get("name", "")

        if search and search.lower() not in summary.lower():
            continue
        if status and status.lower() != status_name.lower():
            continue

        results.append({
            "key": ticket.get("key"),
            "summary": summary,
            "status": status_name,
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "url": f"{config.JIRA_BASE_URL}/browse/{ticket.get('key')}",
        })

    return enrich_tool_response({
        "status": "ok",
        "count": len(results),
        "tickets": results[:limit],
    }, tool="tckt_history")


@mcp.tool()
def deployment_metrics(
    days: int = 30,
) -> dict:
    """Get DORA-style deployment metrics from local deployment history.

    Args:
        days: Number of days to include in metrics (default 30)
    """
    import deployment_history
    from datetime import datetime, timedelta

    try:
        history = deployment_history.load_history()
    except deployment_history.HistoryLoadError as exc:
        return enrich_tool_response({
            "status": "error",
            "error": str(exc),
        }, tool="deployment_metrics")

    if not history:
        return enrich_tool_response({
            "status": "ok",
            "message": "No deployment history found.",
            "metrics": {},
        }, tool="deployment_metrics")

    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for entry in history:
        ts_str = entry.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts >= cutoff:
                recent.append(entry)
        except (ValueError, TypeError):
            continue

    total_deployments = len(recent)
    total_tickets = sum(
        sum(len(c.get("tickets", [])) for c in e.get("clients", {}).values())
        for e in recent
    )
    total_success = sum(e.get("success", 0) for e in recent)
    total_errors = sum(e.get("errors", 0) for e in recent)
    total_skipped = sum(e.get("skipped", 0) for e in recent)

    success_rate = (total_success / (total_success + total_errors) * 100) if (total_success + total_errors) > 0 else 0

    frequency_per_week = total_deployments / (days / 7) if days > 0 else 0

    return enrich_tool_response({
        "status": "ok",
        "period_days": days,
        "metrics": {
            "total_deployments": total_deployments,
            "total_tickets": total_tickets,
            "total_success": total_success,
            "total_errors": total_errors,
            "total_skipped": total_skipped,
            "success_rate_percent": round(success_rate, 1),
            "deployments_per_week": round(frequency_per_week, 2),
        },
    }, tool="deployment_metrics")


@mcp.tool()
def verify_linked_tickets(
    ticket_keys: list[str],
    expected_states: list[str] | None = None,
    apply_label: str | None = None,
    require_acceptance_criteria: bool = True,
) -> dict:
    """Verify linked tickets before deployment.

    Checks that all referenced tickets are in expected states, have summaries,
    and optionally have acceptance criteria. Can also apply a release label.

    Args:
        ticket_keys: List of Jira ticket keys to verify (e.g. ["PIC-123", "AN-456"])
        expected_states: List of acceptable states (defaults to Done, Closed, etc.)
        apply_label: If provided, apply this label to passing tickets
        require_acceptance_criteria: Whether to require acceptance criteria (default True)
    """
    import linked_ticket_verifier as ltv

    states = tuple(expected_states) if expected_states else ltv.DEFAULT_EXPECTED_STATES

    report = ltv.verify_tickets(
        ticket_keys,
        fetch=jira_client.get_issue,
        expected_states=states,
        require_acceptance_criteria=require_acceptance_criteria,
    )

    result = report.to_dict()
    result["summary"] = ltv.human_summary(report)

    if apply_label and report.all_ok:
        def update_label(key: str, label: str) -> None:
            jira_client.add_label(key, label)

        labelled = ltv.apply_release_label(
            report, label=apply_label, label_update=update_label
        )
        result["labelled_tickets"] = labelled
        result["label_applied"] = apply_label

    return enrich_tool_response(result, tool="verify_linked_tickets")


@mcp.tool()
def list_tckt_templates() -> dict:
    """List all available TCKT ticket templates (built-in + user-defined).

    Returns template names, descriptions, and tags for each available preset.
    """
    import template_library

    templates = template_library.list_templates()
    return enrich_tool_response({
        "status": "ok",
        "templates": [
            {
                "name": t.name,
                "description": t.description,
                "tags": t.tags,
                "data_keys": list(t.data.keys()),
            }
            for t in templates
        ],
        "count": len(templates),
    }, tool="list_tckt_templates")


@mcp.tool()
def apply_tckt_template(
    name: str,
    draft: dict[str, Any],
    overwrite: bool = False,
) -> dict:
    """Apply a template to a TCKT draft, filling in preset values.

    Args:
        name: Template name (from list_tckt_templates)
        draft: Current draft dict to merge template values into
        overwrite: If true, replace existing values; if false, only fill empty fields
    """
    import template_library

    try:
        template = template_library.load_template(name)
    except KeyError:
        return enrich_tool_response({
            "status": "error",
            "error": f"Template '{name}' not found.",
        }, tool="apply_tckt_template")

    merged = template_library.apply_template(draft, template, overwrite=overwrite)
    return enrich_tool_response({
        "status": "ok",
        "template_name": name,
        "applied_fields": list(template.data.keys()),
        "merged_draft": merged,
    }, tool="apply_tckt_template")


@mcp.tool()
def save_tckt_template(
    name: str,
    draft: dict[str, Any],
    description: str = "",
    tags: list[str] | None = None,
) -> dict:
    """Save the current TCKT draft as a reusable template.

    Args:
        name: Template name (alphanumeric, hyphens, underscores only)
        draft: Draft dict to capture as template
        description: Human-readable description of this template
        tags: List of tags for categorization
    """
    import template_library

    try:
        template = template_library.capture_from_draft(
            name, draft, description=description, tags=tags
        )
        path = template_library.save_template(template)
        return enrich_tool_response({
            "status": "ok",
            "name": template.name,
            "path": str(path),
            "captured_fields": list(template.data.keys()),
        }, tool="save_tckt_template")
    except (ValueError, FileExistsError) as exc:
        return enrich_tool_response({
            "status": "error",
            "error": str(exc),
        }, tool="save_tckt_template")


