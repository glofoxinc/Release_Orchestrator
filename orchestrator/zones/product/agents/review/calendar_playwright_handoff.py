"""Playwright MCP handoff for Daily Review calendar scheduling.

Primary path (Cursor chat): agent executes these steps via **Playwright MCP**
(same pattern as SharePoint upload in browser_automation.py).

Unattended fallback: embedded Playwright → Outlook web (schedule_outlook_playwright.mjs)
when embedded_playwright_fallback_enabled is true (Task Scheduler only).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import browser_automation

CALENDAR_DAY_BASE = "https://outlook.cloud.microsoft/calendar/view/day"
DEFAULT_TZ = "Asia/Kolkata"


def _attendee_email(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("email") or "").strip()
    return str(getattr(entry, "email", None) or "").strip()


def _step(
    order: int,
    title: str,
    *,
    mcp_tool: str,
    arguments: dict[str, Any] | None = None,
    note: str = "",
) -> dict[str, Any]:
    return {
        "order": order,
        "title": title,
        "mcp": browser_automation.playwright_mcp(),
        "mcp_tool": mcp_tool,
        "arguments": arguments or {},
        "operator_note": note,
    }


def calendar_day_url(iso_or_day: str, *, timezone: str = DEFAULT_TZ) -> str:
    """Outlook web calendar day view URL for the meeting start date."""
    raw = (iso_or_day or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return f"{CALENDAR_DAY_BASE}/{raw}"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(timezone))
        day = dt.astimezone(ZoneInfo(timezone)).strftime("%Y-%m-%d")
        return f"{CALENDAR_DAY_BASE}/{day}"
    except ValueError:
        return CALENDAR_DAY_BASE


def _format_time12(iso: str, *, timezone: str = DEFAULT_TZ) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(timezone))
    text = dt.astimezone(ZoneInfo(timezone)).strftime("%I:%M %p")
    return text.lstrip("0") if text.startswith("0") else text


def build_daily_review_calendar_handoff(
    *,
    subject: str,
    start_iso: str,
    end_iso: str,
    attendees: list[dict[str, str]],
    body_text: str = "",
    timezone: str = DEFAULT_TZ,
    primary: bool = False,
) -> dict[str, Any]:
    """Return Playwright MCP steps to create one Outlook calendar meeting."""
    day_url = calendar_day_url(start_iso, timezone=timezone)
    try:
        start12 = _format_time12(start_iso, timezone=timezone)
        end12 = _format_time12(end_iso, timezone=timezone)
    except ValueError:
        start12 = start_iso
        end12 = end_iso

    emails = [email for a in attendees if (email := _attendee_email(a))]
    safe_subject = subject.replace("\\", "\\\\").replace("'", "\\'")
    attendee_list = ", ".join(emails)

    steps = [
        _step(
            1,
            "Open Outlook calendar (abcfitness.com)",
            mcp_tool="browser_navigate",
            arguments={"url": day_url},
            note="Sign in with abcfitness.com if redirected to login.microsoftonline.com.",
        ),
        _step(
            2,
            "Confirm calendar loaded",
            mcp_tool="browser_snapshot",
            arguments={},
            note="Look for **New event** button on the day view.",
        ),
        _step(
            3,
            "Open New event compose dialog",
            mcp_tool="browser_click",
            arguments={"element": "New event button", "ref": "use snapshot ref for New event"},
            note="Or use browser_run_code_unsafe to click getByRole('button', { name: /New event/i }).",
        ),
        _step(
            4,
            f"Set title: {subject}",
            mcp_tool="browser_type",
            arguments={
                "element": "Add title textbox",
                "ref": "use snapshot ref",
                "text": subject,
            },
        ),
        _step(
            5,
            f"Set time {start12} – {end12}",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event/i }).first();"
                    "  const dtBtn = dialog.getByRole('button', { name: /\\d{1,2}:\\d{2}.*-/i }).first();"
                    "  if (await dtBtn.count()) { await dtBtn.click(); await page.waitForTimeout(600); }"
                    f"  const start = page.getByRole('combobox', {{ name: 'Start time' }});"
                    f"  if (await start.count()) {{ await start.fill('{start12}'); await page.keyboard.press('Enter'); }}"
                    f"  const end = page.getByRole('combobox', {{ name: 'End time' }});"
                    f"  if (await end.count()) {{ await end.fill('{end12}'); await page.keyboard.press('Enter'); }}"
                    "  await page.keyboard.press('Escape');"
                    "  await page.keyboard.press('Escape');"
                    "  return 'times set';"
                    "}"
                ),
            },
            note="Close time picker with Escape if a backdrop blocks clicks.",
        ),
    ]

    order = 6
    for email in emails:
        local = email.split("@")[0]
        steps.append(
            _step(
                order,
                f"Add attendee: {email}",
                mcp_tool="browser_run_code_unsafe",
                arguments={
                    "code": (
                        "async (page) => {"
                        "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event/i }).first();"
                        "  const field = dialog.getByLabel(/Invite required attendees/i);"
                        "  await field.click({ force: true });"
                        f"  await page.keyboard.type('{email}', {{ delay: 20 }});"
                        "  await page.waitForTimeout(1200);"
                        f"  const opt = page.getByRole('option', {{ name: /{local}/i }}).first();"
                        "  if (await opt.count()) await opt.click();"
                        "  else await page.keyboard.press('Enter');"
                        "  return 'attendee added';"
                        "}"
                    ),
                },
            )
        )
        order += 1

    steps.extend(
        [
            _step(
                order,
                "Enable Teams meeting (if switch visible)",
                mcp_tool="browser_run_code_unsafe",
                arguments={
                    "code": (
                        "async (page) => {"
                        "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event/i }).first();"
                        "  const sw = dialog.getByRole('switch').first();"
                        "  if (await sw.count() && (await sw.getAttribute('aria-checked')) !== 'true') await sw.click();"
                        "  return 'teams toggle checked';"
                        "}"
                    ),
                },
            ),
            _step(
                order + 1,
                "Send invite",
                mcp_tool="browser_click",
                arguments={"element": "Send button", "ref": "use snapshot ref for Send"},
                note="Confirm invite appears on calendar before saying **calendar done**.",
            ),
        ]
    )

    mcp_name = browser_automation.playwright_mcp()
    if primary:
        instruction = (
            f"Schedule the Teams review call via **Playwright MCP** (`{mcp_name}`). "
            "Execute each step below in order. Sign in with abcfitness.com if redirected. "
            "When the invite is sent, say **calendar done**."
        )
        primary_path = f"Playwright MCP ({mcp_name}) — schedule review call / daily review live run"
        fallback_phrase = "schedule review call"
    else:
        instruction = (
            f"Embedded calendar scheduling failed. Execute each step below using "
            f"**Playwright MCP** (`{mcp_name}`). When the invite is sent, say **calendar done**."
        )
        primary_path = "embedded playwright_outlook (python -m daily_review_agent --outlook-login)"
        fallback_phrase = "daily review calendar playwright"

    return {
        "ok": True,
        "delivery": "cursor_playwright_mcp",
        "primary": primary,
        "mcp": mcp_name,
        "instruction": instruction,
        "meeting": {
            "subject": subject,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "start_display": start12,
            "end_display": end12,
            "attendees": emails,
            "body_preview": (body_text or "")[:500],
            "calendar_url": day_url,
        },
        "completion": {
            "user_phrases": ["calendar done", "meeting scheduled", "daily review calendar done"],
            "validate": "Subject visible on Outlook calendar; invite sent to all attendees.",
        },
        "steps": steps,
        "primary_path": primary_path,
        "fallback_phrase": fallback_phrase,
    }


def handoff_from_run_context(
    *,
    subject: str,
    start: datetime,
    end: datetime,
    attendees: list[dict[str, str]],
    body_text: str = "",
    timezone: str = DEFAULT_TZ,
    primary: bool = False,
) -> dict[str, Any]:
    """Build handoff from runner schedule context."""
    tz = ZoneInfo(timezone)
    start_aware = start if start.tzinfo else start.replace(tzinfo=tz)
    end_aware = end if end.tzinfo else end.replace(tzinfo=tz)
    return build_daily_review_calendar_handoff(
        subject=subject,
        start_iso=start_aware.isoformat(),
        end_iso=end_aware.isoformat(),
        attendees=attendees,
        body_text=body_text,
        timezone=timezone,
        primary=primary,
    )
