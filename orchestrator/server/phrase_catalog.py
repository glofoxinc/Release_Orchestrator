"""Single source of truth — user phrases → actions → E2E expectations.

Agents and tests import this module so routing and documentation stay aligned.
"""

from __future__ import annotations

from typing import Any

# Each flow: phrases that trigger it, interpret outcome, and what must happen next.
PHRASE_E2E_FLOWS: tuple[dict[str, Any], ...] = (
    {
        "id": "fetch_review",
        "title": "Fetch review tickets (lock)",
        "phrases": (
            "fetch review tickets",
            "fetch review tkts",
            "fetch review",
            "review tickets",
        ),
        "interpret": {"action": "welcome", "start_path": "fetch_review_tickets"},
        "e2e_chain": (
            "Step 1 ticket_review — review-ready statuses (PIC Review + AN Passed QA)",
            "User yes → lock snapshot",
            "Steps 2–8 full release continues",
        ),
        "requires_workflow": False,
    },
    {
        "id": "fetch_release_list",
        "title": "Fetch release tickets (list only)",
        "phrases": (
            "fetch release tickets",
            "fetch release tkts",
            "list release tickets",
        ),
        "interpret": {"action": "list_release_tickets"},
        "e2e_chain": (
            "Call list_release_ready_tickets (release-ready statuses)",
            "Return formatted_list — no wizard lock",
        ),
        "requires_workflow": False,
    },
    {
        "id": "schedule_review_call",
        "title": "Schedule review call",
        "phrases": (
            "schedule review call",
            "review call schedule",
            "schedule review meeting",
        ),
        "interpret": {"action": "daily_review_calendar_handoff"},
        "e2e_chain": (
            "Playwright MCP → Outlook web → Teams invite",
            "User calendar done when invite sent",
        ),
        "requires_workflow": False,
    },
    {
        "id": "create_release_notes",
        "title": "Create release notes + SharePoint",
        "phrases": (
            "create release notes",
            "start with release notes",
            "generate release notes",
        ),
        "interpret": {"action": "welcome", "start_path": "release_notes"},
        "confirm_phrases": ("create release notes", "yes", "yes generate docx"),
        "e2e_chain": (
            "Generate DOCX",
            "Auto sharepoint_upload=playwright",
            "User sharepoint done + URL",
        ),
        "requires_workflow": True,
    },
    {
        "id": "create_shipit",
        "title": "Create SHIPIT + Slack",
        "phrases": (
            "create shipit",
            "create shipit ticket",
            "create service ticket",
        ),
        "interpret": {"action": "welcome", "start_path": "shipit"},
        "confirm_phrases": ("create shipit", "yes", "yes create shipit"),
        "e2e_chain": (
            "Create SHIPIT in Jira",
            "Auto slack_decision=playwright",
            "User slack done after both channels posted",
        ),
        "requires_workflow": True,
    },
    {
        "id": "full_release",
        "title": "Full / week release",
        "phrases": ("week release", "full release", "weekly release", "yes", "lets go"),
        "interpret": {"action": "welcome", "start_path": "fetch_review_tickets", "confirm_defaults": True},
        "e2e_chain": ("Steps 1–8",),
        "requires_workflow": False,
    },
)


def all_phrases() -> list[tuple[str, str]]:
    """Flatten (phrase, flow_id) for parametrized tests."""
    out: list[tuple[str, str]] = []
    for flow in PHRASE_E2E_FLOWS:
        fid = str(flow["id"])
        for phrase in flow.get("phrases") or ():
            out.append((phrase, fid))
    return out


def flow_by_id(flow_id: str) -> dict[str, Any] | None:
    for flow in PHRASE_E2E_FLOWS:
        if flow.get("id") == flow_id:
            return dict(flow)
    return None


def format_e2e_cheat_sheet() -> str:
    lines = [
        "**Release Orchestrator — phrase E2E map**",
        "",
        "| Say | E2E outcome |",
        "|-----|-------------|",
    ]
    for flow in PHRASE_E2E_FLOWS:
        primary = (flow.get("phrases") or ("",))[0]
        chain = " → ".join(flow.get("e2e_chain") or ())
        lines.append(f"| **{primary}** | {chain} |")
    lines.append("")
    lines.append("List-only **fetch release tickets** never locks. **fetch review tickets** locks at Step 1.")
    return "\n".join(lines)


# Onboarding help / cheat-sheet blocks (setup + weekly steps). Imported by onboarding_guide.
ONBOARDING_WORKFLOW_PHRASES: dict[str, dict[str, Any]] = {
    "setup": {
        "title": "First-time setup",
        "phrases": [
            "welcome onboard", "onboarding", "done", "mcp configured", "setup status", "help",
            "use glofox", "use ignite", "projects pic an", "crew done", "crew status",
        ],
        "agent_does": "Walk .env + MCP + team/project + crew one step at a time; never ask user to paste tokens in chat.",
    },
    "team_crew": {
        "title": "Team + crew (one-time .env)",
        "phrases": [
            "use glofox", "use ignite", "team etl", "projects pic an", "projects pic",
            "crew add Name <email@x.com> to review", "crew exclude email@x.com", "crew done",
        ],
        "agent_does": (
            "Pick Jira team + PIC/AN projects; confirm review/release/QA/leadership crew; paste .env block. "
            "Daily Review uses this crew for meeting invites: required = leadership + QA + in-squad assignees; "
            "optional = review/release crew; never invite TEAM_CREW_EXCLUDE or outside-squad assignees "
            "(e.g. Gabriel/Erasmo). Their tickets are also skipped at fetch unless explicitly opted in. "
            "MCP: daily_review_attendee_policy."
        ),
    },
    "start": {
        "title": "Choose release path",
        "phrases": ["yes", "week release", "full release", "start", "fetch review tickets", "start with release notes", "create SHIPIT ticket"],
        "agent_does": "yes/full release = standard PIC+AN path · start = menu for notes-only or SHIPIT-only.",
    },
    "step_1_2": {
        "title": "Tickets & exclusions",
        "phrases": [
            "fetch review tickets",
            "fetch review",
            "fetch release tickets",
            "yes",
            "exclude PIC-1234",
            "yes skip exclusions",
        ],
        "agent_does": (
            "fetch review tickets = review-ready statuses + lock. "
            "fetch release tickets = release-ready list only (no lock)."
        ),
    },
    "review_call": {
        "title": "Schedule review call",
        "phrases": ["schedule review call", "review call schedule", "calendar done"],
        "agent_does": "Playwright → Outlook web → Teams invite for PIC/AN review call.",
    },
    "step_3": {
        "title": "Release notes DOCX + SharePoint",
        "phrases": [
            "create release notes",
            "yes",
            "yes generate docx",
            "include PIC-1234 for release notes",
        ],
        "agent_does": (
            "Generate Word release notes, then auto-start Playwright SharePoint upload "
            "(Glofox default). Development Team = Customize BI Team."
        ),
    },
    "step_4": {
        "title": "SharePoint upload confirm",
        "phrases": ["upload sharepoint", "sharepoint done https://...", "paste SharePoint URL"],
        "agent_does": "Complete Playwright upload to quarter folder; save document URL for SHIPIT + Slack.",
    },
    "step_5": {
        "title": "SHIPIT + Slack announce",
        "phrases": [
            "create shipit",
            "yes create shipit",
            "emergency deployment",
            "skip shipit link",
        ],
        "agent_does": (
            "Preview/create SHIPIT (10:30-11:30 AM IST window), link PIC/AN tickets, "
            "then auto-start Playwright Slack announce to squad + buddies."
        ),
    },
    "step_6": {
        "title": "Slack confirm",
        "phrases": ["send slack", "slack done", "skip slack", "send slack playwright"],
        "agent_does": (
            "Complete Playwright post (gold-standard linked message per slack_reference); "
            "user says **slack done** when both channels show the message."
        ),
    },
    "step_7_8": {
        "title": "Deploy & mark released",
        "phrases": ["yes deploy", "yes", "skip"],
        "agent_does": "Jira deployment comments + Done transitions; optional mark fix version released.",
    },
    "checks": {
        "title": "Readiness & sign-off",
        "phrases": ["production ready", "shipit confirmed", "slack confirmed"],
        "agent_does": "Verify automated checks; record operator sign-offs for launch complete.",
    },
    "daily_review": {
        "title": "Daily Review Agent (6 PM PIC/AN)",
        "phrases": [
            "daily review setup",
            "daily review preflight",
            "daily review live",
            "outlook login",
            "schedule daily review for 2 weeks",
        ],
        "agent_does": (
            "daily_review_setup → teams_login → daily_review_outlook_login → "
            "daily_review_preflight(live=true) → daily_review_run_live"
        ),
    },
}
