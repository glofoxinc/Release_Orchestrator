"""Persist welcome-onboard progress (team crew draft) between chat turns."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from orchestrator.paths import ONBOARDING_STATE_FILE

_override: Path | None = None


def _state_path() -> Path:
    return _override or ONBOARDING_STATE_FILE


def set_state_path_override(path: Path | None) -> None:
    global _override
    _override = path


def load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def merge_state(updates: dict[str, Any]) -> dict[str, Any]:
    state = load_state()
    for key, value in updates.items():
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
    save_state(state)
    return state


def clear_state() -> None:
    path = _state_path()
    if path.is_file():
        path.unlink(missing_ok=True)


def get_track() -> str | None:
    raw = str(load_state().get("onboarding_track") or "").strip().lower()
    if raw in {"release", "daily_review", "both"}:
        return raw
    return None


def set_track(track: str) -> dict[str, Any]:
    return merge_state({"onboarding_track": str(track).strip().lower()})


def manual_confirmed(step_id: str) -> bool:
    confirms = load_state().get("manual_confirms") or {}
    return bool(confirms.get(step_id))


def record_manual_confirm(step_id: str) -> dict[str, Any]:
    confirms = dict(load_state().get("manual_confirms") or {})
    confirms[str(step_id)] = True
    return merge_state({"manual_confirms": confirms})
