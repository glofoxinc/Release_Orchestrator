"""Shared Daily Review ticket fetch + scope + review-done filters."""

from __future__ import annotations

from typing import Any

from daily_review_agent.assignee_scope import TicketScopeConfig, filter_assignee_scope, ticket_scope_policy_summary
from daily_review_agent.config_loader import AgentConfig
from daily_review_agent.review_filter import filter_already_reviewed
from daily_review_agent.ticket_fetch import fetch_review_tickets
from release_gates import issue_project_key


def _rebuild_by_project(by_project: dict[str, Any], kept_issues: list[dict]) -> dict[str, Any]:
    buckets: dict[str, list[dict]] = {}
    for issue in kept_issues:
        pk = issue_project_key(issue)
        buckets.setdefault(pk, []).append(issue)

    out: dict[str, Any] = {}
    for pk, meta in by_project.items():
        row = dict(meta) if isinstance(meta, dict) else {}
        project_issues = buckets.get(pk.upper(), [])
        row["count"] = len(project_issues)
        row["issues"] = project_issues
        out[pk] = row
    return out


def resolve_review_issues(cfg: AgentConfig) -> dict[str, Any]:
    """Fetch PIC/AN review tickets and apply squad scope + review-done filters."""
    fetch = fetch_review_tickets(projects=cfg.projects, jira_team_id=cfg.jira_team_id)
    raw_issues = list(fetch.get("issues") or [])
    scope: TicketScopeConfig = getattr(cfg, "ticket_scope", None) or TicketScopeConfig()

    scoped, skipped_scope = filter_assignee_scope(raw_issues, scope)
    kept, skipped_reviewed = filter_already_reviewed(scoped, cfg.review_filter)

    fetch["issues"] = kept
    fetch["total"] = len(kept)
    fetch["raw_total"] = len(raw_issues)
    fetch["skipped_outside_squad"] = skipped_scope
    fetch["skipped_already_reviewed"] = skipped_reviewed
    fetch["ticket_scope"] = ticket_scope_policy_summary(scope)
    fetch["by_project"] = _rebuild_by_project(fetch.get("by_project") or {}, kept)
    return fetch


__all__ = ["resolve_review_issues"]
