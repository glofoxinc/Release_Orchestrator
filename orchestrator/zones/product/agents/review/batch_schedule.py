"""Schedule multiple back-to-back meetings (pilot / smoke)."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from daily_review_agent.calendar_orchestrator import (
    _run_playwright_payload,
    _to_utc_z,
    _verified_schedule,
    schedule_with_fallback,
)
from daily_review_agent.config_loader import load_agent_config
from daily_review_agent.paths import REPO_ROOT, STATE_DIR, script
from daily_review_agent.teams_mcp import _node_exe

_PROJECT_ROOT = REPO_ROOT
_BATCH_BROWSER_SCRIPT = script("schedule_batch_browser.mjs")
_CANCEL_PLAYWRIGHT_SCRIPT = script("cancel_outlook_playwright.mjs")


def _run_cancel_via_playwright(*, pattern: str, day: str) -> dict[str, Any]:
    """Cancel existing Outlook web events before rescheduling (idempotent batch)."""
    if not _CANCEL_PLAYWRIGHT_SCRIPT.is_file():
        return {"ok": False, "error": "cancel_outlook_playwright.mjs missing"}

    payload_path = STATE_DIR / "_cancel_playwright.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [_node_exe(), str(_CANCEL_PLAYWRIGHT_SCRIPT), pattern, day],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "cancel playwright timeout (300s)"}

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {"ok": False, "error": (proc.stderr or "no cancel output")[:500]}
    try:
        return json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid cancel JSON", "raw": stdout[:300]}


def _run_batch_via_playwright(
    *,
    slots: list[tuple[datetime, datetime]],
    people: list[dict[str, str]],
    subject_prefix: str,
    replace_existing: bool = True,
    timezone: str = "Asia/Kolkata",
) -> dict[str, Any] | None:
    """One Edge login + cancel (optional) + N meetings + verify via Playwright → Outlook web."""
    meetings = []
    for idx, (start, end) in enumerate(slots, start=1):
        meetings.append(
            {
                "subject": f"{subject_prefix} #{idx}",
                "startIso": start.isoformat(),
                "endIso": end.isoformat(),
                "attendees": people,
                "body": f"Daily Review Agent batch call {idx} of {len(slots)}.",
            }
        )

    payload: dict[str, Any] = {
        "meetings": meetings,
        "verify": True,
        "timezone": timezone,
    }
    if replace_existing:
        payload["replacePattern"] = subject_prefix

    data = _run_playwright_payload(payload, timeout=900, timezone=timezone)
    if not data.get("results") and not data.get("ok"):
        return {
            "status": "failed",
            "scheduled": 0,
            "total": len(slots),
            "error": data.get("error") or "playwright batch failed",
            "mode": "playwright_outlook",
        }

    results = []
    ok_count = 0
    for item in data.get("results") or []:
        idx = int(item.get("slot") or 0)
        start, end = slots[idx - 1] if 0 < idx <= len(slots) else (None, None)
        entry = {
            "slot": idx,
            "start": start.isoformat() if start else "",
            "end": end.isoformat() if end else "",
            "subject": item.get("subject"),
            "ok": bool(item.get("ok")),
            "sent": bool(item.get("sent")),
            "backend": item.get("backend") or "playwright_outlook",
            "join_url": item.get("join_url"),
            "error": item.get("error"),
        }
        results.append(entry)
        if _verified_schedule(entry):
            ok_count += 1

    return {
        "status": data.get("status") or ("ok" if ok_count == len(slots) else "partial" if ok_count else "failed"),
        "scheduled": ok_count,
        "total": len(slots),
        "results": results,
        "mode": "playwright_outlook",
        "replaced": data.get("replaced"),
        "verification": data.get("verification"),
        "verified": bool((data.get("verification") or {}).get("ok")) if data.get("verification") else ok_count == len(slots),
    }


def _run_batch_via_browser(
    *,
    slots: list[tuple[datetime, datetime]],
    people: list[dict[str, str]],
    subject_prefix: str,
) -> dict[str, Any] | None:
    """One browser login + N meetings — preferred for ABC tenant."""
    if not _BATCH_BROWSER_SCRIPT.is_file():
        return None

    meetings = []
    for idx, (start, end) in enumerate(slots, start=1):
        meetings.append(
            {
                "subject": f"{subject_prefix} #{idx}",
                "startTime": _to_utc_z(start),
                "endTime": _to_utc_z(end),
                "attendees": people,
                "body": f"Daily Review Agent batch call {idx} of {len(slots)}.",
                "isOnlineMeeting": True,
                "location": "Microsoft Teams Meeting",
            }
        )

    payload_path = STATE_DIR / "_batch_schedule_payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps({"meetings": meetings}), encoding="utf-8")

    try:
        proc = subprocess.run(
            [_node_exe(), str(_BATCH_BROWSER_SCRIPT), str(payload_path)],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "scheduled": 0, "total": len(slots), "error": "batch browser timeout (600s)"}

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {
            "status": "failed",
            "scheduled": 0,
            "total": len(slots),
            "error": (proc.stderr or "no output")[:500],
        }
    try:
        data = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError:
        return {"status": "failed", "scheduled": 0, "total": len(slots), "error": "invalid batch output", "raw": stdout[:300]}

    results = []
    for item in data.get("results") or []:
        idx = int(item.get("slot") or 0)
        start, end = slots[idx - 1] if 0 < idx <= len(slots) else (None, None)
        results.append(
            {
                "slot": idx,
                "start": start.isoformat() if start else "",
                "end": end.isoformat() if end else "",
                "subject": item.get("subject"),
                "ok": bool(item.get("ok")),
                "backend": item.get("backend") or "teams_browser",
                "join_url": item.get("join_url"),
                "event_id": item.get("event_id"),
                "error": item.get("error"),
            }
        )
    return {
        "status": data.get("status") or ("ok" if data.get("ok") else "failed"),
        "scheduled": int(data.get("scheduled") or 0),
        "total": len(slots),
        "results": results,
        "mode": "batch_browser",
    }


def run_batch_schedule(
    *,
    slots: list[tuple[datetime, datetime]],
    attendee_emails: list[str],
    subject_prefix: str = "Daily Review Agent — sync",
    force: bool = True,
    use_batch_browser: bool = True,
    replace_existing: bool = True,
    playwright_only: bool = True,
) -> dict[str, Any]:
    cfg = load_agent_config()
    people = [{"email": e.strip(), "name": ""} for e in attendee_emails if e.strip()]

    auto_backends = {"auto", "playwright_outlook", "playwright", "playwright_mcp", "browser", "outlook_web"}
    if use_batch_browser and (cfg.calendar_backend or "auto").strip().lower() in auto_backends:
        pw_result = _run_batch_via_playwright(
            slots=slots,
            people=people,
            subject_prefix=subject_prefix,
            replace_existing=replace_existing,
            timezone=cfg.timezone,
        )
        if pw_result and pw_result.get("verified"):
            return pw_result
        if pw_result and pw_result.get("status") == "ok":
            return pw_result
        if playwright_only:
            pw_result = pw_result or {"status": "failed", "scheduled": 0, "total": len(slots)}
            pw_result.setdefault("mode", "playwright_outlook")
            pw_result.setdefault(
                "error",
                "Playwright batch failed — sign in to Outlook web in the agent Edge profile once, then retry. "
                "Do not fall back to other backends for batch (avoids duplicate invites).",
            )
            return pw_result

        browser_result = _run_batch_via_browser(slots=slots, people=people, subject_prefix=subject_prefix)
        if browser_result and browser_result.get("scheduled", 0) > 0:
            return browser_result
        if browser_result and browser_result.get("status") == "ok":
            return browser_result

    results: list[dict[str, Any]] = []
    ok_count = 0

    for idx, (start, end) in enumerate(slots, start=1):
        subject = f"{subject_prefix} #{idx}"
        body = f"Pilot batch call {idx} of {len(slots)} — Daily Review Agent multi-backend test."
        schedule = schedule_with_fallback(
            cfg,
            subject=subject,
            body_text=body,
            start=start,
            end=end,
            attendee_emails=people,
            dry_run=False,
        )
        entry = {
            "slot": idx,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "subject": subject,
            "ok": _verified_schedule(schedule) if schedule.get("ok") else False,
            "backend": schedule.get("backend"),
            "join_url": schedule.get("join_url"),
            "event_id": schedule.get("event_id"),
            "error": schedule.get("error"),
            "attempts": schedule.get("attempts"),
            "warning": schedule.get("warning"),
        }
        results.append(entry)
        if entry["ok"]:
            ok_count += 1

    return {
        "status": "ok" if ok_count == len(slots) else "partial" if ok_count else "failed",
        "scheduled": ok_count,
        "total": len(slots),
        "results": results,
        "mode": "fallback_chain",
    }


def build_evening_slots(
    *,
    date_str: str,
    start_hhmm: str,
    count: int,
    duration_minutes: int,
    timezone: str = "Asia/Kolkata",
) -> list[tuple[datetime, datetime]]:
    tz = ZoneInfo(timezone)
    hour, minute = (int(x) for x in start_hhmm.split(":"))
    base = datetime.fromisoformat(date_str).replace(hour=hour, minute=minute, tzinfo=tz)
    slots: list[tuple[datetime, datetime]] = []
    cursor = base
    for _ in range(count):
        end = cursor + timedelta(minutes=duration_minutes)
        slots.append((cursor, end))
        cursor = end
    return slots
