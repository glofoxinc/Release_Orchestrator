"""Daily Review meeting invites — crew from onboarding + squad assignees.

Required (mandatory): leadership, QA pool, in-squad ticket assignees.
Optional: standing review + release crew from welcome onboard (TEAM_CREW_*).
Excluded from invites: TEAM_CREW_EXCLUDE + outside-squad assignees.
Outside-squad tickets are also skipped at fetch (see ticket_scope in agent.yaml).
"""

from __future__ import annotations

from typing import Any

from daily_review_agent.config_loader import AgentConfig, AttendeeSpec
from release_gates import assignee_in_squad, issue_assignee
from teams_schedule import TeamsAttendee

try:
    import team_crew
    from team_crew import CrewPerson, TeamCrewDraft, apply_exclusions, load_crew_from_env
except ImportError:  # pragma: no cover
    team_crew = None  # type: ignore[assignment]
    CrewPerson = TeamCrewDraft = None  # type: ignore[misc, assignment]
    apply_exclusions = load_crew_from_env = None  # type: ignore[assignment]


def _specs_to_attendees(specs: list[AttendeeSpec], invite_type: str) -> list[TeamsAttendee]:
    out: list[TeamsAttendee] = []
    for spec in specs:
        email = (spec.email or "").strip()
        if not email:
            continue
        out.append(
            TeamsAttendee(
                email=email,
                name=spec.name or email,
                type=invite_type if invite_type in {"required", "optional"} else "required",
            )
        )
    return out


def _person_to_attendee(person: CrewPerson, invite_type: str) -> TeamsAttendee | None:
    email = (person.email or "").strip()
    if not email:
        return None
    return TeamsAttendee(email=email, name=person.name or email, type=invite_type)


def _merge_attendees(*groups: list[TeamsAttendee]) -> list[TeamsAttendee]:
    seen: set[str] = set()
    out: list[TeamsAttendee] = []
    for group in groups:
        for attendee in group:
            key = attendee.email.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(attendee)
    return out


def _resolve_qa_with_email(qa: list[CrewPerson], directory: list[CrewPerson]) -> list[CrewPerson]:
    """Map QA name tokens to crew emails when QA entries are names-only."""
    resolved: list[CrewPerson] = []
    for person in qa:
        if person.email:
            resolved.append(person)
            continue
        token = person.name.strip().lower()
        if not token:
            continue
        for candidate in directory:
            email = candidate.email_lower()
            name = candidate.name.strip().lower()
            if not email or not name:
                continue
            if token in name or name.split()[0] == token:
                resolved.append(CrewPerson(name=candidate.name, email=candidate.email))
                break
    return resolved


def _crew_directory(draft: TeamCrewDraft) -> list[CrewPerson]:
    exclude = draft.exclude_emails
    return apply_exclusions(
        list(draft.squad) + list(draft.review) + list(draft.release) + list(draft.leadership),
        exclude,
    )


def _is_excluded_email(email: str, draft: TeamCrewDraft | None) -> bool:
    norm = email.strip().lower()
    if not norm:
        return True
    if draft and norm in draft.exclude_emails:
        return True
    return False


def collect_crew_aware_attendees(cfg: AgentConfig, issues: list[dict]) -> list[TeamsAttendee]:
    """Build required + optional attendee list from onboarding crew and ticket assignees."""
    if load_crew_from_env is None:
        return _legacy_collect(cfg, issues)

    draft = load_crew_from_env()
    if draft is None or not draft.crew_configured():
        return _legacy_collect(cfg, issues)

    exclude = draft.exclude_emails
    directory = _crew_directory(draft)

    leadership = apply_exclusions(draft.leadership, exclude)
    qa_resolved = _resolve_qa_with_email(apply_exclusions(draft.qa, exclude), directory)
    review_crew = apply_exclusions(draft.review, exclude)
    release_crew = apply_exclusions(draft.release, exclude)

    required_people: list[CrewPerson] = list(leadership) + list(qa_resolved)

    for issue in issues:
        name, email = issue_assignee(issue)
        norm = email.strip().lower()
        if not norm or _is_excluded_email(norm, draft):
            continue
        if not assignee_in_squad(name):
            continue
        required_people.append(CrewPerson(name=name, email=email))

    required = _merge_attendees(
        [_person_to_attendee(p, "required") for p in required_people if _person_to_attendee(p, "required")],
    )

    required_emails = {a.email.lower() for a in required}

    optional_people: list[CrewPerson] = list(apply_exclusions(draft.optional, exclude))
    for person in review_crew + release_crew:
        if person.email_lower() and person.email_lower() not in required_emails:
            optional_people.append(person)

    optional = _merge_attendees(
        [_person_to_attendee(p, "optional") for p in optional_people if _person_to_attendee(p, "optional")],
    )

    optional_emails = {a.email.lower() for a in optional}
    extra_optional = [
        a
        for a in _specs_to_attendees(cfg.optional_attendees, "optional")
        if a.email.lower() not in required_emails and a.email.lower() not in optional_emails
    ]

    return _merge_attendees(required, optional, extra_optional)


def _legacy_collect(cfg: AgentConfig, issues: list[dict]) -> list[TeamsAttendee]:
    """agent.yaml required + optional + squad-filtered assignees."""
    required = _specs_to_attendees(cfg.required_attendees, "required")
    optional = _specs_to_attendees(cfg.optional_attendees, "optional")
    seen = {a.email.lower() for a in required + optional}

    assignee_type = (
        cfg.assignee_invite_type if cfg.assignee_invite_type in {"required", "optional"} else "required"
    )
    for issue in issues:
        name, email = issue_assignee(issue)
        norm = email.strip().lower()
        if not norm or norm in seen:
            continue
        if not assignee_in_squad(name):
            continue
        seen.add(norm)
        required.append(TeamsAttendee(email=email, name=name, type=assignee_type))

    return _merge_attendees(required, optional)


def attendee_policy_summary(cfg: AgentConfig, issues: list[dict]) -> dict[str, Any]:
    """Explain who was required vs optional vs skipped (for MCP / dry-run)."""
    skipped_outside_squad: list[dict[str, str]] = []
    skipped_excluded: list[dict[str, str]] = []

    draft = load_crew_from_env() if load_crew_from_env else None
    for issue in issues:
        key = str(issue.get("key") or "")
        name, email = issue_assignee(issue)
        if not email.strip():
            continue
        if draft and email.strip().lower() in draft.exclude_emails:
            skipped_excluded.append({"key": key, "assignee": name, "email": email})
        elif not assignee_in_squad(name):
            skipped_outside_squad.append({"key": key, "assignee": name, "email": email})

    attendees = collect_crew_aware_attendees(cfg, issues)
    return {
        "source": "team_crew" if draft and draft.crew_configured() else "agent_yaml",
        "required": [a.email for a in attendees if a.type == "required"],
        "optional": [a.email for a in attendees if a.type == "optional"],
        "skipped_outside_squad": skipped_outside_squad,
        "skipped_excluded": skipped_excluded,
        "policy": {
            "required": "leadership + QA + in-squad ticket assignees",
            "optional": "TEAM_CREW_OPTIONAL + review/release standing crew",
            "excluded": "TEAM_CREW_EXCLUDE + outside squad assignees (e.g. Standard/AN-only)",
        },
    }


__all__ = ["collect_crew_aware_attendees", "attendee_policy_summary"]
