"""MCP tools: service ticket."""

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
def create_service_ticket(
    version_name: str,
    sharepoint_url: str | None = None,
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    planned_start_date: str | None = None,
    planned_end_date: str | None = None,
    planned_start_time: str | None = None,
    planned_end_time: str | None = None,
    schedule_timezone: str | None = None,
    dry_run: bool = True,
    test_mode: bool | None = None,
    extracted_override: list[dict] | None = None,
    draft_overrides: dict[str, str | list | dict | None] | None = None,
    post_create_overrides: dict[str, bool | str | None] | None = None,
    shipit_owner_account_id: str | None = None,
) -> dict:
    """Create a SHIPIT Manual Change ticket the same way the Release Orchestrator web UI does.

    Covers PIC + AN tickets for the given release version, builds ADF description
    and plans, and uses Service Desk defaults from workspace.yaml.

    If sharepoint_url or version_name is missing, returns status=needs_input with
    questions the agent must ask the user before continuing.

    Defaults to dry_run=true (preflight only). Pass dry_run=false only after the
    user confirms.

    Args:
        version_name: Fix version (e.g. 2026.3.08.12)
        sharepoint_url: SharePoint link to Release Notes .docx (required to create)
        projects: Optional subset of PIC/AN
        ticket_keys: Optional include-only keys
        planned_start_date: YYYY-MM-DD (defaults from version date)
        planned_end_date: YYYY-MM-DD
        planned_start_time: HH:MM in IST (default 10:30 from deployment profile)
        planned_end_time: HH:MM in IST (default 11:30; Jira fields store CST/CDT)
        schedule_timezone: IANA zone (default America/Chicago from workspace.yaml)
        dry_run: If true, validate and preview without creating in Jira
        test_mode: When true, skip team/approver defaults (auto-detected from TEST summary)
        extracted_override: Optional ticket rows for demo/test without fetching Jira version
        draft_overrides: Optional summary/plan/approver field overrides
        post_create_overrides: Optional SHIPIT post-create flags (link_release_tickets,
            transition_status, assign_to_creator, enabled, link_type)
        shipit_owner_account_id: Optional Atlassian accountId for assignee (defaults to API user)
    """
    return enrich_tool_response(
        release_ops.create_service_ticket(
            version_name=version_name,
            sharepoint_url=sharepoint_url,
            projects=projects,
            ticket_keys=ticket_keys,
            planned_start_date=planned_start_date,
            planned_end_date=planned_end_date,
            planned_start_time=planned_start_time,
            planned_end_time=planned_end_time,
            schedule_timezone=schedule_timezone,
            dry_run=dry_run,
            test_mode=test_mode,
            extracted_override=extracted_override,
            draft_overrides=draft_overrides,
            post_create_overrides=post_create_overrides,
            shipit_owner_account_id=shipit_owner_account_id,
        ),
        tool="create_service_ticket",
    )


@mcp.tool()
def dispose_test_shipit_ticket(
    issue_key: str,
    comment: str | None = None,
) -> dict:
    """Comment, cancel, and delete a TEST/demo SHIPIT (DO NOT DEPLOY summaries only).

    Args:
        issue_key: SHIPIT key (e.g. SHIPIT-17076)
        comment: Optional closing comment (default explains demo/test)
    """
    return enrich_tool_response(
        release_ops.dispose_test_shipit_ticket(issue_key, comment=comment),
        tool="dispose_test_shipit_ticket",
    )


