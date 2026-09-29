"""MCP wrappers for pre-review and post-QA release gates."""

from __future__ import annotations

from typing import Any

import config
import jira_client
import release_gates
from slack_assignee_notify import gate_slack_status


def _release_label() -> str:
    parts = []
    for proj in config.PROJECTS:
        pk = proj["key"]
        # MCP callers pass version_name; project releases resolved elsewhere.
        parts.append(pk)
    return " + ".join(parts)


def _resolve_issues_for_version(
    version_name: str,
    projects: list[str] | None,
    ticket_keys: list[str] | None = None,
) -> tuple[list[dict], list[str]]:
    version_name = (version_name or "").strip()
    if not version_name:
        return [], ["version_name is required"]

    keys_filter = {k.strip().upper() for k in (ticket_keys or []) if k and str(k).strip()}
    project_keys = projects or [p["key"] for p in config.PROJECTS]
    issues: list[dict] = []
    errors: list[str] = []

    for pk in project_keys:
        pk = pk.strip().upper()
        try:
            versions = jira_client.get_project_versions(pk)
            target = None
            needle = version_name.lower()
            for ver in versions:
                if str(ver.get("name", "")).strip().lower() == needle:
                    target = ver
                    break
            if not target:
                errors.append(f"Version '{version_name}' not found in {pk}")
                continue
            fetched = jira_client.get_issues_for_version(pk, str(target["id"]))
            if keys_filter:
                fetched = [iss for iss in fetched if iss.get("key", "").upper() in keys_filter]
            issues.extend(fetched)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{pk}: {exc}")
    return issues, errors


def pre_review_gate(
    version_name: str,
    *,
    projects: list[str] | None = None,
    notify: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Classify tickets for Ticket Review readiness; optionally Slack assignees."""
    issues, errors = _resolve_issues_for_version(version_name, projects)
    if errors and not issues:
        return {"status": "error", "errors": errors}
    result = release_gates.run_pre_review_gate(
        issues,
        version_name=version_name,
        notify=notify,
        dry_run=dry_run,
    )
    if errors:
        result["warnings"] = errors
    result["scope"] = _release_label()
    return result


def post_qa_gate(
    version_name: str,
    *,
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    notify: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Find QA failures, build excluded-tickets text, optionally Slack assignees."""
    issues, errors = _resolve_issues_for_version(version_name, projects, ticket_keys)
    if errors and not issues:
        return {"status": "error", "errors": errors}
    result = release_gates.run_post_qa_gate(
        issues,
        version_name=version_name,
        notify=notify,
        dry_run=dry_run,
    )
    if errors:
        result["warnings"] = errors
    result["scope"] = _release_label()
    return result


def release_gate_status() -> dict[str, Any]:
    import github_pr_gate

    return {
        "status": "ok",
        "release_gates_enabled": release_gates.gates_root_enabled(),
        "pre_review_enabled": release_gates.gate_enabled("pre_review"),
        "post_qa_enabled": release_gates.gate_enabled("post_qa"),
        "github_pr_enabled": github_pr_gate.gate_enabled(),
        "github_pr_comment_on_fetch": github_pr_gate.comment_on_fetch_enabled(),
        "github_configured": github_pr_gate.github_configured(),
        "pre_review_statuses": list(release_gates.pre_review_statuses()),
        "post_qa_statuses": list(release_gates.qa_passed_statuses()),
        "slack": gate_slack_status(),
    }


def github_pr_gate_check(
    ticket_keys: list[str] | None = None,
    *,
    dry_run: bool = True,
    post_comments: bool = False,
) -> dict[str, Any]:
    """Check open/unapproved GitHub PRs for tickets; optionally post Jira comments."""
    import github_pr_gate

    keys = [str(k).strip().upper() for k in (ticket_keys or []) if str(k).strip()]
    extracted = [{"ticket": k, "summary": k} for k in keys]
    gate = github_pr_gate.run_pr_gate(extracted, dry_run=dry_run)
    comments = None
    if post_comments and gate.get("blocking_count"):
        comments = github_pr_gate.post_pr_comments(gate, dry_run=dry_run)
        gate["comments"] = comments
    gate["summary"] = github_pr_gate.format_gate_summary(gate)
    return gate
