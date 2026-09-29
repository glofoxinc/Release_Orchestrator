"""Schedule demo Teams meeting — device code sign-in (works in agent terminal)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

_APP_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

_TENANT = os.environ.get("MS_GRAPH_TENANT_ID") or "e0d8274f-1e23-401c-92c8-145fe2152f7a"
_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_SCOPES = "Calendars.ReadWrite User.Read offline_access"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes-from-now", type=int, default=28)
    args = parser.parse_args()

    import requests
    import teams_schedule
    from daily_review_agent.config_loader import load_agent_config
    from daily_review_agent.schedule import demo_window

    cfg = load_agent_config()
    start, end = demo_window(cfg, minutes_from_now=args.minutes_from_now)
    attendees = [
        teams_schedule.TeamsAttendee(email=a.email, name=a.name, type="required")
        for a in cfg.demo_attendees
        if a.email
    ]
    body_html = (
        "<p><strong>Daily Review Agent — demo call</strong></p>"
        "<p>Smoke test for Teams scheduling. Safe to ignore / delete.</p>"
    )
    draft = teams_schedule.build_meeting_draft(
        teams_schedule.load_schedule_config(
            {
                **cfg.teams_schedule_section,
                "enabled": True,
                "organizer_upn": cfg.organizer_upn,
                "default_timezone": cfg.timezone,
            }
        ),
        kind="review",
        subject=cfg.demo_subject,
        start=start,
        end=end,
        timezone_name=cfg.timezone,
        attendees=attendees,
        body=body_html,
    )
    payload = teams_schedule.build_graph_event_payload(draft)

    print("Requesting device code…", flush=True)
    dc = requests.post(
        f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/devicecode",
        data={"client_id": _CLIENT_ID, "scope": _SCOPES},
        timeout=30,
    ).json()
    if dc.get("error"):
        print(json.dumps(dc, indent=2))
        return 1

    print("\n" + "=" * 60)
    print(dc.get("message", ""))
    print("=" * 60 + "\n", flush=True)

    token_url = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"
    interval = int(dc.get("interval") or 5)
    deadline = time.time() + int(dc.get("expires_in") or 900)
    token = ""
    while time.time() < deadline:
        time.sleep(interval)
        tok = requests.post(
            token_url,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": _CLIENT_ID,
                "device_code": dc["device_code"],
            },
            timeout=30,
        ).json()
        if tok.get("access_token"):
            token = str(tok["access_token"])
            break
        err = tok.get("error", "")
        if err and err not in ("authorization_pending", "slow_down"):
            print(json.dumps(tok, indent=2))
            return 1
        if err == "slow_down":
            interval += 2

    if not token:
        print("Timed out waiting for sign-in.")
        return 1

    print("Signed in — creating Teams meeting…", flush=True)
    resp = requests.post(
        "https://graph.microsoft.com/v1.0/me/events",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if resp.status_code >= 400:
        print(json.dumps({"ok": False, "status": resp.status_code, "error": resp.text}, indent=2))
        return 1

    body = resp.json()
    online = body.get("onlineMeeting") if isinstance(body.get("onlineMeeting"), dict) else {}
    join_url = str((online or {}).get("joinUrl") or body.get("onlineMeetingUrl") or "").strip()
    result = {
        "ok": True,
        "event_id": body.get("id"),
        "join_url": join_url,
        "web_link": body.get("webLink"),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "attendees": [a.email for a in attendees],
    }
    out = _APP_ROOT / "orchestrator" / "agents" / "review" / ".state" / "demo_meeting_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if join_url:
        print(f"\nTeams join link:\n{join_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
