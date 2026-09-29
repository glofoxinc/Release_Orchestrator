"""Durable MCP wizard/workflow session persistence.

Sessions are stored as atomic JSON files under a workspace-scoped directory:
``workspaces/<active>/.mcp_wizard_sessions`` when a workspace is active, otherwise
``.mcp_wizard_sessions`` at the app root.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

SCHEMA_VERSION = 1

STATUS_ACTIVE = "active"
STATUS_CANCELLED = "cancelled"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

_VALID_STATUSES = frozenset({STATUS_ACTIVE, STATUS_CANCELLED, STATUS_COMPLETED, STATUS_FAILED})

_APP_DIR = Path(__file__).resolve().parent.parent
_SESSIONS_DIRNAME = ".mcp_wizard_sessions"
_SESSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_SEP = "."

# Optional override for tests (absolute path to the sessions directory).
_sessions_dir_override: Path | None = None
# Optional HMAC secret for confirmation tokens (tests may inject).
_token_secret_override: bytes | None = None


class WizardStoreError(Exception):
    """Base error for wizard session store operations."""


class SessionNotFoundError(WizardStoreError):
    """Raised when a session id does not exist."""


class SessionCorruptError(WizardStoreError):
    """Raised when session JSON cannot be parsed or fails schema checks."""


class InvalidSessionIdError(WizardStoreError):
    """Raised when a session id is unsafe or fails path checks."""


class ConfirmationConsumedError(WizardStoreError):
    """Raised when a confirmation token was already used or is missing."""


class TerminalSessionError(WizardStoreError):
    """Raised when a mutation is attempted on a closed workflow session."""


_TERMINAL_STATUSES = frozenset({STATUS_CANCELLED, STATUS_COMPLETED, STATUS_FAILED})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_slug(value: str, *, max_length: int = 64) -> str:
    """Normalize ``value`` into a filesystem-safe lowercase slug."""
    text = (value or "").strip().lower()
    text = _SLUG_RE.sub("-", text).strip("-_")
    if not text:
        text = "session"
    if len(text) > max_length:
        text = text[:max_length].rstrip("-_")
    if not _SESSION_ID_RE.match(text):
        text = "session"
    return text


def new_session_id(
    *,
    prefix: str = "wf",
    deterministic: str | None = None,
) -> str:
    """Create a safe session id.

    When ``deterministic`` is provided, the id is derived from a stable hash of
    that string (suitable for tests). Otherwise a random uuid4 fragment is used.
    """
    prefix_slug = safe_slug(prefix, max_length=24)
    if deterministic is not None:
        digest = hashlib.sha256(deterministic.encode("utf-8")).hexdigest()[:16]
        return f"{prefix_slug}-{digest}"
    return f"{prefix_slug}-{uuid.uuid4().hex[:16]}"


def set_sessions_dir_override(path: str | Path | None) -> None:
    """Override the sessions directory (tests). Pass ``None`` to clear."""
    global _sessions_dir_override
    _sessions_dir_override = Path(path).resolve() if path is not None else None


def set_token_secret_override(secret: bytes | str | None) -> None:
    """Override the confirmation-token HMAC secret (tests). Pass ``None`` to clear."""
    global _token_secret_override
    if secret is None:
        _token_secret_override = None
    elif isinstance(secret, bytes):
        _token_secret_override = secret
    else:
        _token_secret_override = secret.encode("utf-8")


def _validate_workspace_segment(name: str) -> str:
    """Accept a single workspace directory segment; reject traversal."""
    ws = (name or "").strip()
    if not ws or ws in {".", ".."} or "/" in ws or "\\" in ws or ".." in ws:
        raise InvalidSessionIdError(f"Unsafe workspace name: {name!r}")
    if Path(ws).name != ws:
        raise InvalidSessionIdError(f"Unsafe workspace name: {name!r}")
    return ws


def sessions_dir(*, app_dir: str | Path | None = None) -> Path:
    """Return the workspace-scoped sessions directory, creating it if needed."""
    if _sessions_dir_override is not None:
        path = _sessions_dir_override
        path.mkdir(parents=True, exist_ok=True)
        return path

    root = Path(app_dir) if app_dir is not None else _APP_DIR
    ws = (config.active_workspace_name() or "").strip()
    if ws:
        ws_name = _validate_workspace_segment(ws)
        path = root / "workspaces" / ws_name / _SESSIONS_DIRNAME
    else:
        path = root / _SESSIONS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(payload: Any) -> str:
    """Return a stable SHA-256 hex digest of ``payload``."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _token_secret() -> bytes:
    if _token_secret_override is not None:
        return _token_secret_override
    env = os.environ.get("JIRA_TOOLKIT_WIZARD_TOKEN_SECRET", "").strip()
    if env:
        return env.encode("utf-8")
    secret_path = sessions_dir() / ".confirmation_secret"
    try:
        value = secret_path.read_bytes()
        if value:
            return value
    except FileNotFoundError:
        pass
    value = secrets.token_bytes(32)
    try:
        with secret_path.open("xb") as handle:
            handle.write(value)
        return value
    except FileExistsError:
        return secret_path.read_bytes()


def mint_confirmation_token(
    workflow_id: str,
    step: str,
    preview_payload: Any,
    *,
    deterministic: bool = False,
    nonce: str | None = None,
) -> str:
    """Mint a confirmation token bound to workflow id, step, and preview payload.

    When ``deterministic`` is True (or ``nonce`` is provided), the nonce is stable
    so tests can assert exact tokens. Otherwise a random nonce is used.
    """
    preview_hash = content_hash(preview_payload)
    if nonce is not None:
        use_nonce = safe_slug(nonce, max_length=32)
    elif deterministic:
        use_nonce = content_hash({"workflow_id": workflow_id, "step": step, "preview": preview_hash})[:16]
    else:
        use_nonce = secrets.token_hex(8)

    material = _TOKEN_SEP.join(
        [
            safe_slug(workflow_id, max_length=64),
            safe_slug(step or "step", max_length=64),
            preview_hash,
            use_nonce,
        ]
    )
    sig = hmac.new(_token_secret(), material.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{material}{_TOKEN_SEP}{sig}"


def validate_confirmation_token(
    token: str,
    workflow_id: str,
    step: str,
    preview_payload: Any,
) -> bool:
    """Validate a token against workflow id, step, and preview payload."""
    if not token or not isinstance(token, str):
        return False
    parts = token.split(_TOKEN_SEP)
    if len(parts) != 5:
        return False
    wf_part, step_part, preview_part, nonce, sig = parts
    expected_wf = safe_slug(workflow_id, max_length=64)
    expected_step = safe_slug(step or "step", max_length=64)
    expected_preview = content_hash(preview_payload)
    if wf_part != expected_wf or step_part != expected_step or preview_part != expected_preview:
        return False
    material = _TOKEN_SEP.join([wf_part, step_part, preview_part, nonce])
    expected_sig = hmac.new(_token_secret(), material.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


def _validate_session_id(session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid or not _SESSION_ID_RE.match(sid):
        raise InvalidSessionIdError(f"Invalid session id: {session_id!r}")
    if ".." in sid or "/" in sid or "\\" in sid:
        raise InvalidSessionIdError(f"Invalid session id: {session_id!r}")
    return sid


def _session_path(session_id: str, *, directory: Path | None = None) -> Path:
    sid = _validate_session_id(session_id)
    base = directory if directory is not None else sessions_dir()
    base_resolved = base.resolve()
    path = (base_resolved / f"{sid}.json").resolve()
    try:
        path.relative_to(base_resolved)
    except ValueError as exc:
        raise InvalidSessionIdError(f"Path traversal blocked for session id: {session_id!r}") from exc
    return path


def _empty_session(
    session_id: str,
    workflow: str,
    *,
    step: str = "",
    inputs: dict[str, Any] | None = None,
    drafts: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    status: str = STATUS_ACTIVE,
) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "id": session_id,
        "workflow": workflow,
        "status": status,
        "step": step or "",
        "inputs": dict(inputs or {}),
        "drafts": dict(drafts or {}),
        "artifacts": dict(artifacts or {}),
        "confirmations": {},
        "audit": [
            {
                "at": now,
                "event": "created",
                "detail": {"workflow": workflow, "step": step or ""},
            }
        ],
        "created_at": now,
        "updated_at": now,
    }


def _normalize_loaded(data: Any, *, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SessionCorruptError(f"Session is not a JSON object: {path}")
    required = ("id", "workflow", "status", "schema_version")
    missing = [k for k in required if k not in data]
    if missing:
        raise SessionCorruptError(f"Session missing keys {missing}: {path}")
    data.setdefault("step", "")
    data.setdefault("inputs", {})
    data.setdefault("drafts", {})
    data.setdefault("artifacts", {})
    data.setdefault("confirmations", {})
    data.setdefault("audit", [])
    data.setdefault("created_at", _utc_now_iso())
    data.setdefault("updated_at", data["created_at"])
    if not isinstance(data["inputs"], dict):
        raise SessionCorruptError(f"Session inputs must be an object: {path}")
    if not isinstance(data["drafts"], dict):
        raise SessionCorruptError(f"Session drafts must be an object: {path}")
    if not isinstance(data["artifacts"], dict):
        raise SessionCorruptError(f"Session artifacts must be an object: {path}")
    if not isinstance(data["confirmations"], dict):
        raise SessionCorruptError(f"Session confirmations must be an object: {path}")
    if not isinstance(data["audit"], list):
        raise SessionCorruptError(f"Session audit must be a list: {path}")
    return data


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _replace_with_retry(tmp_path: Path, path: Path, *, attempts: int = 5) -> None:
    """Windows can briefly deny os.replace when antivirus/indexers hold the target."""
    import time

    last_err: OSError | None = None
    for attempt in range(attempts):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError as exc:
            last_err = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(0.05 * (attempt + 1))
    if last_err is not None:
        raise last_err
    os.replace(tmp_path, path)


def _append_audit(session: dict[str, Any], event: str, detail: dict[str, Any] | None = None) -> None:
    entry: dict[str, Any] = {"at": _utc_now_iso(), "event": event}
    if detail:
        entry["detail"] = detail
    audit = session.setdefault("audit", [])
    if not isinstance(audit, list):
        session["audit"] = [entry]
    else:
        audit.append(entry)


def _invalidate_step_confirmation(session: dict[str, Any], step: str | None = None) -> None:
    """Drop confirmation tokens for the given step (or current step)."""
    confirmations = session.setdefault("confirmations", {})
    if not isinstance(confirmations, dict):
        session["confirmations"] = {}
        return
    target = step if step is not None else str(session.get("step") or "")
    keys = [target, safe_slug(target or "step", max_length=64)]
    for key in keys:
        confirmations.pop(key, None)


def create_session(
    workflow: str,
    *,
    step: str = "",
    inputs: dict[str, Any] | None = None,
    drafts: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    session_id: str | None = None,
    deterministic: str | None = None,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Create and persist a new wizard session."""
    workflow_name = (workflow or "").strip()
    if not workflow_name:
        raise WizardStoreError("workflow is required")

    if session_id is not None:
        sid = _validate_session_id(safe_slug(session_id, max_length=128))
    else:
        sid = new_session_id(prefix=safe_slug(workflow_name, max_length=24), deterministic=deterministic)

    session = _empty_session(
        sid,
        workflow_name,
        step=step,
        inputs=inputs,
        drafts=drafts,
        artifacts=artifacts,
    )
    path = _session_path(sid, directory=directory)
    if path.exists():
        raise WizardStoreError(f"Session already exists: {sid}")
    _atomic_write_json(path, session)
    return session


def load_session(session_id: str, *, directory: Path | None = None) -> dict[str, Any]:
    """Load a session by id. Raises on missing or corrupt files."""
    path = _session_path(session_id, directory=directory)
    if not path.is_file():
        raise SessionNotFoundError(f"Session not found: {session_id}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except json.JSONDecodeError as exc:
        raise SessionCorruptError(f"Corrupted session JSON: {path}") from exc
    except OSError as exc:
        raise SessionCorruptError(f"Unable to read session: {path}") from exc
    return _normalize_loaded(raw, path=path)


def save_session(session: dict[str, Any], *, directory: Path | None = None) -> dict[str, Any]:
    """Persist an entire session document (atomic replace)."""
    if not isinstance(session, dict):
        raise WizardStoreError("session must be a dict")
    sid = _validate_session_id(str(session.get("id") or ""))
    session = dict(session)
    session["id"] = sid
    session["schema_version"] = int(session.get("schema_version") or SCHEMA_VERSION)
    session["updated_at"] = _utc_now_iso()
    if "confirmations" not in session or not isinstance(session["confirmations"], dict):
        session["confirmations"] = {}
    path = _session_path(sid, directory=directory)
    _atomic_write_json(path, session)
    return session


def update_session(
    session_id: str,
    *,
    step: str | None = None,
    status: str | None = None,
    inputs: dict[str, Any] | None = None,
    drafts: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    confirmations: dict[str, Any] | None = None,
    merge: bool = True,
    audit_event: str | None = None,
    audit_detail: dict[str, Any] | None = None,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Update fields on an existing session.

    Any update invalidates confirmation tokens for the affected step (previous
    step when step changes, otherwise the current step). Explicit
    ``confirmations`` values are applied after invalidation.
    """
    session = load_session(session_id, directory=directory)
    previous_step = str(session.get("step") or "")
    changed: dict[str, Any] = {}

    if status is not None:
        if status not in _VALID_STATUSES:
            raise WizardStoreError(f"Invalid status: {status!r}")
        session["status"] = status
        changed["status"] = status

    if step is not None:
        session["step"] = step
        changed["step"] = step

    if inputs is not None:
        if merge:
            merged = dict(session.get("inputs") or {})
            merged.update(inputs)
            session["inputs"] = merged
        else:
            session["inputs"] = dict(inputs)
        changed["inputs"] = True

    if drafts is not None:
        if merge:
            merged = dict(session.get("drafts") or {})
            merged.update(drafts)
            session["drafts"] = merged
        else:
            session["drafts"] = dict(drafts)
        changed["drafts"] = True

    if artifacts is not None:
        if merge:
            merged = dict(session.get("artifacts") or {})
            merged.update(artifacts)
            session["artifacts"] = merged
        else:
            session["artifacts"] = dict(artifacts)
        changed["artifacts"] = True

    # Any update invalidates the step confirmation token(s).
    _invalidate_step_confirmation(session, previous_step)
    if step is not None and step != previous_step:
        _invalidate_step_confirmation(session, step)

    if confirmations is not None:
        if merge:
            merged = dict(session.get("confirmations") or {})
            merged.update(confirmations)
            session["confirmations"] = merged
        else:
            session["confirmations"] = dict(confirmations)
        changed["confirmations"] = True

    event = audit_event or "updated"
    detail = dict(audit_detail or {})
    if changed and "changed" not in detail:
        detail["changed"] = sorted(changed.keys())
    _append_audit(session, event, detail or None)
    return save_session(session, directory=directory)


def list_sessions(
    *,
    workflow: str | None = None,
    status: str | None = None,
    directory: Path | None = None,
) -> list[dict[str, Any]]:
    """List sessions as summary dicts, newest ``updated_at`` first.

    Corrupted JSON files are skipped (not raised).
    """
    base = directory if directory is not None else sessions_dir()
    if not base.is_dir():
        return []

    summaries: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            session = _normalize_loaded(raw, path=path)
        except (OSError, json.JSONDecodeError, SessionCorruptError, WizardStoreError):
            continue

        if workflow is not None and session.get("workflow") != workflow:
            continue
        if status is not None and session.get("status") != status:
            continue

        summaries.append(
            {
                "id": session["id"],
                "workflow": session.get("workflow"),
                "status": session.get("status"),
                "step": session.get("step"),
                "created_at": session.get("created_at"),
                "updated_at": session.get("updated_at"),
                "schema_version": session.get("schema_version"),
            }
        )

    summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return summaries


def cancel_session(
    session_id: str,
    *,
    reason: str | None = None,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Mark a session cancelled and invalidate step confirmation tokens."""
    detail = {"reason": reason} if reason else None
    return update_session(
        session_id,
        status=STATUS_CANCELLED,
        audit_event="cancelled",
        audit_detail=detail,
        directory=directory,
    )


def delete_session(session_id: str, *, directory: Path | None = None) -> bool:
    """Delete a session file. Returns True if a file was removed."""
    path = _session_path(session_id, directory=directory)
    if not path.is_file():
        return False
    path.unlink()
    return True


def store_confirmation(
    session_id: str,
    step: str,
    preview_payload: Any,
    *,
    deterministic: bool = False,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Mint a confirmation token for ``step`` and persist it on the session."""
    session = load_session(session_id, directory=directory)
    token = mint_confirmation_token(
        session_id,
        step,
        preview_payload,
        deterministic=deterministic,
    )
    confirmations = dict(session.get("confirmations") or {})
    confirmations[step] = {
        "token": token,
        "preview_hash": content_hash(preview_payload),
        "minted_at": _utc_now_iso(),
    }
    return update_session(
        session_id,
        confirmations=confirmations,
        audit_event="confirmation_minted",
        audit_detail={"step": step},
        directory=directory,
    )


def check_confirmation(
    session_id: str,
    step: str,
    token: str,
    preview_payload: Any,
    *,
    directory: Path | None = None,
) -> bool:
    """Validate ``token`` against the session workflow/step/preview and stored value."""
    session = load_session(session_id, directory=directory)
    if not validate_confirmation_token(token, session_id, step, preview_payload):
        return False
    stored = (session.get("confirmations") or {}).get(step) or {}
    stored_token = stored.get("token") if isinstance(stored, dict) else None
    if not stored_token:
        return False
    if stored.get("consumed_at"):
        return False
    return hmac.compare_digest(str(stored_token), token)


def consume_confirmation(
    session_id: str,
    step: str,
    token: str,
    preview_payload: Any,
    *,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Validate and permanently consume a one-time confirmation token.

    Returns the updated session. Raises ``ConfirmationConsumedError`` when the
    token is missing, stale, already consumed, or does not match the preview.
    """
    session = load_session(session_id, directory=directory)
    if not check_confirmation(
        session_id,
        step,
        token,
        preview_payload,
        directory=directory,
    ):
        raise ConfirmationConsumedError(
            "Confirmation token is missing, stale, consumed, or does not match the latest preview."
        )
    confirmations = dict(session.get("confirmations") or {})
    entry = dict(confirmations.get(step) or {})
    entry["consumed_at"] = _utc_now_iso()
    entry["token"] = ""  # clear so replay cannot succeed
    confirmations[step] = entry
    return update_session(
        session_id,
        confirmations=confirmations,
        audit_event="confirmation_consumed",
        audit_detail={"step": step},
        directory=directory,
    )


def assert_session_mutable(session: dict[str, Any]) -> None:
    """Raise when the session is cancelled, completed, or failed."""
    status = str(session.get("status") or "")
    if status in _TERMINAL_STATUSES:
        raise TerminalSessionError(f"Workflow is {status} and no longer accepts write actions.")


def is_terminal_status(status: str | None) -> bool:
    """True when ``status`` is a closed workflow state."""
    return str(status or "") in _TERMINAL_STATUSES


def write_fingerprint(step: str, payload: Any) -> str:
    """Stable fingerprint for an external write (TCKT / Slack / deploy / mark)."""
    return content_hash({"step": step, "payload": payload})


def record_write_fingerprint(
    session_id: str,
    step: str,
    fingerprint: str,
    *,
    result: Any = None,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Persist that ``fingerprint`` was applied for ``step`` (replay guard)."""
    session = load_session(session_id, directory=directory)
    applied = dict(session.get("artifacts", {}).get("applied_writes") or {})
    applied[step] = {
        "fingerprint": fingerprint,
        "applied_at": _utc_now_iso(),
        "result": result,
    }
    return update_session(
        session_id,
        artifacts={"applied_writes": applied},
        audit_event="write_fingerprint_recorded",
        audit_detail={"step": step, "fingerprint": fingerprint[:16]},
        directory=directory,
    )


def find_applied_write(
    session: dict[str, Any],
    step: str,
    fingerprint: str,
) -> dict[str, Any] | None:
    """Return the stored applied-write entry when fingerprint matches."""
    applied = (session.get("artifacts") or {}).get("applied_writes") or {}
    entry = applied.get(step)
    if not isinstance(entry, dict):
        return None
    if entry.get("fingerprint") != fingerprint:
        return None
    return entry


def store_error_payload(exc: WizardStoreError) -> dict[str, Any]:
    """Structured MCP-friendly error body for store failures."""
    code = "wizard_store_error"
    if isinstance(exc, SessionNotFoundError):
        code = "session_not_found"
    elif isinstance(exc, SessionCorruptError):
        code = "session_corrupt"
    elif isinstance(exc, InvalidSessionIdError):
        code = "invalid_session_id"
    elif isinstance(exc, ConfirmationConsumedError):
        code = "confirmation_invalid"
    elif isinstance(exc, TerminalSessionError):
        code = "terminal_session"
    return {
        "status": "error",
        "error": str(exc),
        "error_code": code,
    }
