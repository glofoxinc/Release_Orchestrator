"""Schedule Teams online meetings via delegated Microsoft Graph (one-time browser sign-in)."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Teams MCP public client — pre-authorized on ABC tenant (Azure CLI client hits AADSTS65002).
_TEAMS_PUBLIC_CLIENT_ID = "5e3ce6c0-2b1f-4285-8d4b-75ee78787346"
_AZURE_CLI_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_DEFAULT_TENANT = "e0d8274f-1e23-401c-92c8-145fe2152f7a"
# offline_access is added by MSAL automatically — do not pass it (reserved scope error).
_SCOPES = ["Calendars.ReadWrite", "User.Read"]
_CACHE_PATH = Path(__file__).resolve().parent / ".state" / "msal_token_cache.bin"


def _tenant_id() -> str:
    return (
        os.environ.get("MS_GRAPH_TENANT_ID")
        or os.environ.get("MICROSOFT_TENANT_ID")
        or _DEFAULT_TENANT
    ).strip()


def _client_id() -> str:
    raw = (os.environ.get("MS_GRAPH_CLIENT_ID") or "").strip()
    if raw:
        return raw
    # ABC tenant blocks Azure CLI app for Graph calendar — Teams client works after browser login.
    return _TEAMS_PUBLIC_CLIENT_ID


def _msal_app():
    import msal

    authority = f"https://login.microsoftonline.com/{_tenant_id()}"
    cache = msal.SerializableTokenCache()
    if _CACHE_PATH.is_file():
        try:
            cache.deserialize(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Could not read MSAL cache at %s", _CACHE_PATH)
    app = msal.PublicClientApplication(
        _client_id(),
        authority=authority,
        token_cache=cache,
    )
    return app, cache


def _persist_cache(cache) -> None:
    if cache.has_state_changed:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(cache.serialize(), encoding="utf-8")


def acquire_graph_token(*, interactive: bool = True) -> str:
    """Return Graph access token; opens browser once, then uses silent refresh."""
    app, cache = _msal_app()
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(_SCOPES, account=accounts[0])
        if result and result.get("access_token"):
            _persist_cache(cache)
            return str(result["access_token"])

    if not interactive:
        raise RuntimeError(
            "Graph sign-in required. Run: python -m daily_review_agent --graph-login"
        )

    result = app.acquire_token_interactive(scopes=_SCOPES)
    if not result or not result.get("access_token"):
        err = str(result)
        if "AADSTS65002" in err:
            raise RuntimeError(
                "ABC tenant blocks direct Graph login (AADSTS65002). "
                "Use teams_login + calendar_backend: teams_mcp, or ask IT for a custom Entra app "
                "(MS_GRAPH_CLIENT_ID + MS_GRAPH_CLIENT_SECRET with Calendars.ReadWrite admin consent)."
            )
        raise RuntimeError(f"Graph interactive auth failed: {result}")
    _persist_cache(cache)
    return str(result["access_token"])


def graph_calendar_ready(*, interactive_probe: bool = False) -> dict[str, Any]:
    """Check whether delegated Graph calendar is ready."""
    blockers: list[str] = []
    try:
        import msal  # noqa: F401
    except ImportError:
        return {
            "enabled": True,
            "available": False,
            "can_schedule": False,
            "blockers": ["msal not installed — pip install msal"],
            "cache_exists": _CACHE_PATH.is_file(),
        }

    cache_exists = _CACHE_PATH.is_file()
    if not cache_exists:
        blockers.append(
            "Graph MSAL cache missing — on ABC tenant use teams_login + calendar_backend: teams_mcp "
            "(--graph-login hits AADSTS65002 until IT provisions Entra app)"
        )

    token_ok = False
    if cache_exists or interactive_probe:
        try:
            acquire_graph_token(interactive=False)
            token_ok = True
        except Exception as exc:
            if cache_exists:
                blockers.append(f"Graph token refresh failed: {exc}")

    return {
        "enabled": True,
        "available": True,
        "can_schedule": token_ok,
        "cache_exists": cache_exists,
        "cache_path": str(_CACHE_PATH),
        "blockers": blockers,
    }


def _extract_join_url(body: dict[str, Any]) -> str:
    online = body.get("onlineMeeting") if isinstance(body.get("onlineMeeting"), dict) else {}
    return str((online or {}).get("joinUrl") or body.get("onlineMeetingUrl") or "").strip()


def _verify_event_join_url(token: str, event_id: str) -> str:
    """Re-fetch event from Graph when create response lacks join URL."""
    if not event_id:
        return ""
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if resp.status_code >= 400:
        logger.warning("Graph verify GET failed: %s", resp.status_code)
        return ""
    return _extract_join_url(resp.json())


def _to_utc_z(dt: datetime) -> str:
    from datetime import timezone

    if dt.tzinfo is None:
        aware = dt.replace(tzinfo=timezone.utc)
    else:
        aware = dt.astimezone(timezone.utc)
    return aware.strftime("%Y-%m-%dT%H:%M:%SZ")


def schedule_meeting_via_graph(
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    attendee_emails: list[dict[str, str]],
    timezone_name: str = "Asia/Kolkata",
    location: str = "Microsoft Teams Meeting",
    organizer_upn: str = "",
    interactive_auth: bool = True,
) -> dict[str, Any]:
    """Create a Teams online meeting on the signed-in user's calendar."""
    people = [a for a in attendee_emails if (a.get("email") or "").strip()]
    if not people:
        return {"ok": False, "backend": "graph_delegated", "error": "No attendee emails"}

    try:
        import teams_schedule
        from teams_schedule import TeamsAttendee

        token = acquire_graph_token(interactive=interactive_auth)
        attendees = [
            TeamsAttendee(email=p["email"], name=p.get("name") or "", type="required")
            for p in people
        ]
        draft = teams_schedule.build_meeting_draft(
            teams_schedule.load_schedule_config(
                {
                    "enabled": True,
                    "organizer_upn": organizer_upn or people[0]["email"],
                    "default_timezone": timezone_name,
                }
            ),
            kind="review",
            subject=subject,
            start=start,
            end=end,
            timezone_name=timezone_name,
            attendees=attendees,
            body=f"<p>{body_text.replace(chr(10), '<br>')}</p>",
            location=location,
        )
        payload = teams_schedule.build_graph_event_payload(draft)
        resp = requests.post(
            "https://graph.microsoft.com/v1.0/me/events",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if resp.status_code >= 400:
            return {
                "ok": False,
                "backend": "graph_delegated",
                "error": f"Graph HTTP {resp.status_code}: {resp.text[:500]}",
            }
        body = resp.json()
        event_id = str(body.get("id") or "")
        join_url = _extract_join_url(body)
        if not join_url and event_id:
            join_url = _verify_event_join_url(token, event_id)
        if not join_url:
            return {
                "ok": False,
                "backend": "graph_delegated",
                "error": "Graph event created but Teams join URL missing after verification",
                "event_id": event_id,
                "web_link": body.get("webLink"),
            }
        return {
            "ok": True,
            "backend": "graph_delegated",
            "event_id": event_id,
            "join_url": join_url,
            "web_link": body.get("webLink"),
            "subject": subject,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "attendees": [p["email"] for p in people],
        }
    except Exception as exc:
        logger.exception("Graph delegated schedule failed")
        return {"ok": False, "backend": "graph_delegated", "error": str(exc)}
