"""Platform-parity helpers for Release Orchestrator MCP (PIC + AN).

Mirrors Streamlit flows without touching UI code or session state.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import adf_builder as adf
import config
import jira_client
import schedule_time
import shipit_test_mode
import team_scope
from generators.release_notes_draft import build_release_notes_draft_from_extracted
from generators.release_notes_insights import readiness_to_dict
from generators.release_notes_publish import publish_release_notes_docx
from generators.release_notes_quality import improve_extracted
from generators.shipit_evidence_plans import build_evidence_description_adf
from generators.shipit_ticket_evidence import enrich_extracted_with_jira_evidence
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
import shipit_post_create
from shipit_reference import build_shipit_summary
from tckt_reference import build_summary_from_reference_pattern

_build_backout = build_backout
_build_impact = build_impact
_build_impl = build_impl
_build_test = build_test
_build_communication = build_communication
_build_reason = build_reason

_FIX_VERSION_RE = re.compile(r"(\d{4})\.(\d)\.(\d{2})\.(\d{2})")
_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def parse_fix_version_name(name: str) -> tuple[str, str] | None:
    """Parse ``2026.3.07.06`` into ``(v2026.3.07.06, 06-July-2026)``."""
    match = _FIX_VERSION_RE.search((name or "").strip())
    if not match:
        return None
    year, quarter, month_str, day_str = match.groups()
    month = int(month_str)
    day = int(day_str)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"v{year}.{quarter}.{month_str}.{day_str}", f"{day:02d}-{_MONTH_NAMES[month]}-{year}"


def parse_fix_version_date(name: str) -> date | None:
    match = _FIX_VERSION_RE.search((name or "").strip())
    if not match:
        return None
    year, _, month_str, day_str = match.groups()
    try:
        return date(int(year), int(month_str), int(day_str))
    except ValueError:
        return None


def resolve_version(project_key: str, version_name: str) -> dict[str, Any]:
    needle = version_name.strip().lower()
    for ver in jira_client.get_project_versions(project_key):
        if ver.get("name", "").strip().lower() == needle:
            return ver
    available = [v.get("name") for v in jira_client.get_project_versions(project_key)[:15]]
    raise ValueError(
        f"Version '{version_name}' not found in {project_key}. "
        f"Recent versions: {available}"
    )


def _default_projects(projects: list[str] | None) -> list[str]:
    if projects:
        return [p.strip().upper() for p in projects if p and p.strip()]
    return [p["key"] for p in config.PROJECTS]


def team_scope_status(project_key: str, *, version_id: str = "") -> dict[str, Any]:
    """Return configuration/preflight status for a project's team scope."""
    pk = project_key.strip().upper()
    if not pk:
        return {"status": "error", "error": "project_key is required"}
    try:
        result = jira_client.validate_team_scope(pk, version_id=version_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "project_key": pk, "error": str(exc)}
    result["status"] = "ok" if result.get("configured") and not result.get("blocking") else "blocked"
    return result


def extracted_row_from_jira_issue(
    issue: dict,
    *,
    project_key: str = "",
    source_label: str = "",
) -> dict[str, Any]:
    """Normalize one Jira issue into the extracted-ticket dict used across MCP steps."""
    fields = issue.get("fields") or {}
    summary = fields.get("summary") or ""
    key = str(issue.get("key") or "").strip().upper()
    pk = (project_key or (key.split("-", 1)[0] if "-" in key else "")).strip().upper()
    assignee_obj = fields.get("assignee") or {}
    info = jira_client.extract_ticket_info(summary, key)
    info.update(
        {
            "ticket": key,
            "summary": summary,
            "status": (fields.get("status") or {}).get("name"),
            "assignee": assignee_obj.get("displayName", ""),
            "assignee_email": assignee_obj.get("emailAddress", ""),
            "parent": (fields.get("parent") or {}).get("key", key),
            "project": pk,
            "fix_version": source_label,
            "link": f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{key}",
        }
    )
    return info


def _supplement_squad_assignee_status_issues(
    project_key: str,
    statuses: list[str],
    *,
    team_ids: list[str] | None,
    existing_rows: list[dict],
) -> tuple[list[dict], list[str]]:
    """Merge in-squad status tickets missed by the Jira Team-field filter."""
    import release_gates as rg

    if not team_ids or not rg.ticket_review_include_squad_without_team():
        return existing_rows, []
    seen = {str(row.get("ticket") or "").strip().upper() for row in existing_rows if row.get("ticket")}
    try:
        broad_issues = jira_client.get_issues_for_statuses(
            project_key,
            statuses,
            jira_team_ids=None,
        )
    except Exception:  # noqa: BLE001
        return existing_rows, []

    merged = list(existing_rows)
    added_keys: list[str] = []
    for issue in broad_issues:
        row = extracted_row_from_jira_issue(issue, project_key=project_key)
        key = str(row.get("ticket") or "").strip().upper()
        if not key or key in seen:
            continue
        assignee = str(row.get("assignee") or "")
        if not rg.assignee_in_squad(assignee):
            continue
        merged.append(row)
        added_keys.append(key)
        seen.add(key)
    return merged, added_keys


def fetch_release_tickets(
    version_name: str = "",
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    *,
    selection_mode: str = "fix_version",
    statuses_by_project: dict[str, list[str]] | None = None,
    jira_team_ids_by_project: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Fetch + extract tickets for a fix version or by Jira status across PIC and/or AN."""
    mode = (selection_mode or "fix_version").strip()
    version_name = (version_name or "").strip()
    if mode == "status":
        if not statuses_by_project or not any(statuses_by_project.values()):
            return {
                "status": "needs_input",
                "missing": ["statuses_by_project"],
                "questions": [
                    {
                        "field": "statuses_by_project",
                        "prompt": "Map project keys to status names, e.g. {\"PIC\": [\"Review\"], \"AN\": [\"Passed QA\"]}",
                    }
                ],
            }
    elif not version_name:
        return {
            "status": "needs_input",
            "missing": ["version_name"],
            "questions": [
                {
                    "field": "version_name",
                    "prompt": "Which release version? (e.g. 2026.3.08.12)",
                }
            ],
        }

    selected = set(k.strip().upper() for k in (ticket_keys or []) if k)
    project_keys = _default_projects(projects)
    scope_blocked: list[str] = []
    scope_meta: dict[str, Any] = {}
    for pk in project_keys:
        st = team_scope.scope_status(pk)
        scope_meta[pk] = st
        if st.get("blocking"):
            scope_blocked.append(pk)
    if scope_blocked:
        return {
            "status": "blocked",
            "version_name": version_name,
            "selection_mode": mode,
            "projects": project_keys,
            "scope_blocked_projects": scope_blocked,
            "scope_by_project": scope_meta,
            "message": (
                "Team ticket scope is not configured for: "
                + ", ".join(scope_blocked)
                + ". Configure board/filter/JQL in workspace.yaml before fetching."
            ),
        }

    team_map = jira_team_ids_by_project or {}
    by_project: dict[str, Any] = {}
    extracted: list[dict] = []
    missing_versions: list[str] = []
    supplement_keys: list[str] = []

    for pk in project_keys:
        team_ids = team_map.get(pk) or None
        if mode == "status":
            statuses = list(statuses_by_project.get(pk) or []) if statuses_by_project else []
            if not statuses:
                by_project[pk] = {"statuses": [], "count": 0, "tickets": []}
                continue
            try:
                issues = jira_client.get_issues_for_statuses(
                    pk, statuses, jira_team_ids=team_ids,
                )
            except Exception as exc:
                by_project[pk] = {"error": str(exc), "tickets": []}
                continue
            source_label = ", ".join(statuses)
            project_rows = [
                extracted_row_from_jira_issue(iss, project_key=pk, source_label=source_label)
                for iss in issues
            ]
            project_rows, added = _supplement_squad_assignee_status_issues(
                pk,
                statuses,
                team_ids=team_ids,
                existing_rows=project_rows,
            )
            supplement_keys.extend(added)
        else:
            try:
                ver = resolve_version(pk, version_name)
            except ValueError as exc:
                missing_versions.append(str(exc))
                by_project[pk] = {"error": str(exc), "tickets": []}
                continue
            try:
                issues = jira_client.get_issues_for_version(
                    pk, ver["id"], jira_team_ids=team_ids,
                )
            except Exception as exc:
                by_project[pk] = {"error": str(exc), "tickets": []}
                continue
            source_label = ver.get("name", version_name)

        project_tickets: list[dict] = []
        if mode == "status":
            for row in project_rows:
                key = str(row.get("ticket") or "").strip().upper()
                if selected and key not in selected:
                    continue
                project_tickets.append(row)
                extracted.append(row)
        else:
            for iss in issues:
                key = iss.get("key", "")
                if selected and key.upper() not in selected:
                    continue
                info = extracted_row_from_jira_issue(
                    iss,
                    project_key=pk,
                    source_label=source_label if mode == "fix_version" else "",
                )
                project_tickets.append(info)
                extracted.append(info)

        if mode == "status":
            by_project[pk] = {
                "statuses": statuses,
                "count": len(project_tickets),
                "tickets": [
                    {
                        "key": t["ticket"],
                        "summary": t["summary"],
                        "status": t["status"],
                        "type": t["type"],
                        "client": t["client"],
                        "report": t["report"],
                        "assignee": t["assignee"],
                    }
                    for t in project_tickets
                ],
            }
        else:
            by_project[pk] = {
                "version": ver.get("name"),
                "version_id": ver.get("id"),
                "released": ver.get("released", False),
                "count": len(project_tickets),
                "scope": jira_client.scoped_version_metadata(pk, str(ver.get("id") or "")),
                "tickets": [
                    {
                        "key": t["ticket"],
                        "summary": t["summary"],
                        "status": t["status"],
                        "type": t["type"],
                        "client": t["client"],
                        "report": t["report"],
                        "assignee": t["assignee"],
                    }
                    for t in project_tickets
                ],
            }

    extracted = improve_extracted(extracted)
    return {
        "status": "ok",
        "version_name": version_name,
        "selection_mode": mode,
        "include_fix_version_metadata": mode == "fix_version",
        "projects": project_keys,
        "scope_by_project": scope_meta,
        "total_tickets": len(extracted),
        "by_project": by_project,
        "missing_versions": missing_versions,
        "supplement_squad_assignee_keys": supplement_keys,
        "extracted": extracted,
    }


def format_extracted_list_lines(extracted: list[dict]) -> str:
    """One line per ticket — for chat paste (release or review lists)."""
    lines: list[str] = []
    for row in extracted:
        key = str(row.get("ticket") or row.get("key") or "").strip()
        if not key:
            continue
        client = str(row.get("client") or row.get("client_name") or "").strip()
        summary = str(row.get("summary") or row.get("title") or "").strip()
        if client:
            lines.append(f"{key} – {client} – {summary}")
        else:
            lines.append(f"{key} – {summary}")
    return "\n".join(lines)


def list_release_ready_tickets(
    projects: list[str] | None = None,
    *,
    jira_team_ids_by_project: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Fetch release-ready tickets (comment-gated) — list only, no wizard lock."""
    import release_gates

    project_keys = _default_projects(projects)
    statuses = {pk: list(config.release_notes_default_statuses(pk)) for pk in project_keys}
    result = fetch_release_notes_extracted(
        selection_mode="status",
        projects=project_keys,
        release_notes_statuses_by_project=statuses,
        jira_team_ids_by_project=jira_team_ids_by_project,
    )
    if result.get("status") not in {"ok", "blocked"}:
        return result
    extracted = list(result.get("extracted") or [])
    outside = release_gates.filter_extracted_outside_squad_assignees(extracted)
    if outside.get("status") == "ok":
        extracted = list(outside.get("kept") or extracted)
    formatted = format_extracted_list_lines(extracted)
    comment_gate = result.get("release_comment_gate") or {}
    return {
        **result,
        "extracted": extracted,
        "total_tickets": len(extracted),
        "list_only": True,
        "fetch_intent": "release_list",
        "statuses_by_project": statuses,
        "formatted_list": formatted,
        "ticket_count": len(extracted),
        "held_back_keys": comment_gate.get("held_back_keys") or [],
        "held_back_count": len(comment_gate.get("held_back_keys") or []),
    }


def extracted_from_jira_issue(issue: dict) -> dict:
    """Turn one raw Jira issue into the extracted-ticket row used by release notes."""
    return extracted_row_from_jira_issue(issue)


def fetch_tickets_by_keys(ticket_keys: list[str]) -> dict[str, Any]:
    """Fetch specific Jira tickets by key (for release-notes explicit overrides)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in ticket_keys or []:
        key = str(raw).strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)

    if not ordered:
        return {"status": "ok", "extracted": [], "errors": {}, "requested_keys": []}

    extracted: list[dict] = []
    errors: dict[str, str] = {}
    for key in ordered:
        try:
            issue = jira_client.get_issue(key)
            extracted.append(extracted_from_jira_issue(issue))
        except Exception as exc:  # noqa: BLE001
            errors[key] = str(exc)

    extracted = improve_extracted(extracted)
    if not extracted:
        status = "error"
    elif errors:
        status = "partial"
    else:
        status = "ok"
    return {
        "status": status,
        "extracted": extracted,
        "errors": errors,
        "requested_keys": ordered,
    }


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


def release_notes_default_statuses_by_project(projects: list[str] | None = None) -> dict[str, list[str]]:
    keys = [str(p).strip().upper() for p in (projects or []) if str(p).strip()]
    if not keys:
        keys = [p["key"] for p in config.PROJECTS]
    return {pk: list(config.release_notes_default_statuses(pk)) for pk in keys}


def _merge_release_ready_comment_candidates(
    extracted: list[dict],
    *,
    projects: list[str],
    release_notes_statuses_by_project: dict[str, list[str]] | None = None,
    jira_team_ids_by_project: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Release Notes admission — comment required; status alone is not enough."""
    import release_gates

    phrases = list(release_gates.ready_for_release_comment_phrases())
    held_back: list[dict] = []
    if release_gates.require_ready_for_release_comment_all():
        gate = release_gates.filter_extracted_ready_for_release_comments(extracted)
        held_back = list(gate.get("held_back") or [])
        extracted = list(gate.get("kept") or [])
    elif not release_gates.include_ready_for_release_comments_enabled():
        return {
            "status": "disabled",
            "extracted": extracted,
            "comment_included_keys": [],
            "comment_included": [],
            "held_back": [],
            "held_back_keys": [],
            "candidate_fetch": None,
            "phrases": phrases,
        }

    by_key = {
        str(item.get("ticket") or "").upper(): item
        for item in extracted
        if str(item.get("ticket") or "").strip()
    }
    comment_included: list[dict[str, str]] = [
        {
            "key": key,
            "summary": str(item.get("summary") or ""),
            "status": str(item.get("status") or "").strip(),
            "reason": "Jira comment indicates ready for release",
        }
        for key, item in by_key.items()
    ]

    candidate_fetch = None
    candidate_statuses: dict[str, list[str]] = {}
    if release_gates.include_ready_for_release_comments_enabled():
        candidate_statuses = release_gates.ready_for_release_comment_candidate_statuses(projects)
        candidate_fetch = fetch_release_tickets(
            selection_mode="status",
            projects=projects,
            statuses_by_project=candidate_statuses,
            jira_team_ids_by_project=jira_team_ids_by_project,
        )
        for item in candidate_fetch.get("extracted") or []:
            key = str(item.get("ticket") or "").upper()
            if not key or key in by_key:
                continue
            ready, snippet = release_gates.ticket_has_ready_for_release_comment(key)
            if not ready:
                continue
            by_key[key] = item
            comment_included.append(
                {
                    "key": key,
                    "summary": str(item.get("summary") or ""),
                    "status": str(item.get("status") or "").strip(),
                    "reason": "Jira comment indicates ready for release",
                    "comment_snippet": snippet,
                }
            )

    return {
        "status": "ok",
        "extracted": list(by_key.values()),
        "comment_included_keys": [row["key"] for row in comment_included if row.get("key")],
        "comment_included": comment_included,
        "held_back": held_back,
        "held_back_keys": [row["key"] for row in held_back if row.get("key")],
        "candidate_fetch": candidate_fetch,
        "phrases": phrases,
        "candidate_statuses_by_project": candidate_statuses,
    }


def fetch_release_notes_extracted(
    *,
    selection_mode: str = "fix_version",
    projects: list[str],
    release_notes_statuses_by_project: dict[str, list[str]] | None = None,
    locked_ticket_keys: list[str] | None = None,
    include_ticket_keys: list[str] | None = None,
    jira_team_ids_by_project: dict[str, list[str]] | None = None,
    version_name: str = "",
    initial_fetch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shared Step 3 logic: release-ready refetch, locked-key intersect, explicit overrides."""
    mode = (selection_mode or "fix_version").strip()
    project_keys = [str(p).strip().upper() for p in projects if str(p).strip()]
    rn_statuses = release_notes_statuses_by_project or release_notes_default_statuses_by_project(
        project_keys
    )
    ordered_locked_keys = _merge_unique_ticket_keys([], locked_ticket_keys or [])
    locked_keys = set(ordered_locked_keys)
    include_keys = _merge_unique_ticket_keys([], include_ticket_keys or [])

    if initial_fetch is not None:
        fetch = initial_fetch
    elif mode == "status":
        fetch = fetch_release_tickets(
            selection_mode="status",
            projects=project_keys,
            statuses_by_project=rn_statuses,
            jira_team_ids_by_project=jira_team_ids_by_project,
        )
    else:
        fetch = fetch_release_tickets(
            selection_mode="fix_version",
            projects=project_keys,
            version_name=version_name,
            jira_team_ids_by_project=jira_team_ids_by_project,
        )

    fetch_blocked = fetch.get("status") == "blocked"
    if fetch_blocked and not include_keys:
        return {
            "status": "blocked",
            "message": fetch.get("message", "Release-notes ticket fetch blocked."),
            "fetch": fetch,
            "release_notes_statuses_by_project": rn_statuses,
            "locked_keys": sorted(locked_keys),
            "not_release_ready_keys": [],
            "release_ready_ticket_keys": [],
            "explicit_override_keys": [],
            "extracted": [],
            "override_fetch": None,
        }

    extracted = [] if fetch_blocked else list(fetch.get("extracted") or [])
    comment_gate = _merge_release_ready_comment_candidates(
        extracted,
        projects=project_keys,
        release_notes_statuses_by_project=rn_statuses,
        jira_team_ids_by_project=jira_team_ids_by_project,
    )
    if comment_gate.get("status") != "disabled":
        extracted = list(comment_gate.get("extracted") or extracted)
    not_release_ready_keys: list[str] = []
    release_ready_keys_set: set[str] = set()

    if locked_keys:
        extracted_by_key = {
            str(item.get("ticket") or "").upper(): item
            for item in extracted
            if str(item.get("ticket") or "").strip()
        }
        release_ready_keys_set = set(extracted_by_key)
        extracted = [
            extracted_by_key[key]
            for key in ordered_locked_keys
            if key in extracted_by_key
        ]
        not_release_ready_keys = [
            key for key in ordered_locked_keys if key not in extracted_by_key
        ]
    else:
        release_ready_keys_set = {
            str(item.get("ticket") or "").upper()
            for item in extracted
            if str(item.get("ticket") or "").strip()
        }

    explicit_override_keys: list[str] = []
    override_fetch: dict[str, Any] | None = None
    if include_keys:
        existing_keys = {
            str(item.get("ticket") or "").upper()
            for item in extracted
            if str(item.get("ticket") or "").strip()
        }
        pending_override = [key for key in include_keys if key not in existing_keys]
        if pending_override:
            override_fetch = fetch_tickets_by_keys(pending_override)
            override_rows = list(override_fetch.get("extracted") or [])
            by_key = {
                str(item.get("ticket") or "").upper(): item
                for item in extracted
                if str(item.get("ticket") or "").strip()
            }
            for row in override_rows:
                key = str(row.get("ticket") or "").upper()
                if key:
                    by_key[key] = row
            explicit_override_keys = [
                key for key in pending_override if key in by_key and key not in release_ready_keys_set
            ]
            if locked_keys:
                extracted = [by_key[key] for key in ordered_locked_keys if key in by_key]
                trailing = [
                    by_key[key]
                    for key in include_keys
                    if key in by_key and key not in ordered_locked_keys
                ]
                extracted.extend(trailing)
            else:
                extracted = list(extracted)
                for key in include_keys:
                    row = by_key.get(key)
                    if row and row not in extracted:
                        extracted.append(row)
            not_release_ready_keys = [
                key for key in not_release_ready_keys if key not in explicit_override_keys
            ]

    if locked_keys:
        release_ready_ticket_keys = [
            str(item.get("ticket") or "")
            for item in extracted
            if str(item.get("ticket") or "").strip()
        ]
    else:
        release_ready_ticket_keys = [
            str(item.get("ticket") or "")
            for item in extracted
            if str(item.get("ticket") or "").strip()
        ]

    message = ""
    if fetch_blocked and extracted:
        message = (
            "Release-ready fetch was blocked; using explicit ticket override(s): "
            + ", ".join(explicit_override_keys or release_ready_ticket_keys)
            + "."
        )
    elif not extracted:
        if locked_keys and not_release_ready_keys:
            message = (
                "None of the locked tickets are in release-ready status yet. "
                f"Not release-ready: {', '.join(not_release_ready_keys)}."
            )
        elif comment_gate.get("held_back_keys"):
            message = (
                "No tickets with a ready-for-release Jira comment. "
                f"Held back (status alone not enough): {', '.join(comment_gate['held_back_keys'])}."
            )
        else:
            message = "No tickets matched release-ready statuses."

    return {
        "status": "ok" if extracted else "blocked",
        "message": message,
        "extracted": extracted,
        "release_notes_statuses_by_project": rn_statuses,
        "locked_keys": sorted(locked_keys),
        "not_release_ready_keys": not_release_ready_keys,
        "explicit_override_keys": explicit_override_keys,
        "release_ready_ticket_keys": release_ready_ticket_keys,
        "release_comment_gate": comment_gate if comment_gate.get("status") != "disabled" else None,
        "comment_included_keys": comment_gate.get("comment_included_keys") or [],
        "fetch": fetch,
        "override_fetch": override_fetch,
    }


def _build_docx_data(
    extracted: list[dict],
    version_name: str,
    *,
    include_fix_version_metadata: bool = True,
) -> dict[str, Any]:
    return build_release_notes_draft_from_extracted(
        extracted,
        version_name,
        include_fix_version_metadata=include_fix_version_metadata,
    )


def write_release_notes_docx_bytes(
    docx_bytes: bytes,
    version_name: str,
    *,
    readiness: Any = None,
    hyperlink_check: dict[str, Any] | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Persist DOCX bytes and return metadata (shared by wizard confirm path)."""
    parsed = parse_fix_version_name(version_name.lstrip("vV"))
    version = parsed[0] if parsed else f"v{version_name.lstrip('vV')}"
    if output_path:
        out = Path(output_path)
    else:
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.\-]+", "_", version.lstrip("v"))
        out = _OUTPUT_DIR / f"Release Notes {safe.lstrip('v')}.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.write_bytes(docx_bytes)
    except PermissionError:
        stem = out.stem
        alt = out.with_name(f"{stem} ({int(datetime.now().timestamp())}).docx")
        alt.write_bytes(docx_bytes)
        out = alt
    body: dict[str, Any] = {
        "status": "ok",
        "version": version,
        "docx_path": str(out.resolve()),
        "docx_filename": out.name,
        "docx_bytes": len(docx_bytes),
    }
    if readiness is not None:
        body["readiness"] = readiness_to_dict(readiness)
    if hyperlink_check:
        body["hyperlink_check"] = hyperlink_check
    return body


def generate_release_notes_docx_file(
    version_name: str,
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    output_path: str | None = None,
    data_overrides: dict[str, Any] | None = None,
    extracted_override: list[dict] | None = None,
    *,
    enforce_readiness: bool = True,
) -> dict[str, Any]:
    """Generate the same Word release notes DOCX the Streamlit UI produces."""
    if extracted_override is not None:
        fetch = {
            "status": "ok",
            "projects": _default_projects(projects),
            "by_project": {},
            "extracted": extracted_override,
        }
    elif ticket_keys:
        fetch = fetch_tickets_by_keys(ticket_keys)
        import release_gates

        gate = release_gates.filter_extracted_ready_for_release_comments(fetch.get("extracted") or [])
        fetch = {**fetch, "extracted": list(gate.get("kept") or [])}
    else:
        fetch = fetch_release_notes_extracted(
            selection_mode="fix_version",
            projects=_default_projects(projects),
            version_name=version_name,
        )
    if fetch.get("status") == "needs_input":
        return fetch
    extracted = fetch.get("extracted") or []
    if not extracted:
        return {
            "status": "error",
            "error": f"No tickets found for version '{version_name}' in {fetch.get('projects')}.",
            "by_project": fetch.get("by_project"),
        }

    data = _build_docx_data(extracted, version_name)
    if data_overrides:
        allowed = set(data)
        data.update({
            key: value
            for key, value in data_overrides.items()
            if key in allowed
        })

    publish = publish_release_notes_docx(data, enforce_readiness=enforce_readiness)
    if publish.status == "blocked":
        blocked = publish.to_dict()
        blocked["status"] = "blocked"
        return blocked
    if publish.status != "ok" or not publish.docx_bytes:
        return {
            "status": "error",
            "error": publish.error or "Release notes generation failed.",
            **publish.to_dict(),
        }

    docx_meta = write_release_notes_docx_bytes(
        publish.docx_bytes,
        version_name,
        readiness=publish.readiness,
        hyperlink_check=publish.hyperlink_check,
        output_path=output_path,
    )
    docx_meta["release_date"] = data["release_date"]
    docx_meta["ticket_count"] = len(extracted)
    docx_meta["projects"] = fetch.get("projects")
    docx_meta["by_project_counts"] = {
        pk: info.get("count", 0)
        for pk, info in (fetch.get("by_project") or {}).items()
        if isinstance(info, dict)
    }
    docx_meta["message"] = (
        f"Release notes DOCX written ({docx_meta.get('docx_bytes', 0)} bytes). "
        "Same generator/style as the Release Orchestrator web UI."
    )
    return docx_meta


def _text_to_adf(plain: str) -> dict:
    lines = plain.strip().splitlines()
    content: list[dict] = []
    for i, line in enumerate(lines):
        if i > 0:
            content.append(adf.hard_break())
        content.append(adf.text(line))
    return adf.doc(adf.paragraph(*content)) if content else adf.doc(adf.paragraph(adf.text(" ")))


def _multi_para_adf(plain: str) -> dict:
    """SHIPIT plan fields — bold phase headings (SHIPIT-17036 parity)."""
    return adf.shipit_plan_to_doc(plain)


def _build_description_adf(
    extracted: list[dict],
    sharepoint_url: str,
    version_label: str,
    window: dict[str, str] | None = None,
) -> dict:
    """ADF description — SHIPIT-17036 evidence-based standard."""
    link_label = f"Release Notes {version_label.lstrip('v')}.docx" if sharepoint_url else None
    return build_evidence_description_adf(
        extracted,
        version_label=version_label,
        window=window,
        sharepoint_url=sharepoint_url,
        sharepoint_label=link_label,
    )


def _parse_hhmm(value: str, default: time) -> time:
    value = (value or "").strip()
    if not value:
        return default
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(value, fmt).time().replace(second=0, microsecond=0)
        except ValueError:
            continue
    raise ValueError(f"Invalid time '{value}'. Use HH:MM (e.g. 10:00).")


def _plan_context(
    extracted: list[dict],
    sharepoint: str,
    version_label: str,
    window: dict[str, str],
) -> dict[str, Any]:
    has_analyze = any(e["type"] == "Analyze" for e in extracted)
    has_custom = any(e["type"] == "Custom" for e in extracted)
    scope = []
    if has_analyze:
        scope.append("Standard (Analyze)")
    if has_custom:
        scope.append("Custom")
    clients = sorted({
        e["client"] for e in extracted
        if e["client"] not in ("Standard", "Unknown")
    })
    return {
        "extracted": extracted,
        "sharepoint": sharepoint,
        "window": window,
        "version_name": version_label,
        "scope_str": " and ".join(scope) or "the project",
        "clients": clients,
        "dashboards": sorted({e["report"] for e in extracted if e["report"]}),
        "descriptions": [e for e in extracted if e["description"]],
        "workspaces": " / ".join(["Standard", *clients]),
        "has_analyze": has_analyze,
        "has_custom": has_custom,
    }


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
    deployment_profile: str | None = None,
    dry_run: bool = True,
    extracted_override: list[dict] | None = None,
    draft_overrides: dict[str, Any] | None = None,
    test_mode: bool | None = None,
    post_create_overrides: dict[str, Any] | None = None,
    shipit_owner_account_id: str | None = None,
) -> dict[str, Any]:
    """Create a SHIPIT change ticket the same way the platform Service Ticket app does.

    Missing required inputs return ``status=needs_input`` with questions for the agent
    to ask the user (SharePoint link, version, etc.).
    """
    questions: list[dict[str, str]] = []
    missing: list[str] = []

    version_name = (version_name or "").strip()
    if not version_name:
        missing.append("version_name")
        questions.append({
            "field": "version_name",
            "prompt": "Which release version should the service ticket cover? (e.g. 2026.3.08.12)",
        })

    sharepoint = (sharepoint_url or "").strip()
    if not sharepoint:
        missing.append("sharepoint_url")
        questions.append({
            "field": "sharepoint_url",
            "prompt": (
                "Paste the SharePoint URL for the Release Notes Word doc "
                f"(Release Notes {version_name or '<version>'}.docx)."
            ),
        })

    if missing:
        return {
            "status": "needs_input",
            "missing": missing,
            "questions": questions,
            "hint": (
                "Ask the user for the missing fields, then call create_service_ticket again. "
                "Default dry_run=true previews without creating in Jira."
            ),
        }

    version_ok, version_error = shipit_test_mode.validate_fix_version_name(version_name)
    if not version_ok and not test_mode:
        return {
            "status": "needs_input",
            "missing": ["version_name"],
            "questions": [{
                "field": "version_name",
                "prompt": version_error or "Invalid fix version format.",
            }],
            "hint": "Use the PIC/AN fix version exactly (YYYY.Q.MM.DD), e.g. 2026.3.09.11.",
        }

    if extracted_override is not None:
        fetch = {
            "status": "ok",
            "projects": _default_projects(projects),
            "by_project": {},
            "extracted": extracted_override,
        }
    elif ticket_keys:
        fetch = fetch_tickets_by_keys(ticket_keys)
        import release_gates

        gate = release_gates.filter_extracted_ready_for_release_comments(fetch.get("extracted") or [])
        fetch = {**fetch, "extracted": list(gate.get("kept") or [])}
    else:
        fetch = fetch_release_notes_extracted(
            selection_mode="fix_version",
            projects=_default_projects(projects),
            version_name=version_name,
        )
    if fetch.get("status") == "needs_input":
        return fetch
    extracted = enrich_extracted_with_jira_evidence(fetch.get("extracted") or [])
    fetch = {**fetch, "extracted": extracted}
    if not extracted:
        return {
            "status": "error",
            "error": f"No tickets found for version '{version_name}'.",
            "by_project": fetch.get("by_project"),
        }

    import release_defaults as rd

    draft = draft_overrides or {}
    parsed_early = parse_fix_version_name(version_name)
    version_label_early = parsed_early[0] if parsed_early else f"v{version_name}"
    is_test = bool(test_mode) if test_mode is not None else False
    if not is_test and draft.get("summary"):
        is_test = shipit_test_mode.is_test_shipit_summary(str(draft["summary"]))
    provisional_summary = str(
        draft.get("summary")
        or (
            shipit_test_mode.default_test_summary(version_label_early)
            if is_test
            else build_shipit_summary(version_name=version_name)
        )
    )
    if not is_test and shipit_test_mode.is_test_shipit_summary(provisional_summary):
        is_test = True
    if is_test:
        draft = shipit_test_mode.merge_test_draft(draft)
    else:
        draft = shipit_test_mode.merge_prod_draft(draft)

    parsed = parse_fix_version_name(version_name)
    version_label = parsed[0] if parsed else f"v{version_name}"
    # Deploy window always follows the release-notes fix version date (YYYY.Q.MM.DD),
    # including TEST SHIPIT — release notes are prepared T+1 before deploy day.
    release_date = (
        shipit_test_mode.parse_release_version_date(version_name)
        or parse_fix_version_date(version_name)
        or date.today()
    )
    profile_key = deployment_profile or "normal"
    sched_defaults = rd.default_deployment_schedule(profile_key)
    profiles = rd.deployment_profiles()
    profile = profiles.get(profile_key) if isinstance(profiles, dict) else None
    profile_change_type = (
        str((profile or {}).get("change_type") or "").strip() or None
    )

    try:
        start_d = (
            datetime.strptime(planned_start_date, "%Y-%m-%d").date()
            if planned_start_date else release_date
        )
        end_d = (
            datetime.strptime(planned_end_date, "%Y-%m-%d").date()
            if planned_end_date else release_date
        )
        start_t = _parse_hhmm(
            planned_start_time or sched_defaults["start_time"].strftime("%H:%M"),
            sched_defaults["start_time"],
        )
        end_t = _parse_hhmm(
            planned_end_time or sched_defaults["end_time"].strftime("%H:%M"),
            sched_defaults["end_time"],
        )
    except ValueError as exc:
        return {
            "status": "needs_input",
            "missing": ["schedule"],
            "questions": [{"field": "schedule", "prompt": str(exc)}],
        }

    source_tz = schedule_timezone or sched_defaults.get("source_timezone") or config.TCKT_SCHEDULE_SOURCE_TZ
    store_tz = sched_defaults.get("store_timezone") or config.TCKT_SCHEDULE_TZ
    display_tz = sched_defaults.get("display_timezone") or config.TCKT_DISPLAY_TZ
    window = schedule_time.window_statement(
        start_d, start_t, end_d, end_t,
        tz_name=source_tz,
        display_tz=display_tz,
    )
    jira_sched = schedule_time.resolve_jira_schedule(
        start_d, start_t, end_d, end_t,
        source_tz=source_tz,
        store_tz=store_tz,
    )

    if draft.get("summary"):
        summary = str(draft["summary"])
    elif is_test:
        summary = shipit_test_mode.default_test_summary(version_label)
    else:
        summary = build_shipit_summary(version_name=version_name)
    desc_adf = draft.get("description_adf") or _build_description_adf(
        extracted, sharepoint, version_label, window,
    )
    ctx = _plan_context(extracted, sharepoint, version_label, window)
    ctx["version"] = version_label
    implementation_plan = str(draft.get("implementation_plan") or _build_impl(ctx))
    test_plan = str(draft.get("test_plan") or _build_test(ctx))
    backout_plan = str(draft.get("backout_plan") or _build_backout(ctx))
    business_impact = str(draft.get("business_impact") or _build_impact(ctx))
    communication_plan = str(draft.get("communication_plan") or _build_communication(ctx))
    reason_for_change = str(draft.get("reason_for_change") or _build_reason(ctx))
    risks_management = str(draft.get("risks_management") or build_risks(ctx))
    qa_test_plan = str(draft.get("qa_test_plan") or build_qa_test_plan(ctx))

    impl_key = config.service_desk_field("implementation_steps")
    test_key = config.service_desk_field("verification_steps")
    backout_key = config.service_desk_field("rollback_steps")
    risks_key = config.TCKT_FIELDS.get("risks_management", "")
    qa_key = config.TCKT_FIELDS.get("qa_test_plan", "")

    fields: dict[str, Any] = {
        "description": desc_adf,
        "priority": draft.get(
            "priority", config.TCKT_DEFAULTS.get("priority", {"name": "Medium"}),
        ),
        config.TCKT_FIELDS["change_type"]: draft.get(
            "change_type",
            config.resolve_tckt_select(
                "change_type", profile_change_type or "Normal",
            ),
        ),
        config.TCKT_FIELDS["change_risk"]: draft.get(
            "change_risk", config.resolve_tckt_select("change_risk", "Medium"),
        ),
        # SHIPIT-16769 parity: Rekha's prod tickets leave impact/urgency unset (None)
        # Only set if explicitly provided in draft override
        config.TCKT_FIELDS["planned_start"]: jira_sched["start_iso"],
        config.TCKT_FIELDS["planned_end"]: jira_sched["end_iso"],
        impl_key: _text_to_adf(implementation_plan),
        test_key: _multi_para_adf(test_plan),
        backout_key: _text_to_adf(backout_plan),
        config.TCKT_FIELDS["business_impact"]: _multi_para_adf(business_impact),
    }
    if risks_key and risks_management.strip():
        fields[risks_key] = _multi_para_adf(risks_management)
    if qa_key and qa_test_plan.strip():
        fields[qa_key] = _text_to_adf(qa_test_plan)
    # Impact/Urgency: only set if explicitly provided (Rekha's tickets leave these as None)
    if draft.get("impact"):
        fields[config.TCKT_FIELDS["impact"]] = draft["impact"]
    if draft.get("urgency"):
        fields[config.TCKT_FIELDS["urgency"]] = draft["urgency"]
    # Production tickets use the verified Glofox service from workspace config.
    # Test/demo tickets deliberately remain unassigned.
    affected = draft.get("affected_services") or config.TCKT_DEFAULTS.get("affected_services")
    if not is_test and affected and config.TCKT_FIELDS.get("affected_services"):
        fields[config.TCKT_FIELDS["affected_services"]] = affected
    if config.TCKT_FIELDS.get("communication_plan"):
        fields[config.TCKT_FIELDS["communication_plan"]] = _multi_para_adf(communication_plan)
    if config.TCKT_FIELDS.get("reason_for_change") and reason_for_change.strip():
        fields[config.TCKT_FIELDS["reason_for_change"]] = reason_for_change.strip()
    if config.TCKT_FIELDS.get("approvers"):
        approvers = (
            draft.get("approvers", [])
            if is_test
            else draft.get("approvers", config.TCKT_DEFAULTS.get("approvers", []))
        )
        if approvers:
            fields[config.TCKT_FIELDS["approvers"]] = approvers
    for optional_key in ("assignment_group", "affects_pf", "outage_required", "team", "approver_groups", "unplanned"):
        field_id = config.TCKT_FIELDS.get(optional_key)
        if is_test and optional_key in ("assignment_group", "team", "approver_groups"):
            if optional_key in draft and draft.get(optional_key):
                fields[field_id] = draft[optional_key]
            continue
        if optional_key == "assignment_group":
            value = jira_client.resolve_assignment_group_value(config.TCKT_DEFAULTS)
        else:
            value = config.TCKT_DEFAULTS.get(optional_key)
        if optional_key in draft:
            value = draft[optional_key]
        if field_id and value:
            fields[field_id] = value

    problems = jira_client.validate_service_desk_create_payload(summary, fields)
    if problems:
        return {
            "status": "preflight_failed",
            "summary": summary,
            "problems": problems,
            "ticket_count": len(extracted),
            "dry_run": dry_run,
        }

    if dry_run:
        from generators.shipit_quality import assess_shipit_draft

        desc_plain = adf.adf_to_plain_text(desc_adf) if isinstance(desc_adf, dict) else ""
        quality = assess_shipit_draft(
            ctx,
            summary=summary,
            description_plain=desc_plain,
            plans={
                "implementation_plan": implementation_plan,
                "verification_plan": test_plan,
                "rollback_plan": backout_plan,
                "business_impact": business_impact,
                "communication_plan": communication_plan,
                "risks_management": risks_management,
                "qa_test_plan": qa_test_plan,
            },
        )
        post_create_plan = shipit_post_create.build_post_create_plan(
            extracted,
            is_test=is_test,
            options=post_create_overrides,
            owner_account_id=shipit_owner_account_id,
        )
        return {
            "status": "dry_run",
            "summary": summary,
            "ticket_count": len(extracted),
            "projects": fetch.get("projects"),
            "by_project_counts": {
                pk: info.get("count", 0)
                for pk, info in (fetch.get("by_project") or {}).items()
                if isinstance(info, dict)
            },
            "sharepoint_url": sharepoint,
            "planned_start": fields[config.TCKT_FIELDS["planned_start"]],
            "planned_end": fields[config.TCKT_FIELDS["planned_end"]],
            "deployment_window": window.get("sentence"),
            "browse_preview": f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{config.TCKT_PROJECT_KEY}-????",
            "message": (
                "Preflight OK. No ticket created (dry_run=true). "
                "Call again with dry_run=false after user confirms."
            ),
            "tickets": [e["ticket"] for e in extracted],
            "test_mode": is_test,
            "cab_quality": quality,
            "request_type": config.TCKT_REQUEST_TYPE_NAME or "Manual Change",
            "post_create_plan": post_create_plan,
        }

    result, rt_status = jira_client.create_tckt_issue(summary, fields)
    key = result.get("key")
    if key and window:
        try:
            jira_client.add_schedule_window_comment(key, window)
        except Exception as exc:  # noqa: BLE001 — best-effort post-create
            result["schedule_comment_warning"] = str(exc)

    if key:
        ctx["ticket_key"] = key
        comm_field = config.TCKT_FIELDS.get("communication_plan")
        updated_comm = _build_communication(ctx)
        if comm_field and updated_comm and updated_comm != communication_plan:
            try:
                jira_client.edit_issue(
                    key,
                    {comm_field: _multi_para_adf(updated_comm)},
                )
            except Exception as exc:  # noqa: BLE001
                result["communication_plan_warning"] = str(exc)

    post_create_result: dict[str, Any] | None = None
    if key:
        try:
            post_create_result = shipit_post_create.apply_post_create(
                key,
                extracted,
                is_test=is_test,
                options=post_create_overrides,
                owner_account_id=shipit_owner_account_id,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort post-create
            post_create_result = {
                "status": "error",
                "warnings": [str(exc)],
                "applied": [],
                "skipped": [],
            }

    return {
        "status": "created",
        "key": key,
        "url": f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{key}" if key else None,
        "summary": summary,
        "ticket_count": len(extracted),
        "test_mode": is_test,
        "request_type": rt_status.to_dict() if hasattr(rt_status, "to_dict") else str(rt_status),
        "supplementalWarning": result.get("supplementalWarning"),
        "linked_tickets": shipit_post_create.release_ticket_keys_from_extracted(extracted),
        "post_create": post_create_result,
        "message": f"Service ticket {key} created." if key else "Create returned without a key.",
    }


def dispose_test_shipit_ticket(
    issue_key: str,
    *,
    comment: str | None = None,
) -> dict[str, Any]:
    """Close and delete a TEST/demo SHIPIT (comment → cancel → delete)."""
    return jira_client.dispose_test_shipit_ticket(
        issue_key,
        comment=comment
        or (
            "Test demo ticket — Release Orchestrator validation only. "
            "DO NOT DEPLOY. Safe to cancel and delete."
        ),
    )
