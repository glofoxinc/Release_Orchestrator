"""MCP tools: gates."""

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
def release_step_status(step_id: str = "") -> dict:
    """Per-step release guide — catalog, phrases, MCP tools, and readiness for one step.

    Pass empty ``step_id`` for the full 8-step map + onboarding status.
    Examples: ``ticket_review``, ``release_notes``, ``slack``, ``onboarding``.

    Use with ``release_orchestrator`` chat — user says the ``say_first`` phrase for each step.
    """
    from release_mcp.steps.step_tools import release_step_status as _status

    payload = _status(step_id)
    return enrich_tool_response(payload, tool="release_step_status")


@mcp.tool()
def release_gate_status() -> dict:
    """Status for pre-review and post-QA release gates (workspace.yaml release_gates)."""
    return gate_ops.release_gate_status()


@mcp.tool()
def pre_review_gate(
    version_name: str,
    projects: list[str] | None = None,
    notify: bool = False,
    dry_run: bool = True,
) -> dict:
    """Pre-review gate: hide non-review-ready tickets; optionally Slack assignees.

    Tickets whose Jira status is not in release_gates.pre_review.ready_statuses
    are held back from Ticket Review. Use notify=true to DM assignees (requires
    SLACK_BOT_TOKEN with im:write and users:read.email).

    Args:
        version_name: Fix version name (e.g. 2026.3.08.12)
        projects: Optional subset e.g. ["PIC", "AN"]
        notify: When true, send Slack DMs (respects dry_run)
        dry_run: Preview Slack messages without sending (default true)
    """
    return gate_ops.pre_review_gate(
        version_name,
        projects=projects,
        notify=notify,
        dry_run=dry_run,
    )


@mcp.tool()
def post_qa_gate(
    version_name: str,
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    notify: bool = False,
    dry_run: bool = True,
) -> dict:
    """Post-QA gate: find QA failures, build excluded-tickets text, Slack assignees.

    Tickets not in release_gates.post_qa.passed_statuses should be excluded from
    Release Notes and the release. Returns excluded_tickets_text for the DOCX section.

    Args:
        version_name: Fix version name
        projects: Optional project subset
        ticket_keys: Optional limit to specific keys (must already be scoped)
        notify: Send Slack DMs when true
        dry_run: Preview only (default true)
    """
    return gate_ops.post_qa_gate(
        version_name,
        projects=projects,
        ticket_keys=ticket_keys,
        notify=notify,
        dry_run=dry_run,
    )


@mcp.tool()
def generate_release_notes_docx(
    version_name: str,
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    output_path: str | None = None,
) -> dict:
    """Generate internal Release Notes Word .docx and a client-facing sibling.

    Internal file matches Streamlit. Client sibling is PIC/custom only, using the
    same Insights Cambria / navy / Grid Table 4 Accent 1 styling.

    Args:
        version_name: Fix version / release name (e.g. 2026.3.08.12)
        projects: Optional subset, e.g. ["PIC", "AN"] (default both)
        ticket_keys: Optional include-only ticket keys
        output_path: Optional full path for the .docx; otherwise writes under ./output/
    """
    return enrich_tool_response(
        release_ops.generate_release_notes_docx_file(
            version_name=version_name,
            projects=projects,
            ticket_keys=ticket_keys,
            output_path=output_path,
        ),
        tool="generate_release_notes_docx",
    )


@mcp.tool()
def generate_client_release_notes_docx(
    version_name: str,
    ticket_keys: list[str] | None = None,
    output_path: str | None = None,
    projects: list[str] | None = None,
) -> dict:
    """Generate client-facing Word notes for custom (PIC) clients only.

    Client language (not Jira tasks). Per-client: what changed, user impact,
    implementation, expected impact, validation. Ticket and fix-version
    hyperlinks on one References line. Tables share one left edge.
    Writes to Downloads when output_path is omitted.

    Args:
        version_name: Fix version / release name (e.g. 2026.4.10.15)
        ticket_keys: Optional include-only keys (AN keys are still dropped)
        output_path: Optional full .docx path; default is Downloads
        projects: Optional Jira projects (default PIC, then PIC+AN if PIC empty)
    """
    return enrich_tool_response(
        release_ops.generate_client_release_notes_docx_file(
            version_name=version_name,
            ticket_keys=ticket_keys,
            output_path=output_path,
            projects=projects,
        ),
        tool="generate_client_release_notes_docx",
    )


