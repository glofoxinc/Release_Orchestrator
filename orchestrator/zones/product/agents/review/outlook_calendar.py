"""Schedule Teams meetings via local Outlook COM (signed-in Windows profile)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# olAppointmentItem
_OL_APPOINTMENT = 1
# olMeeting
_OL_MEETING = 1
# required attendee
_OL_REQUIRED = 1


def _naive_local(dt: datetime) -> datetime:
    """Outlook COM expects naive local datetimes."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def schedule_meeting_via_outlook(
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    attendee_emails: list[dict[str, str]],
    location: str = "Microsoft Teams Meeting",
) -> dict[str, Any]:
    """Create and send a Teams online meeting through desktop Outlook."""
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError:
        return {
            "ok": False,
            "backend": "outlook_com",
            "error": "pywin32 not installed — pip install pywin32 in the agent venv",
        }

    people = [a for a in attendee_emails if (a.get("email") or "").strip()]
    if not people:
        return {"ok": False, "backend": "outlook_com", "error": "No attendee emails provided"}

    try:
        outlook = win32com.client.gencache.EnsureDispatch("Outlook.Application")
        appt = outlook.CreateItem(_OL_APPOINTMENT)
        appt.Subject = subject
        appt.Body = body_text
        appt.Start = _naive_local(start)
        appt.End = _naive_local(end)
        appt.Location = location or "Microsoft Teams Meeting"
        appt.MeetingStatus = _OL_MEETING

        for person in people:
            recip = appt.Recipients.Add(str(person["email"]).strip())
            recip.Type = _OL_REQUIRED
        appt.Recipients.ResolveAll()

        for provider in (5, 1, 3):  # Teams provider IDs vary by Outlook version
            try:
                appt.IsOnlineMeeting = True
                appt.OnlineMeetingProvider = provider
                break
            except Exception as exc:
                logger.debug("Outlook OnlineMeetingProvider=%s: %s", provider, exc)

        appt.Save()
        appt.Send()

        join_url = ""
        for attr in ("MeetingWorkspaceURL", "OnlineMeetingJoinUrl", "OnlineMeetingURL"):
            try:
                join_url = str(getattr(appt, attr, "") or "").strip()
            except Exception:
                join_url = ""
            if join_url:
                break

        if not join_url:
            return {
                "ok": False,
                "backend": "outlook_com",
                "error": "local_outlook_no_teams_link — not production-safe; use graph_delegated",
                "event_id": str(getattr(appt, "EntryID", "") or ""),
                "subject": subject,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "attendees": [p["email"] for p in people],
            }

        return {
            "ok": True,
            "backend": "outlook_com",
            "event_id": str(getattr(appt, "EntryID", "") or ""),
            "join_url": join_url,
            "subject": subject,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "attendees": [p["email"] for p in people],
        }
    except Exception as exc:
        logger.exception("Outlook COM schedule failed")
        return {"ok": False, "backend": "outlook_com", "error": str(exc)}


def outlook_calendar_ready() -> dict[str, Any]:
    """Check whether Outlook COM automation is available."""
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError:
        return {
            "enabled": True,
            "available": False,
            "can_schedule": False,
            "blockers": ["pywin32 not installed"],
        }

    try:
        win32com.client.Dispatch("Outlook.Application")
        return {
            "enabled": True,
            "available": True,
            "can_schedule": True,
            "blockers": [],
            "warning": "outlook_com is dev-only — may not sync to Teams/Outlook web",
        }
    except Exception as exc:
        return {
            "enabled": True,
            "available": False,
            "can_schedule": False,
            "blockers": [f"Outlook not available: {exc}"],
        }
