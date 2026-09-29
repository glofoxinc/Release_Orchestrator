"""Release-critical validation shared by Platform UI and MCP.

All hard blockers, warnings, and workflow prerequisite checks for the
release-critical path live here so Streamlit and MCP cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import config
import schedule_time
import slack_announce as sa
import sharepoint_receipt as sp_receipt
from sharepoint_url import sharepoint_validation_message, validate_sharepoint_url


@dataclass(frozen=True)
class WorkflowFlags:
    """Standalone mode flags — mirror Platform session keys."""

    service_ticket_standalone: bool = False
    release_notes_standalone: bool = False
    deployer_standalone: bool = False


@dataclass
class ValidationReport:
    """Structured validation result for UI and MCP."""

    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    coverage_warnings: list[dict[str, Any]] = field(default_factory=list)
    approver_validation: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "suggestions": list(self.suggestions),
            "coverage_warnings": list(self.coverage_warnings),
            "approver_validation": self.approver_validation,
        }


@dataclass(frozen=True)
class PrerequisiteResult:
    ok: bool
    missing: list[str]
    fixes: list[tuple[str, str]]


def _snapshot(state: dict[str, Any]) -> dict[str, Any]:
    snap = state.get("shared_snapshot")
    return snap if isinstance(snap, dict) else {}


def has_snapshot(state: dict[str, Any]) -> bool:
    snap = _snapshot(state)
    if snap.get("ticket_keys"):
        return True
    return bool(snap.get("selected_ticket_keys"))


def has_release_doc(state: dict[str, Any]) -> bool:
    return bool(state.get("shared_docx_generated"))


def has_sharepoint_link(state: dict[str, Any]) -> bool:
    url = (state.get("shared_sharepoint_url") or state.get("stk_sharepoint") or "").strip()
    return validate_sharepoint_url(url)


def has_service_ticket(state: dict[str, Any]) -> bool:
    return bool(state.get("stk_created_key"))


def workflow_checkpoints(state: dict[str, Any]) -> dict[str, bool]:
    """Checkpoint flags used by home/sidebar and MCP status."""
    release = state.get("wiz_release") or {}
    deploy_results = state.get(f"wiz_results_{release.get('id')}", {})
    if not isinstance(deploy_results, dict):
        deploy_results = {}
    releases = bool(state.get("wiz_release"))
    if not releases:
        for key, value in state.items():
            if key.startswith("shared_release_") and value:
                releases = True
                break
    return {
        "releases": releases,
        "ticket_review": has_snapshot(state),
        "release_notes": has_release_doc(state),
        "sharepoint": has_sharepoint_link(state),
        "service_ticket": has_service_ticket(state),
        "deployer": bool(deploy_results.get("success", 0)),
    }


def check_app_prerequisites(
    app_id: str,
    state: dict[str, Any],
    *,
    flags: WorkflowFlags | None = None,
    scope_blocking: list[str] | None = None,
) -> PrerequisiteResult:
    """Platform/MCP parity for workflow app gating."""
    fl = flags or WorkflowFlags()
    missing: list[str] = []
    fixes: list[tuple[str, str]] = []

    if scope_blocking:
        missing.append("Team ticket scope for: " + ", ".join(scope_blocking))
        fixes.append(("settings", "Configure team scope in Settings"))

    if app_id == "ticket_review":
        return PrerequisiteResult(not missing, missing, _dedupe_fixes(fixes))

    if not has_snapshot(state):
        missing.append("Ticket Review lock-in (approved ticket list)")
        fixes.append(("ticket_review", "Open Ticket Review"))

    if app_id == "release_notes":
        if fl.release_notes_standalone:
            return PrerequisiteResult(True, [], [])
        return PrerequisiteResult(not missing, missing, _dedupe_fixes(fixes))

    if not has_release_doc(state):
        missing.append("Release Notes Word document generated and downloaded")
        fixes.append(("release_notes", "Open Release Notes"))

    if app_id == "service_ticket":
        if fl.service_ticket_standalone:
            return PrerequisiteResult(True, [], [])
        if not has_sharepoint_link(state):
            missing.append("SharePoint link to the uploaded Release Notes .docx")
            if not any(app == "release_notes" for app, _ in fixes):
                fixes.append(("release_notes", "Add SharePoint link in Release Notes"))
        return PrerequisiteResult(not missing, missing, _dedupe_fixes(fixes))

    if not has_service_ticket(state):
        missing.append(f"Service Ticket ({config.TCKT_PROJECT_KEY}) created in Jira")
        fixes.append(("service_ticket", "Open Service Ticket"))

    if app_id == "release_deployer":
        if fl.deployer_standalone:
            return PrerequisiteResult(True, [], [])
        return PrerequisiteResult(not missing, missing, _dedupe_fixes(fixes))

    return PrerequisiteResult(True, [], [])


def _dedupe_fixes(fixes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for app, label in fixes:
        if app not in seen:
            seen[app] = label
    return list(seen.items())


def schedule_blockers(state: dict[str, Any]) -> list[str]:
    """Validate planned start/end window when schedule fields are present."""
    start_d = state.get("stk_planned_start_date")
    end_d = state.get("stk_planned_end_date")
    start_t = state.get("stk_planned_start_time")
    end_t = state.get("stk_planned_end_time")
    fields = (start_d, end_d, start_t, end_t)
    if not any(fields):
        return []
    if not all(fields):
        return ["Schedule is incomplete — set planned start and end date/time."]
    if isinstance(start_d, str):
        start_d = date.fromisoformat(start_d)
    if isinstance(end_d, str):
        end_d = date.fromisoformat(end_d)
    if isinstance(start_t, str):
        start_t = datetime.strptime(start_t, "%H:%M:%S").time()
    info = schedule_time.describe_window(
        start_d,
        start_t,
        end_d,
        end_t,
        tz_name=state.get("stk_schedule_tz") or config.TCKT_SCHEDULE_TZ,
        display_tz=config.TCKT_DISPLAY_TZ,
    )
    if not info.get("valid"):
        return ["Planned end is before or equal to planned start."]
    return []


def service_ticket_review_warnings(state: dict[str, Any]) -> list[str]:
    """Non-blocking warnings on the service ticket review step."""
    warnings: list[str] = []
    for field_key, label in (
        ("stk_impl_plan", "Implementation Steps"),
        ("stk_test_plan", "Verification Steps"),
        ("stk_backout_plan", "Rollback Steps"),
        ("stk_business_impact", "Business Impact"),
    ):
        if not str(state.get(field_key) or "").strip():
            warnings.append(f"{label} is empty.")
    if not str(state.get("stk_sharepoint") or state.get("shared_sharepoint_url") or "").strip():
        warnings.append(
            "SharePoint link is missing — the description will not include a release notes link."
        )
    start_d = state.get("stk_planned_start_date")
    end_d = state.get("stk_planned_end_date")
    start_t = state.get("stk_planned_start_time")
    end_t = state.get("stk_planned_end_time")
    if start_d and end_d and start_t and end_t:
        if isinstance(start_d, str):
            start_d = date.fromisoformat(start_d)
        if isinstance(end_d, str):
            end_d = date.fromisoformat(end_d)
        if isinstance(start_t, str):
            start_t = datetime.strptime(start_t, "%H:%M:%S").time()
        start_dt = datetime.combine(start_d, start_t)
        end_dt = datetime.combine(end_d, end_t)
        if end_dt <= start_dt:
            warnings.append("Planned end is before or equal to planned start.")
    return warnings


def sharepoint_receipt_blockers(state: dict[str, Any]) -> list[str]:
    """Validate SharePoint upload receipt when present (MCP wizard path)."""
    receipt = state.get("shared_sharepoint_receipt")
    if not isinstance(receipt, dict):
        return []
    ok, issues = sp_receipt.validate_receipt(receipt)
    return list(issues) if not ok else []


def github_pr_create_blockers(state: dict[str, Any]) -> list[str]:
    """Block SHIPIT when GitHub PR gate finds unmerged PRs (unless explicit override)."""
    if state.get("allow_github_pr_override"):
        return []
    import github_pr_gate as gp

    if not gp.block_on_create_enabled():
        return []
    gate = state.get("github_pr_gate") or {}
    if not isinstance(gate, dict):
        return []
    if gate.get("status") in {"disabled", "skipped"}:
        return []
    blocking = gate.get("tickets_with_blocking_prs") or []
    if not blocking:
        return []
    keys = ", ".join(str(row.get("ticket") or "?") for row in blocking)
    return [
        "GitHub PR gate: every included ticket needs at least one merged PR "
        f"({keys}). Merge PRs or set allow_github_pr_override=true with a reason."
    ]


def service_ticket_create_blockers(
    state: dict[str, Any],
    *,
    flags: WorkflowFlags | None = None,
) -> list[str]:
    """Hard blockers before irreversible service ticket creation — shared contract."""
    fl = flags or WorkflowFlags(
        service_ticket_standalone=bool(state.get("shared_stk_standalone_mode")),
    )
    blockers: list[str] = []

    if not str(state.get("stk_summary") or "").strip():
        blockers.append("Ticket summary is empty.")
    if not state.get("stk_description_adf"):
        blockers.append("Description was not built — go back to Step 3.")
    if not state.get("stk_extracted"):
        blockers.append("No tickets loaded — go back to Step 1 and select releases.")

    for field_key, label in (
        ("stk_impl_plan", "Implementation Steps"),
        ("stk_test_plan", "Verification Steps"),
        ("stk_backout_plan", "Rollback Steps"),
        ("stk_business_impact", "Business Impact"),
    ):
        if not str(state.get(field_key) or "").strip():
            blockers.append(f"{label} is empty.")

    sp_url = str(state.get("stk_sharepoint") or "")
    if not sp_url and "stk_sharepoint" not in state:
        sp_url = str(state.get("shared_sharepoint_url") or "")
    if not validate_sharepoint_url(sp_url):
        msg = sharepoint_validation_message(sp_url) or "SharePoint link is invalid."
        if fl.service_ticket_standalone:
            blockers.append(f"SharePoint link is required — {msg}")
        else:
            blockers.append(f"SharePoint link is required (upload Release Notes .docx first). {msg}")

    if not fl.service_ticket_standalone:
        if not has_release_doc(state):
            blockers.append("Release Notes .docx has not been generated in this session.")
        if not has_snapshot(state):
            blockers.append("Ticket Review lock-in is missing.")

    blockers.extend(schedule_blockers(state))

    validation = state.get("stk_approver_validation")
    if validation is not None:
        if isinstance(validation, dict):
            if not validation.get("all_ok", True):
                blockers.append("Approver/group validation failed — fix assignments in Step 2.")
        elif hasattr(validation, "all_ok") and not validation.all_ok:
            blockers.append("Approver/group validation failed — fix assignments in Step 2.")
    else:
        groups = state.get("stk_approver_groups") or config.TCKT_DEFAULTS.get("approver_groups", [])
        approvers_field = config.service_desk_field("approvers")
        if approvers_field:
            approvers = state.get("stk_approvers") or config.TCKT_DEFAULTS.get("approvers", [])
            if not approvers and not groups:
                blockers.append("No approvers or approver groups configured — set them in Step 2.")
        elif not groups:
            blockers.append("No approver groups configured — set them in Step 2.")

    blockers.extend(sharepoint_receipt_blockers(state))
    blockers.extend(github_pr_create_blockers(state))

    return blockers


def service_ticket_soft_warnings(state: dict[str, Any]) -> list[str]:
    """Non-blocking warnings shown on review step."""
    warnings: list[str] = []
    if not str(state.get("stk_sharepoint") or state.get("shared_sharepoint_url") or "").strip():
        warnings.append(
            "SharePoint link is missing — the description will not include a release notes link."
        )
    return warnings


def service_ticket_validation_report(
    state: dict[str, Any],
    *,
    flags: WorkflowFlags | None = None,
    coverage_warnings: list[dict[str, Any]] | None = None,
    approver_validation: dict[str, Any] | None = None,
) -> ValidationReport:
    """Full structured validation for service ticket create."""
    fl = flags or WorkflowFlags(
        service_ticket_standalone=bool(state.get("shared_stk_standalone_mode")),
    )
    report = ValidationReport(
        blockers=service_ticket_create_blockers(state, flags=fl),
        warnings=service_ticket_soft_warnings(state),
        coverage_warnings=list(coverage_warnings or []),
        approver_validation=approver_validation,
    )
    if coverage_warnings:
        for item in coverage_warnings:
            msg = str(item.get("message") or "")
            if msg and msg not in report.warnings:
                report.warnings.append(msg)
    if approver_validation and not approver_validation.get("all_ok", True):
        if "Approver/group validation failed — fix assignments in Step 2." not in report.blockers:
            report.blockers.append("Approver/group validation failed — fix assignments in Step 2.")
    return report


def release_notes_publish_blockers(data: dict[str, Any]) -> list[str]:
    """Blockers before final DOCX publish."""
    from generators.release_notes_insights import assess_release_notes_readiness

    report = assess_release_notes_readiness(data)
    blockers = [item.message for item in report.blockers]
    if not blockers and not report.ready:
        blockers.append(f"Readiness score {report.score}/100 — resolve blockers before publishing.")
    return blockers


def slack_deploy_gate_blockers(state: dict[str, Any]) -> list[str]:
    """Blockers before deployer when Slack announce is enabled and sendable."""
    cfg = sa.load_announce_config({"slack_announce": config.SLACK_ANNOUNCE})
    if not sa.slack_gate_applies(cfg):
        return []
    if sa.deployer_slack_gate_open(
        enabled=True,
        sent=bool(state.get("stk_slack_sent")),
        skipped=bool(state.get("stk_slack_skipped")),
        can_send=cfg.can_send(),
    ):
        return []
    return ["Slack announce is enabled but not sent or skipped — complete the Slack step first."]


def deploy_execution_blockers(state: dict[str, Any]) -> list[str]:
    """Blockers before deploy execution."""
    blockers: list[str] = []
    if not state.get("wiz_filled"):
        blockers.append("No deployment info found — fill deployment details first.")
    if not state.get("wiz_release"):
        blockers.append("No release selected.")
    blockers.extend(slack_deploy_gate_blockers(state))
    return blockers


def wizard_session_to_platform_state(
    session: dict[str, Any],
    *,
    extracted: list[dict[str, Any]] | None = None,
    service_ticket_draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map MCP wizard session artifacts to Platform session keys for validation."""
    draft = dict(
        service_ticket_draft or (session.get("drafts") or {}).get("service_ticket") or {}
    )
    inputs = session.get("inputs") or {}
    artifacts = session.get("artifacts") or {}
    snap = artifacts.get("ticket_snapshot") or {}
    if isinstance(snap, dict) and snap.get("selected_ticket_keys") and not snap.get("ticket_keys"):
        snap = {**snap, "ticket_keys": list(snap.get("selected_ticket_keys") or [])}
    if extracted is None:
        extracted = snap.get("extracted") if isinstance(snap, dict) else None
    return {
        "stk_summary": draft.get("summary"),
        "stk_description_adf": draft.get("description_adf"),
        "stk_extracted": extracted or [],
        "stk_impl_plan": draft.get("implementation_plan"),
        "stk_test_plan": draft.get("test_plan"),
        "stk_backout_plan": draft.get("backout_plan"),
        "stk_business_impact": draft.get("business_impact"),
        "stk_communication_plan": draft.get("communication_plan"),
        "stk_reason_for_change": draft.get("reason_for_change"),
        "stk_sharepoint": artifacts.get("sharepoint_url") or draft.get("sharepoint"),
        "shared_sharepoint_url": artifacts.get("sharepoint_url"),
        "shared_sharepoint_receipt": artifacts.get("sharepoint_receipt"),
        "github_pr_gate": artifacts.get("github_pr_gate"),
        "allow_github_pr_override": bool(inputs.get("allow_github_pr_override")),
        "stk_approvers": draft.get("approvers"),
        "stk_approver_groups": draft.get("approver_groups"),
        "stk_approver_validation": artifacts.get("approver_validation"),
        "shared_docx_generated": bool(artifacts.get("release_notes_docx")),
        "shared_snapshot": snap if isinstance(snap, dict) else None,
        "shared_stk_standalone_mode": inputs.get("workflow_mode") == "service_ticket_only",
        "shared_rn_standalone_mode": inputs.get("workflow_mode") == "release_notes_only",
        "shared_deployer_standalone_mode": inputs.get("workflow_mode") == "deployer_only",
        "stk_planned_start_date": inputs.get("planned_start_date"),
        "stk_planned_end_date": inputs.get("planned_end_date"),
        "stk_planned_start_time": inputs.get("planned_start_time"),
        "stk_planned_end_time": inputs.get("planned_end_time"),
        "stk_schedule_tz": (
            inputs.get("schedule_source_timezone")
            or inputs.get("schedule_timezone")
            or config.TCKT_SCHEDULE_SOURCE_TZ
        ),
        "stk_created_key": (artifacts.get("service_ticket") or {}).get("key"),
        "stk_slack_sent": (artifacts.get("slack") or {}).get("status") == "sent",
        "stk_slack_skipped": inputs.get("slack_decision") == "skip",
        "wiz_filled": inputs.get("deployment_info"),
        "wiz_release": inputs.get("version_name"),
    }


def deploy_gate_state_from_wizard(session: dict[str, Any]) -> dict[str, Any]:
    """Minimal platform state for deploy/slack gate checks from wizard session."""
    inputs = session.get("inputs") or {}
    artifacts = session.get("artifacts") or {}
    slack = artifacts.get("slack") or {}
    return {
        "wiz_filled": inputs.get("deployment_info"),
        "wiz_release": inputs.get("version_name"),
        "stk_slack_sent": slack.get("status") == "sent",
        "stk_slack_skipped": inputs.get("slack_decision") == "skip",
    }


def mcp_service_ticket_blocked(
    *,
    preflight_status: str,
    approver_all_ok: bool,
    duplicate_blocked: bool,
    platform_blockers: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Unified blocked decision for MCP service ticket step."""
    blockers = list(platform_blockers or [])
    if preflight_status == "preflight_failed":
        blockers.append("Jira service-desk preflight failed — fix field mapping or payload.")
    if not approver_all_ok:
        if "Approver/group validation failed — fix assignments in Step 2." not in blockers:
            blockers.append("Approver/group validation failed — fix assignments in Step 2.")
    if duplicate_blocked:
        blockers.append(
            "A recent service ticket with this summary already exists. "
            "Set allow_duplicate_tckt=true only if intentional."
        )
    return bool(blockers), blockers


__all__ = [
    "PrerequisiteResult",
    "ValidationReport",
    "WorkflowFlags",
    "check_app_prerequisites",
    "deploy_execution_blockers",
    "github_pr_create_blockers",
    "sharepoint_receipt_blockers",
    "has_release_doc",
    "has_service_ticket",
    "has_sharepoint_link",
    "has_snapshot",
    "deploy_gate_state_from_wizard",
    "mcp_service_ticket_blocked",
    "service_ticket_review_warnings",
    "wizard_session_to_platform_state",
    "release_notes_publish_blockers",
    "schedule_blockers",
    "service_ticket_create_blockers",
    "service_ticket_soft_warnings",
    "service_ticket_validation_report",
    "slack_deploy_gate_blockers",
    "workflow_checkpoints",
]
