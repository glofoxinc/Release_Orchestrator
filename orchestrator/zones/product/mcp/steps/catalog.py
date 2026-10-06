"""Release step catalog — maps step IDs to MCP tools, phrases, and platform parity."""

from __future__ import annotations

from typing import Any

from release_mcp import step_ux

# Step id → primary MCP tools (direct or via release_orchestrator)
RELEASE_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "onboarding",
        "number": "setup",
        "title": "First-time onboard",
        "user_phrases": ["welcome onboard", "done", "use glofox", "crew done", "crew status"],
        "mcp_tools": ["onboarding_guide", "team_crew_status", "release_orchestrator"],
        "required_mcps": ["release-orchestrator", "slack"],
    },
    {
        "id": "ticket_review",
        "number": "1",
        "title": "Ticket review — fetch & lock",
        "user_phrases": ["yes", "full release", "exclude PIC-1234"],
        "mcp_tools": ["release_orchestrator", "fetch_release_tickets", "pre_review_gate", "team_scope_status"],
        "required_mcps": ["release-orchestrator"],
    },
    {
        "id": "exclusions",
        "number": "2",
        "title": "Exclusions",
        "user_phrases": ["yes", "exclude AN-1234"],
        "mcp_tools": ["release_orchestrator", "release_wizard"],
        "required_mcps": ["release-orchestrator"],
    },
    {
        "id": "release_date_confirm",
        "number": "2b",
        "title": "Release date confirm",
        "user_phrases": ["yes", "2026.3.09.18"],
        "mcp_tools": ["release_orchestrator", "release_wizard"],
        "required_mcps": ["release-orchestrator"],
    },
    {
        "id": "release_notes",
        "number": "3",
        "title": "Release notes DOCX",
        "user_phrases": ["yes", "yes generate docx"],
        "mcp_tools": ["release_orchestrator", "generate_release_notes_docx", "generate_release_notes"],
        "required_mcps": ["release-orchestrator"],
    },
    {
        "id": "sharepoint",
        "number": "4",
        "title": "SharePoint upload",
        "user_phrases": ["upload sharepoint", "sharepoint done"],
        "mcp_tools": [
            "release_orchestrator",
            "sharepoint_playwright_handoff",
            "browser_automation_status",
            "sharepoint_upload_release_notes",
            "sharepoint_upload_status",
        ],
        "required_mcps": ["release-orchestrator", "playwright"],
    },
    {
        "id": "service_ticket",
        "number": "5",
        "title": "SHIPIT service ticket",
        "user_phrases": ["yes", "emergency deployment"],
        "mcp_tools": ["release_orchestrator", "create_service_ticket", "validate_service_ticket"],
        "required_mcps": ["release-orchestrator"],
    },
    {
        "id": "slack",
        "number": "6",
        "title": "Slack announce",
        "user_phrases": ["send slack", "slack done", "skip slack"],
        "mcp_tools": [
            "release_orchestrator",
            "slack_mcp_e2e_handoff",
            "slack_playwright_handoff",
            "slack_mcp_verify",
            "slack_reference",
            "slack_preview",
        ],
        "required_mcps": ["release-orchestrator", "slack", "playwright"],
    },
    {
        "id": "teams_meeting",
        "number": "5b",
        "title": "Teams / Outlook meeting (optional)",
        "user_phrases": ["schedule review call", "calendar done"],
        "mcp_tools": [
            "teams_playwright_handoff",
            "teams_schedule_meeting",
            "teams_schedule_status",
            "browser_automation_status",
        ],
        "required_mcps": ["release-orchestrator", "playwright"],
    },
    {
        "id": "deploy",
        "number": "7",
        "title": "Deploy comments + Done",
        "user_phrases": ["yes deploy", "yes"],
        "mcp_tools": ["release_orchestrator", "release_wizard"],
        "required_mcps": ["release-orchestrator"],
    },
    {
        "id": "mark_released",
        "number": "8",
        "title": "Mark fix version released",
        "user_phrases": ["yes", "skip"],
        "mcp_tools": ["release_orchestrator", "release_wizard"],
        "required_mcps": ["release-orchestrator"],
    },
)


def step_catalog_payload() -> dict[str, Any]:
    steps = []
    for row in RELEASE_STEPS:
        sid = str(row["id"])
        ux = step_ux.STEP_UX.get(sid, {})
        steps.append(
            {
                **row,
                "progress": step_ux.progress_header(sid),
                "hint": ux.get("hint") or step_ux.step_hint(sid),
                "say_first": step_ux.primary_phrases(sid, limit=2),
            }
        )
    return {
        "steps": steps,
        "entry_phrases": ["welcome onboard", "yes", "full release", "help"],
        "weekly_flow": ["yes", "yes", "upload sharepoint", "yes", "send slack", "yes deploy"],
    }
