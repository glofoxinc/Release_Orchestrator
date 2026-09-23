"""Durable, confirmation-gated Release Orchestrator MCP workflow."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import approver_validator
import assignment_ops
import config
import deploy_ops
import deploy_prefill
import deployment_history
import exclusion_ops
import jira_client
import release_gates
import release_critical as rc
import schedule_time
import team_scope
import ticket_validator
from generators.release_notes_draft import release_notes_draft_schema
from generators.release_notes_insights import (
    assess_release_notes_readiness,
    build_release_summary_paragraph,
    readiness_to_dict,
)
from release_mcp import browser_ops, release_ops, sharepoint_ops, slack_ops, teams_ops, wizard_store
from release_mcp.operator_guide import operator_cheat_sheet
from release_mcp.release_notes_preview import build_structured_preview
from release_mcp import workflow_modes
from service_ticket_plans import (
    build_backout,
    build_communication,
    build_impact,
    build_impl,
    build_qa_test_plan,
    build_reason,
    build_risks,
    build_test,
)
from tckt_reference import build_summary_from_reference_pattern

WORKFLOW_NAME = "releaseops-full"

STEP_TICKET_REVIEW = "ticket_review"
STEP_EXCLUSIONS = "exclusions"
STEP_RELEASE_DATE = "release_date_confirm"
STEP_RELEASE_NOTES = "release_notes"
STEP_SHAREPOINT = "sharepoint"
STEP_SERVICE_TICKET = "service_ticket"
STEP_SLACK = "slack"
STEP_DEPLOY = "deploy"
STEP_MARK_RELEASED = "mark_released"
STEP_COMPLETE = "complete"
STEP_UNDO = "undo_deployment"

STEP_ORDER = [
    STEP_TICKET_REVIEW,
    STEP_EXCLUSIONS,
    STEP_RELEASE_NOTES,
    STEP_SHAREPOINT,
    STEP_SERVICE_TICKET,
    STEP_SLACK,
    STEP_DEPLOY,
    STEP_MARK_RELEASED,
    STEP_COMPLETE,
]


def _response(
    session: dict[str, Any],
    *,
    status: str,
    prompt: str,
    questions: list[dict[str, Any]] | None = None,
    preview: Any = None,
    confirmation_token: str | None = None,
    allowed_actions: list[str] | None = None,
) -> dict[str, Any]:
    mode = _workflow_mode(session)
    return {
        "status": status,
        "workflow_id": session["id"],
        "step": session.get("step"),
        "workflow_mode": mode,
        "prompt": prompt,
        "questions": questions or [],
        "preview": preview,
        "confirmation_token": confirmation_token,
        "allowed_actions": allowed_actions or ["update", "resume", "cancel"],
        "updated_at": session.get("updated_at"),
        "workflow_status": session.get("status"),
        "operator_guide": operator_cheat_sheet(
            step=str(session.get("step") or ""),
            workflow_mode=mode,
            status=status,
        ),
    }


def _workflow_mode(session: dict[str, Any]) -> str:
    return workflow_modes.normalize_mode(str((session.get("inputs") or {}).get("workflow_mode") or "full"))


def _step_order(session: dict[str, Any]) -> list[str]:
    return workflow_modes.steps_for(_workflow_mode(session))


def _advance_to_next_step(session: dict[str, Any], current_step: str) -> str:
    order = _step_order(session)
    try:
        index = order.index(current_step)
    except ValueError:
        return STEP_COMPLETE
    if index + 1 >= len(order):
        return STEP_COMPLETE
    return str(order[index + 1])


def _process_step(session: dict[str, Any], step: str) -> dict[str, Any]:
    """Route to the processor for ``step`` (used after mode-aware transitions)."""
    if step == STEP_COMPLETE:
        return _complete(session)
    session = wizard_store.update_session(session["id"], step=step)
    return _process(session)


def _ensure_ticket_snapshot(session: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Bootstrap ticket_snapshot for standalone MCP modes when missing."""
    if (session.get("artifacts") or {}).get("ticket_snapshot"):
        return session, None
    mode = _workflow_mode(session)
    if not workflow_modes.skip_snapshot_prerequisites(mode):
        return session, _response(
            session,
            status="blocked",
            prompt="Ticket Review lock is required. Complete ticket_review or use a standalone workflow_mode.",
            questions=[
                _question(
                    "workflow_mode",
                    "Use release_notes_only, service_ticket_only, or deployer_only to skip ticket review.",
                    required=False,
                ),
            ],
        )
    inputs = dict(session.get("inputs") or {})
    selection_mode = str(inputs.get("selection_mode") or "fix_version").strip()
    from release_mcp import welcome as welcome_mod

    projects = _selected_projects(inputs)
    team_map = welcome_mod.team_ids_map_for_projects(projects, inputs)
    if selection_mode == "status":
        rn_statuses = welcome_mod.release_notes_default_statuses_by_project(projects)
        rn_result = release_ops.fetch_release_notes_extracted(
            selection_mode="status",
            projects=projects,
            release_notes_statuses_by_project=rn_statuses,
            jira_team_ids_by_project=team_map or None,
        )
        fetch = {
            "status": rn_result.get("status"),
            "extracted": rn_result.get("extracted") or [],
            "by_project": (rn_result.get("fetch") or {}).get("by_project") or {},
            "projects": projects,
            "total_tickets": len(rn_result.get("extracted") or []),
        }
    else:
        version = str(inputs.get("version_name") or "").strip()
        if not version:
            return session, _response(
                session,
                status="needs_input",
                prompt="Standalone mode requires version_name to fetch tickets from Jira.",
                questions=[_question("version_name", "Fix version name (e.g. 2026.3.08.12)")],
            )
        rn_result = release_ops.fetch_release_notes_extracted(
            selection_mode="fix_version",
            projects=projects,
            version_name=version,
            jira_team_ids_by_project=team_map or None,
        )
        fetch = {
            "status": rn_result.get("status"),
            "extracted": rn_result.get("extracted") or [],
            "by_project": (rn_result.get("fetch") or {}).get("by_project") or {},
            "projects": projects,
            "total_tickets": len(rn_result.get("extracted") or []),
            "message": rn_result.get("message"),
        }
    if fetch.get("status") == "blocked":
        return session, _response(session, status="blocked", prompt="Team scope blocked ticket fetch.", preview=fetch)
    if fetch.get("status") != "ok" or fetch.get("missing_projects"):
        missing = fetch.get("missing_projects") or []
        return session, _response(
            session,
            status="needs_input",
            prompt=f"Provide version for project(s): {missing or fetch.get('projects')}",
            questions=[_question("version_name", "Shared fix version name for PIC + AN.")],
            preview=fetch,
        )
    extracted = list(fetch.get("extracted") or [])
    inputs = session.get("inputs") or {}
    filter_keys = inputs.get("selected_ticket_keys") or inputs.get("ticket_keys")
    if filter_keys:
        key_set = {str(k).strip().upper() for k in filter_keys if str(k).strip()}
        extracted = [item for item in extracted if str(item.get("ticket") or "").upper() in key_set]
    if not extracted:
        return session, _response(
            session,
            status="needs_input",
            prompt="No tickets matched. Adjust ticket_keys or verify the fix version in Jira.",
            preview={"total_fetched": fetch.get("total_tickets", 0)},
        )
    keys = _ticket_keys(extracted)
    snapshot = {
        "selected_ticket_keys": keys,
        "excluded_ticket_keys": [],
        "extracted": extracted,
        "ticket_keys": keys,
    }
    session = wizard_store.update_session(
        session["id"],
        artifacts={
            "ticket_snapshot": snapshot,
            "ticket_fetch": {"by_project": fetch.get("by_project") or {}},
        },
        audit_event="standalone_snapshot_bootstrapped",
        audit_detail={"mode": mode, "ticket_count": len(keys)},
    )
    return session, None


def _question(field: str, prompt: str, *, required: bool = True) -> dict[str, Any]:
    return {"field": field, "prompt": prompt, "required": required}


def _already_applied(
    session: dict[str, Any],
    *,
    prompt: str,
    preview: Any = None,
) -> dict[str, Any]:
    return _response(
        session,
        status="already_applied",
        prompt=prompt,
        preview=preview,
        allowed_actions=["resume", "status", "back", "cancel"],
    )


_DOWNSTREAM_ARTIFACT_KEYS: dict[str, tuple[str, ...]] = {
    STEP_TICKET_REVIEW: (
        "ticket_snapshot",
        "ticket_snapshot_draft",
        "exclusion_results",
        "release_notes_docx",
        "sharepoint_url",
        "service_ticket_preflight",
        "service_ticket",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
        "applied_writes",
    ),
    STEP_EXCLUSIONS: (
        "exclusion_results",
        "release_notes_docx",
        "sharepoint_url",
        "service_ticket_preflight",
        "service_ticket",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_RELEASE_NOTES: (
        "release_notes_docx",
        "sharepoint_url",
        "service_ticket_preflight",
        "service_ticket",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_SHAREPOINT: (
        "sharepoint_url",
        "service_ticket_preflight",
        "service_ticket",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_SERVICE_TICKET: (
        "service_ticket_preflight",
        "duplicate_tckt",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_SLACK: (
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_DEPLOY: (
        "deployment_context",
        "pending_preview",
    ),
    STEP_MARK_RELEASED: ("pending_preview",),
}


def _archive_external_refs(artifacts: dict[str, Any]) -> dict[str, Any]:
    """Keep already-created external records as immutable audit references."""
    refs = dict(artifacts.get("external_refs") or {})
    service = artifacts.get("service_ticket")
    if isinstance(service, dict) and service.get("key"):
        refs["service_ticket"] = {
            "key": service.get("key"),
            "url": service.get("url"),
            "summary": service.get("summary"),
            "status": service.get("status"),
        }
    slack = artifacts.get("slack")
    if isinstance(slack, dict) and slack.get("results"):
        refs["slack"] = {
            "status": slack.get("status"),
            "results": slack.get("results"),
        }
    deploy_results = artifacts.get("deployment_results")
    if isinstance(deploy_results, dict) and deploy_results:
        refs["deployment_results"] = deploy_results
    elif artifacts.get("deployment_result"):
        refs["deployment_result"] = artifacts.get("deployment_result")
    if refs:
        artifacts = dict(artifacts)
        artifacts["external_refs"] = refs
    return artifacts


def _clear_downstream_artifacts(session: dict[str, Any], target_step: str) -> dict[str, Any]:
    """Drop regenerated artifacts after going back / changing selection.

    Already-created external records are retained under ``external_refs``.
    """
    artifacts = _archive_external_refs(dict(session.get("artifacts") or {}))
    cleared = {key: None for key in _DOWNSTREAM_ARTIFACT_KEYS.get(target_step, ()) if key != "external_refs"}
    cleared["external_refs"] = artifacts.get("external_refs") or {}
    cleared["pending_preview"] = None
    return wizard_store.update_session(
        session["id"],
        artifacts=cleared,
        audit_event="downstream_artifacts_invalidated",
        audit_detail={"target_step": target_step},
    )


def _selected_projects(inputs: dict[str, Any]) -> list[str]:
    raw = inputs.get("projects")
    if raw:
        return [str(value).strip().upper() for value in raw if str(value).strip()]
    versions = inputs.get("versions")
    if isinstance(versions, dict) and versions:
        return [str(key).strip().upper() for key in versions if str(key).strip()]
    return [project["key"] for project in config.PROJECTS]


def _version_for(inputs: dict[str, Any], project_key: str) -> str:
    versions = inputs.get("versions")
    if isinstance(versions, dict):
        value = versions.get(project_key) or versions.get(project_key.lower())
        if value:
            return str(value).strip()
    return str(inputs.get("version_name") or "").strip()


def _merge_unique_ticket_keys(existing: list[str] | None, new_keys: list[str] | None) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for raw in list(existing or []) + list(new_keys or []):
        key = str(raw).strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(key)
    return merged


def _release_notes_include_keys(inputs: dict[str, Any]) -> list[str]:
    raw = inputs.get("release_notes_include_ticket_keys")
    if not isinstance(raw, list):
        return []
    return _merge_unique_ticket_keys([], raw)


def _release_notes_statuses_for_inputs(
    inputs: dict[str, Any],
    projects: list[str],
) -> dict[str, list[str]]:
    from release_mcp import welcome as welcome_mod

    explicit = inputs.get("release_notes_statuses_by_project")
    if isinstance(explicit, dict) and any(explicit.values()):
        return {
            str(project_key).strip().upper(): [
                str(status).strip()
                for status in (values if isinstance(values, list) else [values])
                if str(status).strip()
            ]
            for project_key, values in explicit.items()
            if str(project_key).strip()
        }
    return welcome_mod.release_notes_default_statuses_by_project(projects)


def _fetch_release_notes_extracted(session: dict[str, Any]) -> dict[str, Any]:
    """Fetch tickets using release-ready statuses; intersect with locked keys when present."""
    from release_mcp import welcome as welcome_mod

    inputs = session.get("inputs") or {}
    projects = _selected_projects(inputs)
    selection_mode = str(inputs.get("selection_mode") or "fix_version").strip()
    snapshot = (session.get("artifacts") or {}).get("ticket_snapshot") or {}
    locked_keys = [
        str(key).strip().upper()
        for key in (snapshot.get("selected_ticket_keys") or [])
        if str(key).strip()
    ]
    rn_statuses = _release_notes_statuses_for_inputs(inputs, projects)
    team_map = welcome_mod.team_ids_map_for_projects(projects, inputs)
    initial_fetch = _fetch_projects(inputs) if selection_mode != "status" else None

    result = release_ops.fetch_release_notes_extracted(
        selection_mode=selection_mode,
        projects=projects,
        release_notes_statuses_by_project=rn_statuses,
        locked_ticket_keys=locked_keys,
        include_ticket_keys=_release_notes_include_keys(inputs),
        jira_team_ids_by_project=team_map or None,
        version_name=str(inputs.get("version_name") or "").strip(),
        initial_fetch=initial_fetch,
    )
    if selection_mode == "status":
        result["review_statuses_by_project"] = dict(inputs.get("statuses_by_project") or {})
    else:
        result["review_statuses_by_project"] = None
    if result.get("status") == "blocked" and result.get("message"):
        msg = str(result["message"])
        if "include PIC-XXXX" not in msg:
            result["message"] = msg + " Say include PIC-XXXX for release notes to add an explicit override."
    return result


def _fetch_projects(inputs: dict[str, Any]) -> dict[str, Any]:
    from release_mcp import welcome as welcome_mod

    projects = _selected_projects(inputs)
    mode = str(inputs.get("selection_mode") or "fix_version").strip()

    if mode == "status":
        statuses = inputs.get("statuses_by_project")
        if not isinstance(statuses, dict) or not any(statuses.values()):
            statuses = welcome_mod.default_statuses_by_project(projects)
        team_map = welcome_mod.team_ids_map_for_projects(projects, inputs)
        return release_ops.fetch_release_tickets(
            selection_mode="status",
            projects=projects,
            statuses_by_project=statuses,
            jira_team_ids_by_project=team_map or None,
        )

    combined: list[dict] = []
    by_project: dict[str, Any] = {}
    missing: list[str] = []
    for project_key in projects:
        version_name = _version_for(inputs, project_key)
        if not version_name:
            missing.append(project_key)
            continue
        team_map = welcome_mod.team_ids_map_for_projects([project_key], inputs)
        result = release_ops.fetch_release_tickets(
            version_name,
            projects=[project_key],
            jira_team_ids_by_project=team_map or None,
        )
        if result.get("status") == "blocked":
            return result
        info = (result.get("by_project") or {}).get(project_key) or {}
        by_project[project_key] = info
        combined.extend(result.get("extracted") or [])
    return {
        "status": "needs_input" if missing else "ok",
        "projects": projects,
        "missing_projects": missing,
        "by_project": by_project,
        "extracted": combined,
        "total_tickets": len(combined),
        "selection_mode": mode,
    }


def _ticket_keys(extracted: list[dict]) -> list[str]:
    return [str(item.get("ticket") or "") for item in extracted if item.get("ticket")]


def _effective_extracted(session: dict[str, Any]) -> list[dict]:
    """Post-QA filtered extracted list when release notes step has run."""
    artifacts = session.get("artifacts") or {}
    if artifacts.get("release_notes_extracted") is not None:
        return list(artifacts["release_notes_extracted"])
    snapshot = artifacts.get("ticket_snapshot") or {}
    return list(snapshot.get("extracted") or [])


def _consolidation_suggestions_for_session(session: dict[str, Any]) -> list[dict[str, Any]]:
    from consolidation_detector import detect_consolidation_opportunities

    extracted = _effective_extracted(session)
    return [item.to_dict() for item in detect_consolidation_opportunities(extracted)]


def _apply_consolidation_if_requested(session: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Apply ``apply_consolidation`` input (label or zero-based index) when set."""
    from consolidation_detector import apply_suggestion, detect_consolidation_opportunities

    token = session.get("inputs", {}).get("apply_consolidation")
    if token is None or token == "":
        return session, None

    extracted = list(_effective_extracted(session))
    suggestions = detect_consolidation_opportunities(extracted)
    if not suggestions:
        return session, _response(
            session,
            status="needs_input",
            prompt="No consolidation suggestions available for the current ticket list.",
            preview={"consolidation_suggestions": []},
        )

    chosen = None
    if isinstance(token, int) or (isinstance(token, str) and str(token).isdigit()):
        index = int(token)
        if 0 <= index < len(suggestions):
            chosen = suggestions[index]
    if chosen is None:
        needle = str(token).strip().lower()
        for suggestion in suggestions:
            if suggestion.label.strip().lower() == needle:
                chosen = suggestion
                break
    if chosen is None:
        return session, _response(
            session,
            status="needs_input",
            prompt="apply_consolidation did not match a suggestion. Use label or zero-based index.",
            preview={"consolidation_suggestions": [s.to_dict() for s in suggestions]},
            questions=[
                _question(
                    "apply_consolidation",
                    "Suggestion label (e.g. dashboard name) or index from consolidation_suggestions.",
                    required=False,
                ),
            ],
        )

    merged = apply_suggestion(extracted, chosen)
    snapshot = dict(session["artifacts"].get("ticket_snapshot") or {})
    snapshot["extracted"] = merged
    snapshot["selected_ticket_keys"] = _ticket_keys(merged)
    snapshot["ticket_keys"] = snapshot["selected_ticket_keys"]
    session = wizard_store.update_session(
        session["id"],
        inputs={"apply_consolidation": None},
        drafts={"service_ticket": None},
        artifacts={
            "ticket_snapshot": snapshot,
            "release_notes_extracted": merged,
        },
        audit_event="consolidation_applied",
        audit_detail={"label": chosen.label, "tickets": chosen.tickets},
    )
    return session, None


def _effective_selected_keys(session: dict[str, Any]) -> list[str]:
    return list(session["artifacts"]["ticket_snapshot"].get("selected_ticket_keys") or [])


def _shipit_post_create_kwargs(session: dict[str, Any]) -> dict[str, Any]:
    """Build flexible SHIPIT post-create options from wizard session inputs."""
    inputs = session.get("inputs") or {}
    overrides: dict[str, Any] = dict(inputs.get("shipit_post_create") or {})
    if inputs.get("skip_shipit_link_tickets"):
        overrides["link_release_tickets"] = False
    if inputs.get("skip_shipit_review_ready"):
        overrides["transition_to_status"] = False
    if inputs.get("skip_shipit_assignee"):
        overrides["assign_to_creator"] = False
    if inputs.get("shipit_post_create_disabled"):
        overrides["enabled"] = False
    kwargs: dict[str, Any] = {}
    if overrides:
        kwargs["post_create_overrides"] = overrides
    owner = str(inputs.get("shipit_owner_account_id") or "").strip()
    if owner:
        kwargs["shipit_owner_account_id"] = owner
    return kwargs


def _run_teams_meeting(session: dict[str, Any], kind: str) -> dict[str, Any] | None:
    """Optional Teams scheduling — disabled when archived."""
    if config.teams_archived():
        return None
    payload = session["inputs"].get(f"teams_{kind}_meeting")
    if not isinstance(payload, dict) or not payload.get("start"):
        return None
    schedule_live = bool(payload.get("schedule"))
    return teams_ops.teams_schedule_meeting(
        kind=kind,
        start=str(payload["start"]),
        end=str(payload["end"]) if payload.get("end") else None,
        subject=str(payload.get("subject") or ""),
        timezone_name=str(payload.get("timezone") or "") or None,
        attendees=payload.get("attendees"),
        body=str(payload.get("body") or ""),
        version=_release_version_label(session),
        dry_run=not schedule_live,
    )


def _suggest_deployment_info(session: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, dict], list[str]]:
    grouped_keys = list((context.get("tickets_by_client") or {}).keys())
    draft = (session.get("drafts") or {}).get("release_notes") or {}
    docx = session["artifacts"].get("release_notes_docx") or {}
    docx_bytes = None
    docx_path = docx.get("docx_path")
    if docx_path:
        try:
            docx_bytes = Path(docx_path).read_bytes()
        except OSError:
            docx_bytes = None
    version_label = _release_version_label(session)
    return deploy_prefill.build_deploy_prefill(
        grouped_keys,
        deployment_row_text=str(draft.get("deployment_rows") or ""),
        docx_bytes=docx_bytes,
        sharepoint_url=str(session["artifacts"].get("sharepoint_url") or ""),
        release_version=version_label.lstrip("vV") or None,
    )


def _extracted_to_jira_issues(extracted: list[dict]) -> list[dict]:
    issues: list[dict] = []
    for item in extracted:
        key = str(item.get("ticket") or "").strip()
        if not key:
            continue
        project = str(item.get("project") or key.split("-", 1)[0]).upper()
        issues.append(
            {
                "key": key,
                "fields": {
                    "summary": str(item.get("summary") or ""),
                    "status": {"name": str(item.get("status") or "")},
                    "assignee": {
                        "displayName": str(item.get("assignee") or "Unassigned"),
                        "emailAddress": str(item.get("assignee_email") or ""),
                    },
                    "project": {"key": project},
                },
            }
        )
    return issues


def _jira_issues_for_selected(session: dict[str, Any]) -> list[dict]:
    snapshot = session["artifacts"]["ticket_snapshot"]
    fetch = session["artifacts"]["ticket_fetch"]
    selected = {str(key) for key in snapshot.get("selected_ticket_keys") or [] if str(key).strip()}
    issues: list[dict] = []
    for project_key, info in fetch.get("by_project", {}).items():
        version_id = str(info.get("version_id") or "").strip()
        if not version_id:
            continue
        for issue in jira_client.get_issues_for_version(project_key, version_id):
            if issue.get("key") in selected:
                issues.append(issue)
    return issues


def _gate_notify_flags(inputs: dict[str, Any], prefix: str) -> tuple[bool, bool]:
    notify = bool(inputs.get(f"{prefix}_notify"))
    dry_run = bool(inputs.get(f"{prefix}_dry_run", True))
    if notify:
        return True, dry_run
    return False, True


def _snapshot_drift(session: dict[str, Any]) -> dict[str, Any]:
    """Compare the locked snapshot with current fix-version membership."""
    snapshot = session["artifacts"]["ticket_snapshot"]
    fetch = session["artifacts"]["ticket_fetch"]
    selected = set(snapshot.get("selected_ticket_keys") or [])
    result: dict[str, Any] = {}
    has_drift = False
    missing_from_release: list[str] = []
    for project_key, original in fetch["by_project"].items():
        version_name = _version_for(session["inputs"], project_key)
        version = release_ops.resolve_version(project_key, version_name)
        current_issues = jira_client.get_issues_for_version(project_key, version["id"])
        current = {issue["key"] for issue in current_issues}
        original_keys = {ticket["key"] for ticket in original.get("tickets", [])}
        required = {key for key in selected if key.startswith(f"{project_key}-")}
        missing_selected = sorted(required - current)
        added = sorted(current - original_keys)
        project_drift = bool(missing_selected or added)
        has_drift = has_drift or project_drift
        missing_from_release.extend(missing_selected)
        result[project_key] = {
            "missing_selected": missing_selected,
            "missing_from_release": missing_selected,
            "added_since_lock": added,
            "has_drift": project_drift,
            "version_id": version.get("id"),
            "version_name": version.get("name"),
        }
    return {
        "has_drift": has_drift,
        "missing_from_release": missing_from_release,
        "projects": result,
    }


def _relock_ticket_snapshot(session: dict[str, Any]) -> dict[str, Any]:
    """Refresh the locked snapshot from current Jira membership (audited)."""
    inputs = dict(session["inputs"])
    fetch = _fetch_projects(inputs)
    if fetch.get("status") == "needs_input" or not fetch.get("extracted"):
        return wizard_store.update_session(
            session["id"],
            inputs={"relock_snapshot": False},
            audit_event="ticket_snapshot_relock_failed",
        )
    previous = set((session.get("artifacts") or {}).get("ticket_snapshot", {}).get("selected_ticket_keys") or [])
    all_keys = _ticket_keys(fetch["extracted"])
    current_set = set(all_keys)
    # Keep prior selections that still exist; newly discovered keys are selected.
    kept = [key for key in all_keys if key in previous]
    added = [key for key in all_keys if key not in previous]
    selected = kept + added
    excluded = [key for key in all_keys if key not in set(selected)]
    snapshot = {
        "locked_at": datetime.now().astimezone().isoformat(),
        "by_project": fetch["by_project"],
        "all_ticket_keys": all_keys,
        "selected_ticket_keys": selected,
        "excluded_ticket_keys": excluded,
        "extracted": [item for item in fetch["extracted"] if item.get("ticket") in set(selected)],
        "relocked": True,
    }
    return wizard_store.update_session(
        session["id"],
        inputs={"relock_snapshot": False, "proceed_with_locked_snapshot": False},
        artifacts={
            "ticket_fetch": fetch,
            "ticket_snapshot": snapshot,
            "ticket_snapshot_draft": snapshot,
        },
        audit_event="ticket_snapshot_relocked",
        audit_detail={
            "selected": len(selected),
            "added": added,
            "removed_from_jira": sorted(previous - current_set),
        },
    )


def _handle_relock_request(session: dict[str, Any]) -> dict[str, Any] | None:
    if not session["inputs"].get("relock_snapshot"):
        return None
    session = _relock_ticket_snapshot(session)
    return _process(session)


def _confirmation(
    session: dict[str, Any],
    preview: Any,
    prompt: str,
    *,
    actions: list[str] | None = None,
) -> dict[str, Any]:
    session = wizard_store.update_session(
        session["id"],
        artifacts={"pending_preview": preview},
        audit_event="previewed",
        audit_detail={"step": session["step"]},
    )
    session = wizard_store.store_confirmation(session["id"], session["step"], preview)
    token = session["confirmations"][session["step"]]["token"]
    return _response(
        session,
        status="awaiting_confirmation",
        prompt=prompt,
        preview=preview,
        confirmation_token=token,
        allowed_actions=actions or ["confirm", "update", "back", "cancel"],
    )


def _check_confirmation(
    session: dict[str, Any],
    token: str | None,
) -> tuple[bool, Any]:
    preview = (session.get("artifacts") or {}).get("pending_preview")
    if preview is None or not token:
        return False, preview
    return (
        wizard_store.check_confirmation(
            session["id"],
            session["step"],
            token,
            preview,
        ),
        preview,
    )


def _process_ticket_review(session: dict[str, Any]) -> dict[str, Any]:
    inputs = session["inputs"]
    blocked = team_scope.projects_missing_scope()
    if blocked:
        return _response(
            session,
            status="blocked",
            prompt=(
                "Team ticket scope is not configured for: "
                + ", ".join(blocked)
                + ". Configure board/filter/JQL in workspace.yaml before fetching tickets."
            ),
            preview={"scope_blocked_projects": blocked},
            allowed_actions=["cancel", "status"],
        )
    selection_mode = str(inputs.get("selection_mode") or "fix_version").strip()
    has_version = bool(str(inputs.get("version_name") or "").strip() or inputs.get("versions"))
    if selection_mode != "status" and not has_version:
        from release_mcp import welcome as welcome_mod

        welcome = welcome_mod.build_welcome()
        return _response(
            session,
            status="needs_input",
            prompt=(
                "No release version yet. For review-ready tickets say "
                "action=welcome (or start with selection_mode=status). "
                "For a fix version, provide version_name."
            ),
            questions=[
                _question(
                    "selection_mode",
                    "Use status (review-ready PIC Review + AN Passed QA) or fix_version?",
                    required=False,
                ),
                _question(
                    "version_name",
                    "Release version shared by PIC and AN (for example 2026.3.08.12), "
                    "or provide versions={PIC: ..., AN: ...}.",
                    required=False,
                ),
            ],
            preview={"welcome_defaults": welcome.get("suggested_defaults")},
            allowed_actions=["update", "cancel", "status"],
        )
    if selection_mode == "status":
        from release_mcp import welcome as welcome_mod

        merged = dict(inputs)
        if not merged.get("statuses_by_project"):
            merged["statuses_by_project"] = welcome_mod.default_statuses_by_project(
                _selected_projects(merged)
            )
        if not welcome_mod.team_ids_map_for_projects(_selected_projects(merged), merged):
            team_res = welcome_mod.resolve_team(str(merged.get("jira_team_name") or ""))
            if team_res.get("status") == "ok":
                tid = str((team_res.get("team") or {}).get("id") or "")
                if tid:
                    merged["jira_team_id"] = tid
        session = wizard_store.update_session(session["id"], inputs=merged)
        inputs = merged
    fetch = _fetch_projects(inputs)
    if fetch.get("status") == "blocked":
        return _response(
            session,
            status="blocked",
            prompt=fetch.get("message", "Team scope is not configured."),
            preview=fetch,
            allowed_actions=["cancel", "status"],
        )
    if fetch["status"] == "needs_input":
        missing = fetch.get("missing_projects") or fetch.get("missing") or []
        if selection_mode == "status":
            return _response(
                session,
                status="needs_input",
                prompt="Status fetch needs statuses_by_project and optional team filter.",
                questions=fetch.get("questions")
                or [
                    _question(
                        "statuses_by_project",
                        'Map statuses, e.g. {"PIC": ["Review"], "AN": ["Passed QA"]}',
                    ),
                    _question("jira_team_name", "Jira team (default Glofox Insights Customize)", required=False),
                ],
                preview=fetch,
            )
        return _response(
            session,
            status="needs_input",
            prompt="Tell me which release version to review for PIC and AN.",
            questions=[
                _question(
                    "version_name",
                    "Release version shared by PIC and AN (for example 2026.3.08.12), "
                    "or provide versions={PIC: ..., AN: ...}.",
                )
            ],
            preview={"missing_projects": missing},
        )
    if not fetch["extracted"]:
        return _response(
            session,
            status="error",
            prompt="No tickets were found for the selected release versions.",
            preview=fetch["by_project"],
        )

    extracted = list(fetch["extracted"])
    in_progress_payload = release_gates.filter_extracted_in_progress_review_candidates(extracted)
    extracted = list(in_progress_payload.get("kept") or extracted)
    held_keys: set[str] = set(in_progress_payload.get("held_back_keys") or [])
    review_comment_payload: dict[str, Any] | None = None
    if release_gates.skip_review_completed_comments_enabled():
        review_comment_payload = release_gates.filter_extracted_review_completed_comments(extracted)
        if review_comment_payload.get("status") != "disabled":
            extracted = list(review_comment_payload.get("kept") or [])
            held_keys |= set(review_comment_payload.get("held_back_keys") or [])
    outside_squad_payload = release_gates.filter_extracted_outside_squad_assignees(
        extracted,
        include_outside_squad=bool(inputs.get("include_outside_squad_assignees")),
    )
    if outside_squad_payload.get("status") == "ok":
        extracted = list(outside_squad_payload.get("kept") or extracted)
    if held_keys:
        fetch = {
            **fetch,
            "extracted": extracted,
            "by_project": {
                pk: {
                    **block,
                    "tickets": [
                        t
                        for t in (block.get("tickets") or [])
                        if str(t.get("key") or "").upper() not in held_keys
                    ],
                    "count": len(
                        [
                            t
                            for t in (block.get("tickets") or [])
                            if str(t.get("key") or "").upper() not in held_keys
                        ]
                    ),
                }
                for pk, block in (fetch.get("by_project") or {}).items()
            },
        }
    if not extracted and (review_comment_payload or in_progress_payload.get("held_back_keys")):
        return _response(
            session,
            status="blocked",
            prompt=(
                "No tickets left after comment filters — every ticket needs a "
                "'ready for review' Jira comment (status alone is not enough); "
                "tickets with 'review done' comments are excluded. "
                "Move release-ready "
                "tickets to Ready for Release / QA or pick **start with release notes**."
            ),
            preview={
                "review_comment_gate": review_comment_payload,
                "in_progress_gate": in_progress_payload,
                "by_project": fetch.get("by_project"),
            },
            allowed_actions=["cancel", "status"],
        )

    pre_review_payload: dict[str, Any] | None = None
    if release_gates.gate_enabled("pre_review"):
        version_label = _release_version_label({"inputs": inputs})
        notify, dry_run = _gate_notify_flags(inputs, "pre_review")
        pre_review_payload = release_gates.run_pre_review_gate(
            _extracted_to_jira_issues(extracted),
            version_name=version_label,
            notify=notify,
            dry_run=dry_run,
        )
        ready_keys = {str(key) for key in pre_review_payload.get("ready_keys") or [] if key}
        extracted = [item for item in extracted if str(item.get("ticket") or "") in ready_keys]
        fetch = {**fetch, "extracted": extracted}
        if not extracted:
            return _response(
                session,
                status="blocked",
                prompt=(
                    "All tickets are held back by the pre-review gate (not in a review-ready Jira status). "
                    "Move tickets to a review-ready status or disable release_gates.pre_review."
                ),
                preview={"pre_review_gate": pre_review_payload, "by_project": fetch["by_project"]},
                allowed_actions=["cancel", "status"],
            )

    all_keys = _ticket_keys(extracted)
    exclude_assignee_names = [
        str(name).strip()
        for name in (inputs.get("exclude_assignee_names") or [])
        if str(name).strip()
    ]
    assignee_excluded_keys = release_gates.keys_matching_assignee_patterns(
        extracted, exclude_assignee_names
    )
    requested = inputs.get("selected_ticket_keys")
    if requested is not None:
        selected = [key for key in all_keys if key in {str(item) for item in requested}]
    else:
        selected = [key for key in all_keys if key not in set(assignee_excluded_keys)]
    excluded = [key for key in all_keys if key not in set(selected)]
    snapshot = {
        "locked_at": datetime.now().astimezone().isoformat(),
        "by_project": fetch["by_project"],
        "all_ticket_keys": all_keys,
        "selected_ticket_keys": selected,
        "excluded_ticket_keys": excluded,
        "extracted": [item for item in fetch["extracted"] if item.get("ticket") in set(selected)],
    }
    session = wizard_store.update_session(
        session["id"],
        artifacts={
            "ticket_fetch": fetch,
            "ticket_snapshot_draft": snapshot,
            **({"pre_review_gate": pre_review_payload} if pre_review_payload else {}),
            **({"review_comment_gate": review_comment_payload} if review_comment_payload else {}),
        },
        audit_event="tickets_fetched",
        audit_detail={"count": len(all_keys)},
    )
    preview = {
        "projects": fetch["projects"],
        "total_tickets": len(all_keys),
        "selected_count": len(selected),
        "excluded_count": len(excluded),
        "selected_ticket_keys": selected,
        "excluded_ticket_keys": excluded,
        "tickets_by_project": {key: value.get("tickets", []) for key, value in fetch["by_project"].items()},
    }
    if in_progress_payload.get("held_back"):
        preview["in_progress_gate"] = {
            "held_back_count": len(in_progress_payload.get("held_back") or []),
            "held_back_keys": in_progress_payload.get("held_back_keys") or [],
            "held_back": in_progress_payload.get("held_back") or [],
            "phrases": in_progress_payload.get("phrases") or [],
        }
    if review_comment_payload and review_comment_payload.get("held_back"):
        preview["review_comment_gate"] = {
            "held_back_count": len(review_comment_payload.get("held_back") or []),
            "held_back_keys": review_comment_payload.get("held_back_keys") or [],
            "held_back": review_comment_payload.get("held_back") or [],
            "phrases": review_comment_payload.get("phrases") or [],
        }
    if outside_squad_payload.get("skipped"):
        preview["skipped_outside_squad"] = {
            "count": len(outside_squad_payload.get("skipped") or []),
            "ticket_keys": outside_squad_payload.get("skipped_keys") or [],
            "skipped": outside_squad_payload.get("skipped") or [],
            "note": "Outside-squad / TEAM_CREW_EXCLUDE assignees (Gabriel, Erasmo, etc.) are never included.",
        }
    supplement_keys = list(fetch.get("supplement_squad_assignee_keys") or [])
    if supplement_keys:
        preview["supplement_squad_assignee"] = {
            "count": len(supplement_keys),
            "ticket_keys": supplement_keys,
            "note": "In-squad tickets added despite missing/wrong Jira Team field.",
        }
    assignee_check = release_gates.build_assignee_check(extracted)
    preview["assignee_check"] = assignee_check
    if exclude_assignee_names:
        preview["assignee_excluded"] = {
            "patterns": exclude_assignee_names,
            "ticket_keys": assignee_excluded_keys,
        }
    if pre_review_payload:
        preview["pre_review_gate"] = {
            "held_back_count": pre_review_payload.get("blocked_count", 0),
            "held_back_keys": [item.get("key") for item in pre_review_payload.get("blocked") or [] if item.get("key")],
            "ready_statuses": list(release_gates.pre_review_statuses()),
            "slack": pre_review_payload.get("slack"),
        }
    preview["teams_schedule"] = {
        "status": teams_ops.teams_schedule_status(),
        "optional_input": "teams_review_meeting",
        "schema": {
            "start": "ISO-8601 datetime",
            "end": "ISO-8601 datetime (optional)",
            "subject": "Meeting subject",
            "timezone": "IANA timezone",
            "attendees": ["email@example.com"],
            "schedule": "Set true on confirm to create live (default dry-run preview)",
        },
    }
    return _confirmation(
        session,
        preview,
        "Review the PIC/AN list. Confirm to lock it, or update selected_ticket_keys to include/exclude tickets."
        + (
            " Pre-review gate removed tickets that are not review-ready."
            if pre_review_payload and pre_review_payload.get("blocked_count")
            else ""
        )
        + (
            " Tickets missing a ready-for-review Jira comment were held back."
            if in_progress_payload.get("held_back")
            else ""
        )
        + (
            " Tickets with review-complete Jira comments were held back."
            if review_comment_payload and review_comment_payload.get("held_back")
            else ""
        ),
    )


def _confirm_ticket_review(session: dict[str, Any]) -> dict[str, Any]:
    snapshot = session["artifacts"]["ticket_snapshot_draft"]
    session = wizard_store.update_session(
        session["id"],
        step=STEP_EXCLUSIONS,
        artifacts={"ticket_snapshot": snapshot},
        audit_event="ticket_snapshot_locked",
        audit_detail={
            "selected": len(snapshot["selected_ticket_keys"]),
            "excluded": len(snapshot["excluded_ticket_keys"]),
        },
    )
    teams_result = _run_teams_meeting(session, "review")
    if teams_result is not None:
        session = wizard_store.update_session(
            session["id"],
            artifacts={"teams_review_meeting": teams_result},
            audit_event="teams_review_meeting",
        )
    return _process_exclusions(session)


def _exclusions_by_project(session: dict[str, Any]) -> dict[str, list[str]]:
    """Return fix-version removal candidates grouped by project.

    Defaults to Ticket Review exclusions. When ``exclusion_ticket_keys`` is
    provided, those keys replace the default (must still be on the version).
    """
    snapshot = session["artifacts"]["ticket_snapshot"]
    fetch = session["artifacts"]["ticket_fetch"]
    override = session["inputs"].get("exclusion_ticket_keys")
    if override is not None:
        excluded = {str(key) for key in override if str(key).strip()}
    else:
        excluded = set(snapshot.get("excluded_ticket_keys") or [])
    result: dict[str, list[str]] = {}
    for project_key, info in fetch["by_project"].items():
        keys = [ticket["key"] for ticket in info.get("tickets", []) if ticket.get("key") in excluded]
        if keys:
            result[project_key] = keys
    return result


def _exclusion_candidates(session: dict[str, Any]) -> dict[str, Any]:
    """All fix-version tickets with review exclusions pre-selected (Streamlit parity)."""
    snapshot = session["artifacts"]["ticket_snapshot"]
    fetch = session["artifacts"]["ticket_fetch"]
    review_excluded = set(snapshot.get("excluded_ticket_keys") or [])
    by_project: dict[str, Any] = {}
    for project_key, info in fetch["by_project"].items():
        tickets = list(info.get("tickets") or [])
        by_project[project_key] = {
            "version": info.get("version"),
            "all_ticket_keys": [t["key"] for t in tickets if t.get("key")],
            "preselected_exclusion_keys": [t["key"] for t in tickets if t.get("key") in review_excluded],
            "tickets": tickets,
        }
    return {
        "by_project": by_project,
        "review_excluded_ticket_keys": sorted(review_excluded),
        "effective_exclusion_keys": _exclusions_by_project(session),
    }


def _process_exclusions(session: dict[str, Any]) -> dict[str, Any]:
    candidates = _exclusion_candidates(session)
    by_project = candidates["effective_exclusion_keys"]
    review_excluded = candidates["review_excluded_ticket_keys"]

    if session["inputs"].get("skip_fix_version_removal"):
        session = wizard_store.update_session(
            session["id"],
            step=STEP_RELEASE_NOTES,
            artifacts={
                "exclusion_results": {
                    "status": "skipped",
                    "tickets": by_project
                    or {
                        project: candidates["by_project"][project]["preselected_exclusion_keys"]
                        for project in candidates["by_project"]
                        if candidates["by_project"][project]["preselected_exclusion_keys"]
                    },
                    "warning": ("Review exclusions still carry the fix version in Jira." if review_excluded else None),
                }
            },
            audit_event="exclusions_skipped",
        )
        return _process_release_notes(session)

    # Explicit empty list = continue without removing (Streamlit "Continue without excluding").
    if session["inputs"].get("exclusion_ticket_keys") == []:
        session = wizard_store.update_session(
            session["id"],
            step=STEP_RELEASE_NOTES,
            artifacts={
                "exclusion_results": {
                    "status": "not_needed",
                    "warning": (
                        "Continue without excluding — review exclusions may still carry the fix version."
                        if review_excluded
                        else None
                    ),
                }
            },
            audit_event="exclusions_not_needed",
        )
        return _process_release_notes(session)

    if not by_project:
        session = wizard_store.update_session(
            session["id"],
            step=STEP_RELEASE_NOTES,
            artifacts={
                "exclusion_results": {"status": "not_needed"},
                "exclusion_candidates": candidates,
            },
            audit_event="exclusions_not_needed",
        )
        return _process_release_notes(session)

    previews: dict[str, Any] = {}
    for project_key, keys in by_project.items():
        previews[project_key] = exclusion_ops.preview_exclusion(
            project_key,
            _version_for(session["inputs"], project_key),
            keys,
        )
    preview = {
        "candidates": candidates,
        "previews": previews,
        "exclusion_ticket_keys": [key for keys in by_project.values() for key in keys],
        "note": (
            "Update exclusion_ticket_keys to include any additional tickets still "
            "on the fix version (Streamlit Exclude Tickets parity)."
        ),
    }
    return _confirmation(
        session,
        preview,
        "These tickets will lose the fix version. Confirm to remove it, "
        "update exclusion_ticket_keys to change the set, or set "
        "skip_fix_version_removal=true to leave Jira unchanged.",
    )


def _confirm_exclusions(session: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    partial = False
    for project_key, keys in _exclusions_by_project(session).items():
        results[project_key] = exclusion_ops.remove_fix_versions(
            project_key,
            _version_for(session["inputs"], project_key),
            keys,
            dry_run=False,
        )
        if results[project_key].get("status") == "partial":
            partial = True
        if results[project_key].get("status") == "failed":
            partial = True
    session = wizard_store.update_session(
        session["id"],
        artifacts={"exclusion_results": results},
        audit_event="fix_versions_removed",
    )
    if partial:
        return _response(
            session,
            status="error",
            prompt=(
                "Fix-version exclusion was partial or failed. Review per-key errors, "
                "then update and re-confirm. Release notes are not generated yet."
            ),
            preview=results,
            allowed_actions=["update", "resume", "back", "cancel"],
        )
    session = wizard_store.update_session(
        session["id"],
        step=STEP_RELEASE_NOTES,
        artifacts={"exclusion_results": results},
        audit_event="exclusions_completed",
    )
    return _process_release_notes(session)


def _ticket_keys_for_release_date(session: dict[str, Any]) -> list[str]:
    snapshot = (session.get("artifacts") or {}).get("ticket_snapshot") or {}
    keys = [
        str(k).strip().upper()
        for k in (snapshot.get("selected_ticket_keys") or [])
        if str(k).strip()
    ]
    if keys:
        return keys
    fetch = (session.get("artifacts") or {}).get("ticket_fetch") or {}
    return [
        str(item.get("ticket") or "").strip().upper()
        for item in (fetch.get("extracted") or [])
        if str(item.get("ticket") or "").strip()
    ]


def _gate_release_date(session: dict[str, Any], *, return_step: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Block Release Notes / SHIPIT until release date is confirmed (Jira-first)."""
    import release_date_confirm

    inputs = session.get("inputs") or {}
    if inputs.get("release_date_confirmed") and str(inputs.get("version_name") or "").strip():
        return session, None

    keys = _ticket_keys_for_release_date(session)
    proposal = release_date_confirm.build_release_date_proposal(session, keys)
    prompt = release_date_confirm.format_confirmation_prompt(proposal)
    session = wizard_store.update_session(
        session["id"],
        step=STEP_RELEASE_DATE,
        artifacts={
            "release_date_proposal": proposal,
            "release_date_return_step": return_step,
        },
        audit_event="release_date_proposed",
        audit_detail={"source": proposal.get("source"), "version": proposal.get("version_name")},
    )
    return session, _confirmation(
        session,
        {"release_date_proposal": proposal},
        prompt,
    )


def _process_release_date(session: dict[str, Any]) -> dict[str, Any]:
    import release_date_confirm

    return_step = str(
        (session.get("artifacts") or {}).get("release_date_return_step") or STEP_RELEASE_NOTES
    )
    keys = _ticket_keys_for_release_date(session)
    proposal = release_date_confirm.build_release_date_proposal(session, keys)
    prompt = release_date_confirm.format_confirmation_prompt(proposal)
    session = wizard_store.update_session(
        session["id"],
        artifacts={
            "release_date_proposal": proposal,
            "release_date_return_step": return_step,
        },
    )
    return _confirmation(session, {"release_date_proposal": proposal}, prompt)


def _confirm_release_date(session: dict[str, Any]) -> dict[str, Any]:
    import release_date_confirm

    proposal = (session.get("artifacts") or {}).get("release_date_proposal") or {}
    try:
        confirmed = release_date_confirm.confirmed_inputs(session.get("inputs") or {}, proposal)
    except ValueError as exc:
        return _response(
            session,
            status="needs_input",
            prompt=str(exc),
            preview={"release_date_proposal": proposal},
        )
    return_step = str(
        (session.get("artifacts") or {}).get("release_date_return_step") or STEP_RELEASE_NOTES
    )
    session = wizard_store.update_session(
        session["id"],
        inputs=confirmed,
        step=return_step,
        audit_event="release_date_confirmed",
        audit_detail={"version_name": confirmed.get("version_name"), "source": confirmed.get("release_date_source")},
    )
    return _process(session)


def _release_version_label(session: dict[str, Any]) -> str:
    inputs = session["inputs"]
    if inputs.get("release_date_confirmed"):
        confirmed = str(inputs.get("version_name") or inputs.get("release_version") or "").strip()
        if confirmed:
            return confirmed.lstrip("vV")
    explicit = str(inputs.get("version_name") or inputs.get("release_version") or "").strip()
    fix_names = [
        _version_for(inputs, project)
        for project in _selected_projects(inputs)
        if _version_for(inputs, project)
    ]
    deploy_on: date | None = None
    for key in ("planned_start_date", "planned_deploy_date"):
        raw = str(inputs.get(key) or "").strip()
        if raw:
            try:
                deploy_on = date.fromisoformat(raw)
                break
            except ValueError:
                continue
    if deploy_on is None:
        schedule = (session.get("artifacts") or {}).get("service_ticket_schedule")
        if isinstance(schedule, dict) and schedule.get("start_date"):
            try:
                deploy_on = date.fromisoformat(str(schedule["start_date"]))
            except ValueError:
                deploy_on = None
    # Do not silently apply T+1 here — release_date_confirm step must confirm first.
    from generators.release_notes_draft import resolve_release_version_metadata

    version, _ = resolve_release_version_metadata(
        explicit=explicit,
        fix_version_names=fix_names,
        deploy_on=deploy_on,
    )
    return version.lstrip("vV")


def _process_release_notes(session: dict[str, Any]) -> dict[str, Any]:
    session, bootstrap_err = _ensure_ticket_snapshot(session)
    if bootstrap_err is not None:
        return bootstrap_err
    snapshot = session["artifacts"]["ticket_snapshot"]
    rn_fetch = _fetch_release_notes_extracted(session)
    if rn_fetch.get("status") == "blocked":
        statuses = rn_fetch.get("release_notes_statuses_by_project") or {}
        status_summary = ", ".join(
            f"{project_key}: {', '.join(values)}"
            for project_key, values in statuses.items()
            if values
        )
        not_ready = rn_fetch.get("not_release_ready_keys") or []
        locked = rn_fetch.get("locked_keys") or []
        override_errors = (rn_fetch.get("override_fetch") or {}).get("errors") or {}
        return _response(
            session,
            status="needs_input",
            prompt=(
                "Release Notes require release-ready tickets only "
                f"({status_summary}). "
                + (f"Locked but not release-ready: {', '.join(not_ready)}. " if not_ready else "")
                + str(rn_fetch.get("message") or "No tickets matched.")
                + " Move tickets in Jira, re-lock in Ticket Review, say "
                "include PIC-XXXX for release notes for a one-off override, or use "
                "release_notes_only with selection_mode=status to fetch release-ready tickets directly."
                + (
                    f" Override fetch failed for: {', '.join(f'{k} ({v})' for k, v in override_errors.items())}."
                    if override_errors
                    else ""
                )
            ),
            preview={
                "release_notes_statuses_by_project": statuses,
                "review_statuses_by_project": rn_fetch.get("review_statuses_by_project"),
                "locked_ticket_keys": locked,
                "not_release_ready_keys": not_ready,
                "explicit_override_keys": rn_fetch.get("explicit_override_keys") or [],
                "release_ready_ticket_keys": rn_fetch.get("release_ready_ticket_keys") or [],
            },
        )
    extracted = list(rn_fetch["extracted"])
    post_qa_payload: dict[str, Any] | None = None
    excluded_lines = list(snapshot.get("excluded_ticket_keys") or [])
    excluded_text = "\n".join(excluded_lines)
    blocked_keys: set[str] = set()

    if release_gates.gate_enabled("post_qa"):
        issues = _jira_issues_for_selected(session)
        qa_classify = release_gates.classify_post_qa(issues)
        blocked_keys = {ticket.key for ticket in qa_classify.blocked}
        if blocked_keys and not session["inputs"].get("post_qa_apply"):
            if not session["inputs"].get("post_qa_skip"):
                return _response(
                    session,
                    status="needs_input",
                    prompt=(
                        "Post-QA gate found ticket(s) that did not pass QA. "
                        "Set post_qa_apply=true to exclude them from release notes and downstream steps, "
                        "or post_qa_skip=true to continue without excluding (audited override)."
                    ),
                    questions=[
                        _question(
                            "post_qa_apply",
                            "Set true to exclude QA-failed tickets from this release.",
                            required=False,
                        ),
                        _question(
                            "post_qa_skip",
                            "Set true to keep QA-failed tickets (audited override).",
                            required=False,
                        ),
                    ],
                    preview={
                        "qa_failed_count": len(blocked_keys),
                        "qa_failed_keys": sorted(blocked_keys),
                        "passed_statuses": list(release_gates.qa_passed_statuses()),
                    },
                )

        notify, dry_run = _gate_notify_flags(session["inputs"], "post_qa")
        post_qa_payload = release_gates.run_post_qa_gate(
            issues,
            version_name=_release_version_label(session),
            notify=notify,
            dry_run=dry_run,
        )
        if blocked_keys and session["inputs"].get("post_qa_apply"):
            excluded_text = release_gates.merge_excluded_text(excluded_text, qa_classify.blocked)
            extracted = [item for item in extracted if str(item.get("ticket") or "") not in blocked_keys]
            snapshot = dict(snapshot)
            snapshot["selected_ticket_keys"] = [
                key
                for key in snapshot.get("selected_ticket_keys") or []
                if str(key) not in blocked_keys
            ]
            snapshot["qa_excluded_keys"] = sorted(
                set(snapshot.get("qa_excluded_keys") or []) | blocked_keys
            )

    session, date_gate = _gate_release_date(session, return_step=STEP_RELEASE_NOTES)
    if date_gate is not None:
        return date_gate

    import github_pr_gate

    github_pr_payload: dict[str, Any] | None = None
    github_pr_comments: dict[str, Any] | None = None
    if extracted and github_pr_gate.gate_enabled():
        github_pr_payload = github_pr_gate.run_pr_gate(extracted, dry_run=True)
        artifacts = session.get("artifacts") or {}
        if (
            github_pr_payload.get("blocking_count")
            and github_pr_gate.auto_comment_enabled()
            and not artifacts.get("github_pr_comments_posted")
            and not session["inputs"].get("skip_github_pr_comments")
        ):
            github_pr_comments = github_pr_gate.post_pr_comments(
                github_pr_payload,
                dry_run=bool(session["inputs"].get("github_pr_comment_dry_run")),
            )
            if github_pr_comments.get("posted") and not github_pr_comments.get("dry_run"):
                session = wizard_store.update_session(
                    session["id"],
                    artifacts={"github_pr_comments_posted": True},
                    audit_event="github_pr_comments_posted",
                    audit_detail={
                        "posted": [p.get("ticket") for p in github_pr_comments.get("posted") or []],
                    },
                )

    draft = dict((session.get("drafts") or {}).get("release_notes") or {})
    if not draft:
        draft = release_ops._build_docx_data(extracted, _release_version_label(session))
    if session["inputs"].get("apply_suggested_summary") or not str(draft.get("summary_p1") or "").strip():
        if extracted:
            draft["summary_p1"] = build_release_summary_paragraph(extracted)
    if post_qa_payload:
        draft["excluded_tickets"] = excluded_text
    elif not draft.get("excluded_tickets"):
        draft["excluded_tickets"] = excluded_text
    patch = session["inputs"].get("release_notes_draft")
    if isinstance(patch, dict):
        draft.update(patch)
    artifacts: dict[str, Any] = {
        "release_notes_extracted": extracted,
        "release_notes_fetch": {
            "release_notes_statuses_by_project": rn_fetch.get("release_notes_statuses_by_project"),
            "not_release_ready_keys": rn_fetch.get("not_release_ready_keys") or [],
            "explicit_override_keys": rn_fetch.get("explicit_override_keys") or [],
            "release_ready_ticket_keys": rn_fetch.get("release_ready_ticket_keys") or [],
            "comment_included_keys": rn_fetch.get("comment_included_keys") or [],
        },
    }
    if blocked_keys and session["inputs"].get("post_qa_apply"):
        artifacts["ticket_snapshot"] = snapshot
    if post_qa_payload:
        artifacts["post_qa_gate"] = post_qa_payload
    if github_pr_payload:
        artifacts["github_pr_gate"] = github_pr_payload
    if github_pr_comments:
        artifacts["github_pr_comments"] = github_pr_comments
    session = wizard_store.update_session(
        session["id"],
        drafts={"release_notes": draft},
        artifacts=artifacts,
        audit_event="release_notes_draft_built",
    )
    readiness = assess_release_notes_readiness(draft)
    rn_statuses = rn_fetch.get("release_notes_statuses_by_project") or {}
    explicit_overrides = rn_fetch.get("explicit_override_keys") or []
    comment_included = rn_fetch.get("comment_included_keys") or []
    release_comment_gate = rn_fetch.get("release_comment_gate")
    preview = {
        "filename": f"Release Notes {str(draft.get('version') or '').lstrip('v')}.docx",
        "ticket_count": len(extracted),
        "release_notes_statuses_by_project": rn_statuses,
        "release_ready_ticket_keys": rn_fetch.get("release_ready_ticket_keys") or [],
        "not_release_ready_keys": rn_fetch.get("not_release_ready_keys") or [],
        "explicit_override_keys": explicit_overrides,
        "comment_included_keys": comment_included,
        "draft": draft,
        "readiness": readiness_to_dict(readiness),
        "draft_schema": release_notes_draft_schema(),
        "structured_preview": build_structured_preview(draft),
        "note": (
            "Release Notes uses release-ready statuses plus tickets with a "
            "'ready for release' Jira comment (same pattern as review-call gates). "
            + (
                f"Included via comment: {', '.join(comment_included)}. "
                if comment_included
                else ""
            )
            + (
                f"Explicit overrides (not release-ready): {', '.join(explicit_overrides)}. "
                if explicit_overrides
                else ""
            )
            + "Edit any release_notes_draft fields before confirmation. "
            "Set apply_suggested_summary=true to refresh summary_p1."
        ),
    }
    if release_comment_gate:
        preview["release_comment_gate"] = release_comment_gate
    if post_qa_payload:
        preview["post_qa_gate"] = {
            "qa_failed_count": post_qa_payload.get("blocked_count", 0),
            "qa_failed_keys": [item.get("key") for item in post_qa_payload.get("blocked") or [] if item.get("key")],
            "passed_statuses": list(release_gates.qa_passed_statuses()),
            "slack": post_qa_payload.get("slack"),
        }
    if github_pr_payload:
        preview["github_pr_gate"] = {
            "status": github_pr_payload.get("status"),
            "blocking_count": github_pr_payload.get("blocking_count", 0),
            "tickets_with_blocking_prs": github_pr_payload.get("tickets_with_blocking_prs") or [],
            "summary": github_pr_gate.format_gate_summary(github_pr_payload),
            "comments": github_pr_comments,
        }
    status_summary = ", ".join(
        f"{project_key}: {', '.join(values)}"
        for project_key, values in rn_statuses.items()
        if values
    )
    ticket_list = ", ".join(rn_fetch.get("release_ready_ticket_keys") or [])
    override_note = ""
    if explicit_overrides:
        override_note = (
            f" Explicit overrides (not release-ready): {', '.join(explicit_overrides)}."
        )
    comment_note = ""
    if comment_included:
        comment_note = (
            f" Included via 'ready for release' comment: {', '.join(comment_included)}."
        )
    return _confirmation(
        session,
        preview,
        "Review the release-notes ticket list and draft content before generating the Word DOCX. "
        f"Release-ready statuses: {status_summary}. "
        f"Also scans review statuses for Jira comments matching ready-for-release phrases. "
        f"Tickets ({len(extracted)}): {ticket_list or 'none'}."
        + comment_note
        + override_note
        + " Confirm only when this list is correct."
        + (
            " Post-QA gate excluded tickets that did not pass QA."
            if post_qa_payload and post_qa_payload.get("blocked_count")
            else ""
        )
        + (
            " " + str(preview.get("github_pr_gate", {}).get("summary") or "")
            if preview.get("github_pr_gate", {}).get("blocking_count")
            else ""
        ),
    )


def _confirm_release_notes(session: dict[str, Any]) -> dict[str, Any]:
    draft = session["drafts"]["release_notes"]
    readiness = assess_release_notes_readiness(draft)
    if not readiness.ready:
        return _response(
            session,
            status="blocked",
            prompt="Release Notes draft has blockers. Fix them or patch release_notes_draft before confirming.",
            preview={
                "readiness": readiness_to_dict(readiness),
                "draft_schema": release_notes_draft_schema(),
            },
            allowed_actions=["update", "back", "cancel"],
        )
    from generators.release_notes_publish import publish_release_notes_docx

    publish = publish_release_notes_docx(draft, enforce_readiness=True)
    if publish.status != "ok":
        return _response(
            session,
            status="blocked" if publish.status == "blocked" else "error",
            prompt=publish.error or "Release Notes generation failed readiness or hyperlink checks.",
            preview=publish.to_dict(),
        )
    docx_bytes = publish.docx_bytes or b""
    version_label = _release_version_label(session)
    docx_meta = release_ops.write_release_notes_docx_bytes(
        docx_bytes,
        version_label,
        readiness=publish.readiness,
        hyperlink_check=publish.hyperlink_check,
    )
    result = docx_meta
    if result.get("status") != "ok":
        return _response(
            session,
            status="error",
            prompt="Release Notes generation failed.",
            preview=result,
        )
    session = wizard_store.update_session(
        session["id"],
        step=STEP_SHAREPOINT,
        artifacts={"release_notes_docx": result},
        audit_event="release_notes_generated",
        audit_detail={"path": result.get("docx_path")},
    )
    import browser_automation

    if browser_automation.sharepoint_browser_upload_enabled():
        session = wizard_store.update_session(
            session["id"],
            inputs={"sharepoint_upload": "playwright"},
            audit_event="sharepoint_upload_auto_playwright",
        )
    return _process_sharepoint(session)


def _process_sharepoint(session: dict[str, Any]) -> dict[str, Any]:
    from sharepoint_url import sharepoint_validation_message, validate_sharepoint_url

    url = str(
        session["inputs"].get("sharepoint_url")
        or session["artifacts"].get("sharepoint_url")
        or ""
    ).strip()
    docx = session["artifacts"].get("release_notes_docx") or {}
    upload_status = sharepoint_ops.sharepoint_upload_status()

    if url and not validate_sharepoint_url(url):
        return _response(
            session,
            status="needs_input",
            prompt=sharepoint_validation_message(url) or "Paste a valid SharePoint (*.sharepoint.com) document URL.",
            questions=[_question("sharepoint_url", "Paste a valid SharePoint URL.", required=False)],
            preview={"docx": docx, "upload_status": upload_status},
        )

    if str(session["inputs"].get("sharepoint_decision") or "").lower() in {
        "done", "uploaded", "sharepoint done",
    } and url and validate_sharepoint_url(url):
        next_step = _advance_to_next_step(session, STEP_SHAREPOINT)
        session = wizard_store.update_session(
            session["id"],
            step=next_step,
            artifacts={"sharepoint_url": url, "sharepoint_delivery": "playwright_or_manual"},
            audit_event="sharepoint_playwright_done",
        )
        return _process_step(session, next_step)

    if url and validate_sharepoint_url(url):
        next_step = _advance_to_next_step(session, STEP_SHAREPOINT)
        session = wizard_store.update_session(
            session["id"],
            step=next_step,
            artifacts={"sharepoint_url": url},
            audit_event="sharepoint_link_saved",
        )
        return _process_step(session, next_step)

    upload_mode = str(session["inputs"].get("sharepoint_upload") or "").strip().lower()
    wants_playwright = upload_mode in {"true", "1", "yes", "playwright", "browser"}
    if (wants_playwright or session["inputs"].get("sharepoint_upload") is True) and docx.get("docx_path"):
        handoff = browser_ops.sharepoint_playwright_handoff(
            str(docx["docx_path"]),
            version_name=_release_version_label(session),
            remote_name=docx.get("docx_filename"),
        )
        preview = browser_ops.enrich_sharepoint_preview(
            {"docx": docx, "upload_status": upload_status, "playwright_upload": handoff},
            local_path=str(docx["docx_path"]),
            version_name=_release_version_label(session),
        )
        return _response(
            session,
            status="needs_input",
            prompt=(
                handoff.get("instruction")
                or "Upload via Playwright MCP, then paste the SharePoint URL or say **sharepoint done**."
            ),
            preview=preview,
            questions=[
                _question(
                    "sharepoint_url",
                    "Paste the SharePoint document URL after upload.",
                    required=False,
                ),
                _question(
                    "sharepoint_decision",
                    "Say sharepoint done after upload completes.",
                    required=False,
                ),
            ],
        )

    if session["inputs"].get("sharepoint_upload") and docx.get("docx_path"):
        if config.sharepoint_upload_archived():
            return _response(
                session,
                status="needs_input",
                prompt=(
                    "SharePoint Graph upload is archived. Paste a manual SharePoint "
                    "document URL for the Release Notes .docx."
                ),
                questions=[_question("sharepoint_url", "SharePoint URL for the Release Notes DOCX.", required=False)],
                preview={"docx": docx, "upload_status": upload_status},
            )
        plan = sharepoint_ops.sharepoint_upload_release_notes(
            str(docx["docx_path"]),
            remote_name=docx.get("docx_filename"),
            dry_run=True,
        )
        if not plan.get("ok"):
            return _response(
                session,
                status="error",
                prompt=plan.get("error") or "SharePoint upload plan failed.",
                preview={"upload_status": upload_status, "plan": plan},
            )
        return _confirmation(
            session,
            {
                "action": "sharepoint_upload",
                "upload_plan": plan,
                "docx": docx,
                "upload_status": upload_status,
            },
            "Confirm Graph upload of the generated Release Notes DOCX to SharePoint.",
        )

    sharepoint_questions = [
        _question(
            "sharepoint_url",
            "SharePoint URL for the Release Notes DOCX.",
            required=False,
        ),
        _question(
            "sharepoint_upload",
            "Set to playwright (or true) for Playwright MCP upload; graph when MS Graph is enabled.",
            required=False,
        ),
    ]

    browser_status = browser_ops.browser_automation_status()
    pw_hint = ""
    if browser_status.get("ready"):
        pw_hint = (
            " Or say **upload sharepoint** to get a Playwright MCP upload playbook "
            "(no Graph credentials)."
        )

    return _response(
        session,
        status="needs_input",
        prompt=(
            "Paste the SharePoint document URL for the Release Notes .docx."
            + pw_hint
            if config.sharepoint_upload_archived()
            else (
                "Provide a SharePoint URL, **upload sharepoint** (Playwright MCP), "
                "or sharepoint_upload=true for Microsoft Graph."
            )
        ),
        questions=sharepoint_questions,
        preview=browser_ops.enrich_sharepoint_preview(
            {"docx": docx, "upload_status": upload_status, "browser_automation": browser_status},
            local_path=str(docx.get("docx_path") or ""),
            version_name=_release_version_label(session),
        ) if docx.get("docx_path") else {
            "docx": docx,
            "upload_status": upload_status,
            "browser_automation": browser_status,
        },
    )


def _confirm_sharepoint(session: dict[str, Any]) -> dict[str, Any]:
    docx = session["artifacts"].get("release_notes_docx") or {}
    path = docx.get("docx_path")
    if not path:
        return _response(
            session,
            status="error",
            prompt="No generated DOCX found to upload.",
        )
    result = sharepoint_ops.sharepoint_upload_release_notes(
        str(path),
        remote_name=docx.get("docx_filename"),
        dry_run=False,
    )
    if not result.get("ok"):
        return _response(
            session,
            status="error",
            prompt=result.get("error") or "SharePoint upload failed.",
            preview=result,
        )
    url = str(result.get("web_url") or "").strip()
    next_step = _advance_to_next_step(session, STEP_SHAREPOINT)
    session = wizard_store.update_session(
        session["id"],
        step=next_step,
        inputs={"sharepoint_url": url},
        artifacts={"sharepoint_url": url, "sharepoint_upload_result": result},
        audit_event="sharepoint_uploaded",
    )
    return _process_step(session, next_step)


def _service_schedule(session: dict[str, Any]) -> dict[str, Any]:
    import release_defaults as rd

    inputs = session["inputs"]
    profile_key = str(inputs.get("deployment_profile") or "normal")
    defaults = rd.default_deployment_schedule(profile_key)
    release_date = release_ops.parse_fix_version_date(_release_version_label(session)) or date.today()
    start_date = date.fromisoformat(str(inputs.get("planned_start_date") or release_date.isoformat()))
    end_date = date.fromisoformat(str(inputs.get("planned_end_date") or release_date.isoformat()))
    start_time = release_ops._parse_hhmm(
        str(inputs.get("planned_start_time") or defaults["start_time"].strftime("%H:%M")),
        defaults["start_time"],
    )
    end_time = release_ops._parse_hhmm(
        str(inputs.get("planned_end_time") or defaults["end_time"].strftime("%H:%M")),
        defaults["end_time"],
    )
    source_tz = str(
        inputs.get("schedule_source_timezone")
        or defaults.get("source_timezone")
        or config.TCKT_SCHEDULE_SOURCE_TZ
    )
    store_tz = str(defaults.get("store_timezone") or config.TCKT_SCHEDULE_TZ)
    display_tz = str(defaults.get("display_timezone") or config.TCKT_DISPLAY_TZ)
    window = schedule_time.window_statement(
        start_date,
        start_time,
        end_date,
        end_time,
        tz_name=source_tz,
        display_tz=display_tz,
    )
    described = schedule_time.describe_window(
        start_date,
        start_time,
        end_date,
        end_time,
        tz_name=source_tz,
        display_tz=display_tz,
    )
    jira = schedule_time.resolve_jira_schedule(
        start_date,
        start_time,
        end_date,
        end_time,
        source_tz=source_tz,
        store_tz=store_tz,
    )
    return {
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "source_timezone": source_tz,
        "store_timezone": store_tz,
        "timezone": store_tz,
        "display_timezone": display_tz,
        "window": window,
        "schedule_display": described,
        "jira_storage": jira,
        "planned_start_iso": str(jira["start_iso"]),
        "planned_end_iso": str(jira["end_iso"]),
    }


def _default_service_draft(session: dict[str, Any]) -> dict[str, Any]:
    from generators.shipit_ticket_evidence import enrich_extracted_with_jira_evidence

    extracted = enrich_extracted_with_jira_evidence(_effective_extracted(session))
    sharepoint = str(session.get("artifacts", {}).get("sharepoint_url") or "")
    version_label = release_ops.parse_fix_version_name(_release_version_label(session))
    label = version_label[0] if version_label else f"v{_release_version_label(session)}"
    schedule = _service_schedule(session)
    ctx = release_ops._plan_context(extracted, sharepoint, label, schedule["window"])
    ctx["version"] = label
    import release_defaults as rd
    import shipit_reference

    profile_key = str((session.get("inputs") or {}).get("deployment_profile") or "normal")
    profiles = rd.deployment_profiles()
    profile = profiles.get(profile_key) if isinstance(profiles, dict) else None
    profile_change_type = str((profile or {}).get("change_type") or "Normal")
    return {
        "summary": shipit_reference.build_shipit_summary(version_name=_release_version_label(session)),
        "description_adf": release_ops._build_description_adf(
            extracted,
            sharepoint,
            label,
            schedule["window"],
        ),
        "implementation_plan": build_impl(ctx),
        "test_plan": build_test(ctx),
        "backout_plan": build_backout(ctx),
        "business_impact": build_impact(ctx),
        "communication_plan": build_communication(ctx),
        "reason_for_change": build_reason(ctx),
        "risks_management": build_risks(ctx),
        "qa_test_plan": build_qa_test_plan(ctx),
        "approvers": [],
        "approver_groups": config.TCKT_DEFAULTS.get("approver_groups", []),
        "team": None,
        "change_type": config.resolve_tckt_select("change_type", profile_change_type),
        "change_risk": config.resolve_tckt_select("change_risk", "Medium"),
        # SHIPIT-17036 parity: impact/urgency/team left unset; risks + QA evidence populated
    }


def _process_service_ticket(session: dict[str, Any]) -> dict[str, Any]:
    relocked = _handle_relock_request(session)
    if relocked is not None:
        return relocked
    session, bootstrap_err = _ensure_ticket_snapshot(session)
    if bootstrap_err is not None:
        return bootstrap_err
    if not workflow_modes.skip_drift_gate(_workflow_mode(session)):
        try:
            drift = _snapshot_drift(session)
        except Exception as exc:  # noqa: BLE001 - fail closed on Jira read
            return _response(
                session,
                status="blocked",
                prompt=f"Could not verify ticket snapshot drift: {exc}",
                questions=[
                    _question(
                        "retry_drift_check",
                        "Set true after Jira is reachable to retry the drift check.",
                        required=False,
                    ),
                    _question(
                        "relock_snapshot",
                        "Set true to refresh the locked ticket list from Jira.",
                        required=False,
                    ),
                ],
                preview={"drift_error": str(exc)},
                allowed_actions=["update", "back", "cancel"],
            )
        if drift.get("missing_from_release") and not session["inputs"].get("proceed_with_locked_snapshot"):
            return _response(
                session,
                status="blocked",
                prompt=(
                    "Locked tickets are missing from the fix version in Jira. "
                    "Fix the fix version, relock the snapshot, or set "
                    "proceed_with_locked_snapshot=true only as an audited override."
                ),
                questions=[
                    _question(
                        "relock_snapshot",
                        "Set true to refresh the locked ticket list from Jira.",
                        required=False,
                    ),
                    _question(
                        "proceed_with_locked_snapshot",
                        "Set true to continue with the locked list despite missing keys (audited override).",
                        required=False,
                    ),
                ],
                preview=drift,
                allowed_actions=["update", "back", "cancel"],
            )
        if drift["has_drift"] and not session["inputs"].get("proceed_with_locked_snapshot"):
            return _response(
                session,
                status="needs_input",
                prompt="Jira changed after Ticket Review was locked. Review the drift before continuing.",
                questions=[
                    _question(
                        "relock_snapshot",
                        "Set true to refresh the locked ticket list from Jira (recommended).",
                        required=False,
                    ),
                    _question(
                        "proceed_with_locked_snapshot",
                        "Set true to keep the locked list (audited override).",
                        required=False,
                    ),
                ],
                preview=drift,
            )
    session, consolidation_err = _apply_consolidation_if_requested(session)
    if consolidation_err is not None:
        return consolidation_err
    session, date_gate = _gate_release_date(session, return_step=STEP_SERVICE_TICKET)
    if date_gate is not None:
        return date_gate
    try:
        draft = dict((session.get("drafts") or {}).get("service_ticket") or {})
        if not draft:
            draft = _default_service_draft(session)
    except ValueError as exc:
        return _response(
            session,
            status="needs_input",
            prompt=str(exc),
            questions=[_question("schedule", "Use YYYY-MM-DD dates and HH:MM times.")],
        )
    patch = session["inputs"].get("service_ticket_draft")
    if isinstance(patch, dict):
        draft.update(patch)

    extracted = _effective_extracted(session)
    coverage = ticket_validator.validate_coverage(
        {
            "extracted": extracted,
            "description_adf": draft.get("description_adf"),
            "implementation_plan": draft.get("implementation_plan"),
            "test_plan": draft.get("test_plan"),
            "backout_plan": draft.get("backout_plan"),
            "business_impact": draft.get("business_impact"),
        }
    )
    approvers = approver_validator.validate_defaults(
        draft.get("approvers") or [],
        draft.get("approver_groups") or [],
    )
    dry_run = release_ops.create_service_ticket(
        _release_version_label(session),
        sharepoint_url=session["artifacts"]["sharepoint_url"],
        projects=_selected_projects(session["inputs"]),
        ticket_keys=_effective_selected_keys(session),
        planned_start_date=session["inputs"].get("planned_start_date"),
        planned_end_date=session["inputs"].get("planned_end_date"),
        planned_start_time=session["inputs"].get("planned_start_time"),
        planned_end_time=session["inputs"].get("planned_end_time"),
        schedule_timezone=session["inputs"].get("schedule_timezone"),
        deployment_profile=session["inputs"].get("deployment_profile"),
        dry_run=True,
        extracted_override=extracted,
        draft_overrides=draft,
        test_mode=session["inputs"].get("test_mode"),
        **_shipit_post_create_kwargs(session),
    )
    duplicate = jira_client.find_tckt_by_summary(draft["summary"])
    schedule = _service_schedule(session)
    platform_state = rc.wizard_session_to_platform_state(
        session,
        extracted=extracted,
        service_ticket_draft=draft,
    )
    validation = rc.service_ticket_validation_report(
        platform_state,
        coverage_warnings=[warning.to_dict() for warning in coverage],
        approver_validation=approvers.to_dict(),
    )
    session = wizard_store.update_session(
        session["id"],
        drafts={"service_ticket": draft},
        artifacts={
            "service_ticket_preflight": dry_run,
            "coverage_warnings": [warning.to_dict() for warning in coverage],
            "approver_validation": approvers.to_dict(),
            "duplicate_tckt": duplicate,
        },
        audit_event="service_ticket_preflight",
    )
    preview = {
        "draft": draft,
        "preflight": dry_run,
        "validation": validation.to_dict(),
        "coverage_warnings": [warning.to_dict() for warning in coverage],
        "approver_validation": approvers.to_dict(),
        "duplicate_tckt": duplicate,
        "consolidation_suggestions": _consolidation_suggestions_for_session(session),
        "consolidation_note": (
            "Set apply_consolidation to a suggestion label or zero-based index, then update "
            "to merge tickets before confirming TCKT create."
        ),
        "schedule": {
            "timezone": schedule["timezone"],
            "display_timezone": schedule["display_timezone"],
            "window": schedule["window"],
            "schedule_display": schedule["schedule_display"],
            "planned_start_iso": schedule["planned_start_iso"],
            "planned_end_iso": schedule["planned_end_iso"],
            "sentence": schedule["window"].get("sentence"),
            "primary": schedule["window"].get("primary"),
            "secondary": schedule["window"].get("secondary"),
        },
        "teams_schedule": {
            "status": teams_ops.teams_schedule_status(),
            "optional_input": "teams_deployment_meeting",
            "schema": {
                "start": "ISO-8601 datetime",
                "end": "ISO-8601 datetime (optional)",
                "subject": "Meeting subject",
                "timezone": "IANA timezone",
                "attendees": ["email@example.com"],
                "schedule": "Set true on confirm to create live (default dry-run preview)",
            },
        },
    }
    duplicate_blocked = bool(duplicate) and not session["inputs"].get("allow_duplicate_tckt")
    blocked, blockers = rc.mcp_service_ticket_blocked(
        preflight_status=str(dry_run.get("status") or ""),
        approver_all_ok=approvers.all_ok,
        duplicate_blocked=duplicate_blocked,
        platform_blockers=validation.blockers,
    )
    if blocked:
        prompt = (
            "A recent TCKT with this summary already exists. Set "
            "allow_duplicate_tckt=true only if a second ticket is intentional."
            if duplicate_blocked
            else "Service-ticket preflight has blockers. Update service_ticket_draft and retry."
        )
        preview["blockers"] = blockers
        return _response(
            session,
            status="blocked",
            prompt=prompt,
            preview=preview,
            allowed_actions=["update", "back", "cancel"],
        )
    # Replay guard: identical create already succeeded.
    existing = session["artifacts"].get("service_ticket") or (
        (session["artifacts"].get("external_refs") or {}).get("service_ticket")
    )
    if isinstance(existing, dict) and existing.get("key"):
        fp = wizard_store.write_fingerprint(
            STEP_SERVICE_TICKET,
            {"summary": draft.get("summary"), "sharepoint": session["artifacts"].get("sharepoint_url")},
        )
        applied = wizard_store.find_applied_write(session, STEP_SERVICE_TICKET, fp)
        if applied:
            return _already_applied(
                session,
                prompt=f"Service ticket {existing.get('key')} was already created for this preview.",
                preview=existing,
            )
    return _confirmation(
        session,
        preview,
        "Review the complete TCKT draft, dual-timezone schedule, and warnings. "
        "Confirm to create the Jira Service Ticket and schedule-window comment.",
    )


def _confirm_service_ticket(session: dict[str, Any]) -> dict[str, Any]:
    draft = session["drafts"]["service_ticket"]
    write_fp = wizard_store.write_fingerprint(
        STEP_SERVICE_TICKET,
        {
            "summary": draft.get("summary"),
            "sharepoint": session["artifacts"].get("sharepoint_url"),
        },
    )
    applied = wizard_store.find_applied_write(session, STEP_SERVICE_TICKET, write_fp)
    if applied:
        return _already_applied(
            session,
            prompt="This service-ticket create was already applied.",
            preview=applied.get("result"),
        )

    extracted = _effective_extracted(session)
    try:
        result = release_ops.create_service_ticket(
            _release_version_label(session),
            sharepoint_url=session["artifacts"]["sharepoint_url"],
            projects=_selected_projects(session["inputs"]),
            ticket_keys=_effective_selected_keys(session),
            planned_start_date=session["inputs"].get("planned_start_date"),
            planned_end_date=session["inputs"].get("planned_end_date"),
            planned_start_time=session["inputs"].get("planned_start_time"),
            planned_end_time=session["inputs"].get("planned_end_time"),
            schedule_timezone=session["inputs"].get("schedule_timezone"),
            deployment_profile=session["inputs"].get("deployment_profile"),
            dry_run=False,
            extracted_override=extracted,
            draft_overrides=draft,
            test_mode=session["inputs"].get("test_mode"),
            **_shipit_post_create_kwargs(session),
        )
    except Exception as exc:  # noqa: BLE001 - classify ambiguous create
        existing = None
        try:
            existing = jira_client.find_tckt_by_summary(draft["summary"])
        except Exception:  # noqa: BLE001 - best-effort only
            existing = None
        preview = {
            "error": str(exc),
            "existing_tckt": existing,
            "retry_safe": existing is None,
        }
        session = wizard_store.update_session(
            session["id"],
            artifacts={"service_ticket_create_failure": preview},
            audit_event="service_ticket_create_failed",
        )
        if existing:
            return _response(
                session,
                status="error",
                prompt=(
                    f"Create failed after a matching TCKT may already exist "
                    f"({existing.get('key')}). Do not retry blindly — adopt the "
                    f"existing ticket or inspect Jira first."
                ),
                preview=preview,
                allowed_actions=["update", "back", "cancel", "status"],
            )
        return _response(
            session,
            status="error",
            prompt=(
                "Create failed and no matching TCKT was found in the last hour — "
                "retrying is safe after fixing the error."
            ),
            preview=preview,
            allowed_actions=["update", "resume", "back", "cancel"],
        )

    if result.get("status") != "created":
        existing = None
        try:
            existing = jira_client.find_tckt_by_summary(draft["summary"])
        except Exception:  # noqa: BLE001 - best-effort only
            existing = None
        preview = {
            "result": result,
            "existing_tckt": existing,
            "retry_safe": existing is None,
        }
        session = wizard_store.update_session(
            session["id"],
            artifacts={"service_ticket_create_failure": preview},
            audit_event="service_ticket_create_failed",
        )
        if existing:
            return _response(
                session,
                status="error",
                prompt=(
                    f"Create did not report success, but TCKT {existing.get('key')} "
                    f"matches this summary. Do not retry — use the existing ticket."
                ),
                preview={
                    **preview,
                    "existing_tckt_url": existing.get("url") or existing.get("browse_url"),
                },
                allowed_actions=["update", "back", "cancel", "status"],
            )
        return _response(
            session,
            status="error",
            prompt=(
                "The service ticket was not created. No matching TCKT was found — "
                "retrying is safe after fixing the error."
            ),
            preview=preview,
        )

    assignment_result = assignment_ops.verify_and_repair(
        result["key"],
        draft,
    )
    result["assignment_verification"] = assignment_result
    session = wizard_store.record_write_fingerprint(
        session["id"],
        STEP_SERVICE_TICKET,
        write_fp,
        result=result,
    )
    session = wizard_store.update_session(
        session["id"],
        step=_advance_to_next_step(session, STEP_SERVICE_TICKET),
        artifacts={"service_ticket": result},
        audit_event="service_ticket_created",
        audit_detail={"key": result.get("key")},
    )
    teams_result = _run_teams_meeting(session, "deployment")
    if teams_result is not None:
        session = wizard_store.update_session(
            session["id"],
            artifacts={"teams_deployment_meeting": teams_result},
            audit_event="teams_deployment_meeting",
        )
    next_step = str(session.get("step") or STEP_SLACK)
    import browser_automation

    if next_step == STEP_SLACK and browser_automation.slack_auto_handoff_after_shipit():
        session = wizard_store.update_session(
            session["id"],
            inputs={"slack_decision": "playwright", "slack_via_playwright": True},
            audit_event="slack_auto_playwright_after_shipit",
        )
    return _process_step(session, next_step)


def _continue_after_slack(session: dict[str, Any], **update_kwargs: Any) -> dict[str, Any]:
    """Advance past Slack using workflow_mode step order (deploy vs complete)."""
    next_step = _advance_to_next_step(session, STEP_SLACK)
    session = wizard_store.update_session(session["id"], step=next_step, **update_kwargs)
    return _process_step(session, next_step)


def _slack_preview(session: dict[str, Any]) -> dict[str, Any]:
    tckt = session["artifacts"]["service_ticket"]
    schedule = _service_schedule(session)
    preview = slack_ops.build_slack_preview(
        ticket_key=tckt["key"],
        summary=tckt["summary"],
        ticket_url=tckt["url"],
        version_name=_release_version_label(session),
        sharepoint_url=session["artifacts"]["sharepoint_url"],
        deploy_date=schedule["start_date"].isoformat(),
        environments=str(session["inputs"].get("slack_environments") or "Analyze & Custom environments"),
    )
    edits = session["inputs"].get("slack_messages")
    if isinstance(edits, dict):
        preview = slack_ops.apply_slack_message_edits(preview, edits)
    return browser_ops.enrich_slack_preview(preview)


def _process_slack(session: dict[str, Any]) -> dict[str, Any]:
    import browser_automation

    decision = str(session["inputs"].get("slack_decision") or "").lower()
    preview = _slack_preview(session)
    if config.slack_archived() or not preview.get("enabled", True):
        reason = "archived" if config.slack_archived() else "disabled"
        return _continue_after_slack(
            session,
            artifacts={"slack": {"status": "skipped", "reason": reason}},
            audit_event="slack_skipped_archived" if reason == "archived" else "slack_skipped_disabled",
        )
    if str(session["inputs"].get("slack_decision") or "").lower() in {"done", "posted", "slack done"}:
        return _continue_after_slack(
            session,
            artifacts={"slack": {"status": "handoff_sent", "delivery": preview.get("delivery_mode")}},
            audit_event="slack_mcp_handoff_done",
        )
    if decision == "skip":
        return _continue_after_slack(
            session,
            artifacts={"slack": {"status": "skipped"}},
            audit_event="slack_skipped",
        )
    partial = session["artifacts"].get("slack_partial") or {}
    if partial.get("sent_keys"):
        preview["already_sent_keys"] = list(partial.get("sent_keys") or [])
        preview["prior_results"] = list(partial.get("results") or [])
        preview["remaining_keys"] = [
            channel["key"]
            for channel in preview.get("channels") or []
            if channel["key"] not in set(preview["already_sent_keys"])
        ]
    if decision != "send":
        mcp_hint = ""
        if preview.get("can_post_via_playwright") and (
            browser_automation.prefer_playwright_slack()
            or not preview.get("can_post_via_slack_mcp")
        ):
            mcp_hint = (
                " Say **send slack** (Playwright MCP — opens both Glofox channels in browser), "
                "then **slack done** when posted."
            )
        elif preview.get("can_post_via_slack_mcp"):
            mcp_hint = (
                " Post via **Cursor Slack MCP** — say **send slack**, then **slack done**."
            )
        elif preview.get("can_post_via_playwright"):
            mcp_hint = (
                " Say **send slack playwright** for Playwright MCP browser steps to both channels."
            )
        elif preview.get("can_send"):
            mcp_hint = " Reply **send slack** to auto-post via bot token."
        return _response(
            session,
            status="needs_input",
            prompt=(
                "Review the Slack preview for #insights-customize-squad."
                + mcp_hint
                + " Say **skip slack** to continue without posting."
                if not partial
                else "Previous Slack send was partial. Reply **send slack** to retry failed channels only."
            ),
            questions=[
                _question("slack_decision", "Use 'send' or 'skip'."),
                _question(
                    "slack_messages",
                    "Optional map of channel key/name to edited message body. "
                    "Required CC mentions are always reappended from config.",
                    required=False,
                ),
            ],
            preview=preview,
        )
    slack_via_playwright = (
        decision in {"playwright", "browser"}
        or bool(session["inputs"].get("slack_via_playwright"))
        or (decision == "send" and browser_automation.prefer_playwright_slack())
    )
    if slack_via_playwright and preview.get("can_post_via_playwright"):
        pw = preview.get("playwright_slack") or {}
        return _response(
            session,
            status="needs_input",
            prompt=pw.get("instruction") or "Post to both Slack channels via Playwright MCP, then **slack done**.",
            preview={**preview, "playwright_slack": pw},
        )

    if preview.get("can_post_via_slack_mcp") and not preview.get("can_send"):
        handoff = preview.get("slack_mcp") or slack_ops.handoff_for_slack_mcp(preview)
        pw_note = ""
        if preview.get("can_post_via_playwright"):
            pw_note = " Or say **send slack playwright** to use Playwright MCP instead."
        return _response(
            session,
            status="needs_input",
            prompt=(handoff.get("instruction") or "Post via Slack MCP, then say **slack done**.") + pw_note,
            preview={**preview, "slack_mcp": handoff},
        )

    return _confirmation(
        session,
        preview,
        "Confirm to send these Slack messages to the configured channels. "
        "Already-sent channels from a partial attempt will not be posted again.",
    )


def _confirm_slack(session: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    partial = session["artifacts"].get("slack_partial") or {}
    skip_keys = list(partial.get("sent_keys") or [])
    write_fp = wizard_store.write_fingerprint(
        STEP_SLACK,
        {
            "channels": [{"key": c.get("key"), "text": c.get("text")} for c in preview.get("channels") or []],
            "skip_keys": skip_keys,
        },
    )
    applied = wizard_store.find_applied_write(session, STEP_SLACK, write_fp)
    if applied:
        return _already_applied(
            session,
            prompt="This Slack send was already applied for the current preview.",
            preview=applied.get("result"),
        )

    result = slack_ops.send_slack_preview(preview, skip_channel_keys=skip_keys)
    if result.get("status") == "partial":
        session = wizard_store.update_session(
            session["id"],
            step=STEP_SLACK,
            inputs={"slack_decision": None},
            artifacts={
                "slack_partial": result,
                "slack": result,
            },
            audit_event="slack_partial_send",
        )
        return _response(
            session,
            status="error",
            prompt=(
                "Slack announcement was partially sent. Already-sent channels are "
                "recorded; update slack_decision=send to retry only failed channels."
            ),
            preview=result,
            allowed_actions=["update", "resume", "back", "cancel"],
        )
    if result.get("status") not in {"sent", "skipped"}:
        return _response(
            session,
            status="error",
            prompt="Slack announcement was not fully sent. Review errors before proceeding.",
            preview=result,
        )
    session = wizard_store.record_write_fingerprint(
        session["id"],
        STEP_SLACK,
        write_fp,
        result=result,
    )
    return _continue_after_slack(
        session,
        artifacts={"slack": result, "slack_partial": None},
        audit_event="slack_sent",
    )


def _project_cfg(project_key: str) -> dict[str, Any]:
    for project in config.PROJECTS:
        if project["key"] == project_key:
            return project
    return {}


def _deploy_context(session: dict[str, Any]) -> dict[str, Any]:
    inputs = session["inputs"]
    project_key = str(inputs.get("deployment_project") or "").upper()
    version_name = _version_for(inputs, project_key)
    version = release_ops.resolve_version(project_key, version_name)
    issues = jira_client.get_issues_for_version(project_key, version["id"])
    selected_default = [
        key
        for key in _effective_selected_keys(session)
        if str(key).upper().startswith(f"{project_key}-")
    ]
    on_release = {issue["key"] for issue in issues}
    if not selected_default and workflow_modes.normalize_mode(_workflow_mode(session)) == workflow_modes.WORKFLOW_MODE_DEPLOYER:
        selected_default = sorted(on_release)
    missing_from_release = sorted(set(selected_default) - on_release)
    requested = inputs.get("deployment_ticket_keys")
    if requested is None:
        selected = list(selected_default)
        selection_explicit = False
    else:
        selected = [key for key in requested if str(key).upper().startswith(f"{project_key}-")]
        selection_explicit = True
    # Partial-deploy retry: only failed keys from prior attempt when requested.
    if inputs.get("retry_failed_only"):
        prior = (session["artifacts"].get("deployment_results") or {}).get(project_key) or {}
        failed = list(prior.get("failed_keys") or [])
        if failed:
            selected = [key for key in failed if key in set(selected_default) or key in on_release]
            selection_explicit = True
    cfg = _project_cfg(project_key)
    multi_client = bool(cfg.get("multi_client"))
    grouped = jira_client.group_issues_by_client(issues, project_key=project_key) if multi_client else {}
    tickets_by_client: dict[str, list[str]] = {}
    if multi_client:
        for client, client_issues in grouped.items():
            keys = [iss["key"] for iss in client_issues if iss["key"] in set(selected_default)]
            if keys:
                tickets_by_client[client] = keys
    else:
        tickets_by_client[project_key] = list(selected_default)
    return {
        "project_key": project_key,
        "version": version,
        "issues": issues,
        "selected": selected,
        "selected_default": selected_default,
        "selection_explicit": selection_explicit,
        "missing_from_release": missing_from_release,
        "multi_client": multi_client,
        "grouped": grouped,
        "tickets_by_client": tickets_by_client,
    }


def _deploy_drift_gate(session: dict[str, Any]) -> dict[str, Any] | None:
    """Return a wizard response when snapshot drift blocks deploy; else None."""
    if workflow_modes.skip_drift_gate(_workflow_mode(session)):
        return None
    inputs = session["inputs"]
    try:
        drift = _snapshot_drift(session)
    except Exception as exc:  # noqa: BLE001 - fail closed on Jira read
        return _response(
            session,
            status="blocked",
            prompt=f"Could not verify ticket snapshot drift: {exc}",
            questions=[
                _question(
                    "retry_drift_check",
                    "Set true after Jira is reachable to retry the drift check.",
                    required=False,
                ),
                _question(
                    "relock_snapshot",
                    "Set true to refresh the locked ticket list from Jira.",
                    required=False,
                ),
            ],
            preview={"drift_error": str(exc)},
            allowed_actions=["update", "back", "cancel"],
        )
    if drift.get("missing_from_release") and not inputs.get("proceed_with_locked_snapshot"):
        return _response(
            session,
            status="blocked",
            prompt=(
                "Locked tickets are missing from the fix version in Jira. "
                "Fix the fix version, relock, or set proceed_with_locked_snapshot=true."
            ),
            questions=[
                _question("relock_snapshot", "Set true to refresh the locked list.", required=False),
                _question(
                    "proceed_with_locked_snapshot",
                    "Set true to deploy only tickets still on the version (audited override).",
                    required=False,
                ),
            ],
            preview=drift,
            allowed_actions=["update", "back", "cancel"],
        )
    if drift["has_drift"] and not inputs.get("proceed_with_locked_snapshot"):
        return _response(
            session,
            status="needs_input",
            prompt="Jira changed after Ticket Review was locked. Review the drift before deployment.",
            questions=[
                _question(
                    "relock_snapshot",
                    "Set true to refresh the locked ticket list from Jira.",
                    required=False,
                ),
                _question(
                    "proceed_with_locked_snapshot",
                    "Set true to deploy only the locked list.",
                    required=False,
                ),
            ],
            preview=drift,
        )
    return None


def _process_deploy(session: dict[str, Any]) -> dict[str, Any]:
    relocked = _handle_relock_request(session)
    if relocked is not None:
        return relocked
    inputs = session["inputs"]
    project_key = str(inputs.get("deployment_project") or "").upper()
    if not project_key:
        return _response(
            session,
            status="needs_input",
            prompt="Which project release should be deployed first?",
            questions=[
                _question(
                    "deployment_project",
                    f"Choose one of {_selected_projects(inputs)}. The platform deploys one project at a time.",
                )
            ],
        )

    drift_response = _deploy_drift_gate(session)
    if drift_response is not None:
        return drift_response

    filled = inputs.get("deployment_info")
    paste = str(inputs.get("deployment_paste") or "").strip()

    if not isinstance(filled, dict) or not filled:
        try:
            context = _deploy_context(session)
        except ValueError as exc:
            return _response(session, status="error", prompt=str(exc))
        if paste:
            filled = deploy_prefill.deployment_info_from_paste(
                paste,
                list((context.get("tickets_by_client") or {}).keys()),
            )
        if not isinstance(filled, dict) or not filled:
            suggested, sources = _suggest_deployment_info(session, context)
            return _response(
                session,
                status="needs_input",
                prompt=(
                    "Provide deployment_info for each client, paste deployment output "
                    "(deployment_paste), or accept suggested_deployment_info from release notes / SharePoint / history."
                ),
                questions=[
                    _question(
                        "deployment_info",
                        "Map client/project names to deployment_id, deployment_date, deployment_time.",
                        required=False,
                    ),
                    _question(
                        "deployment_paste",
                        "Paste raw deployment output to parse (same as Deployer paste zone).",
                        required=False,
                    ),
                ],
                preview={
                    "project": context["project_key"],
                    "clients": list(context["tickets_by_client"].keys()),
                    "suggested_deployment_info": suggested,
                    "prefill_sources": sources,
                    "candidates": context["selected_default"],
                },
            )

    invalid = [
        name
        for name, info in filled.items()
        if not isinstance(info, dict)
        or not info.get("deployment_id")
        or not info.get("deployment_date")
        or not info.get("deployment_time")
    ]
    if invalid:
        return _response(
            session,
            status="needs_input",
            prompt=f"Deployment details are incomplete for: {invalid}",
            questions=[_question("deployment_info", "Complete all three fields for each entry.")],
        )

    try:
        context = _deploy_context(session)
    except ValueError as exc:
        return _response(session, status="error", prompt=str(exc))

    if context["missing_from_release"] and not inputs.get("proceed_with_locked_snapshot"):
        return _response(
            session,
            status="blocked",
            prompt=(
                "Ticket Review selected tickets that are not on this fix version. "
                "No deploy confirmation is offered until this is fixed or overridden."
            ),
            preview={
                "missing_from_release": context["missing_from_release"],
                "project": context["project_key"],
                "version": context["version"].get("name"),
            },
            questions=[
                _question("relock_snapshot", "Set true to refresh the locked list.", required=False),
                _question(
                    "proceed_with_locked_snapshot",
                    "Set true to continue without the missing tickets (audited).",
                    required=False,
                ),
            ],
            allowed_actions=["update", "back", "cancel"],
        )

    if inputs.get("deployment_ticket_keys") is None and not inputs.get("retry_failed_only"):
        return _response(
            session,
            status="needs_input",
            prompt=(
                "Select which locked tickets to deploy for this project. "
                "Uncheck failed-in-production tickets by omitting their keys."
            ),
            questions=[
                _question(
                    "deployment_ticket_keys",
                    "List of ticket keys to deploy (defaults shown in preview). "
                    f"Candidates: {context['selected_default']}",
                ),
                _question(
                    "force_deploy",
                    "Optional: set true to ignore existing verified deployment comments.",
                    required=False,
                ),
            ],
            preview={
                "project": context["project_key"],
                "candidates": context["selected_default"],
                "tickets_by_client": context["tickets_by_client"],
                "deployment_info": filled,
            },
        )

    preview = deploy_ops.preview_deploy(
        filled=filled,
        release=context["version"],
        project_key=context["project_key"],
        selected_keys=context["selected"],
        issues=context["issues"],
        grouped=context["grouped"],
        multi_client=context["multi_client"],
        force_deploy=bool(inputs.get("force_deploy")),
    )
    preview["deployment_info"] = filled
    preview["selected_ticket_keys"] = context["selected"]
    preview["tickets_by_client"] = context["tickets_by_client"]
    preview["candidates"] = context["selected_default"]
    preview["missing_from_release"] = context["missing_from_release"]
    session = wizard_store.update_session(
        session["id"],
        artifacts={"deployment_context": context},
        audit_event="deployment_previewed",
    )
    if preview.get("errors"):
        return _response(
            session,
            status="blocked",
            prompt="Deployment preview has comment-verification errors.",
            preview=preview,
            allowed_actions=["update", "back", "cancel"],
        )
    gate_state = rc.deploy_gate_state_from_wizard(session)
    gate_state["wiz_filled"] = filled
    gate_state["wiz_release"] = context["version"]
    deploy_blockers = rc.deploy_execution_blockers(gate_state)
    if deploy_blockers:
        preview["validation"] = {"blockers": deploy_blockers, "ready": False}
        return _response(
            session,
            status="blocked",
            prompt=deploy_blockers[0],
            preview=preview,
            allowed_actions=["update", "back", "cancel"],
        )
    preview["validation"] = {"blockers": [], "ready": True}
    return _confirmation(
        session,
        preview,
        "Review comments, transitions, duplicate skips, and deployment IDs. "
        "Confirm to update Jira and transition tickets to Done.",
    )


def _confirm_deploy(session: dict[str, Any]) -> dict[str, Any]:
    context = session["artifacts"]["deployment_context"]
    project_key = context["project_key"]
    selected = list(context["selected"])
    write_fp = wizard_store.write_fingerprint(
        STEP_DEPLOY,
        {
            "project": project_key,
            "selected": sorted(selected),
            "deployment_info": session["inputs"].get("deployment_info"),
            "force_deploy": bool(session["inputs"].get("force_deploy")),
        },
    )
    applied = wizard_store.find_applied_write(session, STEP_DEPLOY, write_fp)
    if applied:
        return _already_applied(
            session,
            prompt="This deployment was already executed for the current selection.",
            preview=applied.get("result"),
        )

    slack_artifact = (session.get("artifacts") or {}).get("slack")
    slack_results = (
        slack_artifact.get("results")
        if isinstance(slack_artifact, dict)
        else slack_artifact
    )
    tckt = (session.get("artifacts") or {}).get("service_ticket") or {}
    result = deploy_ops.execute_deploy(
        filled=session["inputs"]["deployment_info"],
        release=context["version"],
        project_key=project_key,
        selected_keys=selected,
        issues=context["issues"],
        grouped=context["grouped"],
        multi_client=context["multi_client"],
        force_deploy=bool(session["inputs"].get("force_deploy")),
        dry_run=False,
        sharepoint_url=str(session["artifacts"].get("sharepoint_url") or ""),
        tckt_key=str(tckt.get("key") or ""),
        tckt_url=str(tckt.get("url") or ""),
        slack_results=slack_results,
    )
    # Derive failed keys from log / error count for retry.
    failed_keys: list[str] = []
    if result.get("errors"):
        for line in result.get("log") or []:
            if "FAILED" in line or "SKIPPED (cannot verify" in line:
                for key in selected:
                    if key in line and key not in failed_keys:
                        failed_keys.append(key)
    result = dict(result)
    result["failed_keys"] = failed_keys
    result["project"] = project_key

    results = dict(session["artifacts"].get("deployment_results") or {})
    results[project_key] = result
    session = wizard_store.update_session(
        session["id"],
        artifacts={
            "deployment_result": result,  # latest for compatibility
            "deployment_results": results,
        },
        audit_event="deployment_executed",
        audit_detail={
            "project": project_key,
            "success": result.get("success"),
            "errors": result.get("errors"),
            "status": result.get("status"),
        },
    )

    if result.get("status") in {"failed", "empty"}:
        return _response(
            session,
            status="error",
            prompt="Deployment did not complete.",
            preview=result,
            allowed_actions=["update", "resume", "back", "cancel"],
        )

    if result.get("status") == "partial" or int(result.get("errors") or 0) > 0:
        session = wizard_store.update_session(
            session["id"],
            step=STEP_DEPLOY,
            inputs={
                "retry_failed_only": None,
                "deployment_ticket_keys": None,
            },
            artifacts={
                "deployment_result": result,
                "deployment_results": results,
            },
            audit_event="deployment_partial",
        )
        return _response(
            session,
            status="error",
            prompt=(
                "Deployment partially completed. Mark-released is not offered until "
                "the run is clean. Set retry_failed_only=true to retry failed tickets, "
                "or adjust deployment_ticket_keys."
            ),
            preview={
                **result,
                "failed_keys": failed_keys,
                "retry_hint": "update with retry_failed_only=true",
            },
            questions=[
                _question(
                    "retry_failed_only",
                    "Set true to retry only failed ticket keys.",
                    required=False,
                ),
                _question(
                    "deployment_ticket_keys",
                    "Or provide an explicit key list to retry.",
                    required=False,
                ),
            ],
            allowed_actions=["update", "resume", "back", "cancel", "undo"],
        )

    session = wizard_store.record_write_fingerprint(
        session["id"],
        STEP_DEPLOY,
        write_fp,
        result=result,
    )
    session = wizard_store.update_session(
        session["id"],
        step=STEP_MARK_RELEASED,
        artifacts={
            "deployment_result": result,
            "deployment_results": results,
        },
        inputs={"retry_failed_only": False},
        audit_event="deployment_clean_success",
    )
    return _process_mark_released(session)


def _deploy_is_clean_success(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    return int(result.get("success") or 0) > 0 and int(result.get("errors") or 0) == 0


def _process_mark_released(session: dict[str, Any]) -> dict[str, Any]:
    current_project = session["artifacts"]["deployment_context"]["project_key"]
    try:
        scope = team_scope.scope_from_project(current_project)
    except team_scope.TeamScopeError:
        scope = team_scope.parse_scope({})
    if not scope.owns_version:
        return _after_project(session)

    results = session["artifacts"].get("deployment_results") or {}
    latest = results.get(current_project) or session["artifacts"].get("deployment_result")
    if current_project in set(session["artifacts"].get("deployed_projects") or []):
        return _after_project(session)

    if not _deploy_is_clean_success(latest):
        return _response(
            session,
            status="blocked",
            prompt=(
                "Mark-released is only offered after a clean deploy "
                "(success > 0 and errors == 0). Go back to deploy and retry."
            ),
            preview=latest,
            allowed_actions=["back", "update", "undo", "cancel"],
        )

    decision = session["inputs"].get("mark_version_released")
    if decision is None:
        return _response(
            session,
            status="needs_input",
            prompt="Deployment finished cleanly. Mark this Jira fix version as Released?",
            questions=[_question("mark_version_released", "Use true or false.")],
            preview=latest,
        )
    if not bool(decision):
        return _after_project(session)
    context = session["artifacts"]["deployment_context"]
    preview = {
        "project": context["project_key"],
        "version": context["version"].get("name"),
        "version_id": context["version"].get("id"),
        "action": "mark_released",
    }
    return _confirmation(
        session,
        preview,
        "Confirm to mark this Jira fix version as Released.",
    )


def _confirm_mark_released(session: dict[str, Any]) -> dict[str, Any]:
    version_id = session["artifacts"]["deployment_context"]["version"]["id"]
    project_key = session["artifacts"]["deployment_context"]["project_key"]
    write_fp = wizard_store.write_fingerprint(
        STEP_MARK_RELEASED,
        {"project": project_key, "version_id": version_id},
    )
    applied = wizard_store.find_applied_write(session, STEP_MARK_RELEASED, write_fp)
    if applied:
        return _already_applied(
            session,
            prompt="This version was already marked Released for the current preview.",
            preview=applied.get("result"),
        )
    history_ts = None
    deploy_results = (session.get("artifacts") or {}).get("deployment_results") or {}
    latest = deploy_results.get(project_key) or (session.get("artifacts") or {}).get("deployment_result") or {}
    history_ts = latest.get("history_timestamp")
    version_name = str(session["artifacts"]["deployment_context"]["version"].get("name") or "")
    result = deploy_ops.mark_release(
        version_id,
        project_key=project_key,
        history_timestamp=history_ts,
        version_name=version_name,
    )
    if result.get("status") != "released":
        return _response(
            session,
            status="error",
            prompt="The Jira version was not marked Released.",
            preview=result,
        )
    previous = dict(session["artifacts"].get("mark_released_results") or {})
    previous[project_key] = result
    session = wizard_store.record_write_fingerprint(
        session["id"],
        STEP_MARK_RELEASED,
        write_fp,
        result=result,
    )
    session = wizard_store.update_session(
        session["id"],
        artifacts={"mark_released_results": previous},
        audit_event="version_released",
    )
    return _after_project(session)


def _after_project(session: dict[str, Any]) -> dict[str, Any]:
    artifacts = session["artifacts"]
    context = artifacts["deployment_context"]
    deployed = list(artifacts.get("deployed_projects") or [])
    current = context["project_key"]
    if current not in deployed:
        deployed.append(current)
        session = wizard_store.update_session(
            session["id"],
            artifacts={"deployed_projects": deployed},
            audit_event="project_deployment_finished",
            audit_detail={"project": current},
        )
    remaining = [project for project in _selected_projects(session["inputs"]) if project not in deployed]
    if not remaining:
        return _complete(session)

    decision = session["inputs"].get("deploy_remaining_projects")
    if decision is None:
        return _response(
            session,
            status="needs_input",
            prompt=f"{current} is finished. Deploy the remaining project(s) {remaining}?",
            questions=[_question("deploy_remaining_projects", "Use true or false.")],
            preview={"completed_projects": deployed, "remaining_projects": remaining},
        )
    if not bool(decision):
        return _complete(session)

    session = wizard_store.update_session(
        session["id"],
        step=STEP_DEPLOY,
        inputs={
            "deployment_project": remaining[0],
            "deployment_info": {},
            "deployment_ticket_keys": None,
            "mark_version_released": None,
            "deploy_remaining_projects": None,
        },
        audit_event="next_project_started",
        audit_detail={"project": remaining[0]},
    )
    return _process_deploy(session)


def _complete(session: dict[str, Any]) -> dict[str, Any]:
    session = wizard_store.update_session(
        session["id"],
        step=STEP_COMPLETE,
        status=wizard_store.STATUS_COMPLETED,
        audit_event="workflow_completed",
    )
    return _response(
        session,
        status="completed",
        prompt="Release Orchestrator workflow completed. You can inspect history or start another release.",
        preview={
            "docx": session["artifacts"].get("release_notes_docx"),
            "service_ticket": session["artifacts"].get("service_ticket"),
            "slack": session["artifacts"].get("slack"),
            "deployment": session["artifacts"].get("deployment_result"),
            "deployments": session["artifacts"].get("deployment_results"),
            "released": session["artifacts"].get("mark_released_results"),
            "external_refs": session["artifacts"].get("external_refs"),
        },
        allowed_actions=["status", "history", "undo", "start"],
    )


def _process(session: dict[str, Any]) -> dict[str, Any]:
    step = session.get("step")
    processors = {
        STEP_TICKET_REVIEW: _process_ticket_review,
        STEP_EXCLUSIONS: _process_exclusions,
        STEP_RELEASE_DATE: _process_release_date,
        STEP_RELEASE_NOTES: _process_release_notes,
        STEP_SHAREPOINT: _process_sharepoint,
        STEP_SERVICE_TICKET: _process_service_ticket,
        STEP_SLACK: _process_slack,
        STEP_DEPLOY: _process_deploy,
        STEP_MARK_RELEASED: _process_mark_released,
        STEP_COMPLETE: _complete,
    }
    processor = processors.get(str(step))
    if not processor:
        return _response(
            session,
            status="error",
            prompt=f"Unknown workflow step: {step}",
        )
    return processor(session)


def _confirm(session: dict[str, Any], token: str | None) -> dict[str, Any]:
    valid, preview = _check_confirmation(session, token)
    if not valid:
        return _response(
            session,
            status="confirmation_invalid",
            prompt="The confirmation token is missing, stale, consumed, or does not match the latest preview.",
            preview=preview,
            allowed_actions=["resume", "update", "cancel"],
        )
    try:
        session = wizard_store.consume_confirmation(
            session["id"],
            session["step"],
            token or "",
            preview,
        )
    except wizard_store.ConfirmationConsumedError as exc:
        return _response(
            session,
            status="confirmation_invalid",
            prompt=str(exc),
            preview=preview,
            allowed_actions=["resume", "update", "cancel"],
        )
    handlers = {
        STEP_TICKET_REVIEW: _confirm_ticket_review,
        STEP_EXCLUSIONS: _confirm_exclusions,
        STEP_RELEASE_DATE: _confirm_release_date,
        STEP_RELEASE_NOTES: _confirm_release_notes,
        STEP_SHAREPOINT: _confirm_sharepoint,
        STEP_SERVICE_TICKET: _confirm_service_ticket,
        STEP_SLACK: lambda current: _confirm_slack(current, preview),
        STEP_DEPLOY: _confirm_deploy,
        STEP_MARK_RELEASED: _confirm_mark_released,
        STEP_UNDO: _confirm_undo,
    }
    handler = handlers.get(str(session.get("step")))
    if not handler:
        return _response(
            session,
            status="error",
            prompt=f"Step {session.get('step')} has no confirmable write.",
        )
    return handler(session)


def _back(session: dict[str, Any]) -> dict[str, Any]:
    step = str(session.get("step"))
    order = _step_order(session)
    if step not in order:
        return _response(session, status="error", prompt="Cannot go back from this step.")
    index = order.index(step)
    if index == 0:
        return _process(session)
    target = order[index - 1]
    session = _clear_downstream_artifacts(session, target)
    session = wizard_store.update_session(
        session["id"],
        step=target,
        audit_event="went_back",
        audit_detail={"from": step, "to": target},
    )
    return _process(session)


def _combined_undo_data(session: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect undo rows and history timestamps across all deployed projects."""
    results = session["artifacts"].get("deployment_results")
    if isinstance(results, dict) and results:
        undo_data: list[dict[str, Any]] = []
        timestamps: list[str] = []
        for project_key in sorted(results):
            entry = results[project_key] or {}
            undo_data.extend(entry.get("undo_data") or [])
            ts = entry.get("history_timestamp")
            if ts:
                timestamps.append(str(ts))
        return undo_data, timestamps
    result = session["artifacts"].get("deployment_result") or {}
    ts = result.get("history_timestamp")
    return list(result.get("undo_data") or []), [str(ts)] if ts else []


def _undo_preview(session: dict[str, Any]) -> dict[str, Any]:
    undo_data, timestamps = _combined_undo_data(session)
    if not undo_data:
        return _response(
            session,
            status="error",
            prompt="This workflow has no deployment changes available to undo.",
        )
    previous = str(session.get("step"))
    session = wizard_store.update_session(
        session["id"],
        step=STEP_UNDO,
        artifacts={"pre_undo_step": previous},
        audit_event="undo_previewed",
    )
    preview = {
        "tickets": [
            {
                "key": item.get("key"),
                "comment_id": item.get("comment_id"),
                "revert_status_to": item.get("prev_status") if item.get("transitioned") else None,
            }
            for item in undo_data
        ],
        "history_timestamps": timestamps,
        "history_timestamp": timestamps[0] if timestamps else None,
        "projects": sorted((session["artifacts"].get("deployment_results") or {}).keys()),
    }
    return _confirmation(
        session,
        preview,
        "Confirm to delete deployment comments and revert ticket statuses where possible "
        "for all projects recorded in this workflow.",
    )


def _confirm_undo(session: dict[str, Any]) -> dict[str, Any]:
    undo_data, timestamps = _combined_undo_data(session)
    combined_log: list[str] = []
    statuses: list[str] = []
    if timestamps:
        # First timestamp reverts tickets; remaining timestamps only mark history.
        first = True
        for ts in timestamps:
            chunk = undo_data if first else []
            first = False
            result = deploy_ops.undo_deploy(chunk, history_timestamp=ts)
            combined_log.extend(result.get("log") or [])
            statuses.append(str(result.get("status") or "ok"))
        overall = "ok" if all(status == "ok" for status in statuses) else "partial"
        result = {
            "status": overall,
            "log": combined_log,
            "history_timestamps": timestamps,
            "ticket_count": len(undo_data),
        }
    else:
        result = deploy_ops.undo_deploy(undo_data, history_timestamp=None)
    target = str(session["artifacts"].get("pre_undo_step") or STEP_COMPLETE)
    session = wizard_store.update_session(
        session["id"],
        step=target,
        artifacts={"undo_result": result},
        audit_event="deployment_undone",
    )
    return _response(
        session,
        status="completed" if result.get("status") == "ok" else "partial",
        prompt="Deployment undo finished.",
        preview=result,
        allowed_actions=["status", "history"],
    )


def _history(session: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        entries = deployment_history.load_history()
    except deployment_history.HistoryLoadError as exc:
        return {"status": "error", "error": str(exc)}
    return {
        "status": "ok",
        "workflow_id": session.get("id") if session else None,
        "entries": entries,
        "count": len(entries),
    }


def run_wizard(
    action: str,
    *,
    workflow_id: str | None = None,
    inputs: dict[str, Any] | None = None,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    """Run or resume the durable Release Orchestrator workflow."""
    action_name = (action or "").strip().lower()
    payload = dict(inputs or {})

    try:
        return _run_wizard_inner(
            action_name,
            workflow_id=workflow_id,
            payload=payload,
            confirmation_token=confirmation_token,
        )
    except wizard_store.WizardStoreError as exc:
        body = wizard_store.store_error_payload(exc)
        if workflow_id:
            body["workflow_id"] = workflow_id
        return body


def _run_wizard_inner(
    action_name: str,
    *,
    workflow_id: str | None,
    payload: dict[str, Any],
    confirmation_token: str | None,
) -> dict[str, Any]:
    if action_name == "welcome":
        from release_mcp import welcome as welcome_mod

        welcome_body = welcome_mod.build_welcome(payload)
        if welcome_body.get("auto_start") and welcome_body.get("recommended_call"):
            rec = welcome_body.get("recommended_call") or {}
            payload = dict(rec.get("inputs") or payload)
            action_name = "start"
        elif payload.get("confirm_defaults") in {True, "yes", "yes — start Step 1", "true", "1"} or payload.get(
            "start_now"
        ) in {True, "yes", "true"}:
            payload = welcome_mod.build_start_inputs(payload)
            action_name = "start"
        elif welcome_body.get("step") in {"start_menu", "onboarding"}:
            return welcome_body
        else:
            return welcome_body

    if action_name == "start":
        mode = workflow_modes.normalize_mode(str(payload.get("workflow_mode") or "full"))
        payload = dict(payload)
        payload["workflow_mode"] = mode
        session = wizard_store.create_session(
            workflow_modes.workflow_name_for(mode),
            step=workflow_modes.start_step_for(mode),
            inputs=payload,
        )
        return _process(session)

    if action_name in {"list", "sessions"}:
        return {
            "status": "ok",
            "sessions": wizard_store.list_sessions(workflow=WORKFLOW_NAME),
        }

    if action_name == "history":
        session = wizard_store.load_session(workflow_id) if workflow_id else None
        return _history(session)

    if not workflow_id:
        return {
            "status": "needs_input",
            "questions": [_question("workflow_id", "Which workflow ID should be used?")],
        }

    session = wizard_store.load_session(workflow_id)

    if action_name in {"resume", "status"}:
        if action_name == "status":
            return {
                "status": "ok",
                "workflow_id": session["id"],
                "step": session["step"],
                "workflow_status": session["status"],
                "inputs": session["inputs"],
                "drafts": session["drafts"],
                "artifacts": session["artifacts"],
                "updated_at": session["updated_at"],
            }
        if wizard_store.is_terminal_status(session.get("status")):
            return _response(
                session,
                status="error",
                prompt=(
                    f"Workflow is {session.get('status')} and cannot be resumed for writes. "
                    "Use status, history, undo (if available), or start a new workflow."
                ),
                allowed_actions=["status", "history", "start", "undo"],
            )
        return _process(session)

    mutating = action_name in {"update", "confirm", "back", "cancel"}
    if mutating and action_name != "cancel":
        try:
            wizard_store.assert_session_mutable(session)
        except wizard_store.TerminalSessionError as exc:
            return _response(
                session,
                status="error",
                prompt=str(exc),
                allowed_actions=["status", "history", "start", "undo"],
            )

    if action_name == "update":
        if "release_notes_include_ticket_keys" in payload:
            new_keys = payload.get("release_notes_include_ticket_keys")
            if isinstance(new_keys, list):
                existing = list((session.get("inputs") or {}).get("release_notes_include_ticket_keys") or [])
                payload["release_notes_include_ticket_keys"] = _merge_unique_ticket_keys(
                    existing, new_keys
                )
        if "exclude_assignee_names" in payload:
            new_names = payload.get("exclude_assignee_names")
            if isinstance(new_names, list):
                existing = list((session.get("inputs") or {}).get("exclude_assignee_names") or [])
                merged_names = list(dict.fromkeys([*existing, *[str(n).strip() for n in new_names if str(n).strip()]]))
                payload["exclude_assignee_names"] = merged_names
        if "version_name" in payload or "planned_deploy_date" in payload:
            payload["release_date_confirmed"] = False
        # Changing ticket selection invalidates downstream generated artifacts.
        if any(
            key in payload
            for key in (
                "selected_ticket_keys",
                "exclusion_ticket_keys",
                "exclude_assignee_names",
                "release_notes_include_ticket_keys",
                "release_notes_draft",
                "sharepoint_url",
                "versions",
                "version_name",
                "planned_deploy_date",
                "release_date_confirmed",
            )
        ):
            step = str(session.get("step") or STEP_TICKET_REVIEW)
            session = _clear_downstream_artifacts(session, step)
        session = wizard_store.update_session(
            workflow_id,
            inputs=payload,
            audit_event="user_input_updated",
            audit_detail={"keys": sorted(payload)},
        )
        return _process(session)
    if action_name == "confirm":
        return _confirm(session, confirmation_token)
    if action_name == "back":
        return _back(session)
    if action_name == "cancel":
        session = wizard_store.cancel_session(
            workflow_id,
            reason=str(payload.get("reason") or ""),
        )
        return _response(
            session,
            status="cancelled",
            prompt="Release Orchestrator workflow cancelled. No pending write will run.",
            allowed_actions=["status", "start"],
        )
    if action_name == "undo":
        return _undo_preview(session)

    return {
        "status": "error",
        "workflow_id": workflow_id,
        "error": (
            "Unknown action. Use welcome, start, resume, status, update, confirm, "
            "back, cancel, list, history, or undo."
        ),
    }
