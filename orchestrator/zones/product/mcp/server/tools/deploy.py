"""MCP tools: deploy."""

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
def deploy_preview(
    project_key: str,
    release_id: str,
    filled: dict[str, Any],
    selected_keys: list[str] | None = None,
    force_deploy: bool = False,
) -> dict:
    """Preview deployment comments for selected tickets (no Jira writes)."""
    import deploy_ops

    ctx = release_ops.resolve_deploy_execution_context(
        project_key,
        release_id,
        selected_keys=selected_keys,
    )
    return deploy_ops.preview_deploy(
        None,
        filled=filled,
        release=ctx["version"],
        project_key=ctx["project_key"],
        selected_keys=ctx["selected_keys"],
        issues=ctx["issues"],
        grouped=ctx["grouped"],
        multi_client=ctx["multi_client"],
        force_deploy=force_deploy,
        dry_run=True,
    )


@mcp.tool()
def deploy_execute(
    project_key: str,
    release_id: str,
    filled: dict[str, Any],
    selected_keys: list[str] | None = None,
    force_deploy: bool = False,
    dry_run: bool = False,
) -> dict:
    """Execute deployment comments and transitions for selected tickets."""
    import deploy_ops

    ctx = release_ops.resolve_deploy_execution_context(
        project_key,
        release_id,
        selected_keys=selected_keys,
    )
    return deploy_ops.execute_deploy(
        filled=filled,
        release=ctx["version"],
        project_key=ctx["project_key"],
        selected_keys=ctx["selected_keys"],
        issues=ctx["issues"],
        grouped=ctx["grouped"],
        multi_client=ctx["multi_client"],
        force_deploy=force_deploy,
        dry_run=dry_run,
    )


@mcp.tool()
def record_operator_signoff(signoff_id: str, detail: str = "") -> dict:
    """Record a one-time operator sign-off after a live check.

    Args:
        signoff_id: ``shipit_dry_run`` or ``slack_live_confirm``
        detail: Optional note (version, channel, date)
    """
    import operator_signoff as osign

    result = osign.record_signoff(signoff_id, detail=detail)
    if not result.get("ok"):
        return result
    import production_readiness as pr

    return {
        **result,
        "readiness": pr.assess_production_readiness(surface="both"),
    }


@mcp.tool()
def production_readiness(surface: str = "both") -> dict:
    """Production readiness — same report for MCP and platform.

    Returns VERIFIED / UNVERIFIED / OPERATOR REQUIRED, IST→CST schedule check,
    and Slack delivery mode (**cursor_slack_mcp** = no SLACK_BOT_TOKEN needed).

    Args:
        surface: ``mcp``, ``platform``, or ``both`` (default)
    """
    import production_readiness as pr

    key = surface.strip().lower() if surface else "both"
    if key not in {"mcp", "platform", "both"}:
        key = "both"
    return pr.assess_production_readiness(surface=key)  # type: ignore[arg-type]


