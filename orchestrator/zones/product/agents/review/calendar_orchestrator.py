"""Multi-backend calendar scheduling — ABC tenant safe (no Graph MSAL required)."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from daily_review_agent.config_loader import AgentConfig
from daily_review_agent.paths import REPO_ROOT, STATE_DIR, script
from daily_review_agent.teams_mcp import _node_exe, teams_mcp_call

logger = logging.getLogger(__name__)
_PROJECT_ROOT = REPO_ROOT
_TEAMS_BROWSER_SCRIPT = script("schedule_meeting_now.mjs")
_PLAYWRIGHT_OUTLOOK_SCRIPT = script("schedule_outlook_playwright.mjs")

# ABC Fitness: Graph MSAL blocked (AADSTS65002). Outlook COM creates local ghosts (no Teams sync).
# Primary (Cursor chat): Playwright MCP handoff — agent drives Outlook web in Cursor browser.
# Unattended fallback: embedded playwright_outlook script (Task Scheduler only when enabled).
DEFAULT_ABC_CHAIN = ("playwright_mcp",)
_BACKEND_ALIASES = {
    "playwright": "playwright_outlook",
    "browser": "playwright_outlook",
    "outlook_web": "playwright_outlook",
    "cursor_playwright_mcp": "playwright_mcp",
    "teams_browser_automation": "teams_browser",
}


def _to_utc_z(dt: datetime) -> str:
    from datetime import timezone

    if dt.tzinfo is None:
        aware = dt.replace(tzinfo=timezone.utc)
    else:
        aware = dt.astimezone(timezone.utc)
    return aware.strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_backend_chain(cfg: AgentConfig) -> tuple[str, ...]:
    raw = getattr(cfg, "calendar_backends", None) or []
    if raw:
        out: list[str] = []
        for b in raw:
            name = _BACKEND_ALIASES.get(str(b).strip().lower(), str(b).strip().lower())
            if name and name not in out:
                out.append(name)
        return _maybe_append_embedded_fallback(cfg, tuple(out))
    backend = _BACKEND_ALIASES.get(
        (cfg.calendar_backend or "auto").strip().lower(),
        (cfg.calendar_backend or "auto").strip().lower(),
    )
    if backend == "auto":
        if getattr(cfg, "playwright_mcp_primary_enabled", True):
            chain: tuple[str, ...] = ("playwright_mcp",)
        else:
            chain = ("playwright_outlook",)
        return _maybe_append_embedded_fallback(cfg, chain)
    if backend == "playwright_mcp":
        return _maybe_append_embedded_fallback(cfg, ("playwright_mcp",))
    return (backend,)


def _maybe_append_embedded_fallback(cfg: AgentConfig, chain: tuple[str, ...]) -> tuple[str, ...]:
    if not getattr(cfg, "embedded_playwright_fallback_enabled", False):
        return chain
    if "playwright_outlook" in chain:
        return chain
    if "playwright_mcp" not in chain:
        return chain
    return chain + ("playwright_outlook",)


def _verified_schedule(result: dict[str, Any]) -> bool:
    """True when invite is real in cloud — join URL or Playwright Send confirmed."""
    if not result.get("ok"):
        return False
    if str(result.get("join_url") or "").strip():
        return True
    return result.get("backend") == "playwright_outlook" and bool(result.get("sent"))


def _run_playwright_payload(
    payload: dict[str, Any], *, timeout: int = 600, timezone: str = "Asia/Kolkata"
) -> dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("timezone", timezone)
    """Run Playwright Outlook web script (mirrors Playwright MCP flow)."""
    if not _PLAYWRIGHT_OUTLOOK_SCRIPT.is_file():
        return {
            "ok": False,
            "backend": "playwright_outlook",
            "error": f"Missing {_PLAYWRIGHT_OUTLOOK_SCRIPT}",
        }

    payload_path = STATE_DIR / "_playwright_schedule_payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        proc = subprocess.run(
            [_node_exe(), str(_PLAYWRIGHT_OUTLOOK_SCRIPT), str(payload_path)],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "backend": "playwright_outlook",
            "error": f"Playwright Outlook schedule timed out ({timeout}s)",
        }

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {
            "ok": False,
            "backend": "playwright_outlook",
            "error": (proc.stderr or "no output")[:500],
            "exit_code": proc.returncode,
        }
    try:
        data = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "backend": "playwright_outlook",
            "error": f"Invalid JSON: {exc}",
            "raw": stdout[:300],
        }
    data.setdefault("backend", "playwright_outlook")
    return data


def _schedule_playwright_mcp(
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    people: list[dict[str, str]],
    timezone: str = "Asia/Kolkata",
) -> dict[str, Any]:
    from daily_review_agent.calendar_playwright_handoff import build_daily_review_calendar_handoff

    handoff = build_daily_review_calendar_handoff(
        subject=subject,
        start_iso=start.isoformat(),
        end_iso=end.isoformat(),
        attendees=people,
        body_text=body_text,
        timezone=timezone,
        primary=True,
    )
    return {
        "ok": True,
        "backend": "cursor_playwright_mcp",
        "handoff_required": True,
        "handoff": handoff,
        "instruction": handoff.get("instruction") or "",
        "completion_phrases": handoff.get("completion", {}).get("user_phrases") or ["calendar done"],
        "subject": subject,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "attendees": [p["email"] for p in people],
    }


def _schedule_playwright_outlook(
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    people: list[dict[str, str]],
    timezone: str = "Asia/Kolkata",
) -> dict[str, Any]:
    payload = {
        "meetings": [
            {
                "subject": subject,
                "startIso": start.isoformat(),
                "endIso": end.isoformat(),
                "attendees": [{"email": p["email"], "name": p.get("name") or ""} for p in people],
                "body": body_text,
            }
        ]
    }
    data = _run_playwright_payload(payload, timeout=300, timezone=timezone)
    if not data.get("ok") and data.get("status") != "partial":
        return {
            "ok": False,
            "backend": "playwright_outlook",
            "error": data.get("error") or "playwright_outlook failed",
            "detail": data,
        }

    results = data.get("results") or []
    first = results[0] if results else {}
    if not first.get("ok"):
        return {
            "ok": False,
            "backend": "playwright_outlook",
            "error": first.get("error") or data.get("error") or "playwright_outlook failed",
            "detail": data,
        }
    return {
        "ok": True,
        "sent": bool(first.get("sent")),
        "backend": "playwright_outlook",
        "join_url": first.get("join_url") or "",
        "subject": first.get("subject") or subject,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "attendees": [p["email"] for p in people],
    }


def _schedule_teams_mcp(
    cfg: AgentConfig,
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    people: list[dict[str, str]],
) -> dict[str, Any]:
    from daily_review_agent.teams_delivery import schedule_meeting_via_mcp

    return schedule_meeting_via_mcp(
        cfg,
        subject=subject,
        body_text=body_text,
        start=start,
        end=end,
        attendee_emails=people,
        dry_run=False,
    )


def _schedule_teams_browser(
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    people: list[dict[str, str]],
) -> dict[str, Any]:
    if not _TEAMS_BROWSER_SCRIPT.is_file():
        return {"ok": False, "backend": "teams_browser", "error": f"Missing {_TEAMS_BROWSER_SCRIPT}"}

    payload = {
        "subject": subject,
        "startTime": _to_utc_z(start),
        "endTime": _to_utc_z(end),
        "attendees": [{"email": p["email"], "name": p.get("name") or ""} for p in people],
        "body": body_text,
        "isOnlineMeeting": True,
        "location": "Microsoft Teams Meeting",
    }
    payload_path = STATE_DIR / "_schedule_payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        proc = subprocess.run(
            [_node_exe(), str(_TEAMS_BROWSER_SCRIPT), str(payload_path)],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "backend": "teams_browser", "error": "Browser login/schedule timed out (300s)"}

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {
            "ok": False,
            "backend": "teams_browser",
            "error": (proc.stderr or "no output")[:500],
            "exit_code": proc.returncode,
        }
    try:
        data = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {"ok": False, "backend": "teams_browser", "error": f"Invalid JSON: {exc}", "raw": stdout[:300]}

    if not data.get("ok"):
        return {
            "ok": False,
            "backend": "teams_browser",
            "error": data.get("error") or "teams_browser failed",
            "detail": data,
        }
    return {
        "ok": True,
        "backend": "teams_browser",
        "event_id": data.get("event_id"),
        "join_url": data.get("join_url"),
        "subject": data.get("subject") or subject,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "attendees": [p["email"] for p in people],
    }


def _schedule_outlook_com(
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    people: list[dict[str, str]],
    accept_without_join_url: bool,
) -> dict[str, Any]:
    from daily_review_agent.outlook_calendar import schedule_meeting_via_outlook

    result = schedule_meeting_via_outlook(
        subject=subject,
        body_text=body_text,
        start=start,
        end=end,
        attendee_emails=people,
    )
    if result.get("ok"):
        return result
    if accept_without_join_url and result.get("event_id"):
        return {
            **result,
            "ok": True,
            "warning": "invite_sent_without_verified_teams_link",
            "join_url": result.get("join_url") or "",
        }
    return result


def _schedule_graph(
    cfg: AgentConfig,
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    people: list[dict[str, str]],
) -> dict[str, Any]:
    from daily_review_agent.graph_calendar import schedule_meeting_via_graph

    return schedule_meeting_via_graph(
        subject=subject,
        body_text=body_text,
        start=start,
        end=end,
        attendee_emails=people,
        timezone_name=cfg.timezone,
        location=cfg.meeting_location or "Microsoft Teams Meeting",
        organizer_upn=cfg.organizer_upn,
        interactive_auth=False,
    )


def schedule_with_fallback(
    cfg: AgentConfig,
    *,
    subject: str,
    body_text: str,
    start: datetime,
    end: datetime,
    attendee_emails: list[dict[str, str]],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Try each backend in chain until one succeeds."""
    people = [{"email": a["email"], "name": a.get("name") or ""} for a in attendee_emails if a.get("email")]
    if not people:
        return {"ok": False, "error": "No attendee emails", "attempts": []}

    preview = {
        "subject": subject,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "attendees": people,
        "chain": list(resolve_backend_chain(cfg)),
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "preview": preview}

    accept_outlook = bool(getattr(cfg, "calendar_accept_outlook_without_join_url", True))
    attempts: list[dict[str, Any]] = []

    for backend in resolve_backend_chain(cfg):
        logger.info("Trying calendar backend: %s", backend)
        if backend == "playwright_mcp":
            result = _schedule_playwright_mcp(
                subject=subject,
                body_text=body_text,
                start=start,
                end=end,
                people=people,
                timezone=cfg.timezone,
            )
            attempts.append(
                {
                    "backend": backend,
                    "ok": True,
                    "handoff_required": True,
                    "error": None,
                }
            )
            result["attempts"] = attempts
            return result
        if backend == "playwright_outlook":
            result = _schedule_playwright_outlook(
                subject=subject,
                body_text=body_text,
                start=start,
                end=end,
                people=people,
                timezone=cfg.timezone,
            )
        elif backend == "teams_mcp":
            result = _schedule_teams_mcp(cfg, subject=subject, body_text=body_text, start=start, end=end, people=people)
        elif backend == "teams_browser":
            result = _schedule_teams_browser(
                subject=subject, body_text=body_text, start=start, end=end, people=people
            )
        elif backend == "outlook_com":
            result = _schedule_outlook_com(
                subject=subject,
                body_text=body_text,
                start=start,
                end=end,
                people=people,
                accept_without_join_url=accept_outlook,
            )
        elif backend == "graph_delegated":
            result = _schedule_graph(
                cfg, subject=subject, body_text=body_text, start=start, end=end, people=people
            )
        else:
            result = {"ok": False, "backend": backend, "error": f"Unknown backend: {backend}"}

        verified = _verified_schedule(result)
        attempts.append(
            {
                "backend": backend,
                "ok": verified,
                "error": result.get("error") or (None if verified else "missing join_url — not synced to Teams"),
            }
        )
        if verified:
            result["attempts"] = attempts
            result.setdefault("backend", backend)
            return result
        if result.get("ok") and not verified:
            logger.warning(
                "Backend %s returned ok without join URL — trying next backend",
                backend,
            )

    return {
        "ok": False,
        "error": "All calendar backends failed",
        "attempts": attempts,
        "preview": preview,
    }


def orchestrator_readiness(cfg: AgentConfig) -> dict[str, Any]:
    """At least one backend in the chain must be schedulable."""
    from daily_review_agent.graph_calendar import graph_calendar_ready
    from daily_review_agent.outlook_calendar import outlook_calendar_ready

    chain = resolve_backend_chain(cfg)
    backends: dict[str, Any] = {}
    can_any = False
    blockers: list[str] = []

    for name in chain:
        if name == "outlook_com":
            st = outlook_calendar_ready()
        elif name == "teams_mcp":
            st = teams_mcp_call("status")
            st = {
                "can_schedule": bool(st.get("calendar_ready") or st.get("graph_ready")),
                "blockers": [] if st.get("calendar_ready") else [st.get("message") or "teams_login required"],
            }
        elif name == "playwright_mcp":
            import browser_automation

            st = browser_automation.playwright_mcp_readiness()
            st["primary"] = True
            st["handoff_tool"] = "dr_cal_handoff"
            st["trigger_phrases"] = st.get("trigger_phrases") or ["schedule review call"]
        elif name == "playwright_outlook":
            from daily_review_agent.playwright_outlook_auth import outlook_readiness

            st = outlook_readiness()
            st["aliases"] = ["playwright", "browser", "outlook_web"]
            st["note"] = "Unattended fallback — enable embedded_playwright_fallback_enabled for Task Scheduler"
        elif name == "teams_browser":
            st = {
                "can_schedule": _TEAMS_BROWSER_SCRIPT.is_file(),
                "blockers": [] if _TEAMS_BROWSER_SCRIPT.is_file() else ["schedule_meeting_now.mjs missing"],
                "note": "Fallback — msteams-mcp browser automation",
            }
        elif name == "graph_delegated":
            st = graph_calendar_ready()
        else:
            st = {"can_schedule": False, "blockers": [f"Unknown backend {name}"]}

        backends[name] = st
        if st.get("can_schedule"):
            can_any = True
        else:
            for b in st.get("blockers") or []:
                if b and b not in blockers:
                    blockers.append(str(b))

    return {
        "backend_mode": cfg.calendar_backend,
        "chain": list(chain),
        "can_schedule_any": can_any,
        "backends": backends,
        "blockers": blockers if not can_any else [],
        "outlook_mcp_note": "Outlook MCP is email-only — not used for calendar",
    }
