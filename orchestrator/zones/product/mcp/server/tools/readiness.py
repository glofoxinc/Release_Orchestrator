"""MCP tools: readiness."""

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
def mcp_production_readiness() -> dict:
    """Alias for production_readiness(surface=mcp). Say **production ready** in chat."""
    import production_readiness as pr

    return pr.assess_production_readiness(surface="mcp")


@mcp.tool()
def release_orchestrator(
    message: str = "welcome",
    workflow_id: str | None = None,
    confirmation_token: str | None = None,
) -> dict:
    """Release Orchestrator — easy guided E2E (platform parity). START HERE.

    User says **welcome** / **onboarding** / **start** → shows defaults and suggests
    Step 1 (fetch review-ready PIC + AN tickets for Glofox team). User says **yes** →
    fetch and lock flow continues step-by-step through release notes, SharePoint,
    SHIPIT, Slack announce, deploy.

    **You do NOT need to remember steps.** Every response includes:
    - say_to_user: plain text to show the user
    - user_can_say: suggested replies (yes, team override, exclude tickets, etc.)
    - workflow_id: pass on every follow-up call
    - step_number / step_title / roadmap

    **Onboarding flow:** First time? I'll ask for anything missing. Just say
    "onboarding" or "welcome" to start.

    **Team override:** user says "use Ignite" → call with message="use Ignite".
    **Version mode:** user says "version 2026.3.09.14" → switches to fix-version fetch.
    **Slack:** at Step 6 say "send slack" or "skip slack".

    One-time .env: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
    Optional: DEFAULT_JIRA_TEAM, DEFAULT_PROJECTS=PIC,AN, SLACK_BOT_TOKEN

    Args:
        message: Natural language — welcome, onboarding, yes, next, help, use Ignite, send slack, etc.
        workflow_id: From prior response; omit on first welcome
        confirmation_token: Usually auto-resolved when user says yes; pass if provided
    """
    from release_mcp import guided

    return guided.run_guided(
        message,
        workflow_id=workflow_id,
        confirmation_token=confirmation_token,
    )


@mcp.tool()
def release_wizard(
    action: str,
    workflow_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    confirmation_token: str | None = None,
) -> dict:
    """Advanced: low-level Release Orchestrator workflow (use release_orchestrator for guided E2E).

    This mirrors the web platform: Ticket Review and lock, exclusions, editable
    Word release notes, SharePoint handoff, editable TCKT Service Ticket,
    Slack send/skip, deployment comments and Done transitions, history, undo,
    and optional mark-released.

    Prefer release_orchestrator(message="welcome") for conversational flow.

    Standalone modes (set inputs.workflow_mode on start):
    - release_notes_only — DOCX + SharePoint without ticket-review lock
    - service_ticket_only — TCKT from version + SharePoint URL
    - deployer_only — post-deploy comments only

    Args:
        action: welcome, start, resume, status, update, confirm, back, cancel,
            list, history, or undo
        workflow_id: Returned by start; required for all workflow actions
        inputs: Step-specific answers/edits (workflow_mode, version, ticket
            selection, SharePoint URL, TCKT draft, Slack decision, deployment
            info, etc.)
        confirmation_token: Exact token returned by an awaiting_confirmation
            response; required only for confirm
    """
    from release_mcp import guided

    result = wizard.run_wizard(
        action,
        workflow_id=workflow_id,
        inputs=inputs,
        confirmation_token=confirmation_token,
    )
    if action.strip().lower() == "welcome" or (inputs or {}).get("guided"):
        return guided.enrich_response(result)
    return result

