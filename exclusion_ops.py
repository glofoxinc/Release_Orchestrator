"""Headless fix-version exclusion (preview + confirmed remove).

Mirrors the Deployer exclude-tickets flow without Streamlit.
"""

from __future__ import annotations

from typing import Any, Iterable

import jira_client
import team_scope


def resolve_version(project_key: str, version_name: str) -> dict[str, Any]:
    """Resolve a fix version by exact name (case-insensitive)."""
    needle = version_name.strip().lower()
    for ver in jira_client.get_project_versions(project_key):
        if ver.get("name", "").strip().lower() == needle:
            return ver
    available = [v.get("name") for v in jira_client.get_project_versions(project_key)[:15]]
    raise ValueError(
        f"Version '{version_name}' not found in {project_key}. "
        f"Recent versions: {available}"
    )


def _normalize_keys(ticket_keys: Iterable[str] | None) -> list[str]:
    return sorted({str(k).strip() for k in (ticket_keys or []) if k and str(k).strip()})


def preview_exclusion(
    project_key: str,
    version_name: str,
    ticket_keys: Iterable[str] | None,
) -> dict[str, Any]:
    """Preview removing ``version_name`` from the given ticket keys (no writes)."""
    keys = _normalize_keys(ticket_keys)
    if not keys:
        return {
            "status": "needs_input",
            "missing": ["ticket_keys"],
            "message": "Provide ticket_keys to exclude from the fix version.",
        }

    try:
        version = resolve_version(project_key, version_name)
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}

    version_id = str(version.get("id", ""))
    version_label = version.get("name", version_name)
    issues = jira_client.get_issues_for_version(project_key, version_id)
    on_version = {iss["key"]: iss for iss in issues}

    would_remove = [k for k in keys if k in on_version]
    not_on_version = [k for k in keys if k not in on_version]

    return {
        "status": "dry_run",
        "project": project_key,
        "version": version_label,
        "version_id": version_id,
        "ticket_keys": keys,
        "would_remove": would_remove,
        "not_on_version": not_on_version,
        "message": (
            "Preview only — no Jira writes. "
            "Call again with dry_run=false after confirmation."
        ),
    }


def remove_fix_versions(
    project_key: str,
    version_name: str,
    ticket_keys: Iterable[str] | None,
    *,
    dry_run: bool = True,
    issues_by_key: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Remove fix version from selected tickets (default ``dry_run=True``)."""
    if dry_run:
        return preview_exclusion(project_key, version_name, ticket_keys)

    keys = _normalize_keys(ticket_keys)
    if not keys:
        return {
            "status": "needs_input",
            "missing": ["ticket_keys"],
            "message": "Provide ticket_keys to exclude from the fix version.",
        }

    try:
        version = resolve_version(project_key, version_name)
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}

    version_id = str(version.get("id", ""))
    version_label = version.get("name", version_name)

    if issues_by_key is None:
        issues = jira_client.get_issues_for_version(project_key, version_id)
        issues_by_key = {iss["key"]: iss for iss in issues}

    try:
        team_scope.assert_keys_in_scoped_version(
            project_key, version_id, keys, scoped_keys=issues_by_key.keys(),
        )
    except team_scope.TeamScopeError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "project": project_key,
            "version": version_label,
            "dry_run": False,
        }

    result = jira_client.remove_fix_version_from_issues(
        keys,
        version_id,
        issues_by_key=issues_by_key,
    )

    status = "ok"
    if result["errors"] and result["success"]:
        status = "partial"
    elif result["errors"] and not result["success"]:
        status = "failed"
    elif not result["success"] and result["skipped"]:
        status = "skipped"

    return {
        "status": status,
        "project": project_key,
        "version": version_label,
        "version_id": version_id,
        "success": result["success"],
        "skipped": result["skipped"],
        "errors": [{"key": k, "error": msg} for k, msg in result["errors"]],
        "dry_run": False,
    }
