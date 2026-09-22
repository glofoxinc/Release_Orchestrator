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
        "title": "Full release",
        "phrases": ("full release", "yes", "lets go"),
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
