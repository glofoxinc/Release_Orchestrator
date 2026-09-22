"""Fetch review-ready tickets (PIC + AN, Glofox team, status defaults)."""

from __future__ import annotations

from typing import Any

import config
import jira_client
from release_gates import issue_assignee, issue_status_name


def resolve_fetch_statuses(project_key: str) -> list[str]:
    """Map workspace default_checked_statuses to live Jira status names."""
    pk = project_key.strip().upper()
    try:
        options = jira_client.get_project_status_names(pk)
    except Exception:
        options = []
    options_map = {name.casefold(): name for name in options}
    picked: list[str] = []
    for target in config.ticket_review_default_checked_statuses(pk):
        canonical = options_map.get(target.casefold())
        if canonical and canonical not in picked:
            picked.append(canonical)
        elif target not in picked and not options:
            picked.append(target)
    return picked


def fetch_review_tickets(
    *,
    projects: list[str],
    jira_team_id: str,
) -> dict[str, Any]:
    """Fetch tickets per project using Ticket Review status defaults + team filter."""
    team_ids = [jira_team_id] if jira_team_id else None
    by_project: dict[str, Any] = {}
    all_issues: list[dict] = []
    errors: list[str] = []

    for pk in projects:
        statuses = resolve_fetch_statuses(pk)
        if not statuses:
            errors.append(f"{pk}: no fetch statuses resolved")
            by_project[pk] = {"statuses": [], "count": 0, "issues": []}
            continue
        try:
            issues = jira_client.get_issues_for_statuses(pk, statuses, jira_team_ids=team_ids)
        except Exception as exc:
            errors.append(f"{pk}: {exc}")
            by_project[pk] = {"statuses": statuses, "error": str(exc), "count": 0, "issues": []}
            continue
        by_project[pk] = {"statuses": statuses, "count": len(issues), "issues": issues}
        all_issues.extend(issues)

    return {
        "status": "ok" if not errors else "partial",
        "total": len(all_issues),
        "by_project": by_project,
        "issues": all_issues,
        "errors": errors,
    }


def ticket_rows(issues: list[dict]) -> list[dict[str, str]]:
    """Flatten Jira issues for report + meeting body."""
    rows: list[dict[str, str]] = []
    base = (config.JIRA_BASE_URL or "").rstrip("/")
    for issue in issues:
        key = str(issue.get("key") or "")
        fields = issue.get("fields") or {}
        summary = str(fields.get("summary") or "")
        status = issue_status_name(issue)
        assignee_name, assignee_email = issue_assignee(issue)
        link = f"{base}/browse/{key}" if base and key else ""
        rows.append(
            {
                "key": key,
                "summary": summary,
                "status": status,
                "assignee": assignee_name,
                "assignee_email": assignee_email,
                "link": link,
            }
        )
    return rows
