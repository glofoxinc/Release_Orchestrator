"""Inline operator guidance for MCP wizard and atomic tool responses."""

from __future__ import annotations

from typing import Any

WORKFLOW_MODES_DOC = {
    "full": "Complete PIC + AN release: ticket review through mark-released.",
    "release_notes_only": "Generate DOCX + manual SharePoint link without ticket-review lock.",
    "service_ticket_only": "Create SHIPIT from version + SharePoint URL, then Slack announce (Steps 5–6).",
    "deployer_only": "Post deployment comments and Done transitions only.",
}


def operator_cheat_sheet(
    *,
    step: str | None = None,
    workflow_mode: str = "full",
    status: str = "",
    tool: str | None = None,
) -> dict[str, Any]:
    """Return concise next-step guidance for agents and operators."""
    mode = (workflow_mode or "full").strip().lower()
    guide: dict[str, Any] = {
        "workflow_mode": mode,
        "workflow_mode_description": WORKFLOW_MODES_DOC.get(mode, WORKFLOW_MODES_DOC["full"]),
        "docs": "See docs/RUNBOOK.md for full Release Orchestrator operator runbook.",
    }

    if tool:
        guide.update(_tool_guide(tool, status))
        return guide

    guide["next_recommended_action"] = _next_action(step, mode, status)
    guide["example_inputs"] = _example_inputs(step, mode, status)
    guide["related_tools"] = _related_tools(step, mode)
    if status == "awaiting_confirmation":
        guide["confirmation_reminder"] = (
            "Copy the exact confirmation_token from this response into action=confirm. "
            "Tokens are one-time and tied to the latest preview."
        )
    if status in {"needs_input", "blocked"}:
        guide["dry_run_reminder"] = (
            "External writes (Jira) always preview first. "
            "Slack/Teams/Graph are archived — use dry_run=true on atomic tools when exploring."
        )
    if step == "welcome" or (not step and status == "ok"):
        guide["welcome_hint"] = (
            "New session: release_orchestrator(message='welcome'). User says yes → "
            "release_orchestrator(message='yes', workflow_id=...)."
        )
    return guide


def enrich_tool_response(result: dict[str, Any], *, tool: str) -> dict[str, Any]:
    """Attach operator_guide to an atomic MCP tool result."""
    if not isinstance(result, dict):
        return result
    enriched = dict(result)
    guide = operator_cheat_sheet(
        tool=tool,
        status=str(result.get("status") or ""),
    )
    guide["tool"] = tool
    enriched["operator_guide"] = guide
    return enriched


def _next_action(step: str | None, mode: str, status: str) -> str:
    if status == "awaiting_confirmation":
        return "action=confirm with confirmation_token from this response"
    if status == "already_applied":
        return "action=resume or action=status to continue"
    if status in {"blocked", "error"}:
        return "action=update with fields from questions/preview, or action=back"

    actions = {
        "ticket_review": "update with version_name, projects, selected_ticket_keys; then confirm lock",
        "exclusions": "update exclusion_ticket_keys or confirm to skip",
        "release_notes": "patch release_notes_draft; set apply_suggested_summary=true if needed; confirm to generate DOCX",
        "sharepoint": "update sharepoint_url (manual link; Graph upload archived); confirm when set",
        "service_ticket": "patch service_ticket draft; confirm to create SHIPIT",
        "slack": "archived — step auto-skipped; use email for comms",
        "deploy": "update deployment_project, deployment_info or deployment_paste; confirm deploy",
        "mark_released": "confirm to mark fix version released in Jira",
        "complete": "Workflow finished — action=start for a new release",
    }
    if step and step in actions:
        return f"action=update — {actions[step]}"
    if mode != "full":
        return f"action=start with inputs.workflow_mode={mode!r} and version_name"
    return "action=start to begin a new full release workflow"


def _example_inputs(step: str | None, mode: str, status: str) -> dict[str, Any]:
    if status == "awaiting_confirmation":
        return {"action": "confirm", "confirmation_token": "<token from preview>"}

    if mode == "release_notes_only":
        return {
            "action": "start",
            "inputs": {
                "workflow_mode": "release_notes_only",
                "version_name": "2026.3.08.12",
                "projects": ["PIC", "AN"],
            },
        }
    if mode == "service_ticket_only":
        return {
            "action": "start",
            "inputs": {
                "workflow_mode": "service_ticket_only",
                "version_name": "2026.3.08.12",
                "sharepoint_url": "https://tenant.sharepoint.com/sites/team/Shared%20Documents/Release.docx",
            },
        }
    if mode == "deployer_only":
        return {
            "action": "start",
            "inputs": {
                "workflow_mode": "deployer_only",
                "version_name": "2026.3.08.12",
                "deployment_project": "PIC",
            },
        }

    examples: dict[str, dict[str, Any]] = {
        "ticket_review": {
            "version_name": "2026.3.08.12",
            "projects": ["PIC", "AN"],
            "selected_ticket_keys": ["PIC-1", "AN-2"],
        },
        "release_notes": {
            "apply_suggested_summary": True,
            "release_notes_draft": {"summary_p1": "This release delivers ..."},
        },
        "sharepoint": {"sharepoint_url": "https://tenant.sharepoint.com/.../Release.docx"},
        "service_ticket": {"sharepoint_url": "https://tenant.sharepoint.com/.../Release.docx"},
        "deploy": {
            "deployment_project": "PIC",
            "deployment_info": {
                "Jetts": {
                    "deployment_id": "11111111-1111-1111-1111-111111111111",
                    "deployment_date": "2026-08-12",
                    "deployment_time": "10:00 AM IST",
                }
            },
        },
        "slack": {"slack_decision": "skip"},
    }
    if step and step in examples:
        return {"action": "update", "inputs": examples[step]}
    return {"action": "start", "inputs": {"version_name": "2026.3.08.12", "projects": ["PIC", "AN"]}}


def _related_tools(step: str | None, mode: str) -> list[str]:
    base = ["release_wizard", "fetch_release_tickets", "generate_release_notes_docx"]
    by_step = {
        "ticket_review": ["pre_review_gate", "team_scope_status"],
        "release_notes": ["generate_release_notes_docx"],
        "sharepoint": ["release_wizard"],
        "service_ticket": ["create_service_ticket"],
        "slack": ["release_gate_status"],
        "deploy": ["post_qa_gate"],
    }
    if step and step in by_step:
        return base + by_step[step]
    if mode == "deployer_only":
        return ["release_wizard", "post_qa_gate"]
    if mode == "service_ticket_only":
        return ["release_wizard", "create_service_ticket", "slack_preview"]
    return base


def _tool_guide(tool: str, status: str) -> dict[str, Any]:
    guides = {
        "generate_release_notes_docx": {
            "next_recommended_action": "Use version_name + optional ticket_keys; check readiness in response",
            "related_tools": ["release_wizard", "fetch_release_tickets"],
            "note": "SharePoint Graph upload archived — paste manual link on sharepoint step.",
            "note": "Prefer this over deprecated generate_release_notes text tool.",
        },
        "generate_release_notes": {
            "deprecated": True,
            "use_instead": "generate_release_notes_docx",
            "next_recommended_action": "Switch to generate_release_notes_docx for platform-parity DOCX output.",
        },
        "create_service_ticket": {
            "next_recommended_action": "Provide sharepoint_url, version, schedule; dry_run=true to preview ADF",
            "related_tools": ["release_wizard"],
            "consolidation": "On service_ticket step, review consolidation_suggestions; set apply_consolidation to label or index.",
            "note": "Teams scheduling archived — set meeting details manually if needed.",
        },
        "release_wizard": {
            "next_recommended_action": _next_action(None, "full", status),
            "workflow_modes": WORKFLOW_MODES_DOC,
        },
        "fetch_release_tickets": {
            "next_recommended_action": (
                "fix_version: pass version_name; status-only: selection_mode=status + "
                "statuses_by_project; optional jira_team_ids_by_project"
            ),
            "related_tools": ["generate_release_notes_docx", "release_wizard"],
        },
        "deploy_preview": {
            "next_recommended_action": "Preview deployment comments before deploy_execute",
            "related_tools": ["deploy_execute", "release_wizard"],
        },
        "deploy_execute": {
            "next_recommended_action": "Run after deploy_preview; set dry_run=true to re-preview",
            "related_tools": ["deploy_preview", "post_qa_gate"],
        },
    }
    return guides.get(tool, {"next_recommended_action": "See docs/RUNBOOK.md"})


# UI feature ↔ MCP tool ↔ primary test file (parity matrix for agents).
PARITY_MATRIX: dict[str, dict[str, str]] = {
    "guided_e2e": {
        "ui": "Full Streamlit workflow (Ticket Review → Deployer)",
        "mcp": "release_orchestrator(message=welcome → yes)",
        "tests": "tests/test_mcp_guided.py, tests/test_mcp_welcome.py, tests/test_mcp_wizard.py",
    },
    "ticket_review_lock": {
        "ui": "Ticket Review Step 2 lock-in",
        "mcp": "release_orchestrator / release_wizard (ticket_review step)",
        "tests": "tests/test_mcp_wizard.py, tests/test_final_cleanup.py",
    },
    "status_only_fetch": {
        "ui": "RN/STK snapshot-first + status mode",
        "mcp": "fetch_release_tickets(selection_mode=status)",
        "tests": "tests/test_platform_hardening.py",
    },
    "team_filter_lock": {
        "ui": "ui/jira_team_filter.py (session-wide lock)",
        "mcp": "fetch_release_tickets(jira_team_ids_by_project=...)",
        "tests": "tests/test_jira_team_filter.py, tests/test_platform_hardening.py",
    },
    "release_notes_docx": {
        "ui": "Release Notes Step 4 generate",
        "mcp": "generate_release_notes_docx / release_wizard",
        "tests": "tests/test_reference_parity.py, tests/test_platform_reference_parity.py",
    },
    "service_ticket_create": {
        "ui": "SHIPIT Step 5 review + create",
        "mcp": "create_service_ticket / release_wizard",
        "tests": "tests/test_service_desk_create.py, tests/test_release_critical_parity.py",
    },
    "deploy_comments": {
        "ui": "Release Deployer Step 5 execute",
        "mcp": "deploy_preview, deploy_execute",
        "tests": "tests/test_headless_ops.py, tests/test_platform_ops.py",
    },
    "session_restore": {
        "ui": "app startup session_restore",
        "mcp": "wizard_store session JSON",
        "tests": "tests/test_session_persist.py, tests/test_platform_hardening.py",
    },
    "scope_restore_gate": {
        "ui": "continue_with_drift_gate + render_scope_restore_gate",
        "mcp": "N/A (Platform-only gate)",
        "tests": "tests/test_session_persist.py",
    },
}
