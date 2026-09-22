"""Fetch Teams join link for demo meeting from Outlook calendar or Graph."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

_SUBJECT_HINT = "Daily Review Agent DEMO"


def _from_outlook_com() -> dict | None:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return None

    tz = ZoneInfo("Asia/Kolkata")
    start = datetime.now(tz) - timedelta(hours=2)
    end = datetime.now(tz) + timedelta(days=1)
    outlook = win32com.client.Dispatch("Outlook.Application")
    calendar = outlook.GetNamespace("MAPI").GetDefaultFolder(9)  # olFolderCalendar
    items = calendar.Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")
    restriction = f"[Start] >= '{start.strftime('%m/%d/%Y %H:%M %p')}' AND [Start] <= '{end.strftime('%m/%d/%Y %H:%M %p')}'"
    filtered = items.Restrict(restriction)
    for item in filtered:
        try:
            subject = str(getattr(item, "Subject", "") or "")
            if _SUBJECT_HINT.lower() not in subject.lower() and "demo" not in subject.lower():
                continue
            join_url = str(getattr(item, "MeetingWorkspaceURL", "") or "")
            if not join_url:
                body = str(getattr(item, "Body", "") or "")
                for line in body.splitlines():
                    if "teams.microsoft.com" in line.lower():
                        join_url = line.strip().strip("<>")
                        break
            return {
                "ok": True,
                "source": "outlook_com",
                "subject": subject,
                "start": str(getattr(item, "Start", "")),
                "end": str(getattr(item, "End", "")),
                "join_url": join_url,
                "web_link": str(getattr(item, "EntryID", "") or ""),
            }
        except Exception:
            continue
    return {"ok": False, "source": "outlook_com", "error": "No matching demo meeting in Outlook calendar"}


def _from_graph() -> dict | None:
    import ms_graph
    import requests

    client = ms_graph.GraphClient()
    if not client.configured():
        return None

    token = client.get_access_token()
    tz = ZoneInfo("Asia/Kolkata")
    start = (datetime.now(tz) - timedelta(hours=2)).isoformat()
    end = (datetime.now(tz) + timedelta(days=1)).isoformat()
    url = (
        "https://graph.microsoft.com/v1.0/me/calendarView"
        f"?startDateTime={start}&endDateTime={end}"
        "&$select=subject,start,end,onlineMeeting,webLink,bodyPreview"
        "&$orderby=start/dateTime"
    )
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if resp.status_code >= 400:
        # App-only: use organizer mailbox
        from daily_review_agent.config_loader import load_agent_config

        cfg = load_agent_config()
        from urllib.parse import quote

        upn = quote(cfg.organizer_upn)
        url = (
            f"https://graph.microsoft.com/v1.0/users/{upn}/calendarView"
            f"?startDateTime={start}&endDateTime={end}"
            "&$select=subject,start,end,onlineMeeting,webLink,bodyPreview"
        )
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if resp.status_code >= 400:
        return {"ok": False, "source": "graph", "error": resp.text[:500]}

    for ev in resp.json().get("value") or []:
        subject = str(ev.get("subject") or "")
        if _SUBJECT_HINT.lower() not in subject.lower() and "demo" not in subject.lower():
            continue
        online = ev.get("onlineMeeting") if isinstance(ev.get("onlineMeeting"), dict) else {}
        join_url = str((online or {}).get("joinUrl") or "").strip()
        return {
            "ok": True,
            "source": "graph",
            "subject": subject,
            "start": ev.get("start"),
            "end": ev.get("end"),
            "join_url": join_url,
            "web_link": ev.get("webLink"),
        }
    return {"ok": False, "source": "graph", "error": "No matching demo meeting via Graph"}


def main() -> int:
    results = []
    graph = _from_graph()
    if graph is not None:
        results.append(graph)
    outlook = _from_outlook_com()
    if outlook is not None:
        results.append(outlook)

    winner = next((r for r in results if r.get("ok") and r.get("join_url")), None)
    if not winner:
        winner = next((r for r in results if r.get("ok")), None)

    payload = {
        "found": bool(winner and winner.get("join_url")),
        "attempts": results,
        "need": (
            "Add MS_GRAPH_TENANT_ID + MS_GRAPH_CLIENT_ID + MS_GRAPH_CLIENT_SECRET to .env, "
            "or MS_GRAPH_ACCESS_TOKEN from Graph Explorer, then re-run. "
            "Or send the Teams invite from the open dialog first."
        ),
    }
    print(json.dumps(payload, indent=2, default=str))
    if winner and winner.get("join_url"):
        print(f"\nTeams join link:\n{winner['join_url']}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
