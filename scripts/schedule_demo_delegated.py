"""Schedule demo Teams call using delegated Graph auth (device code — no app secret).

Usage:
  python scripts/schedule_demo_delegated.py
  python scripts/schedule_demo_delegated.py --minutes-from-now 15

Sign in as the calendar organizer when prompted in the browser.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

# Azure CLI public client — registered in ABC Fitness tenant (device + browser flow).
_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_SCOPES = ["Calendars.ReadWrite", "User.Read", "offline_access"]
# ABC Fitness tenant (resolved from abcfitness.com OpenID metadata).
_DEFAULT_TENANT = "e0d8274f-1e23-401c-92c8-145fe2152f7a"
_TENANT = os.environ.get("MS_GRAPH_TENANT_ID") or os.environ.get("MICROSOFT_TENANT_ID") or _DEFAULT_TENANT


def _acquire_token() -> str:
    """Browser sign-in (preferred) then device-code fallback."""
    import msal

    authority = f"https://login.microsoftonline.com/{_TENANT}"
    app = msal.PublicClientApplication(_CLIENT_ID, authority=authority)
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(_SCOPES, account=accounts[0])
        if result and result.get("access_token"):
            return str(result["access_token"])

    try:
        result = app.acquire_token_interactive(scopes=_SCOPES)
        if result and result.get("access_token"):
            return str(result["access_token"])
        raise RuntimeError(result)
    except Exception as exc:
        print(f"Interactive auth unavailable ({exc}); trying device code…")

    import requests

    dc_url = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/devicecode"
    resp = requests.post(
        dc_url,
        data={"client_id": _CLIENT_ID, "scope": " ".join(_SCOPES)},
        timeout=30,
    )
    resp.raise_for_status()
    dc = resp.json()
    print("\n=== Microsoft sign-in required ===")
    print(dc.get("message", ""))
    print(f"Verification URL: {dc.get('verification_uri')}")
    print(f"Code: {dc.get('user_code')}\n")

    token_url = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"
    interval = int(dc.get("interval") or 5)
    deadline = time.time() + int(dc.get("expires_in") or 900)
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
        )
        body = tok.json()
        if tok.status_code == 200 and body.get("access_token"):
            return str(body["access_token"])
        err = body.get("error", "")
        if err and err not in ("authorization_pending", "slow_down"):
            raise RuntimeError(f"Device code auth failed: {body}")
        if err == "slow_down":
            interval += 2
    raise TimeoutError("Device code auth timed out — run again and sign in faster.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes-from-now", type=int, default=30)
    args = parser.parse_args()

    import config
    import requests
    import teams_schedule
    from daily_review_agent.config_loader import load_agent_config
    from daily_review_agent.demo_call import run_demo_call
    from daily_review_agent.schedule import demo_window, schedule_review_meeting

    config.reload_workspace()
    agent_cfg = load_agent_config()
    attendees = [
        teams_schedule.TeamsAttendee(email=a.email, name=a.name, type="required")
        for a in agent_cfg.demo_attendees
        if a.email
    ]
    if len(attendees) < 2:
        print("Need 2 demo attendee emails in daily_review_agent/agent.yaml", file=sys.stderr)
        return 2

    start, end = demo_window(agent_cfg, minutes_from_now=args.minutes_from_now)
    body_html = (
        "<p><strong>Daily Review Agent — demo call</strong></p>"
        "<p>Smoke test for Teams scheduling. Safe to ignore / delete.</p>"
    )
    teams_cfg = agent_cfg.teams_schedule_section
    draft = teams_schedule.build_meeting_draft(
        teams_schedule.load_schedule_config(
            {
                **teams_cfg,
                "enabled": True,
                "organizer_upn": agent_cfg.organizer_upn,
                "default_timezone": agent_cfg.timezone,
            }
        ),
        kind="review",
        subject=agent_cfg.demo_subject,
        start=start,
        end=end,
        timezone_name=agent_cfg.timezone,
        attendees=attendees,
        body=body_html,
    )
    payload = teams_schedule.build_graph_event_payload(draft)

    token = _acquire_token()
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
        "attendees": [{"email": a.email, "name": a.name} for a in attendees],
    }
    print(json.dumps(result, indent=2))
    if join_url:
        print(f"\nTeams join link:\n{join_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
