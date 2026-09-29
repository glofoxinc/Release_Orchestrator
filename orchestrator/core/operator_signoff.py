"""Operator sign-off — track one-time live checks after automated readiness passes."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import config

APP_DIR = os.path.dirname(os.path.abspath(__file__))

SIGNOFF_SHIPIT_DRY_RUN = "shipit_dry_run"
SIGNOFF_SLACK_LIVE = "slack_live_confirm"

REQUIRED_SIGNOFFS: tuple[str, ...] = (SIGNOFF_SHIPIT_DRY_RUN, SIGNOFF_SLACK_LIVE)


def signoff_path(app_dir: str | None = None) -> str:
    root = app_dir if app_dir is not None else APP_DIR
    ws = config.active_workspace_name()
    if ws:
        ws_dir = os.path.join(root, "workspaces", ws)
        os.makedirs(ws_dir, exist_ok=True)
        return os.path.join(ws_dir, ".operator_signoff.json")
    return os.path.join(root, ".operator_signoff.json")


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
    if key not in REQUIRED_SIGNOFFS:
        return {
            "ok": False,
            "error": f"Unknown signoff '{key}'. Use: {', '.join(REQUIRED_SIGNOFFS)}",
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


def signoff_status(path: str | None = None) -> dict[str, Any]:
    """Summary for production readiness and launch scripts."""
    state = load_signoffs(path)
    signoffs = state.get("signoffs") or {}
    missing = [k for k in REQUIRED_SIGNOFFS if k not in signoffs]
    return {
        "shipit_dry_run": SIGNOFF_SHIPIT_DRY_RUN in signoffs,
        "slack_live_confirm": SIGNOFF_SLACK_LIVE in signoffs,
        "launch_complete": not missing,
        "missing": missing,
        "signoffs": signoffs,
        "updated_at": state.get("updated_at"),
    }


__all__ = [
    "REQUIRED_SIGNOFFS",
    "SIGNOFF_SHIPIT_DRY_RUN",
    "SIGNOFF_SLACK_LIVE",
    "is_signed_off",
    "load_signoffs",
    "record_signoff",
    "signoff_path",
    "signoff_status",
]
