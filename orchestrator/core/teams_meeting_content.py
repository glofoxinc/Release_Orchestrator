"""Rich Teams meeting bodies and attendee helpers (review + deployment)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Any

import config
from release_gates import issue_assignee, issue_status_name
from teams_schedule import TeamsAttendee
from template_engine import render_template


@dataclass
class MeetingContext:
    """Release context used to auto-fill Teams invite subject/body/attendees."""

    version: str = ""
    kind: str = "review"  # review | deployment
    base_url: str = ""
    tickets: list[dict[str, Any]] = field(default_factory=list)
    grouped: dict[str, list[dict[str, Any]]] | None = None
    sharepoint_url: str = ""
    tckt_key: str = ""
    tckt_url: str = ""
    deploy_window: str = ""
    deploy_date: date | None = None
    blocked_tickets: list[dict[str, str]] = field(default_factory=list)
    team_name: str = ""


def _teams_root() -> dict[str, Any]:
    root = getattr(config, "TEAMS_SCHEDULE", {}) or {}
    return root if isinstance(root, dict) else {}


def load_attendee_groups() -> dict[str, list[TeamsAttendee]]:
    """Named attendee rosters from workspace (review_core, deployment_core, etc.)."""
    groups_raw = _teams_root().get("attendee_groups") or {}
    if not isinstance(groups_raw, dict):
        return {}
    out: dict[str, list[TeamsAttendee]] = {}
    for name, members in groups_raw.items():
        if not isinstance(members, list):
            continue
        people: list[TeamsAttendee] = []
        for item in members:
            if isinstance(item, str):
                people.append(TeamsAttendee(email=item.strip()))
            elif isinstance(item, dict):
                email = str(item.get("email") or "").strip()
                if email:
                    people.append(
                        TeamsAttendee(
                            email=email,
                            name=str(item.get("name") or "").strip(),
                            type=str(item.get("type") or "required").strip() or "required",
                        )
                    )
        if people:
            out[str(name)] = people
    return out


def attendees_for_groups(group_names: list[str]) -> list[TeamsAttendee]:
    """Merge attendees from named groups (template attendee_groups list)."""
    groups = load_attendee_groups()
    merged: list[TeamsAttendee] = []
    for name in group_names:
        merged = merge_attendees(merged, groups.get(name) or [])
    return merged


def template_attendee_groups(kind: str) -> list[str]:
    section = _template_section(kind)
    raw = section.get("attendee_groups") or []
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def collect_qa_pool_attendees() -> list[TeamsAttendee]:
    """Optional invites from release_notes.test_by_pool (names only — no emails)."""
    pool = getattr(config, "RELEASE_NOTES_TEST_BY_POOL", ()) or ()
    return [TeamsAttendee(email="", name=str(name), type="optional") for name in pool if name]


def collect_release_owner_attendee() -> list[TeamsAttendee]:
    owner = (getattr(config, "RELEASE_META", {}) or {}).get("release_owner") or ""
    name = str(owner).strip()
    if not name:
        return []
    return [TeamsAttendee(email="", name=name, type="optional")]


def _template_section(kind: str) -> dict[str, Any]:
    root = _teams_root()
    templates = root.get("templates") if isinstance(root, dict) else {}
    if not isinstance(templates, dict):
        return {}
    section = templates.get(kind) or {}
    return section if isinstance(section, dict) else {}


def _parse_hhmm(raw: str, *, fallback: time = time(15, 0)) -> time:
    text = (raw or "").strip()
    if not text:
        return fallback
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return fallback


def default_meeting_window(
    kind: str,
    *,
    deploy_date: date | None = None,
    deploy_start: datetime | None = None,
    deploy_end: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Compute default start/end from workspace templates + optional deploy window.

    Review defaults use ``default_day_offset`` days before ``deploy_date`` (or today).
    Deployment defaults prefer the TCKT deploy window when provided.
    """
    root = getattr(config, "TEAMS_SCHEDULE", {}) or {}
    section = _template_section(kind)
    review_min = int(root.get("review_duration_minutes") or 45)
    deploy_min = int(root.get("deployment_duration_minutes") or 60)
    duration = review_min if kind == "review" else deploy_min

    if kind == "deployment" and deploy_start and deploy_end and deploy_end > deploy_start:
        return deploy_start.replace(second=0, microsecond=0), deploy_end.replace(
            second=0, microsecond=0
        )

    anchor = deploy_date or date.today()
    day_offset = int(section.get("default_day_offset", -3 if kind == "review" else 0))
    default_time = _parse_hhmm(
        str(section.get("default_time") or ""),
        fallback=time(15, 0) if kind == "review" else time(10, 0),
    )
    start = datetime.combine(anchor + timedelta(days=day_offset), default_time)
    end = start + timedelta(minutes=max(15, duration))
    return start, end


def default_subject(kind: str, version: str, *, team_name: str = "") -> str:
    """Subject line from workspace template or sensible default."""
    tmpl = str(_template_section(kind).get("subject") or "").strip()
    team = team_name or config.WORKSPACE_NAME or "Customize BI"
    if tmpl:
        return tmpl.replace("{{version}}", version).replace("{{team_name}}", team)
    label = "Ticket Review" if kind == "review" else "Deployment"
    suffix = f" — {version}" if version else ""
    return f"{team} {label}{suffix}"


def _ticket_rows(tickets: list[dict[str, Any]], base_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for issue in tickets:
        key = str(issue.get("key") or "").strip()
        if not key:
            continue
        fields = issue.get("fields") or {}
        name, email = issue_assignee(issue)
        rows.append({
            "key": key,
            "summary": str(fields.get("summary") or "").strip(),
            "status": issue_status_name(issue),
            "assignee": name,
            "assignee_email": email,
            "url": f"{base_url.rstrip('/')}/browse/{key}",
        })
    return rows


def collect_assignee_attendees(tickets: list[dict[str, Any]]) -> list[TeamsAttendee]:
    """Unique assignee emails from Jira issues (for optional meeting invites)."""
    seen: set[str] = set()
    out: list[TeamsAttendee] = []
    for issue in tickets:
        name, email = issue_assignee(issue)
        email_norm = email.strip().lower()
        if not email_norm or email_norm in seen:
            continue
        seen.add(email_norm)
        out.append(TeamsAttendee(email=email, name=name, type="optional"))
    return out


def merge_attendees(*groups: list[TeamsAttendee]) -> list[TeamsAttendee]:
    """Merge attendee lists; first occurrence wins; required beats optional."""
    by_email: dict[str, TeamsAttendee] = {}
    for group in groups:
        for person in group:
            email = (person.email or "").strip().lower()
            if not email:
                continue
            existing = by_email.get(email)
            if existing is None:
                by_email[email] = person
                continue
            if existing.type != "required" and person.type == "required":
                by_email[email] = person
    return list(by_email.values())


def attendees_to_text(people: list[TeamsAttendee]) -> str:
    return ", ".join(p.email for p in people if p.email)


def parse_attendees_text(raw: str) -> list[TeamsAttendee]:
    return [
        TeamsAttendee(email=email.strip())
        for email in raw.replace("\n", ",").split(",")
        if email.strip()
    ]


def build_review_meeting_body(ctx: MeetingContext) -> str:
    """HTML body for ticket review call."""
    base_url = ctx.base_url or config.JIRA_BASE_URL
    tickets = ctx.tickets or []
    if ctx.grouped:
        tickets = [iss for group in ctx.grouped.values() for iss in group]
    try:
        return render_template(
            "meetings/review_body.html.j2",
            version=ctx.version,
            team_name=ctx.team_name or config.WORKSPACE_NAME,
            base_url=base_url.rstrip("/"),
            tickets=_ticket_rows(tickets, base_url),
            blocked=ctx.blocked_tickets,
            ticket_count=len(tickets),
        ).strip()
    except Exception:  # noqa: BLE001
        return _fallback_review_body(ctx, tickets, base_url)


def build_deployment_meeting_body(ctx: MeetingContext) -> str:
    """HTML body for deployment call."""
    base_url = ctx.base_url or config.JIRA_BASE_URL
    tickets = ctx.tickets or []
    try:
        return render_template(
            "meetings/deployment_body.html.j2",
            version=ctx.version,
            team_name=ctx.team_name or config.WORKSPACE_NAME,
            base_url=base_url.rstrip("/"),
            sharepoint_url=ctx.sharepoint_url,
            tckt_key=ctx.tckt_key,
            tckt_url=ctx.tckt_url,
            deploy_window=ctx.deploy_window,
            tickets=_ticket_rows(tickets, base_url),
            ticket_count=len(tickets),
        ).strip()
    except Exception:  # noqa: BLE001
        return _fallback_deployment_body(ctx, tickets)


def build_meeting_body(ctx: MeetingContext) -> str:
    if ctx.kind == "deployment":
        return build_deployment_meeting_body(ctx)
    return build_review_meeting_body(ctx)


def _fallback_review_body(
    ctx: MeetingContext,
    tickets: list[dict[str, Any]],
    base_url: str,
) -> str:
    lines = [
        f"<p><strong>Release:</strong> {escape(ctx.version)}</p>",
        f"<p><strong>Tickets for review ({len(tickets)}):</strong></p>",
        "<ul>",
    ]
    for row in _ticket_rows(tickets, base_url):
        lines.append(
            f"<li><a href=\"{escape(row['url'])}\">{escape(row['key'])}</a> — "
            f"{escape(row['summary'])} ({escape(row['status'])}) — {escape(row['assignee'])}</li>"
        )
    lines.append("</ul>")
    if ctx.blocked_tickets:
        lines.append("<p><strong>Gate blockers:</strong></p><ul>")
        for item in ctx.blocked_tickets:
            lines.append(
                f"<li>{escape(item.get('key', ''))}: {escape(item.get('reason', ''))}</li>"
            )
        lines.append("</ul>")
    return "\n".join(lines)


def _fallback_deployment_body(ctx: MeetingContext, tickets: list[dict[str, Any]]) -> str:
    parts = [f"<p><strong>Release:</strong> {escape(ctx.version)}</p>"]
    if ctx.deploy_window:
        parts.append(f"<p><strong>Deployment window:</strong> {escape(ctx.deploy_window)}</p>")
    if ctx.sharepoint_url:
        parts.append(
            f"<p><strong>Release notes:</strong> "
            f"<a href=\"{escape(ctx.sharepoint_url)}\">{escape(ctx.sharepoint_url)}</a></p>"
        )
    if ctx.tckt_key:
        link = ctx.tckt_url or f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{ctx.tckt_key}"
        parts.append(
            f"<p><strong>Change ticket:</strong> "
            f"<a href=\"{escape(link)}\">{escape(ctx.tckt_key)}</a></p>"
        )
    parts.append(f"<p><strong>Tickets deploying:</strong> {len(tickets)}</p>")
    return "\n".join(parts)


__all__ = [
    "MeetingContext",
    "attendees_for_groups",
    "build_deployment_meeting_body",
    "build_meeting_body",
    "build_review_meeting_body",
    "collect_assignee_attendees",
    "collect_qa_pool_attendees",
    "collect_release_owner_attendee",
    "default_meeting_window",
    "default_subject",
    "load_attendee_groups",
    "merge_attendees",
    "parse_attendees_text",
    "attendees_to_text",
    "template_attendee_groups",
]
