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
HANDOFF_VERSION = "2026.11.13-mcp-hardening"
HANDOFF_FEATURES = {
    "optional_row": True,
    "body_step": True,
    "start_date_step": True,
    "idempotency_step": True,
    "send_force": True,
    "tracking_pre_send": True,
}


def _attendee_email(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("email") or "").strip()
    return str(getattr(entry, "email", None) or "").strip()


def _attendee_type(entry: Any) -> str:
    if isinstance(entry, dict):
        raw = str(entry.get("type") or "required").strip().lower()
        return raw if raw in {"required", "optional"} else "required"
    raw = str(getattr(entry, "type", "required") or "required").strip().lower()
    return raw if raw in {"required", "optional"} else "required"


def _js_str(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")


def _ensure_optional_attendees_row_step(order: int) -> dict[str, Any]:
    """Outlook web hides optional attendees until Response options → Add optional."""
    return _step(
        order,
        "Show Invite optional attendees row",
        mcp_tool="browser_run_code_unsafe",
        arguments={
            "code": (
                "async (page) => {"
                "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event|Review call/i }).first();"
                "  const opt = dialog.locator('[aria-label*=\"optional attendees\" i]');"
                "  if (await opt.count()) return 'optional row visible';"
                "  await dialog.getByRole('button', { name: 'Response options' }).click();"
                "  await page.getByRole('menuitem', { name: /optional/i }).first().click();"
                "  await page.keyboard.press('Escape');"
                "  return 'optional row opened';"
                "}"
            ),
        },
        note="Required on edit: optional row is empty until expanded from Response options.",
    )


def _attendee_add_step(order: int, email: str, invite_type: str) -> dict[str, Any]:
    field_label = "Invite required attendees" if invite_type == "required" else "Invite optional attendees"
    local = email.split("@")[0].replace(".", "")
    return _step(
        order,
        f"Add {invite_type} attendee: {email}",
        mcp_tool="browser_run_code_unsafe",
        arguments={
            "code": (
                "async (page) => {"
                "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event|Review call/i }).first();"
                f"  const field = dialog.getByLabel(/{field_label}/i);"
                "  await field.click({ force: true });"
                "  await page.keyboard.press('End');"
                f"  await page.keyboard.type('; {_js_str(email)}', {{ delay: 15 }});"
                "  await page.waitForTimeout(1400);"
                f"  const opt = page.getByRole('option', {{ name: /{_js_str(local)}/i }}).first();"
                "  if (await opt.count()) await opt.click({ force: true });"
                "  else { await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter'); }"
                "  await page.waitForTimeout(400);"
                "  return 'attendee added';"
                "}"
            ),
        },
    )


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


def _format_start_date_us(iso: str, *, timezone: str = DEFAULT_TZ) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(timezone))
    local = dt.astimezone(ZoneInfo(timezone))
    return local.strftime("%m/%d/%Y")


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
        start_date_us = _format_start_date_us(start_iso, timezone=timezone)
    except ValueError:
        start12 = start_iso
        end12 = end_iso
        start_date_us = start_iso[:10]

    subject_js = _js_str(subject)
    required_emails = [
        email for a in attendees if (email := _attendee_email(a)) and _attendee_type(a) == "required"
    ]
    optional_emails = [
        email for a in attendees if (email := _attendee_email(a)) and _attendee_type(a) == "optional"
    ]
    emails = required_emails + optional_emails

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
            f"Idempotency: edit existing “{subject}” or New event",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    f"  const title = /{_js_str(subject.replace('/', '\\/'))}/i;"
                    "  const existing = page.getByText(title).first();"
                    "  if (await existing.count()) {"
                    "    await existing.click({ force: true });"
                    "    await page.waitForTimeout(1200);"
                    "    const edit = page.getByRole('button', { name: /Edit|Open/i }).first();"
                    "    if (await edit.count()) await edit.click({ force: true });"
                    "    return 'edit-existing';"
                    "  }"
                    "  await page.getByRole('button', { name: /New event/i }).click();"
                    "  await page.waitForTimeout(1000);"
                    "  return 'new-event';"
                    "}"
                ),
            },
            note="Avoid duplicate review calls on the same calendar day.",
        ),
        _step(
            4,
            f"Set title: {subject}",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event|Review call/i }).first();"
                    f"  await dialog.getByRole('textbox', {{ name: /Add title/i }}).fill('{subject_js}');"
                    "  return 'title set';"
                    "}"
                ),
            },
        ),
        _step(
            5,
            f"Set Start date {start_date_us}",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event|Review call/i }).first();"
                    "  const dtBtn = dialog.getByRole('button', { name: /\\d{1,2}\\/\\d{1,2}\\/\\d{4}/ }).first();"
                    "  if (await dtBtn.count()) { await dtBtn.click({ force: true }); await page.waitForTimeout(400); }"
                    f"  const startDate = page.getByRole('combobox', {{ name: 'Start date' }});"
                    f"  if (await startDate.count()) {{ await startDate.fill('{start_date_us}'); await page.keyboard.press('Enter'); }}"
                    "  await page.keyboard.press('Escape');"
                    "  return 'start date set';"
                    "}"
                ),
            },
            note="Locks calendar day — must match subject Review call MM/DD/YYYY.",
        ),
        _step(
            6,
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

    order = 7
    for email in required_emails:
        steps.append(_attendee_add_step(order, email, "required"))
        order += 1
    if optional_emails:
        steps.append(_ensure_optional_attendees_row_step(order))
        order += 1
    for email in optional_emails:
        steps.append(_attendee_add_step(order, email, "optional"))
        order += 1

    if (body_text or "").strip():
        body_js = _js_str(body_text.strip())
        steps.append(
            _step(
                order,
                "Set meeting agenda / description",
                mcp_tool="browser_run_code_unsafe",
                arguments={
                    "code": (
                        "async (page) => {"
                        "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event|Review call/i }).first();"
                        "  const body = dialog.getByRole('textbox', { name: /Event body/i });"
                        "  if (await body.count()) {"
                        f"    await body.fill('{body_js}');"
                        "  }"
                        "  return 'body set';"
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
                "Pre-send Tracking gate (verify roster before Send)",
                mcp_tool="browser_run_code_unsafe",
                arguments={
                    "code": (
                        "async (page) => {"
                        "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event|Review call/i }).first();"
                        "  await dialog.getByRole('button', { name: 'Tracking' }).click().catch(() => {});"
                        "  await page.waitForTimeout(800);"
                        "  return 'tracking opened';"
                        "}"
                    ),
                },
                note="Confirm required + optional names before Send — hard stop if roster incomplete.",
            ),
            _step(
                order + 1,
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
                order + 2,
                "Send invite (updates to all attendees on edit)",
                mcp_tool="browser_run_code_unsafe",
                arguments={
                    "code": (
                        "async (page) => {"
                        "  const dialog = page.locator('[role=\"document\"]').filter({ hasText: /New event|Edit event|Review call/i }).first();"
                        "  const teamsWait = page.getByRole('button', { name: /^Ok$/i });"
                        "  if (await teamsWait.count()) await teamsWait.click();"
                        "  await dialog.getByRole('button', { name: /^Send$/i }).first().click({ force: true });"
                        "  await page.waitForTimeout(1500);"
                        "  const all = page.getByRole('button', { name: /All attendees/i });"
                        "  if (await all.count()) await all.first().click({ force: true });"
                        "  return 'sent';"
                        "}"
                    ),
                },
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
        "handoff_version": HANDOFF_VERSION,
        "handoff_features": dict(HANDOFF_FEATURES),
        "primary": primary,
        "mcp": mcp_name,
        "instruction": instruction,
        "meeting": {
            "subject": subject,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "start_date": start_date_us,
            "start_display": start12,
            "end_display": end12,
            "attendees": emails,
            "required_attendees": required_emails,
            "optional_attendees": optional_emails,
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
