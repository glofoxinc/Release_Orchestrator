"""Safe deploy / review dates + cached company holidays (Outlook/Playwright).

MCP never waits on Outlook. Playwright/Graph refresh is a background handoff.
Review may land on Friday; deploy never does, and never the day before a day off.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from orchestrator.paths import STATE_DIR

TZ_NAME = "Asia/Kolkata"
CACHE_FILE = STATE_DIR / "company_holidays.json"
OUTLOOK_CALENDAR_URL = "https://outlook.cloud.microsoft/calendar/view/month"


def _parse_day(raw: str) -> date | None:
    text = (raw or "").strip()[:10]
    if len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def load_holiday_cache(path: Path | None = None) -> set[date]:
    target = path or CACHE_FILE
    if not target.is_file():
        return set()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    days = data.get("holidays") if isinstance(data, dict) else data
    out: set[date] = set()
    if isinstance(days, list):
        for item in days:
            parsed = _parse_day(str(item))
            if parsed:
                out.add(parsed)
    return out


def save_holiday_cache(days: set[date] | list[date], path: Path | None = None) -> Path:
    target = path or CACHE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timezone": TZ_NAME,
        "shared_for": ["glofox", "ignite"],
        "holidays": sorted(d.isoformat() for d in days),
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def remember_extra_day_off(day: date, path: Path | None = None) -> set[date]:
    holidays = load_holiday_cache(path)
    holidays.add(day)
    save_holiday_cache(holidays, path)
    return holidays


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def is_company_off(day: date, holidays: set[date] | None = None) -> bool:
    offs = holidays if holidays is not None else load_holiday_cache()
    return is_weekend(day) or day in offs


def is_safe_deploy_day(day: date, holidays: set[date] | None = None) -> bool:
    """Working Mon–Thu whose next calendar day is also a workday. Never Friday."""
    offs = holidays if holidays is not None else load_holiday_cache()
    if day.weekday() == 4:
        return False
    if is_company_off(day, offs):
        return False
    return not is_company_off(day + timedelta(days=1), offs)


def next_workday(after: date, holidays: set[date] | None = None) -> date:
    """First workday strictly after *after* (Friday is allowed)."""
    offs = holidays if holidays is not None else load_holiday_cache()
    candidate = after + timedelta(days=1)
    for _ in range(14):
        if not is_company_off(candidate, offs):
            return candidate
        candidate += timedelta(days=1)
    return candidate


def next_safe_deploy_day(after: date, holidays: set[date] | None = None) -> date:
    """First safe deploy day strictly after *after*."""
    offs = holidays if holidays is not None else load_holiday_cache()
    candidate = after + timedelta(days=1)
    for _ in range(21):
        if is_safe_deploy_day(candidate, offs):
            return candidate
        candidate += timedelta(days=1)
    return candidate


def propose_release_dates(
    *,
    today: date | None = None,
    holidays: set[date] | None = None,
) -> dict[str, Any]:
    """Dates for this run + reasons. Uses cache only (no Outlook wait)."""
    day = today or date.today()
    offs = holidays if holidays is not None else load_holiday_cache()
    review = next_workday(day, offs)
    deploy = next_safe_deploy_day(day, offs)
    reasons: list[str] = []
    if review != day + timedelta(days=1):
        reasons.append(f"Review skipped a day off after {day.isoformat()}.")
    if deploy.weekday() == 0 and day.weekday() >= 3:
        reasons.append("Deploy moved to Monday (no Friday ships / day before a day off).")
    if deploy != next_workday(day, offs):
        reasons.append(
            f"Deploy is {deploy.isoformat()} — needs the following day in office too."
        )
    return {
        "ok": True,
        "timezone": TZ_NAME,
        "today": day.isoformat(),
        "review_day": review.isoformat(),
        "deploy_day": deploy.isoformat(),
        "review_allows_friday": True,
        "holidays_cached": sorted(d.isoformat() for d in offs),
        "cache_path": str(CACHE_FILE),
        "reasons": reasons,
        "confirm_prompt": (
            f"Review {review.isoformat()} · Deploy {deploy.isoformat()} (IST). "
            "Any extra company day off not on the calendar?"
        ),
        "playwright_handoff": outlook_holiday_handoff(),
    }


def outlook_holiday_handoff() -> dict[str, Any]:
    """Non-blocking Playwright/Outlook steps to refresh the shared holiday cache."""
    return {
        "slow_path": False,
        "note": (
            "Do this in the background. MCP tools keep using the last cache. "
            "Glofox and Ignite share this company calendar."
        ),
        "mcp": "playwright",
        "steps": [
            {
                "order": 1,
                "title": "Open Outlook month calendar",
                "mcp_tool": "browser_navigate",
                "arguments": {"url": OUTLOOK_CALENDAR_URL},
            },
            {
                "order": 2,
                "title": "Read company holiday / all-day events",
                "mcp_tool": "browser_snapshot",
                "arguments": {},
                "operator_note": "Copy holiday dates into company_holidays.json or say the extra day off on confirm.",
            },
        ],
    }
