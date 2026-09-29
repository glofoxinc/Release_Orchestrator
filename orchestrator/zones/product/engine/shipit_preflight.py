"""SHIPIT service-desk preflight — assignment group, metadata, dry-run preview."""

from __future__ import annotations

from typing import Any

import config
import jira_client


def preflight_service_desk_metadata() -> dict[str, Any]:
    """Validate SHIPIT desk / issue type / request type IDs from workspace config."""
    config.reload_workspace()
    missing: list[str] = []
    if not config.TCKT_PROJECT_KEY:
        missing.append("service_desk.project_key")
    if not config.TCKT_ISSUE_TYPE_ID:
        missing.append("service_desk.issue_type_id")
    if not config.TCKT_SERVICE_DESK_ID:
        missing.append("service_desk.service_desk_id")
    if not config.TCKT_REQUEST_TYPE_ID:
        missing.append("service_desk.request_type_id")
    ready = not missing
    return {
        "status": "ok" if ready else "fail",
        "project_key": config.TCKT_PROJECT_KEY,
        "issue_type_id": config.TCKT_ISSUE_TYPE_ID,
        "service_desk_id": config.TCKT_SERVICE_DESK_ID,
        "request_type_id": config.TCKT_REQUEST_TYPE_ID,
        "create_mode": config.SERVICE_DESK_CREATE_MODE,
        "missing": missing,
        "detail": (
            f"{config.TCKT_PROJECT_KEY} desk={config.TCKT_SERVICE_DESK_ID} "
            f"rt={config.TCKT_REQUEST_TYPE_ID}"
            if ready
            else f"Missing: {', '.join(missing)}"
        ),
    }


def preflight_assignment_group(*, group_name: str | None = None) -> dict[str, Any]:
    """Verify assignment group name resolves in Jira (group picker on SHIPIT).

    Uses ``GET /rest/api/3/group?groupName=...``. When ``assignment_group_name`` is
    blank in workspace.yaml, returns ``status=skip`` — post-create edit omits the field.
    """
    config.reload_workspace()
    name = (group_name or config.TCKT_DEFAULTS.get("assignment_group_name") or "").strip()
    payload = jira_client.resolve_assignment_group_value()
    if not name:
        return {
            "status": "skip",
            "group_name": "",
            "payload": payload,
            "detail": "assignment_group_name blank — optional on SHIPIT; post-create edit skips it.",
        }
    if jira_client.is_mock_mode():
        return {
            "status": "mock",
            "group_name": name,
            "payload": payload or {"name": name},
            "detail": f"MOCK_MODE — would validate group '{name}' via Jira REST.",
        }
    try:
        group = jira_client.get_group(name)
    except jira_client.JiraApiError as exc:
        optional = exc.status_code in {400, 404}
        return {
            "status": "warn" if optional else "fail",
            "group_name": name,
            "payload": payload,
            "detail": str(exc),
            "hint": (
                "Assignment group is optional on SHIPIT — clear "
                "service_desk.defaults.assignment_group_name in workspace.yaml "
                "if this group name is wrong for your tenant."
            ),
        }
    if not group:
        return {
            "status": "fail",
            "group_name": name,
            "payload": payload,
            "detail": f"Jira group '{name}' not found (404).",
            "hint": "Confirm exact group name in Jira admin or clear assignment_group_name.",
        }
    return {
        "status": "ok",
        "group_name": name,
        "group_id": group.get("groupId") or group.get("name"),
        "payload": payload,
        "detail": f"Group '{name}' exists — post-create edit can set customfield assignment group.",
    }


GOLDEN_PATH_EXTRACTED: list[dict[str, Any]] = [
    {
        "ticket": "AN-GOLDEN",
        "type": "Analyze",
        "client": "Standard",
        "report": "Golden Path",
        "description": "Offline finalize — validated in test_golden_path_e2e.py",
        "evidence": {
            "description_plain": "Golden path E2E validated in test_golden_path_e2e.py",
            "comments": [],
        },
    },
]


def preflight_shipit_create_dry_run(
    *,
    version_name: str,
    sharepoint_url: str,
    projects: list[str] | None = None,
) -> dict[str, Any]:
    """Run MCP-parity SHIPIT create with dry_run=true (no Jira write)."""
    from release_mcp import release_ops

    return release_ops.create_service_ticket(
        version_name=version_name,
        sharepoint_url=sharepoint_url,
        projects=projects,
        dry_run=True,
    )


def preflight_shipit_create_dry_run_safe(
    *,
    version_name: str,
    sharepoint_url: str,
    projects: list[str] | None = None,
) -> dict[str, Any]:
    """Dry-run SHIPIT create; falls back to offline golden-path sample when Jira is unreachable."""
    try:
        return preflight_shipit_create_dry_run(
            version_name=version_name,
            sharepoint_url=sharepoint_url,
            projects=projects,
        )
    except jira_client.JiraApiError as exc:
        from release_mcp import release_ops

        version = version_name.strip()
        result = release_ops.create_service_ticket(
            version_name=version,
            sharepoint_url=sharepoint_url.strip(),
            projects=projects,
            dry_run=True,
            test_mode=True,
            extracted_override=GOLDEN_PATH_EXTRACTED,
            draft_overrides={
                "summary": f"TEST SHIPIT Finalize - DO NOT DEPLOY (v{version})",
            },
        )
        return {
            **result,
            "offline_fallback": True,
            "jira_error": str(exc),
        }


def summarize_preflight(
    *,
    metadata: dict[str, Any] | None = None,
    assignment: dict[str, Any] | None = None,
    dry_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate preflight results for sign-off scripts."""
    meta = metadata or preflight_service_desk_metadata()
    assign = assignment or preflight_assignment_group()
    parts = [meta, assign]
    if dry_run is not None:
        parts.append({"kind": "dry_run", **dry_run})
    blocking = [
        p for p in parts
        if p.get("status") in {"fail", "error"} or (
            p.get("kind") == "dry_run" and p.get("status") not in {"dry_run", "ok", "needs_input"}
        )
    ]
    return {
        "ready": not blocking,
        "metadata": meta,
        "assignment_group": assign,
        "dry_run": dry_run,
        "blocking": blocking,
    }
