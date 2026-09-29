"""Workspace-aware deployment / release history JSON I/O (headless, no Streamlit).

Entries are backward-compatible: older records only had deploy comment stats.
New fields (SharePoint, TCKT, Slack outcomes, per-project results, mark-released)
are optional and ignored by older readers.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import config
from orchestrator.paths import deployment_history_path as _canonical_history_path

logger = logging.getLogger(__name__)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_MAX_ENTRIES = 200


class HistoryLoadError(Exception):
    """Raised when the history file exists but cannot be parsed as a list."""

    def __init__(self, path: str, message: str):
        self.path = path
        super().__init__(message)


def history_path(app_dir: str | None = None) -> str:
    """Return workspace-aware history file path."""
    if app_dir is not None:
        root = app_dir
        ws = config.active_workspace_name()
        if ws:
            ws_dir = os.path.join(root, "workspaces", ws)
            os.makedirs(ws_dir, exist_ok=True)
            return os.path.join(ws_dir, "deployment_history.json")
        return os.path.join(root, "deployment_history.json")
    ws = config.active_workspace_name()
    path = _canonical_history_path(workspace_name=ws or None)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def load_history(path: str | None = None) -> list[dict]:
    """Load deployment history. Missing file → ``[]``. Corrupt file → ``HistoryLoadError``."""
    hist_path = path if path is not None else history_path()
    if not os.path.exists(hist_path):
        return []
    try:
        with open(hist_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.error("Could not read deployment history at %s: %s", hist_path, exc)
        raise HistoryLoadError(
            hist_path,
            f"Deployment history could not be read from `{hist_path}` ({exc}). "
            "Existing records are still on disk — fix or restore the file to see them.",
        ) from exc
    if not isinstance(data, list):
        logger.error(
            "Deployment history at %s is %s, expected a list",
            hist_path,
            type(data).__name__,
        )
        raise HistoryLoadError(
            hist_path,
            f"Deployment history at `{hist_path}` is malformed (expected a list). Existing records are still on disk.",
        )
    return data


def _write_history(history: list[dict], hist_path: str) -> None:
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(history[:HISTORY_MAX_ENTRIES], f, indent=2)


def serialize_slack_results(results: Any) -> list[dict[str, Any]]:
    """Normalize Slack send results (objects or dicts) for JSON history."""
    out: list[dict[str, Any]] = []
    if not results:
        return out
    for item in results:
        if isinstance(item, dict):
            out.append(
                {
                    "channel_name": str(item.get("channel_name") or item.get("channel") or ""),
                    "ok": bool(item.get("ok")),
                    "permalink": str(item.get("permalink") or ""),
                    "ts": str(item.get("ts") or ""),
                    "error": str(item.get("error") or ""),
                }
            )
            continue
        out.append(
            {
                "channel_name": str(getattr(item, "channel_name", "") or ""),
                "ok": bool(getattr(item, "ok", False)),
                "permalink": str(getattr(item, "permalink", "") or ""),
                "ts": str(getattr(item, "ts", "") or ""),
                "error": str(getattr(item, "error", "") or ""),
            }
        )
    return out


def normalize_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with stable defaults for optional fields."""
    normalized = dict(entry)
    normalized.setdefault("event", "deploy")
    normalized.setdefault("sharepoint_url", "")
    normalized.setdefault("tckt_key", "")
    normalized.setdefault("tckt_url", "")
    normalized.setdefault("slack_results", [])
    normalized.setdefault("project_results", [])
    normalized.setdefault("mark_released", None)
    normalized.setdefault("reverted", False)
    return normalized


def build_history_entry(
    *,
    project: str,
    version: str,
    clients: dict | None = None,
    success: int = 0,
    skipped: int = 0,
    errors: int = 0,
    undo_data: list | None = None,
    sharepoint_url: str | None = None,
    tckt_key: str | None = None,
    tckt_url: str | None = None,
    slack_results: Any = None,
    project_results: list[dict] | None = None,
    mark_released: dict | None = None,
    event: str = "deploy",
    timestamp: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a history record including optional release-audit fields."""
    entry: dict[str, Any] = {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "event": event,
        "project": project,
        "version": version,
        "clients": clients or {},
        "success": success,
        "skipped": skipped,
        "errors": errors,
        "undo_data": list(undo_data or []),
        "sharepoint_url": (sharepoint_url or "").strip(),
        "tckt_key": (tckt_key or "").strip(),
        "tckt_url": (tckt_url or "").strip(),
        "slack_results": serialize_slack_results(slack_results),
        "project_results": list(project_results or []),
        "mark_released": mark_released,
        "reverted": False,
    }
    if extra:
        for key, value in extra.items():
            if key in entry and value is None:
                continue
            entry[key] = value
    return entry


def save_history(entry: dict, path: str | None = None) -> None:
    """Prepend ``entry`` and persist at most ``HISTORY_MAX_ENTRIES`` records."""
    hist_path = path if path is not None else history_path()
    try:
        history = load_history(hist_path)
    except HistoryLoadError:
        history = []
    history.insert(0, normalize_history_entry(entry))
    _write_history(history, hist_path)


def update_history_entry(
    timestamp: str,
    updates: dict[str, Any],
    path: str | None = None,
) -> bool:
    """Merge ``updates`` into the entry matching ``timestamp``. Returns True if updated."""
    if not timestamp:
        return False
    hist_path = path if path is not None else history_path()
    try:
        history = load_history(hist_path)
    except HistoryLoadError:
        return False
    updated = False
    for entry in history:
        if entry.get("timestamp") != timestamp:
            continue
        for key, value in updates.items():
            if key == "slack_results":
                entry[key] = serialize_slack_results(value)
            elif key == "project_results" and isinstance(value, list):
                # Merge by project key when possible.
                existing = {
                    str(p.get("project") or ""): dict(p)
                    for p in (entry.get("project_results") or [])
                    if isinstance(p, dict)
                }
                for proj in value:
                    if not isinstance(proj, dict):
                        continue
                    pk = str(proj.get("project") or "")
                    if pk and pk in existing:
                        existing[pk].update(proj)
                    elif pk:
                        existing[pk] = dict(proj)
                    else:
                        existing[f"_anon_{len(existing)}"] = dict(proj)
                entry["project_results"] = list(existing.values())
            else:
                entry[key] = value
        updated = True
        break
    if updated:
        _write_history(history, hist_path)
    return updated


def record_mark_released(
    timestamp: str,
    *,
    version_id: str,
    version_name: str = "",
    status: str = "released",
    path: str | None = None,
) -> bool:
    """Attach mark-released outcome to an existing history entry."""
    return update_history_entry(
        timestamp,
        {
            "mark_released": {
                "version_id": version_id,
                "version_name": version_name,
                "status": status,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        },
        path=path,
    )


def mark_history_entry_reverted(timestamp: str, path: str | None = None) -> bool:
    """Mark a deployment history record as undone. Returns True if a record was updated."""
    hist_path = path if path is not None else history_path()
    try:
        history = load_history(hist_path)
    except HistoryLoadError:
        return False
    updated = False
    for entry in history:
        if entry.get("timestamp") == timestamp:
            entry["reverted"] = True
            entry["success"] = 0
            entry["reverted_at"] = datetime.now(timezone.utc).isoformat()
            # Keep per-project undo markers when present.
            projects = entry.get("project_results") or []
            if isinstance(projects, list):
                for proj in projects:
                    if isinstance(proj, dict):
                        proj["reverted"] = True
            updated = True
            break
    if updated:
        _write_history(history, hist_path)
    return updated
