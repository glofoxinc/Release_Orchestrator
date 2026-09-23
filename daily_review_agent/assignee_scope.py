"""Daily Review ticket scope — skip outside-squad assignees unless explicitly enabled."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from release_gates import assignee_in_squad, issue_assignee

try:
    from team_crew import load_crew_from_env
except ImportError:  # pragma: no cover
    load_crew_from_env = None  # type: ignore[assignment]


@dataclass
class TicketScopeConfig:
    """Which assignees' tickets appear in Daily Review fetch + summary."""

    include_outside_squad_assignees: bool = False


def _exclude_emails() -> set[str]:
    if load_crew_from_env is None:
        return set()
    draft = load_crew_from_env()
    return set(draft.exclude_emails) if draft else set()


def assignee_scope_reason(name: str, email: str, *, include_outside_squad: bool) -> str | None:
    """Return skip reason, or None when the ticket stays in scope."""
    if include_outside_squad:
        return None
    assignee = (name or "").strip()
    if not assignee or assignee.lower() == "unassigned":
        return None
    norm_email = (email or "").strip().lower()
    if norm_email and norm_email in _exclude_emails():
        return "TEAM_CREW_EXCLUDE"
    if not assignee_in_squad(assignee):
        return "outside_squad_assignee"
    return None


def filter_assignee_scope(
    issues: list[dict],
    scope: TicketScopeConfig,
) -> tuple[list[dict], list[dict[str, str]]]:
    """Drop tickets assigned outside Customize BI squad (Gabriel/Erasmo) unless opted in."""
    if scope.include_outside_squad_assignees:
        return issues, []

    kept: list[dict] = []
    skipped: list[dict[str, str]] = []
    for issue in issues:
        key = str(issue.get("key") or "")
        name, email = issue_assignee(issue)
        reason = assignee_scope_reason(
            name,
            email,
            include_outside_squad=scope.include_outside_squad_assignees,
        )
        if reason:
            skipped.append(
                {
                    "key": key,
                    "assignee": name,
                    "email": email,
                    "reason": reason,
                }
            )
            continue
        kept.append(issue)
    return kept, skipped


def ticket_scope_policy_summary(scope: TicketScopeConfig) -> dict[str, Any]:
    return {
        "include_outside_squad_assignees": scope.include_outside_squad_assignees,
        "default": "Skip outside-squad assignees (e.g. Gabriel, Erasmo) until explicitly enabled",
        "unassigned": "Always included",
        "opt_in": "Set ticket_scope.include_outside_squad_assignees: true in agent.yaml",
    }


__all__ = [
    "TicketScopeConfig",
    "assignee_scope_reason",
    "filter_assignee_scope",
    "ticket_scope_policy_summary",
]
