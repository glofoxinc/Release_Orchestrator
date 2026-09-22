"""Send demo Teams meeting via local Outlook (uses signed-in Windows profile)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from daily_review_agent.config_loader import load_agent_config
from daily_review_agent.schedule import demo_window


def main() -> int:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        print(json.dumps({"ok": False, "error": "pywin32 not installed — pip install pywin32"}))
        return 1

    cfg = load_agent_config()
    start, end = demo_window(cfg, minutes_from_now=15)
    attendees = [a for a in cfg.demo_attendees if a.email]
    if len(attendees) < 2:
        print(json.dumps({"ok": False, "error": "Need 2 demo attendee emails"}))
        return 2

    outlook = win32com.client.Dispatch("Outlook.Application")
    appt = outlook.CreateItem(1)  # olAppointmentItem
    appt.Subject = cfg.demo_subject
    appt.Body = "Daily Review Agent demo call (smoke test). Safe to delete."
    appt.Start = start.replace(tzinfo=None)
    appt.End = end.replace(tzinfo=None)
    appt.Location = "Microsoft Teams Meeting"
    try:
        appt.IsOnlineMeeting = True
    except Exception:
        pass

    for person in attendees:
        recip = appt.Recipients.Add(person.email)
        recip.Type = 1  # required

    appt.MeetingStatus = 1  # olMeeting
    appt.Send()

    join_url = ""
    try:
        join_url = str(getattr(appt, "MeetingWorkspaceURL", "") or "")
    except Exception:
        pass

    result = {
        "ok": True,
        "method": "outlook_com",
        "subject": cfg.demo_subject,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "attendees": [a.email for a in attendees],
        "join_url": join_url,
        "entry_id": str(getattr(appt, "EntryID", "") or ""),
    }
    print(json.dumps(result, indent=2))
    if join_url:
        print(f"\nTeams join link:\n{join_url}")
    else:
        print("\nMeeting sent — check Outlook calendar invite for Teams link.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
