"""Operator sign-off — track one-time live checks after automated readiness passes."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import config
from orchestrator.paths import operator_signoff_path as _canonical_signoff_path

SIGNOFF_SHIPIT_DRY_RUN = "shipit_dry_run"
SIGNOFF_SLACK_LIVE = "slack_live_confirm"
SIGNOFF_DAILY_REVIEW_PILOT = "daily_review_pilot"
SIGNOFF_ONBOARDING_COMPLETE = "onboarding_complete"

REQUIRED_SIGNOFFS: tuple[str, ...] = (SIGNOFF_SHIPIT_DRY_RUN, SIGNOFF_SLACK_LIVE)
ALL_SIGNOFF_IDS: tuple[str, ...] = REQUIRED_SIGNOFFS + (SIGNOFF_DAILY_REVIEW_PILOT, SIGNOFF_ONBOARDING_COMPLETE)


def signoff_path(app_dir: str | None = None) -> str:
    if app_dir is not None:
        root = app_dir
        ws = config.active_workspace_name()
        if ws:
            ws_dir = os.path.join(root, "workspaces", ws)
            os.makedirs(ws_dir, exist_ok=True)
            return os.path.join(ws_dir, "operator_signoff.json")
        return os.path.join(root, "operator_signoff.json")
    ws = config.active_workspace_name()
    path = _canonical_signoff_path(workspace_name=ws or None)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def load_signoffs(path: str | None = None) -> dict[str, Any]:
    target = path if path is not None else signoff_path()
    if not os.path.isfile(target):
        return {"signoffs": {}, "updated_at": None}
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {"signoffs": {}, "updated_at": None}
    if not isinstance(data, dict):
        return {"signoffs": {}, "updated_at": None}
    signoffs = data.get("signoffs")
    if not isinstance(signoffs, dict):
        signoffs = {}
    return {"signoffs": signoffs, "updated_at": data.get("updated_at")}


def record_signoff(
    signoff_id: str,
    *,
    detail: str = "",
    path: str | None = None,
) -> dict[str, Any]:
    """Mark a one-time operator check complete (persisted per workspace)."""
    key = str(signoff_id or "").strip()
    if key not in ALL_SIGNOFF_IDS:
        return {
            "ok": False,
            "error": f"Unknown signoff '{key}'. Use: {', '.join(ALL_SIGNOFF_IDS)}",
        }
    target = path if path is not None else signoff_path()
    state = load_signoffs(target)
    signoffs = dict(state.get("signoffs") or {})
    signoffs[key] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "detail": str(detail or "").strip(),
    }
    payload = {
        "signoffs": signoffs,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return {"ok": True, "signoff_id": key, "signoffs": signoffs}


def is_signed_off(signoff_id: str, path: str | None = None) -> bool:
    state = load_signoffs(path)
    return signoff_id in (state.get("signoffs") or {})


def required_signoffs_for_track(track: str = "release") -> tuple[str, ...]:
    """Release sign-offs; Daily Review pilot when track includes DR."""
    required = list(REQUIRED_SIGNOFFS)
    if track in {"daily_review", "both"}:
        required.append(SIGNOFF_DAILY_REVIEW_PILOT)
    return tuple(required)


def signoff_status(path: str | None = None, *, track: str = "release") -> dict[str, Any]:
    """Summary for production readiness and launch scripts."""
    state = load_signoffs(path)
    signoffs = state.get("signoffs") or {}
    required = required_signoffs_for_track(track)
    missing = [k for k in required if k not in signoffs]
    return {
        "track": track,
        "shipit_dry_run": SIGNOFF_SHIPIT_DRY_RUN in signoffs,
        "slack_live_confirm": SIGNOFF_SLACK_LIVE in signoffs,
        "daily_review_pilot": SIGNOFF_DAILY_REVIEW_PILOT in signoffs,
        "launch_complete": not missing,
        "launch_complete_for_track": not missing,
        "missing": missing,
        "signoffs": signoffs,
        "updated_at": state.get("updated_at"),
    }


__all__ = [
    "ALL_SIGNOFF_IDS",
    "REQUIRED_SIGNOFFS",
    "SIGNOFF_DAILY_REVIEW_PILOT",
    "SIGNOFF_SHIPIT_DRY_RUN",
    "SIGNOFF_SLACK_LIVE",
    "is_signed_off",
    "load_signoffs",
    "record_signoff",
    "required_signoffs_for_track",
    "signoff_path",
    "signoff_status",
]
