"""Daily Review ticket scope — skip outside-squad assignees."""

from __future__ import annotations

from daily_review_agent.assignee_scope import TicketScopeConfig, filter_assignee_scope


def _issue(key: str, name: str, email: str = "") -> dict:
    return {"key": key, "fields": {"assignee": {"displayName": name, "emailAddress": email}}}


def test_outside_squad_tickets_skipped_by_default():
    scope = TicketScopeConfig(include_outside_squad_assignees=False)
    issues = [
        _issue("PIC-1", "Navyasri Kalla", "navyasri.kalla@abcfitness.com"),
        _issue("AN-1", "Erasmo García", "erasmo.garcia@abcfitness.com"),
        _issue("PIC-2", "Gabriel Barbosa", "gabriel.barbosa@abcfitness.com"),
        _issue("PIC-3", "Unassigned", ""),
    ]
    kept, skipped = filter_assignee_scope(issues, scope)
    keys = {i["key"] for i in kept}
    assert keys == {"PIC-1", "PIC-3"}
    skipped_keys = {row["key"] for row in skipped}
    assert skipped_keys == {"AN-1", "PIC-2"}
    assert all(
        row["reason"] in {"outside_squad_assignee", "TEAM_CREW_EXCLUDE"}
        for row in skipped
    )


def test_outside_squad_opt_in_includes_all():
    scope = TicketScopeConfig(include_outside_squad_assignees=True)
    issues = [
        _issue("AN-1", "Erasmo García", "erasmo.garcia@abcfitness.com"),
        _issue("PIC-2", "Gabriel Barbosa", "gabriel.barbosa@abcfitness.com"),
    ]
    kept, skipped = filter_assignee_scope(issues, scope)
    assert len(kept) == 2
    assert skipped == []
