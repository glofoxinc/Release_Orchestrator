"""Daily Review meeting invite policy — crew + squad assignees."""

from __future__ import annotations

import os

import pytest

from daily_review_agent.config_loader import AgentConfig, AttendeeSpec
from daily_review_agent.meeting_attendees import (
    attendee_policy_summary,
    collect_crew_aware_attendees,
)


def _issue(key: str, name: str, email: str) -> dict:
    return {"key": key, "fields": {"assignee": {"displayName": name, "emailAddress": email}}}


def test_outside_squad_assignees_not_invited_legacy(monkeypatch):
    monkeypatch.delenv("DEFAULT_JIRA_TEAM", raising=False)
    cfg = AgentConfig(
        required_attendees=[AttendeeSpec(email="s@x.com", name="Sushma")],
        assignee_invite_type="required",
    )
    issues = [
        _issue("PIC-1", "Navyasri Kalla", "navyasri.kalla@abcfitness.com"),
        _issue("AN-1", "Erasmo García", "erasmo.garcia@abcfitness.com"),
        _issue("PIC-2", "Gabriel Barbosa", "gabriel.barbosa@abcfitness.com"),
    ]
    attendees = collect_crew_aware_attendees(cfg, issues)
    emails = {a.email.lower() for a in attendees}
    assert "s@x.com" in emails
    assert "navyasri.kalla@abcfitness.com" in emails
    assert "erasmo.garcia@abcfitness.com" not in emails
    assert "gabriel.barbosa@abcfitness.com" not in emails


def test_crew_aware_required_and_optional(monkeypatch):
    monkeypatch.setenv("DEFAULT_JIRA_TEAM", "Glofox Insights Customize")
    monkeypatch.setenv("DEFAULT_PROJECTS", "PIC,AN")
    monkeypatch.setenv(
        "TEAM_CREW_REVIEW",
        "Sushma Bhamidipati <VenkataSuryaNagaSushma.Bhamidipati@abcfitness.com>; "
        "Soumyakant Mishra <Soumyakant.Mishra@abcfitness.com>",
    )
    monkeypatch.setenv("TEAM_CREW_RELEASE", "Trent Vanest <Trent.Vanest@abcfitness.com>")
    monkeypatch.setenv("TEAM_CREW_LEADERSHIP", "Trent Vanest <Trent.Vanest@abcfitness.com>")
    monkeypatch.setenv("TEAM_CREW_QA", "Navya, Bharathi")
    monkeypatch.setenv("TEAM_CREW_EXCLUDE", "erasmo.garcia@abcfitness.com")

    cfg = AgentConfig()
    issues = [
        _issue("PIC-1", "Navyasri Kalla", "navyasri.kalla@abcfitness.com"),
        _issue("AN-1", "Erasmo García", "erasmo.garcia@abcfitness.com"),
    ]
    summary = attendee_policy_summary(cfg, issues)
    assert summary["source"] == "team_crew"
    assert "erasmo.garcia@abcfitness.com" in [
        row["email"].lower() for row in summary["skipped_excluded"]
    ]
    attendees = collect_crew_aware_attendees(cfg, issues)
    by_type = {a.email.lower(): a.type for a in attendees}
    assert by_type.get("trent.vanest@abcfitness.com") == "required"
    assert by_type.get("navyasri.kalla@abcfitness.com") == "required"
    assert "erasmo.garcia@abcfitness.com" not in by_type
    assert by_type.get("soumyakant.mishra@abcfitness.com") == "optional"
