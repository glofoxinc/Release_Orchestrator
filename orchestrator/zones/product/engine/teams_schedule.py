"""Teams meeting scheduling via Microsoft Graph (review + deployment).

Credentials stay in env (``MS_GRAPH_*``); defaults (organizer, attendees,
durations) live in ``workspace.yaml`` under ``teams_schedule``.

Creates calendar events with ``isOnlineMeeting=true`` so attendees get a
Teams join link. Preview (dry-run) works without credentials; live schedule
needs MS_GRAPH_* + ``Calendars.ReadWrite`` on the organizer mailbox.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from ms_graph import GraphClient

logger = logging.getLogger(__name__)

MeetingKind = Literal["review", "deployment"]


def _uses_delegated_graph_token() -> bool:
    return bool((os.environ.get("MS_GRAPH_ACCESS_TOKEN") or "").strip())


def _events_collection_path(cfg: "TeamsScheduleConfig") -> str:
    if _uses_delegated_graph_token():
        return "/me/events"
    return f"/users/{quote_upn(cfg.organizer_upn)}/events"


@dataclass
class TeamsAttendee:
    email: str
    name: str = ""
    type: str = "required"  # required | optional | resource

    def to_graph(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "emailAddress": {"address": self.email},
            "type": self.type or "required",
        }
        if self.name:
            payload["emailAddress"]["name"] = self.name
        return payload


@dataclass
class TeamsScheduleConfig:
    enabled: bool = False
    organizer_upn: str = ""  # user principal name / email that owns the calendar
    default_timezone: str = "Asia/Kolkata"
    review_duration_minutes: int = 45
    deployment_duration_minutes: int = 60
    default_attendees: list[TeamsAttendee] = field(default_factory=list)
    review_attendees: list[TeamsAttendee] = field(default_factory=list)
    deployment_attendees: list[TeamsAttendee] = field(default_factory=list)
    graph: GraphClient = field(default_factory=GraphClient)

    def can_schedule(self) -> bool:
        return self.enabled and self.graph.configured() and bool(self.organizer_upn)

    def attendees_for_kind(self, kind: MeetingKind) -> list[TeamsAttendee]:
        if kind == "review" and self.review_attendees:
            return list(self.review_attendees)
        if kind == "deployment" and self.deployment_attendees:
            return list(self.deployment_attendees)
        if self.default_attendees:
            return list(self.default_attendees)
        try:
            import team_crew as tc

            from_env = tc.crew_to_teams_attendees(kind)
            if from_env:
                return list(from_env)
        except Exception:  # noqa: BLE001
            pass
        return []


@dataclass
class MeetingDraft:
    kind: MeetingKind
    subject: str
    start: datetime
    end: datetime
    timezone: str
    attendees: list[TeamsAttendee] = field(default_factory=list)
    body: str = ""
    location: str = "Microsoft Teams Meeting"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "timezone": self.timezone,
            "attendees": [
                {"email": a.email, "name": a.name, "type": a.type} for a in self.attendees
            ],
            "body": self.body,
            "location": self.location,
        }


@dataclass
class ScheduleResult:
    ok: bool
    dry_run: bool = False
    updated: bool = False
    event_id: str = ""
    join_url: str = ""
    web_link: str = ""
    error: str = ""
    draft: MeetingDraft | None = None
    graph_payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "updated": self.updated,
            "event_id": self.event_id,
            "join_url": self.join_url,
            "web_link": self.web_link,
            "error": self.error,
            "draft": self.draft.to_dict() if self.draft else None,
            "graph_payload": self.graph_payload,
        }


def _parse_attendees(raw: Any) -> list[TeamsAttendee]:
    out: list[TeamsAttendee] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            email = item.strip()
            if email:
                out.append(TeamsAttendee(email=email))
            continue
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or item.get("address") or "").strip()
        if not email:
            continue
        out.append(
            TeamsAttendee(
                email=email,
                name=str(item.get("name") or "").strip(),
                type=str(item.get("type") or "required").strip() or "required",
            )
        )
    return out


def load_schedule_config(
    workspace_section: dict[str, Any] | None = None,
    *,
    graph: GraphClient | None = None,
) -> TeamsScheduleConfig:
    section = dict(workspace_section or {})
    return TeamsScheduleConfig(
        enabled=bool(section.get("enabled", False)),
        organizer_upn=str(section.get("organizer_upn") or section.get("organizer") or "").strip(),
        default_timezone=str(section.get("default_timezone") or "Asia/Kolkata").strip()
        or "Asia/Kolkata",
        review_duration_minutes=int(section.get("review_duration_minutes") or 45),
        deployment_duration_minutes=int(section.get("deployment_duration_minutes") or 60),
        default_attendees=_parse_attendees(section.get("default_attendees") or []),
        review_attendees=_parse_attendees(section.get("review_attendees") or []),
        deployment_attendees=_parse_attendees(section.get("deployment_attendees") or []),
        graph=graph or GraphClient(),
    )


def readiness_steps(cfg: TeamsScheduleConfig) -> list[dict[str, Any]]:
    """Ordered checklist for E2E Teams setup (UI + verify script)."""
    graph_st = cfg.graph.status()
    missing = graph_st.get("missing") or []
    steps: list[dict[str, Any]] = [
        {
            "id": "organizer_upn",
            "label": "Organizer mailbox",
            "ok": bool(cfg.organizer_upn),
            "detail": cfg.organizer_upn or "Set teams_schedule.organizer_upn in workspace.yaml",
            "fix": "Settings → Integrations → Organizer email, or edit workspace.yaml.",
        },
        {
            "id": "graph_credentials",
            "label": "Microsoft Graph credentials",
            "ok": graph_st.get("configured") is True,
            "detail": "Configured" if graph_st.get("configured") else "Missing: " + ", ".join(missing),
            "fix": "Add MS_GRAPH_TENANT_ID, MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET to .env.",
        },
        {
            "id": "feature_enabled",
            "label": "Teams scheduling enabled",
            "ok": cfg.enabled,
            "detail": "enabled=true in workspace.yaml" if cfg.enabled else "teams_schedule.enabled is false",
            "fix": "Settings → Integrations → Enable Teams scheduling.",
        },
        {
            "id": "attendees",
            "label": "Default attendees",
            "ok": bool(cfg.default_attendees),
            "detail": f"{len(cfg.default_attendees)} attendee(s) configured",
            "fix": "Add default_attendees in workspace.yaml (Settings → Integrations).",
        },
        {
            "id": "live_ready",
            "label": "Live schedule ready",
            "ok": cfg.can_schedule(),
            "detail": "Preview + Schedule in Teams buttons will work live"
            if cfg.can_schedule()
            else "Complete the steps above, then test with Preview → Schedule in Teams.",
            "fix": "",
        },
    ]
    return steps


def _as_aware(dt: datetime, tz_name: str) -> datetime:
    if dt.tzinfo is not None:
        return dt
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return dt.replace(tzinfo=tz)


def build_meeting_draft(
    cfg: TeamsScheduleConfig,
    *,
    kind: MeetingKind,
    subject: str,
    start: datetime,
    end: datetime | None = None,
    timezone_name: str | None = None,
    attendees: list[TeamsAttendee] | None = None,
    body: str = "",
    version: str = "",
    location: str = "",
) -> MeetingDraft:
    tz_name = (timezone_name or cfg.default_timezone or "Asia/Kolkata").strip()
    start_aware = _as_aware(start, tz_name)
    if end is None:
        minutes = (
            cfg.review_duration_minutes
            if kind == "review"
            else cfg.deployment_duration_minutes
        )
        end_aware = start_aware + timedelta(minutes=max(15, int(minutes)))
    else:
        end_aware = _as_aware(end, tz_name)

    label = "Ticket Review" if kind == "review" else "Deployment"
    subj = (subject or "").strip()
    if not subj:
        bit = f" — {version}" if version else ""
        subj = f"Customize BI {label}{bit}"

    people = list(attendees) if attendees is not None else cfg.attendees_for_kind(kind)
    body_text = (body or "").strip()
    if not body_text:
        body_text = (
            f"Scheduled via Release Orchestrator ({label})."
            + (f" Release: {version}." if version else "")
        )

    loc = (location or "").strip() or "Microsoft Teams Meeting"
    return MeetingDraft(
        kind=kind,
        subject=subj,
        start=start_aware,
        end=end_aware,
        timezone=tz_name,
        attendees=people,
        body=body_text,
        location=loc,
    )


def build_graph_event_payload(draft: MeetingDraft) -> dict[str, Any]:
    """Calendar event payload with Teams online meeting enabled."""
    start_local = draft.start.strftime("%Y-%m-%dT%H:%M:%S")
    end_local = draft.end.strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "subject": draft.subject,
        "body": {
            "contentType": "HTML",
            "content": draft.body.replace("\n", "<br/>"),
        },
        "start": {"dateTime": start_local, "timeZone": draft.timezone},
        "end": {"dateTime": end_local, "timeZone": draft.timezone},
        "location": {"displayName": draft.location},
        "attendees": [a.to_graph() for a in draft.attendees],
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
    }


def status(cfg: TeamsScheduleConfig) -> dict[str, Any]:
    steps = readiness_steps(cfg)
    pending = [s for s in steps if not s.get("ok")]
    return {
        "feature": "teams_schedule",
        "enabled": cfg.enabled,
        "can_schedule": cfg.can_schedule(),
        "organizer_upn": cfg.organizer_upn,
        "organizer_upn_set": bool(cfg.organizer_upn),
        "default_timezone": cfg.default_timezone,
        "review_duration_minutes": cfg.review_duration_minutes,
        "deployment_duration_minutes": cfg.deployment_duration_minutes,
        "default_attendee_count": len(cfg.default_attendees),
        "review_attendee_count": len(cfg.review_attendees),
        "deployment_attendee_count": len(cfg.deployment_attendees),
        "graph": cfg.graph.status(),
        "readiness_steps": steps,
        "pending_step_count": len(pending),
        "note": (
            "Ticket Review + Service Ticket — add MS_GRAPH_* to .env for live scheduling. "
            "Run: python orchestrator/zones/platform/ops/test_teams_schedule.py --dry-run"
        ),
    }


def schedule_meeting(
    cfg: TeamsScheduleConfig,
    draft: MeetingDraft,
    *,
    dry_run: bool = True,
) -> ScheduleResult:
    """Create a Teams online meeting on the organizer's calendar.

    Default ``dry_run=True`` returns the Graph payload without calling Graph.
    """
    payload = build_graph_event_payload(draft)
    if dry_run or not cfg.enabled:
        reason = "" if cfg.enabled else "teams_schedule.enabled is false"
        return ScheduleResult(
            ok=True,
            dry_run=True,
            draft=draft,
            graph_payload=payload,
            error=reason,
        )

    if not cfg.graph.configured():
        return ScheduleResult(
            ok=False,
            dry_run=False,
            draft=draft,
            graph_payload=payload,
            error="Microsoft Graph credentials are not configured (MS_GRAPH_*).",
        )
    if not cfg.organizer_upn:
        return ScheduleResult(
            ok=False,
            dry_run=False,
            draft=draft,
            graph_payload=payload,
            error="teams_schedule.organizer_upn is required in workspace.yaml.",
        )

    try:
        status_code, body = cfg.graph.request(
            "POST",
            _events_collection_path(cfg),
            json_body=payload,
        )
    except Exception as exc:
        logger.exception("Teams schedule failed")
        return ScheduleResult(
            ok=False,
            dry_run=False,
            draft=draft,
            graph_payload=payload,
            error=str(exc),
        )

    if status_code >= 400 or not isinstance(body, dict):
        return ScheduleResult(
            ok=False,
            dry_run=False,
            draft=draft,
            graph_payload=payload,
            error=f"Teams schedule failed (HTTP {status_code}): {body}",
        )

    online = body.get("onlineMeeting") if isinstance(body.get("onlineMeeting"), dict) else {}
    join_url = str(
        (online or {}).get("joinUrl")
        or body.get("onlineMeetingUrl")
        or ""
    ).strip()
    return ScheduleResult(
        ok=True,
        dry_run=False,
        draft=draft,
        graph_payload=payload,
        event_id=str(body.get("id") or ""),
        join_url=join_url,
        web_link=str(body.get("webLink") or ""),
    )


def update_meeting(
    cfg: TeamsScheduleConfig,
    event_id: str,
    draft: MeetingDraft,
    *,
    dry_run: bool = True,
) -> ScheduleResult:
    """Update an existing calendar event (reschedule subject/body/attendees/time)."""
    event_id = (event_id or "").strip()
    if not event_id:
        return ScheduleResult(
            ok=False,
            dry_run=dry_run,
            draft=draft,
            error="event_id is required to update a Teams meeting.",
        )

    payload = build_graph_event_payload(draft)
    if dry_run or not cfg.enabled:
        reason = "" if cfg.enabled else "teams_schedule.enabled is false"
        return ScheduleResult(
            ok=True,
            dry_run=True,
            updated=True,
            event_id=event_id,
            draft=draft,
            graph_payload=payload,
            error=reason,
        )

    if not cfg.graph.configured():
        return ScheduleResult(
            ok=False,
            dry_run=False,
            updated=True,
            event_id=event_id,
            draft=draft,
            graph_payload=payload,
            error="Microsoft Graph credentials are not configured (MS_GRAPH_*).",
        )
    if not cfg.organizer_upn:
        return ScheduleResult(
            ok=False,
            dry_run=False,
            updated=True,
            event_id=event_id,
            draft=draft,
            graph_payload=payload,
            error="teams_schedule.organizer_upn is required in workspace.yaml.",
        )

    try:
        status_code, body = cfg.graph.request(
            "PATCH",
            f"{_events_collection_path(cfg)}/{event_id}",
            json_body=payload,
        )
    except Exception as exc:
        logger.exception("Teams update failed")
        return ScheduleResult(
            ok=False,
            dry_run=False,
            updated=True,
            event_id=event_id,
            draft=draft,
            graph_payload=payload,
            error=str(exc),
        )

    if status_code >= 400 or not isinstance(body, dict):
        return ScheduleResult(
            ok=False,
            dry_run=False,
            updated=True,
            event_id=event_id,
            draft=draft,
            graph_payload=payload,
            error=f"Teams update failed (HTTP {status_code}): {body}",
        )

    online = body.get("onlineMeeting") if isinstance(body.get("onlineMeeting"), dict) else {}
    join_url = str(
        (online or {}).get("joinUrl")
        or body.get("onlineMeetingUrl")
        or ""
    ).strip()
    return ScheduleResult(
        ok=True,
        dry_run=False,
        updated=True,
        draft=draft,
        graph_payload=payload,
        event_id=str(body.get("id") or event_id),
        join_url=join_url,
        web_link=str(body.get("webLink") or ""),
    )


def cancel_meeting(
    cfg: TeamsScheduleConfig,
    event_id: str,
    *,
    dry_run: bool = True,
) -> ScheduleResult:
    """Cancel/delete a scheduled Teams calendar event."""
    event_id = (event_id or "").strip()
    if not event_id:
        return ScheduleResult(
            ok=False,
            dry_run=dry_run,
            error="event_id is required to cancel a Teams meeting.",
        )

    if dry_run or not cfg.enabled:
        return ScheduleResult(
            ok=True,
            dry_run=True,
            updated=True,
            event_id=event_id,
            error="" if cfg.enabled else "teams_schedule.enabled is false",
        )

    if not cfg.graph.configured() or not cfg.organizer_upn:
        return ScheduleResult(
            ok=False,
            dry_run=False,
            event_id=event_id,
            error="Graph credentials and organizer_upn are required to cancel.",
        )

    try:
        status_code, body = cfg.graph.request(
            "DELETE",
            f"{_events_collection_path(cfg)}/{event_id}",
        )
    except Exception as exc:
        logger.exception("Teams cancel failed")
        return ScheduleResult(
            ok=False,
            dry_run=False,
            event_id=event_id,
            error=str(exc),
        )

    if status_code >= 400:
        return ScheduleResult(
            ok=False,
            dry_run=False,
            event_id=event_id,
            error=f"Teams cancel failed (HTTP {status_code}): {body}",
        )
    return ScheduleResult(ok=True, dry_run=False, updated=True, event_id=event_id)


def quote_upn(upn: str) -> str:
    from urllib.parse import quote

    return quote(upn.strip(), safe="@")


__all__ = [
    "MeetingDraft",
    "MeetingKind",
    "ScheduleResult",
    "TeamsAttendee",
    "TeamsScheduleConfig",
    "build_graph_event_payload",
    "build_meeting_draft",
    "cancel_meeting",
    "load_schedule_config",
    "quote_upn",
    "readiness_steps",
    "schedule_meeting",
    "status",
    "update_meeting",
]
