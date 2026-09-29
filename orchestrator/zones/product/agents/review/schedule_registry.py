"""Persist optional auto-schedule window (legacy opt-in — default is on-demand only)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_STATE = Path(__file__).resolve().parent / ".state" / "schedule.json"


def load_schedule() -> dict[str, Any]:
    if not _STATE.is_file():
        return {}
    try:
        raw = json.loads(_STATE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_schedule(data: dict[str, Any]) -> dict[str, Any]:
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return data


def schedule_for_weeks(
    *,
    weeks: int,
    timezone: str = "Asia/Kolkata",
    run_at: str = "18:00",
) -> dict[str, Any]:
    """Register daily review for N weeks from today (inclusive)."""
    tz = ZoneInfo(timezone)
    today = datetime.now(tz).date()
    end = today + timedelta(days=max(1, weeks) * 7)
    payload = {
        "active_from": today.isoformat(),
        "active_until": end.isoformat(),
        "run_at": run_at,
        "timezone": timezone,
        "weeks": weeks,
        "created_at": datetime.now(tz).isoformat(),
    }
    save_schedule(payload)
    return payload


def schedule_is_active(*, timezone: str = "Asia/Kolkata") -> bool:
    """Opt-in only — False when no schedule.json (on-demand mode default)."""
    data = load_schedule()
    if not data:
        return False
    until_raw = str(data.get("active_until") or "").strip()
    if not until_raw:
        return True
    try:
        until = date.fromisoformat(until_raw)
    except ValueError:
        return True
    today = datetime.now(ZoneInfo(timezone)).date()
    start_raw = str(data.get("active_from") or "").strip()
    if start_raw:
        try:
            start = date.fromisoformat(start_raw)
            if today < start:
                return False
        except ValueError:
            pass
    return today <= until


def clear_schedule() -> None:
    if _STATE.is_file():
        _STATE.unlink()


def schedule_status() -> dict[str, Any]:
    data = load_schedule()
    return {
        "configured": bool(data),
        "active": schedule_is_active(timezone=str(data.get("timezone") or "Asia/Kolkata")),
        "schedule": data,
    }
