"""Team + project defaults and review/release crew — one-time .env onboarding."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from orchestrator.paths import REPO_ROOT, TEMPLATES_DIR

_CREW_YAML = TEMPLATES_DIR / "default" / "onboarding" / "team_crew.yaml"
_APP_DIR = REPO_ROOT
_CREW_ENV_KEYS = frozenset({
    "DEFAULT_JIRA_TEAM",
    "DEFAULT_PROJECTS",
    "DEFAULT_JIRA_TEAM_ID",
    "TEAM_CREW_SQUAD",
    "TEAM_CREW_REVIEW",
    "TEAM_CREW_RELEASE",
    "TEAM_CREW_QA",
    "TEAM_CREW_LEADERSHIP",
    "TEAM_CREW_OPTIONAL",
    "TEAM_CREW_EXCLUDE",
})

_EMAIL_IN_ANGLE = re.compile(r"<([^>]+@[^>]+)>")


@dataclass(frozen=True)
class CrewPerson:
    name: str
    email: str = ""

    def display(self) -> str:
        if self.email:
            return f"{self.name} <{self.email}>"
        return self.name

    def email_lower(self) -> str:
        return self.email.strip().lower()


@dataclass
class TeamCrewProfile:
    key: str
    display_name: str
    jira_team_id: str
    default_projects: list[str]
    description: str
    squad: list[CrewPerson] = field(default_factory=list)
    review: list[CrewPerson] = field(default_factory=list)
    release: list[CrewPerson] = field(default_factory=list)
    qa: list[CrewPerson] = field(default_factory=list)
    leadership: list[CrewPerson] = field(default_factory=list)
    optional: list[CrewPerson] = field(default_factory=list)
    exclude: list[CrewPerson] = field(default_factory=list)
    setup_note: str = ""
    sharepoint: dict[str, Any] = field(default_factory=dict)


def _load_yaml() -> dict[str, Any]:
    if not _CREW_YAML.is_file():
        return {}
    with _CREW_YAML.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _people(raw: Any) -> list[CrewPerson]:
    out: list[CrewPerson] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            email = str(item.get("email") or "").strip()
            if name or email:
                out.append(CrewPerson(name=name or email, email=email))
        elif isinstance(item, str) and item.strip():
            out.append(CrewPerson(name=item.strip()))
    return out


def team_profile_keys() -> list[str]:
    teams = _load_yaml().get("teams") or {}
    return list(teams.keys()) if isinstance(teams, dict) else []


def load_team_profile(key: str) -> TeamCrewProfile | None:
    teams = _load_yaml().get("teams") or {}
    if not isinstance(teams, dict):
        return None
    raw = teams.get(str(key).lower().strip())
    if not isinstance(raw, dict):
        return None
    return TeamCrewProfile(
        key=str(key).lower().strip(),
        display_name=str(raw.get("display_name") or key),
        jira_team_id=str(raw.get("jira_team_id") or ""),
        default_projects=[str(p).upper() for p in (raw.get("default_projects") or []) if str(p).strip()],
        description=str(raw.get("description") or ""),
        squad=_people(raw.get("squad")),
        review=_people(raw.get("review")),
        release=_people(raw.get("release")),
        qa=_people(raw.get("qa")),
        leadership=_people(raw.get("leadership")),
        optional=_people(raw.get("optional")),
        exclude=_people(raw.get("exclude")),
        setup_note=str(raw.get("setup_note") or ""),
        sharepoint=dict(raw.get("sharepoint") or {}) if isinstance(raw.get("sharepoint"), dict) else {},
    )


def resolve_team_key_from_phrase(text: str) -> str | None:
    lowered = (text or "").lower()
    if "glofox" in lowered:
        return "glofox"
    if "ignite" in lowered:
        return "ignite"
    if "etl" in lowered:
        return "etl"
    if "other" in lowered or "custom team" in lowered:
        return "other"
    return None


def parse_projects_phrase(text: str) -> list[str] | None:
    lowered = (text or "").lower()
    if re.search(r"\bpic-\d+\b", lowered):
        return None
    if "pic" in lowered and "an" in lowered:
        return ["PIC", "AN"]
    if re.search(r"\bpic\b", lowered) and "an" not in lowered:
        return ["PIC"]
    if re.search(r"\ban\b", lowered) and "pic" not in lowered:
        return ["AN"]
    return None


def parse_crew_person(text: str) -> CrewPerson | None:
    raw = (text or "").strip()
    if not raw:
        return None
    match = _EMAIL_IN_ANGLE.search(raw)
    if match:
        email = match.group(1).strip()
        name = raw[: match.start()].strip(" ,") or email
        return CrewPerson(name=name, email=email)
    if "@" in raw:
        return CrewPerson(name=raw, email=raw)
    return CrewPerson(name=raw)


def apply_exclusions(people: list[CrewPerson], exclude_emails: set[str]) -> list[CrewPerson]:
    if not exclude_emails:
        return list(people)
    return [p for p in people if p.email_lower() not in exclude_emails]


def merge_people(*groups: list[CrewPerson]) -> list[CrewPerson]:
    seen: set[str] = set()
    out: list[CrewPerson] = []
    for group in groups:
        for person in group:
            key = person.email_lower() or person.name.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(person)
    return out


def format_people_env(people: list[CrewPerson]) -> str:
    return "; ".join(p.display() for p in people if p.display())


def format_names_env(people: list[CrewPerson]) -> str:
    return ", ".join(p.name for p in people if p.name)


@dataclass
class TeamCrewDraft:
    team_key: str = ""
    team_name: str = ""
    jira_team_id: str = ""
    projects: list[str] = field(default_factory=list)
    squad: list[CrewPerson] = field(default_factory=list)
    review: list[CrewPerson] = field(default_factory=list)
    release: list[CrewPerson] = field(default_factory=list)
    qa: list[CrewPerson] = field(default_factory=list)
    leadership: list[CrewPerson] = field(default_factory=list)
    optional: list[CrewPerson] = field(default_factory=list)
    exclude_emails: set[str] = field(default_factory=set)
    custom_team_name: str = ""

    def is_complete(self) -> bool:
        return bool(self.team_key and self.projects and self.team_name)

    def crew_configured(self) -> bool:
        """True when review-call policy is usable (leadership + QA, or legacy review/release lists)."""
        if self.leadership and self.qa:
            return True
        return bool(self.review or self.release)


def draft_from_profile(key: str) -> TeamCrewDraft | None:
    profile = load_team_profile(key)
    if profile is None:
        return None
    draft = TeamCrewDraft(
        team_key=profile.key,
        team_name=profile.display_name,
        jira_team_id=profile.jira_team_id,
        projects=list(profile.default_projects),
        squad=list(profile.squad),
        review=list(profile.review),
        release=list(profile.release),
        qa=list(profile.qa),
        leadership=list(profile.leadership),
        optional=list(profile.optional),
    )
    for person in profile.exclude:
        if person.email_lower():
            draft.exclude_emails.add(person.email_lower())
    return draft


def load_crew_from_env() -> TeamCrewDraft | None:
    team = os.getenv("DEFAULT_JIRA_TEAM", "").strip()
    if not team:
        return None
    projects_raw = os.getenv("DEFAULT_PROJECTS", "")
    projects = [p.strip().upper() for p in projects_raw.split(",") if p.strip()]
    draft = TeamCrewDraft(
        team_key=resolve_team_key_from_phrase(team) or "other",
        team_name=team,
        jira_team_id=os.getenv("DEFAULT_JIRA_TEAM_ID", "").strip(),
        projects=projects,
        squad=_parse_people_env(os.getenv("TEAM_CREW_SQUAD", "")),
        review=_parse_people_env(os.getenv("TEAM_CREW_REVIEW", "")),
        release=_parse_people_env(os.getenv("TEAM_CREW_RELEASE", "")),
        qa=_parse_people_env(os.getenv("TEAM_CREW_QA", "")),
        leadership=_parse_people_env(os.getenv("TEAM_CREW_LEADERSHIP", "")),
        optional=_parse_people_env(os.getenv("TEAM_CREW_OPTIONAL", "")),
    )
    ex = os.getenv("TEAM_CREW_EXCLUDE", "")
    draft.exclude_emails = {e.strip().lower() for e in ex.split(",") if e.strip() and "@" in e}
    return draft


def _parse_people_env(raw: str) -> list[CrewPerson]:
    people: list[CrewPerson] = []
    for chunk in re.split(r"[;\n]", raw or ""):
        person = parse_crew_person(chunk.strip())
        if person:
            people.append(person)
    if not people and raw and "," in raw and "@" not in raw:
        for name in raw.split(","):
            name = name.strip()
            if name:
                people.append(CrewPerson(name=name))
    return people


def apply_crew_to_env(draft: TeamCrewDraft, env_path: Path | None = None) -> dict[str, Any]:
    """Merge team crew variables into `.env` (keeps Jira credentials untouched)."""
    target = env_path or (_APP_DIR / ".env")
    snippet = build_env_snippet(draft)
    new_vars: dict[str, str] = {}
    for line in snippet.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        new_vars[key.strip()] = value

    preserved: list[str] = []
    if target.is_file():
        for line in target.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in _CREW_ENV_KEYS:
                continue
            preserved.append(line.rstrip())

    while preserved and not preserved[-1].strip():
        preserved.pop()

    merged = preserved + ["", *snippet.splitlines(), ""]
    target.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
    return {"ok": True, "path": str(target), "keys_written": sorted(new_vars.keys())}


def lock_crew_from_profile(team_key: str, env_path: Path | None = None) -> dict[str, Any]:
    """Load a prefilled team profile and write crew block to `.env`."""
    draft = draft_from_profile(team_key)
    if draft is None or not draft.crew_configured():
        return {"ok": False, "error": f"Team profile '{team_key}' is not ready to lock."}
    result = apply_crew_to_env(draft, env_path=env_path)
    result["team_key"] = team_key
    result["team_name"] = draft.team_name
    return result


def build_env_snippet(draft: TeamCrewDraft) -> str:
    """Lines to paste into .env after onboarding crew confirmation."""
    env_map = (_load_yaml().get("env_vars") or {}) if isinstance(_load_yaml().get("env_vars"), dict) else {}
    team_var = str(env_map.get("team") or "DEFAULT_JIRA_TEAM")
    projects_var = str(env_map.get("projects") or "DEFAULT_PROJECTS")
    team_id_var = str(env_map.get("team_id") or "DEFAULT_JIRA_TEAM_ID")
    squad_var = str(env_map.get("squad") or "TEAM_CREW_SQUAD")
    review_var = str(env_map.get("review") or "TEAM_CREW_REVIEW")
    release_var = str(env_map.get("release") or "TEAM_CREW_RELEASE")
    qa_var = str(env_map.get("qa") or "TEAM_CREW_QA")
    leadership_var = str(env_map.get("leadership") or "TEAM_CREW_LEADERSHIP")
    optional_var = str(env_map.get("optional") or "TEAM_CREW_OPTIONAL")
    exclude_var = str(env_map.get("exclude") or "TEAM_CREW_EXCLUDE")

    review = apply_exclusions(draft.review, draft.exclude_emails)
    release = apply_exclusions(draft.release, draft.exclude_emails)
    leadership = apply_exclusions(draft.leadership, draft.exclude_emails)
    squad = apply_exclusions(draft.squad, draft.exclude_emails)
    optional = apply_exclusions(draft.optional, draft.exclude_emails)

    lines = [
        f"# --- Team one-time setup ({draft.team_name}) ---",
        f"{team_var}={draft.team_name}",
        f"{projects_var}={','.join(draft.projects)}",
    ]
    if draft.jira_team_id:
        lines.append(f"{team_id_var}={draft.jira_team_id}")
    if squad:
        lines.append(f"{squad_var}={format_people_env(squad) if any(p.email for p in squad) else format_names_env(squad)}")
    lines.append(f"{review_var}={format_people_env(review)}")
    lines.append(f"{release_var}={format_people_env(release)}")
    qa_people = apply_exclusions(draft.qa, draft.exclude_emails)
    lines.append(
        f"{qa_var}={format_people_env(qa_people) if any(p.email for p in qa_people) else format_names_env(qa_people)}"
    )
    lines.append(
        f"{leadership_var}={format_people_env(leadership) if any(p.email for p in leadership) else format_names_env(leadership)}"
    )
    if optional:
        lines.append(f"{optional_var}={format_people_env(optional) if any(p.email for p in optional) else format_names_env(optional)}")
    if draft.exclude_emails:
        lines.append(f"{exclude_var}={','.join(sorted(draft.exclude_emails))}")
    else:
        lines.append(f"# {exclude_var}=")
    return "\n".join(lines)


def crew_summary_text(draft: TeamCrewDraft) -> str:
    squad = apply_exclusions(draft.squad, draft.exclude_emails)
    optional = apply_exclusions(draft.optional, draft.exclude_emails)
    squad_names = format_names_env(squad) or "*(from Jira assignees at fetch)*"
    lines = [
        f"**{draft.team_name}** · projects **{', '.join(draft.projects) or '?'}**",
        "",
        f"- **Squad:** {squad_names} *(emails from Jira when tickets are fetched)*",
        f"- **Leadership:** {format_names_env(draft.leadership) or '—'}",
        f"- **QA:** {format_names_env(draft.qa) or '—'}",
        f"- **Optional:** {format_names_env(optional) or '—'}",
    ]
    if draft.exclude_emails:
        lines.append(f"- **Exclude:** {', '.join(sorted(draft.exclude_emails))}")
    return "\n".join(lines)


def squad_roster_tokens() -> tuple[str, ...]:
    """Name tokens for in-squad assignee matching — prefers TEAM_CREW_SQUAD from .env."""
    draft = load_crew_from_env()
    if draft and draft.squad:
        tokens: list[str] = []
        for person in draft.squad:
            if person.name:
                tokens.append(person.name)
            if person.email:
                tokens.append(person.email.split("@", 1)[0])
        return tuple(dict.fromkeys(t for t in tokens if t))
    return ()


def onboarding_checklist() -> list[dict[str, str]]:
    """Standard crew questions for Ignite / ETL / other teams."""
    raw = _load_yaml().get("onboarding_checklist") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(
                {
                    "id": str(item.get("id") or ""),
                    "label": str(item.get("label") or ""),
                    "detail": str(item.get("detail") or ""),
                }
            )
    return out


def _people_with_email(*groups: list[CrewPerson]) -> list[CrewPerson]:
    """Merge groups; keep only people with an email (required for Teams invites)."""
    out: list[CrewPerson] = []
    seen: set[str] = set()
    for group in groups:
        for person in apply_exclusions(group, set()):
            email = person.email_lower()
            if not email or email in seen:
                continue
            seen.add(email)
            out.append(person)
    return out


def crew_to_teams_attendees(kind: str) -> list[Any]:
    """Build Teams attendee list from `.env` crew for review or deployment calls."""
    draft = load_crew_from_env()
    if draft is None:
        return []
    from teams_schedule import TeamsAttendee

    exclude = draft.exclude_emails
    kind_norm = (kind or "review").strip().lower()
    if kind_norm == "deployment":
        people = _people_with_email(
            apply_exclusions(draft.release, exclude),
            apply_exclusions(draft.leadership, exclude),
        )
    else:
        people = _people_with_email(
            apply_exclusions(draft.review, exclude),
            apply_exclusions(draft.leadership, exclude),
            apply_exclusions(draft.qa, exclude),
        )
    return [
        TeamsAttendee(email=p.email, name=p.name, type="required")
        for p in people
        if p.email
    ]


def team_crew_status() -> dict[str, Any]:
    draft = load_crew_from_env()
    profiles = {key: load_team_profile(key) for key in team_profile_keys()}
    review_attendees = crew_to_teams_attendees("review") if draft else []
    deployment_attendees = crew_to_teams_attendees("deployment") if draft else []
    return {
        "configured": draft is not None and draft.is_complete(),
        "crew_in_env": draft is not None and draft.crew_configured(),
        "draft": (
            {
                "team_name": draft.team_name,
                "projects": draft.projects,
                "review_count": len(draft.review),
                "release_count": len(draft.release),
                "qa_count": len(draft.qa),
                "leadership_count": len(draft.leadership),
            }
            if draft
            else None
        ),
        "teams_meeting_attendees": {
            "review": [
                {"email": a.email, "name": a.name} for a in review_attendees
            ],
            "deployment": [
                {"email": a.email, "name": a.name} for a in deployment_attendees
            ],
        },
        "available_teams": [
            {
                "key": key,
                "display_name": (profiles[key].display_name if profiles.get(key) else key),
                "default_projects": (profiles[key].default_projects if profiles.get(key) else []),
                "prefilled_crew": key == "glofox",
            }
            for key in team_profile_keys()
        ],
        "onboard_phrases": [
            "use glofox", "use ignite", "team etl", "projects pic an",
            "crew add Name <email@x.com> to review", "crew exclude email@x.com", "crew done",
        ],
        "daily_review_invite_policy": {
            "required": "TEAM_CREW_LEADERSHIP + TEAM_CREW_QA + in-squad ticket assignees",
            "optional": "TEAM_CREW_OPTIONAL + TEAM_CREW_REVIEW + TEAM_CREW_RELEASE",
            "excluded": "TEAM_CREW_EXCLUDE + outside-squad assignees (e.g. Standard/AN-only)",
            "squad_roster": "TEAM_CREW_SQUAD — defines in-squad assignee matching",
            "ticket_fetch": "Outside-squad tickets not fetched unless ticket_scope.include_outside_squad_assignees: true",
            "preview_tool": "daily_review_attendee_policy",
        },
        "onboarding_checklist": onboarding_checklist(),
    }


__all__ = [
    "CrewPerson",
    "TeamCrewDraft",
    "TeamCrewProfile",
    "apply_exclusions",
    "build_env_snippet",
    "crew_summary_text",
    "crew_to_teams_attendees",
    "draft_from_profile",
    "format_people_env",
    "load_crew_from_env",
    "load_team_profile",
    "onboarding_checklist",
    "parse_crew_person",
    "parse_projects_phrase",
    "resolve_team_key_from_phrase",
    "apply_crew_to_env",
    "lock_crew_from_profile",
    "squad_roster_tokens",
    "team_crew_status",
    "team_profile_keys",
]
