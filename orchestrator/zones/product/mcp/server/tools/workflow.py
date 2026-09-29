"""MCP tools: workflow."""

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
def release_workflow_checkpoints(state: dict[str, Any] | None = None) -> dict:
    """Return release-critical workflow checkpoint flags (Platform/MCP parity).

    Pass a session-like mapping (shared_snapshot, shared_docx_generated,
    stk_created_key, etc.) or omit for an empty baseline.
    """
    import release_critical as rc

    payload = dict(state or {})
    return rc.workflow_checkpoints(payload)


@mcp.tool()
def validate_service_ticket(
    draft: dict[str, Any],
    *,
    standalone: bool = False,
    shared_docx_generated: bool = False,
    has_snapshot: bool = False,
    coverage_warnings: list[dict[str, Any]] | None = None,
    approver_validation: dict[str, Any] | None = None,
) -> dict:
    """Validate a service ticket draft with the same blockers/warnings as the Platform.

    ``draft`` uses Platform field names (stk_summary, stk_impl_plan, …) or MCP
    aliases (summary, implementation_plan, …). Returns structured validation
    matching release_wizard service_ticket preview.
    """
    import release_critical as rc

    state = {
        "stk_summary": draft.get("stk_summary") or draft.get("summary"),
        "stk_description_adf": draft.get("stk_description_adf") or draft.get("description_adf"),
        "stk_extracted": draft.get("stk_extracted") or draft.get("extracted") or [],
        "stk_impl_plan": draft.get("stk_impl_plan") or draft.get("implementation_plan"),
        "stk_test_plan": draft.get("stk_test_plan") or draft.get("test_plan"),
        "stk_backout_plan": draft.get("stk_backout_plan") or draft.get("backout_plan"),
        "stk_business_impact": draft.get("stk_business_impact") or draft.get("business_impact"),
        "stk_sharepoint": draft.get("stk_sharepoint") or draft.get("sharepoint"),
        "shared_sharepoint_url": draft.get("shared_sharepoint_url") or draft.get("sharepoint"),
        "stk_approvers": draft.get("stk_approvers") or draft.get("approvers"),
        "stk_approver_groups": draft.get("stk_approver_groups") or draft.get("approver_groups"),
        "stk_approver_validation": draft.get("stk_approver_validation") or approver_validation,
        "stk_planned_start_date": draft.get("stk_planned_start_date") or draft.get("planned_start_date"),
        "stk_planned_end_date": draft.get("stk_planned_end_date") or draft.get("planned_end_date"),
        "stk_planned_start_time": draft.get("stk_planned_start_time") or draft.get("planned_start_time"),
        "stk_planned_end_time": draft.get("stk_planned_end_time") or draft.get("planned_end_time"),
        "stk_schedule_tz": draft.get("stk_schedule_tz") or draft.get("schedule_timezone"),
        "shared_docx_generated": shared_docx_generated or draft.get("shared_docx_generated"),
        "shared_snapshot": draft.get("shared_snapshot"),
        "shared_stk_standalone_mode": standalone,
    }
    flags = rc.WorkflowFlags(service_ticket_standalone=standalone)
    report = rc.service_ticket_validation_report(
        state,
        flags=flags,
        coverage_warnings=coverage_warnings,
        approver_validation=approver_validation,
    )
    return report.to_dict()


@mcp.tool()
def release_recovery_status(
    platform_state: dict[str, Any] | None = None,
    workflow_id: str | None = None,
) -> dict:
    """Compare Platform draft recovery domains with an MCP wizard session.

    Supply ``platform_state`` (session-like dict) and/or ``workflow_id`` to
    inspect restart safety for snapshot, release notes, SharePoint, TCKT,
    Slack, Teams, and deploy progress.
    """
    from release_mcp import wizard_store
    from recovery_contract import (
        platform_recovery_snapshot,
        recovery_parity_ok,
        wizard_recovery_snapshot,
    )

    platform = platform_recovery_snapshot(platform_state or {})
    wizard = wizard_recovery_snapshot({})
    if workflow_id:
        session = wizard_store.load_session(workflow_id)
        if session:
            wizard = wizard_recovery_snapshot(session)
    return {
        "platform": platform.to_dict(),
        "wizard": wizard.to_dict(),
        "parity_ok": recovery_parity_ok(platform, wizard) if workflow_id else None,
    }


@mcp.tool()
def workspace_config(
    section: str | None = None,
) -> dict:
    """Read workspace configuration from workspace.yaml.

    Args:
        section: Optional section to read (e.g. "projects", "service_desk", "release_notes").
                 If not provided, returns the full workspace config.
    """
    import yaml

    ws_path = config.get_active_workspace_path()
    with open(ws_path, encoding="utf-8") as f:
        ws = yaml.safe_load(f) or {}
    workspace_data = ws.get("workspace", ws)

    if section:
        if section not in workspace_data:
            return enrich_tool_response({
                "status": "error",
                "error": f"Section '{section}' not found in workspace config.",
                "available_sections": list(workspace_data.keys()),
            }, tool="workspace_config")
        return enrich_tool_response({
            "status": "ok",
            "section": section,
            "data": workspace_data[section],
        }, tool="workspace_config")

    return enrich_tool_response({
        "status": "ok",
        "workspace_name": config.active_workspace_name() or "root",
        "data": workspace_data,
    }, tool="workspace_config")


