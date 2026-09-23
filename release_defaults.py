"""Team-level release defaults — last deployment window, saved once per workspace."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, time
from typing import Any

import config

logger = logging.getLogger(__name__)

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def defaults_path(app_dir: str | None = None) -> str:
    root = app_dir if app_dir is not None else APP_DIR
    ws = config.active_workspace_name()
    if ws:
        ws_dir = os.path.join(root, "workspaces", ws)
        os.makedirs(ws_dir, exist_ok=True)
        return os.path.join(ws_dir, ".release_defaults.json")
    return os.path.join(root, ".release_defaults.json")


def _serialize_time(value: time) -> str:
    return value.strftime("%H:%M:%S")


def _parse_time(raw: str) -> time:
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return time(10, 0)


def save_last_schedule_window(
    *,
    start_date: date,
    start_time: time,
    end_date: date,
    end_time: time,
    timezone_name: str,
    path: str | None = None,
) -> None:
    """Remember the last TCKT deployment window for one-click reuse."""
    payload = {
        "start_date": start_date.isoformat(),
        "start_time": _serialize_time(start_time),
        "end_date": end_date.isoformat(),
        "end_time": _serialize_time(end_time),
        "timezone_name": timezone_name,
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }
    target = path if path is not None else defaults_path()
    existing: dict[str, Any] = {}
    if os.path.isfile(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                existing = raw
        except (json.JSONDecodeError, OSError):
            pass
    existing["last_schedule_window"] = payload
    with open(target, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def load_last_schedule_window(path: str | None = None) -> dict[str, Any] | None:
    target = path if path is not None else defaults_path()
    if not os.path.isfile(target):
        return None
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    window = data.get("last_schedule_window")
    if not isinstance(window, dict):
        return None
    try:
        return {
            "start_date": date.fromisoformat(str(window["start_date"])),
            "start_time": _parse_time(str(window.get("start_time") or "10:00")),
            "end_date": date.fromisoformat(str(window["end_date"])),
            "end_time": _parse_time(str(window.get("end_time") or "11:30")),
            "timezone_name": str(window.get("timezone_name") or config.TCKT_SCHEDULE_TZ),
        }
    except (KeyError, ValueError, TypeError):
        return None


def default_deployment_schedule(profile_key: str = "normal") -> dict[str, Any]:
    """Default SHIPIT window: **10:30–11:30 AM IST**, stored in Jira as CST/CDT.

    Times in ``start_time`` / ``end_time`` are in ``source_timezone`` (IST).
    Jira planned start/end fields use ``store_timezone`` (America/Chicago).
    """
    import schedule_time as stz

    profiles = deployment_profiles()
    profile = profiles.get(profile_key) if isinstance(profiles, dict) else None
    sched = profile.get("schedule") if isinstance(profile, dict) else None
    if not isinstance(sched, dict):
        sched = {}
    source_tz = str(
        sched.get("source_timezone")
        or getattr(config, "TCKT_SCHEDULE_SOURCE_TZ", "")
        or stz.DEFAULT_SOURCE_TZ
    ).strip()
    store_tz = str(config.TCKT_SCHEDULE_TZ or stz.DEFAULT_STORE_TZ).strip()
    return {
        "start_time": _parse_time(str(sched.get("start_time") or "10:30")),
        "end_time": _parse_time(str(sched.get("end_time") or "11:30")),
        "source_timezone": source_tz,
        "store_timezone": store_tz,
        "display_timezone": str(config.TCKT_DISPLAY_TZ or store_tz).strip(),
        # Times below are in source_timezone (IST); legacy key for UI session.
        "timezone_name": source_tz,
        "profile_key": profile_key,
        "profile_label": str((profile or {}).get("label") or profile_key),
    }


def deployment_profiles() -> dict[str, dict[str, Any]]:
    """Return configured TCKT deployment profiles (Normal / Emergency, etc.)."""
    sd = getattr(config, "SERVICE_DESK", {}) or {}
    if not isinstance(sd, dict):
        return {}
    profiles = sd.get("deployment_profiles") or {}
    return profiles if isinstance(profiles, dict) else {}


__all__ = [
    "defaults_path",
    "default_deployment_schedule",
    "deployment_profiles",
    "load_last_schedule_window",
    "save_last_schedule_window",
]
