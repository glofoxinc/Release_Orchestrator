"""MCP tools: release."""

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
def generate_release_notes(project_key: str, version_name: str) -> dict:
    """[DEPRECATED] Legacy plain-text summary for one project/version.

    Use generate_release_notes_docx for platform-parity Word output, or
    release_wizard with workflow_mode=release_notes_only for the guided flow.

    Args:
        project_key: Jira project key (e.g. PIC, AN)
        version_name: Version/release name to generate notes for
    """
    versions = jira_client.get_project_versions(project_key)
    target_version = None
    for v in versions:
        if v.get("name", "").strip().lower() == version_name.strip().lower():
            target_version = v
            break

    if not target_version:
        available = [v.get("name") for v in versions[:10]]
        return enrich_tool_response(
            {
                "deprecated": True,
                "use_instead": "generate_release_notes_docx",
                "error": f"Version '{version_name}' not found in project {project_key}",
                "available_versions": available,
            },
            tool="generate_release_notes",
        )

    issues = jira_client.get_issues_for_version(project_key, target_version["id"])

    notes_by_type: dict[str, list[str]] = {}
    for iss in issues:
        iss_fields = iss.get("fields", {})
        itype = iss_fields.get("issuetype", {}).get("name", "Other")
        iss_summary = iss_fields.get("summary", "No summary")
        key = iss.get("key", "?")
        notes_by_type.setdefault(itype, []).append(f"{key}: {iss_summary}")

    return enrich_tool_response(
        {
            "deprecated": True,
            "use_instead": "generate_release_notes_docx",
            "project": project_key,
            "version": version_name,
            "version_id": target_version["id"],
            "released": target_version.get("released", False),
            "release_date": target_version.get("releaseDate"),
            "total_tickets": len(issues),
            "notes_by_type": notes_by_type,
        },
        tool="generate_release_notes",
    )


@mcp.tool()
def fetch_release_tickets(
    version_name: str = "",
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    selection_mode: str = "fix_version",
    statuses_by_project: dict[str, list[str]] | None = None,
    jira_team_ids_by_project: dict[str, list[str]] | None = None,
) -> dict:
    """Fetch the PIC + AN ticket list (fix version or by status).

    Defaults to all workspace projects (PIC and AN). For status-only releases,
    pass selection_mode=\"status\" and statuses_by_project instead of version_name.

    Args:
        version_name: Fix version / release name (e.g. 2026.3.08.12)
        projects: Optional subset, e.g. ["PIC", "AN"]
        ticket_keys: Optional filter to specific issue keys
        selection_mode: \"fix_version\" or \"status\"
        statuses_by_project: e.g. {\"PIC\": [\"Review\"], \"AN\": [\"Passed QA\"]}
        jira_team_ids_by_project: Optional team filter IDs per project
    """
    return release_ops.fetch_release_tickets(
        version_name=version_name,
        projects=projects,
        ticket_keys=ticket_keys,
        selection_mode=selection_mode,
        statuses_by_project=statuses_by_project,
        jira_team_ids_by_project=jira_team_ids_by_project,
    )


@mcp.tool()
def team_scope_status(project_key: str, version_id: str = "") -> dict:
    """Preflight a project's team ticket scope (board/filter/JQL).

    Returns configured/invalid/blocking state, fingerprint, optional sample keys,
    and effective JQL template. Ticket fetches fail closed until scope is valid.

    Args:
        project_key: Jira project key (e.g. PIC, AN)
        version_id: Optional fix version id to include in preflight count
    """
    return release_ops.team_scope_status(project_key, version_id=version_id)


@mcp.tool()
def team_crew_status() -> dict:
    """One-time team setup status — Jira team, PIC/AN projects, review/release crew.

    Reads ``DEFAULT_JIRA_TEAM``, ``DEFAULT_PROJECTS``, and ``TEAM_CREW_*`` from `.env`.
    Used for review calls, release calls, QA routing, and Teams meeting default attendees.
    Safe without Jira credentials. During onboard say **crew status** or **use glofox**.
    """
    import team_crew as tc

    status = tc.team_crew_status()
    import program_pack as pp

    payload = {
        **status,
        "program": pp.program_context(),
        "programs": pp.list_programs(),
        "hint": (
            "Active program pack is isolated (Glofox vs Ignite vs ETL). "
            "Glofox is trained. Do not copy Glofox crew into Ignite. "
            "Say **use glofox** / call train_program(program='glofox'). "
            "Ignite stays empty until trained on its own roster."
        ),
    }
    return enrich_tool_response(payload, tool="team_crew_status")


