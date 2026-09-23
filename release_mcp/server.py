"""MCP Server — Release Orchestrator agent surface (PIC + AN platform parity).

Tools provided:
- create_ticket: Create a Jira ticket from structured or NL input
- triage_ticket: Classify a ticket by component, priority, assignee
- search_tickets: Execute JQL search
- generate_release_notes: Text release-notes summary for one project/version
- fetch_release_tickets: Ticket list for a release version across PIC + AN
- generate_release_notes_docx: Same Word .docx as the web UI (style/format)
- create_service_ticket: Same TCKT Service Ticket flow; asks for SharePoint etc.
- sharepoint_upload_status / sharepoint_upload_release_notes: Graph upload backend
- teams_schedule_status / teams_schedule_meeting: Graph Teams meeting backend
- slack_announce_status / slack_preview / slack_send: deployment Slack announce
- slack_mcp_verify / slack_mcp_e2e_handoff / slack_reference: Cursor Slack MCP + message references
- onboarding_guide: first-time MCP setup, phrase cheat sheet, MCP catalog
- team_crew_status: one-time team + PIC/AN projects + review/release crew from .env
- pre_review_gate / post_qa_gate / release_gate_status: review-ready + QA gates
- release_orchestrator: Guided conversational E2E — say welcome, then yes (START HERE)
- daily_review_orchestrator: Guided Daily Review E2E — say daily review welcome
- daily_review_*: 6 PM PIC/AN review — attendee policy, schedule, preflight, live run, Outlook login
- release_wizard: Durable end-to-end UI-parity workflow with confirmations
- release_workflow_checkpoints / validate_service_ticket / release_recovery_status:
    Shared release-critical validation and recovery parity helpers

Run via: python -m release_mcp
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=True)

try:
    from mcp.server.mcpserver import MCPServer  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - interpreter dependent
    raise ModuleNotFoundError(
        "The MCP server requires mcp>=2.0.0, which provides "
        "'mcp.server.mcpserver'. The interpreter running this module has an "
        "older mcp (or none). Launch it with the project virtualenv "
        r"(.venv\Scripts\python.exe -m release_mcp) or install the pinned "
        "dependencies with 'pip install -r requirements.txt'."
    ) from exc

import config  # noqa: E402
import jira_client  # noqa: E402
from ai_ticket_creator import (  # noqa: E402
    build_jira_create_fields,
    parse_ticket_from_nl,
)
from ai_triage import triage_ticket as _triage_ticket  # noqa: E402
from common.logger import set_log_context, setup_logging  # noqa: E402
from release_mcp import (  # noqa: E402
    browser_ops,
    gate_ops,
    release_ops,
    sharepoint_ops,
    slack_mcp_ops,
    slack_ops,
    teams_ops,
    wizard,
)
from release_mcp.operator_guide import enrich_tool_response  # noqa: E402

setup_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
# Prefer stderr for MCP stdio transports so logs never corrupt the protocol stream.
for _handler in logging.getLogger().handlers:
    if isinstance(_handler, logging.StreamHandler):
        _handler.stream = sys.stderr

config.ensure_workspace_loaded()
set_log_context(workspace=config.active_workspace_name() or "root", surface="mcp")

mcp = MCPServer("release-ops")


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
    return _triage_ticket(ticket_text, project_key)


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
    payload = {
        **status,
        "hint": (
            "Not configured? Say **welcome onboard** → pick team (glofox/ignite/etl) "
            "→ **crew done** → paste `.env` snippet."
        ),
    }
    return enrich_tool_response(payload, tool="team_crew_status")


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
    """Generate the Release Notes Word .docx using the same generator as the web UI.

    Same style/format as Streamlit Release Notes. Writes a .docx and returns its path.

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


@mcp.tool()
def sharepoint_upload_status() -> dict:
    """Status for SharePoint release-notes upload (Graph backend).

    Safe without credentials. Reports enabled flag, folder/site target readiness,
    and whether MS_GRAPH_* env vars are set. Same backend as the platform UI
    (Release Notes Step 4 upload button).
    """
    return sharepoint_ops.sharepoint_upload_status()


@mcp.tool()
def sharepoint_upload_release_notes(
    local_path: str,
    remote_name: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Upload a release-notes .docx to the configured SharePoint folder.

    Defaults to dry_run=True (preview plan only). Live upload requires
    sharepoint_upload.enabled=true in workspace.yaml and MS_GRAPH_* credentials.
    Returns web_url for Service Ticket / Slack reuse when live upload succeeds.

    Args:
        local_path: Absolute or relative path to the .docx file
        remote_name: Optional SharePoint file name (defaults to local basename)
        dry_run: If true, return the upload plan without calling Graph
    """
    return sharepoint_ops.sharepoint_upload_release_notes(
        local_path,
        remote_name=remote_name,
        dry_run=dry_run,
    )


@mcp.tool()
def sharepoint_download_release_notes(
    web_url: str,
    output_path: str | None = None,
) -> dict:
    """Download a SharePoint Release Notes document and parse deployment rows.

    The parsed rows provide client deployment IDs, dates, and times for the
    post-deployment workflow. ``output_path`` is optional; omit it to avoid
    writing the document locally.
    """
    return sharepoint_ops.sharepoint_download_release_notes(
        web_url,
        output_path=output_path,
    )


@mcp.tool()
def browser_automation_status() -> dict:
    """Playwright + Slack MCP handoff readiness for SharePoint upload and Slack announce.

    Safe without credentials. Use when Graph upload is archived or SLACK_BOT_TOKEN
    is not set — the agent posts via Cursor Playwright MCP and/or Slack MCP instead.
    """
    return enrich_tool_response(
        browser_ops.browser_automation_status(),
        tool="browser_automation_status",
    )


@mcp.tool()
def sharepoint_playwright_handoff(
    local_path: str,
    version_name: str = "",
    remote_name: str | None = None,
) -> dict:
    """Return Playwright MCP steps to upload Release Notes .docx to SharePoint.

    Execute steps via Cursor **Playwright MCP** (user-playwright). Operator must be
    signed in to Microsoft 365 in the Playwright browser profile. After upload,
    paste the document URL into the workflow (sharepoint_url).

    Args:
        local_path: Path to generated Release Notes .docx
        version_name: Fix version for remote file name (e.g. 2026.3.09.14)
        remote_name: Optional override file name on SharePoint
    """
    return enrich_tool_response(
        browser_ops.sharepoint_playwright_handoff(
            local_path,
            version_name=version_name,
            remote_name=remote_name,
        ),
        tool="sharepoint_playwright_handoff",
    )


@mcp.tool()
def slack_playwright_handoff(
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
    message_edits: dict[str, str] | None = None,
) -> dict:
    """Return Playwright MCP steps to post deployment announce to both Slack channels.

    Fallback when Slack MCP is unavailable. Prefer ``slack_preview`` +
    Cursor **Slack MCP** ``slack_send_message`` when connected. Includes both
    #insights-customize-squad and #customize-bi-buddies from workspace.yaml.

    Args:
        ticket_key: SHIPIT key (e.g. SHIPIT-17036)
        summary: Service ticket summary
        ticket_url: Jira browse URL
        version_name: Release version
        sharepoint_url: Release Notes SharePoint link
        deploy_date: ISO date YYYY-MM-DD
        environments: Environment label in message body
        message_edits: Optional per-channel message overrides (key → text)
    """
    return enrich_tool_response(
        browser_ops.slack_playwright_handoff(
            ticket_key=ticket_key,
            summary=summary,
            ticket_url=ticket_url,
            version_name=version_name,
            sharepoint_url=sharepoint_url,
            deploy_date=deploy_date,
            environments=environments,
            message_edits=message_edits,
        ),
        tool="slack_playwright_handoff",
    )


@mcp.tool()
def teams_schedule_status() -> dict:
    """Status for Teams review/deployment meeting scheduling (Graph backend).

    Safe without credentials. Reports enabled flag, organizer, defaults, and
    whether MS_GRAPH_* env vars are set. Same backend as the platform UI
    Teams panels in Ticket Review and Service Ticket.
    """
    return teams_ops.teams_schedule_status()


@mcp.tool()
def teams_schedule_meeting(
    kind: str,
    start: str,
    subject: str = "",
    end: str | None = None,
    timezone_name: str | None = None,
    attendees: list[dict] | None = None,
    body: str = "",
    version: str = "",
    dry_run: bool = True,
) -> dict:
    """Schedule a Teams meeting for ticket review or deployment.

    Defaults to dry_run=True (returns Graph calendar payload only). Live create
    requires teams_schedule.enabled=true, organizer_upn, and MS_GRAPH_* credentials.

    Args:
        kind: 'review' or 'deployment'
        start: ISO datetime (YYYY-MM-DDTHH:MM:SS or with offset)
        subject: Meeting subject (auto-built from kind/version when empty)
        end: Optional ISO end datetime (defaults from workspace durations)
        timezone_name: IANA zone (defaults to teams_schedule.default_timezone)
        attendees: Optional list of {email, name?, type?} (else workspace defaults)
        body: Optional HTML/text body
        version: Optional release version for default subject/body
        dry_run: If true, preview payload without calling Graph
    """
    return teams_ops.teams_schedule_meeting(
        kind=kind,
        start=start,
        subject=subject,
        end=end,
        timezone_name=timezone_name,
        attendees=attendees,
        body=body,
        version=version,
        dry_run=dry_run,
    )


@mcp.tool()
def teams_update_meeting(
    event_id: str,
    kind: str,
    start: str,
    subject: str = "",
    end: str | None = None,
    timezone_name: str | None = None,
    attendees: list[dict] | None = None,
    body: str = "",
    version: str = "",
    dry_run: bool = True,
) -> dict:
    """Update/reschedule an existing Teams meeting (Graph PATCH)."""
    return teams_ops.teams_update_meeting(
        event_id=event_id,
        kind=kind,
        start=start,
        subject=subject,
        end=end,
        timezone_name=timezone_name,
        attendees=attendees,
        body=body,
        version=version,
        dry_run=dry_run,
    )


@mcp.tool()
def teams_cancel_meeting(event_id: str, dry_run: bool = True) -> dict:
    """Cancel/delete a scheduled Teams calendar event."""
    return teams_ops.teams_cancel_meeting(event_id=event_id, dry_run=dry_run)


@mcp.tool()
def slack_announce_status() -> dict:
    """Status for deployment Slack announce (Bot API backend).

    Safe without credentials. Reports enabled flag, channel targets, CC
    requirements, and whether SLACK_BOT_TOKEN is set. Same backend as the
    Service Ticket Slack panel and release_wizard slack step.
    """
    return slack_ops.slack_announce_status()


@mcp.tool()
def slack_preview(
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
    edits: dict[str, str] | None = None,
) -> dict:
    """Build deployment Slack channel previews without sending.

    Args:
        ticket_key: Created TCKT key (e.g. TCKT-123)
        summary: Service ticket summary line
        ticket_url: Browse URL for the TCKT
        version_name: Release version string (e.g. v2026.3.08.05)
        sharepoint_url: Link to Release Notes .docx on SharePoint
        deploy_date: ISO date (YYYY-MM-DD) for the deployment window
        environments: Environment label in the message body
        edits: Optional per-channel body overrides keyed by channel key/name
    """
    preview = slack_ops.build_slack_preview(
        ticket_key=ticket_key,
        summary=summary,
        ticket_url=ticket_url,
        version_name=version_name,
        sharepoint_url=sharepoint_url,
        deploy_date=deploy_date,
        environments=environments,
    )
    if edits:
        preview = slack_ops.apply_slack_message_edits(preview, edits)
    return browser_ops.enrich_slack_preview(preview)


@mcp.tool()
def slack_send(
    preview: dict,
    skip_channel_keys: list[str] | None = None,
) -> dict:
    """Send a slack_preview payload to configured channels.

    Requires slack_announce.enabled=true and SLACK_BOT_TOKEN. Use
    skip_channel_keys to retry only failed channels after a partial send.
    """
    return slack_ops.send_slack_preview(preview, skip_channel_keys=skip_channel_keys or [])


@mcp.tool()
def slack_mcp_verify(
    channel_checks: list[dict[str, Any]] | None = None,
    user_checks: list[dict[str, Any]] | None = None,
    refresh_probes: bool = False,
) -> dict:
    """Verify Cursor Slack MCP readiness for Step 6 deployment announce.

    Reports configured channel IDs, CC user IDs, MCP accessibility probes,
    and blockers. Pass ``channel_checks`` / ``user_checks`` after probing with
    Cursor Slack MCP (``slack_read_channel``, ``slack_search_users``).

    Args:
        channel_checks: Optional list of {name, channel_id, accessible, error}
        user_checks: Optional list of {key, name, configured_user_id, resolved_user_id, match}
        refresh_probes: When true, ignore cached probe results (offline config only)
    """
    return enrich_tool_response(
        slack_mcp_ops.slack_mcp_verify(
            channel_checks=channel_checks,
            user_checks=user_checks,
            refresh_probes=refresh_probes,
        ),
        tool="slack_mcp_verify",
    )


@mcp.tool()
def slack_mcp_e2e_handoff(
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
    message_edits: dict[str, str] | None = None,
) -> dict:
    """Full Step 6 E2E: Slack MCP verify + preview + ready-to-post payloads.

    Returns verification blockers, both channel message previews, and
    ``slack_mcp.posts`` for Cursor ``slack_send_message``. Same message copy
    as ``slack_preview``; adds MCP access checklist.
    """
    return enrich_tool_response(
        slack_mcp_ops.slack_mcp_e2e_handoff(
            ticket_key=ticket_key,
            summary=summary,
            ticket_url=ticket_url,
            version_name=version_name,
            sharepoint_url=sharepoint_url,
            deploy_date=deploy_date,
            environments=environments,
            message_edits=message_edits,
        ),
        tool="slack_mcp_e2e_handoff",
    )


@mcp.tool()
def onboarding_guide() -> dict:
    """First-time onboarding — MCP catalog, phrase cheat sheet, setup checklist.

    Safe without credentials. New colleagues: read ``intro``, enable MCPs in
    ``mcp_catalog``, then say **welcome onboard** in ``release_orchestrator``.
    Covers Jira .env, Release Orchestrator MCP, Slack MCP, Playwright MCP,
    and every chat phrase per release step.
    """
    from release_mcp import onboarding

    assessment = onboarding.assess_setup(from_mcp=True)
    payload = onboarding.full_onboarding_guide(assessment=assessment)
    return enrich_tool_response(payload, tool="onboarding_guide")


@mcp.tool()
def onboarding_wizard(message: str = "welcome onboard") -> dict:
    """Beginner linear onboarding — one step at a time, auto-install where possible.

    Say **welcome onboard**, then **`continue`** after each step. Auto-runs venv, pip,
    `.env` template, and MCP merge (generic template — no personal paths).

    Args:
        message: welcome onboard, continue, release only, use glofox, env inputs, etc.
    """
    from release_mcp import beginner_wizard

    payload = beginner_wizard.process_message(message)
    return enrich_tool_response(payload, tool="onboarding_wizard")


@mcp.tool()
def install_mcp_config(track: str = "release") -> dict:
    """Merge Release Orchestrator + Playwright MCP blocks into Cursor mcp.json.

    Uses detected repo paths — no hard-coded usernames. Backs up existing mcp.json.
    Reload Cursor MCP after this tool returns ok.

    Args:
        track: release, daily_review, or both (adds teams server when both).
    """
    from release_mcp import mcp_installer

    key = (track or "release").strip().lower()
    if key not in {"release", "daily_review", "both"}:
        key = "release"
    result = mcp_installer.merge_starter_servers(track=key, backup=True)
    return enrich_tool_response(result, tool="install_mcp_config")


@mcp.tool()
def onboarding_env(message: str = "") -> dict:
    """Natural-language `.env` onboarding — parse chat inputs and show required params.

    Users can say random phrases (org name, email, use glofox, projects pic an).
    The tool writes recognized keys to local ``.env`` and returns what is still missing.

    Args:
        message: Free-form chat, or empty for full checklist. Examples:
            ``env checklist``, ``org is abcfinancial``, ``email you@abcfitness.com``,
            ``use glofox``, ``projects pic an``.
    """
    from release_mcp import env_onboarding as env_ob

    if not (message or "").strip():
        payload = {
            "prompt": env_ob.format_env_checklist(),
            "status": env_ob.assess_env_params(),
        }
    else:
        payload = env_ob.process_env_message(message)
    return enrich_tool_response(payload, tool="onboarding_env")


@mcp.tool()
def slack_reference(reference_key: str = "") -> dict:
    """Operator-approved Slack deployment announce references (SHIPIT-17191 gold standard).

    Returns per-channel example messages, CC rules, body structure, and parity
    check when the engine re-renders the reference ticket. Use before Step 6
    live post so copy matches squad vs buddies format.

    Args:
        reference_key: Optional SHIPIT key (default SHIPIT-17191). Empty = full status.
    """
    return enrich_tool_response(
        slack_mcp_ops.slack_reference(reference_key=reference_key),
        tool="slack_reference",
    )


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

    return deploy_ops.preview_deploy(
        None,
        filled=filled,
        release={"id": release_id, "name": release_id},
        project_key=project_key,
        selected_keys=selected_keys,
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

    return deploy_ops.execute_deploy(
        filled=filled,
        release={"id": release_id, "name": release_id},
        project_key=project_key,
        selected_keys=selected_keys,
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


from release_mcp import daily_review_ops  # noqa: E402
from release_mcp.steps.register import register_release_step_tools  # noqa: E402

register_release_step_tools(mcp, enrich=enrich_tool_response)
daily_review_ops.register(mcp)


def main() -> None:
    """Run the MCP server via stdio transport."""
    mcp.run(transport="stdio")
