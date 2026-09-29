"""Persist Release Deployer draft state for single-user desktop restart recovery.

Streamlit session state is lost on process restart. This module writes a small
JSON draft (workspace-scoped) so operators can resume filled deployment info
and ticket selection without re-entering everything.

No secrets are stored — only release identifiers, filled deploy fields, and
already-known SharePoint / TCKT references from the session.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, time, timezone
from typing import Any

import config
import team_scope
from orchestrator.paths import deploy_draft_path as _canonical_draft_path
from orchestrator.paths import deploy_draft_sidecar_path as _canonical_sidecar_path

logger = logging.getLogger(__name__)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DRAFT_SCHEMA_VERSION = 2

# Session keys safe to persist for desktop recovery.
_PERSIST_KEYS = (
    "wiz_step",
    "wiz_project",
    "wiz_project_idx",
    "wiz_release",
    "wiz_release_id",
    "wiz_filled",
    "wiz_force_deploy",
    "wiz_deploy_selected_keys",
    "shared_sharepoint_url",
    "stk_sharepoint",
    "stk_created_key",
    "stk_created_url",
    "stk_summary",
    "active_app",
)

PERSIST_KEYS: tuple[str, ...] = _PERSIST_KEYS


def draft_path(app_dir: str | None = None) -> str:
    """Return workspace-aware deploy draft path."""
    if app_dir is not None:
        root = app_dir
        ws = config.active_workspace_name()
        if ws:
            ws_dir = os.path.join(root, "workspaces", ws)
            os.makedirs(ws_dir, exist_ok=True)
            return os.path.join(ws_dir, "deploy_draft.json")
        return os.path.join(root, "deploy_draft.json")
    ws = config.active_workspace_name()
    path = _canonical_draft_path(workspace_name=ws or None)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def docx_sidecar_path(app_dir: str | None = None) -> str:
    """Binary sidecar for large rn_docx_bytes (kept out of JSON draft)."""
    if app_dir is not None:
        return draft_path(app_dir).replace("deploy_draft.json", "deploy_draft.rn_docx.bin")
    ws = config.active_workspace_name()
    path = _canonical_sidecar_path(workspace_name=ws or None)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _write_docx_sidecar(data: bytes, app_dir: str | None = None) -> str:
    path = docx_sidecar_path(app_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def _read_docx_sidecar(path: str) -> bytes | None:
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return handle.read()


def _serialize_value(value: Any, *, key: str = "") -> Any:
    if key == "rn_docx_bytes" and isinstance(value, bytes):
        return {"__docx_sidecar__": _write_docx_sidecar(value)}
    if isinstance(value, bytes):
        import base64

        return {"__bytes_b64__": base64.b64encode(value).decode("ascii")}
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _serialize_value(value.to_dict())
    if isinstance(value, set):
        return sorted(str(v) for v in value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Skip non-JSON Streamlit widgets / custom objects.
    return None


def build_draft_from_mapping(state: dict[str, Any]) -> dict[str, Any]:
    """Extract a JSON-safe draft payload from a session-like mapping."""
    payload: dict[str, Any] = {
        "schema_version": DRAFT_SCHEMA_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "workspace": config.active_workspace_name() or "",
        "scope_fingerprints": team_scope.collect_scope_fingerprints(),
    }
    for key in _PERSIST_KEYS:
        if key not in state:
            continue
        serialized = _serialize_value(state.get(key), key=key)
        if serialized is not None:
            payload[key] = serialized

    slack_results = state.get("stk_slack_results")
    if slack_results:
        try:
            from deployment_history import serialize_slack_results

            payload["stk_slack_results"] = serialize_slack_results(slack_results)
        except Exception:  # noqa: BLE001 — draft save must never crash UI
            logger.debug("Could not serialize slack results for draft", exc_info=True)
    return payload


def save_deploy_draft(state: dict[str, Any], path: str | None = None) -> str:
    """Persist draft from a session-like mapping. Delegates to release_session (single writer)."""
    import release_session as rs

    if path is not None and path != draft_path():
        return _save_deploy_draft_legacy(state, path)
    return rs.save_release_session(state)


def _save_deploy_draft_legacy(state: dict[str, Any], draft_file: str) -> str:
    """Write to an explicit path (tests only) with release_session merge."""
    payload = build_draft_from_mapping(state)
    if os.path.isfile(draft_file):
        try:
            with open(draft_file, encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict) and existing.get("release_session"):
                payload.setdefault("release_session", existing["release_session"])
        except (json.JSONDecodeError, OSError):
            pass
    import release_session as rs

    extra = rs._extract_extra(state)  # noqa: SLF001
    if extra:
        payload["release_session"] = {**(payload.get("release_session") or {}), **extra}
    has_substance = bool(
        payload.get("wiz_filled")
        or payload.get("wiz_release")
        or payload.get("release_session")
    )
    if not has_substance:
        clear_deploy_draft(draft_file)
        return draft_file
    os.makedirs(os.path.dirname(draft_file) or ".", exist_ok=True)
    with open(draft_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return draft_file


def load_deploy_draft(path: str | None = None) -> dict[str, Any] | None:
    """Load draft JSON or return None when missing/corrupt/scope-mismatch."""
    draft, _reason = load_deploy_draft_with_reason(path)
    return draft


def load_deploy_draft_with_reason(
    path: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Load draft; return (data, discard_reason). discard_reason empty when ok."""
    draft_file = path if path is not None else draft_path()
    if not os.path.isfile(draft_file):
        return None, ""
    try:
        with open(draft_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read deploy draft at %s: %s", draft_file, exc)
        return None, f"Could not read draft file ({exc})."
    if not isinstance(data, dict):
        return None, "Draft file is malformed."
    schema = int(data.get("schema_version") or 1)
    if schema < DRAFT_SCHEMA_VERSION:
        logger.info(
            "Deploy draft schema v%s — skipping scope fingerprint check (will upgrade on save)",
            schema,
        )
        return data, ""
    warnings: list[str] = []
    saved_ws = str(data.get("workspace") or "").strip()
    current_ws = config.active_workspace_name() or ""
    if saved_ws and current_ws and saved_ws != current_ws:
        warnings.append(
            f"Draft was saved under workspace '{saved_ws}' (now using '{current_ws}')."
        )

    stored_fp = data.get("scope_fingerprints") or {}
    matches, changed = team_scope.snapshot_scope_matches(
        stored_fp if isinstance(stored_fp, dict) else {},
        lenient=True,
    )
    if not matches:
        scope_msg = (
            "Team scope changed for: "
            + ", ".join(changed)
            + ". Release Notes / SHIPIT draft was still loaded — re-validate tickets in "
            "Ticket Review before deploy."
        )
        logger.warning("Deploy draft scope drift — %s", scope_msg)
        warnings.append(scope_msg)

    reason = " ".join(warnings).strip()
    if not matches and changed:
        data["_scope_restore_blocked"] = True
        data["_scope_restore_changed"] = list(changed)
    return data, reason


def deserialize_persisted_value(key: str, value: Any) -> Any:
    """Restore special serialized types from draft JSON."""
    if key == "rn_docx_bytes":
        if isinstance(value, dict) and "__docx_sidecar__" in value:
            data = _read_docx_sidecar(str(value["__docx_sidecar__"]))
            return data if data is not None else b""
        if isinstance(value, dict) and "__bytes_b64__" in value:
            import base64

            return base64.b64decode(value["__bytes_b64__"])
    if key in ("tr_selected_keys", "rn_selected_keys", "wiz_deploy_selected_keys"):
        if isinstance(value, list):
            return set(value)
    return value


def apply_deploy_draft(state: dict[str, Any], draft: dict[str, Any]) -> list[str]:
    """Apply draft fields onto a mutable session-like mapping. Returns restored keys."""
    restored: list[str] = []
    for key in _PERSIST_KEYS:
        if key not in draft:
            continue
        value = deserialize_persisted_value(key, draft[key])
        state[key] = value
        restored.append(key)
    if "stk_slack_results" in draft and isinstance(draft["stk_slack_results"], list):
        state["stk_slack_results"] = draft["stk_slack_results"]
        restored.append("stk_slack_results")
    state["wiz_draft_restored_at"] = draft.get("saved_at") or datetime.now(timezone.utc).isoformat()
    return restored


def clear_deploy_draft(path: str | None = None) -> None:
    """Delete the draft file and DOCX sidecar when present."""
    draft_file = path if path is not None else draft_path()
    sidecar = draft_file.replace(".deploy_draft.json", ".rn_docx.bin")
    try:
        if os.path.isfile(draft_file):
            os.remove(draft_file)
        if os.path.isfile(sidecar):
            os.remove(sidecar)
    except OSError as exc:
        logger.warning("Could not clear deploy draft %s: %s", draft_file, exc)
