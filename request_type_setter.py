"""Hardened Service Desk request-type auto-setter (A8).

Every TCKT created via the plain Jira REST API starts out without a request
type attached, which breaks the Service Desk portal layout. The existing
toolkit attempts to attach it via ``/rest/servicedeskapi/request/<key>/request-type``
but occasionally hits transient 5xx responses. This module wraps that call
with retry, exponential backoff, and a persistent audit log.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from common.retry import RetryError, RetryLog, retry

logger = logging.getLogger(__name__)


# The caller provides a transport: (method, path, payload) -> (status, body)
RequestTransport = Callable[[str, str, dict[str, Any] | None], tuple[int, str]]


@dataclass
class SetRequestTypeResult:
    ok: bool
    attempts: int = 0
    last_status: int = 0
    message: str = ""
    audit: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "attempts": self.attempts,
            "last_status": self.last_status,
            "message": self.message,
            "audit": list(self.audit),
        }


class _Transient(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"transient HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


class _Permanent(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


def _is_transient(status: int) -> bool:
    return status == 429 or 500 <= status < 600


def set_request_type(
    issue_key: str,
    *,
    service_desk_id: str,
    request_type_id: str,
    transport: RequestTransport,
    max_attempts: int = 4,
    base_delay: float = 0.5,
    jitter: bool = True,
    audit_path: Path | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> SetRequestTypeResult:
    """Attach ``request_type_id`` to ``issue_key`` with retries.

    ``transport`` is called with ``("POST", path, payload)`` and must return a
    ``(status, body)`` tuple. Returns a populated :class:`SetRequestTypeResult`.
    """
    if not (issue_key and service_desk_id and request_type_id):
        return SetRequestTypeResult(
            ok=False,
            message="missing issue_key, service_desk_id or request_type_id",
        )

    path = f"/rest/servicedeskapi/request/{issue_key}/request-type"
    payload = {"serviceDeskId": str(service_desk_id), "requestTypeId": str(request_type_id)}
    log = RetryLog()

    @retry(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=10.0,
        jitter=jitter,
        retry_on=(_Transient,),
        audit=log,
        sleep=sleep,
    )
    def _do_call() -> tuple[int, str]:
        status, body = transport("POST", path, payload)
        if 200 <= status < 300:
            return status, body
        if _is_transient(status):
            raise _Transient(status, body)
        raise _Permanent(status, body)

    outcome = SetRequestTypeResult(ok=False)
    try:
        status, body = _do_call()
        outcome.ok = True
        outcome.last_status = status
        outcome.message = "request type applied"
    except RetryError as exc:
        inner = exc.last_error
        if isinstance(inner, (_Transient, _Permanent)):
            outcome.last_status = inner.status
            outcome.message = (
                f"retries exhausted after transient HTTP {inner.status}"
                if isinstance(inner, _Transient)
                else f"permanent failure HTTP {inner.status}"
            )
        else:
            outcome.message = f"retries exhausted: {inner}"
    except _Permanent as exc:
        outcome.last_status = exc.status
        outcome.message = (
            f"permanent failure HTTP {exc.status} — "
            "check service_desk_id and request_type_id"
        )
    except Exception as exc:
        outcome.message = f"unexpected error: {exc}"

    outcome.attempts = len(log.attempts) + (1 if outcome.ok else 0)
    outcome.audit = [a.__dict__ for a in log.attempts]

    if audit_path is not None:
        try:
            _append_audit(audit_path, issue_key, outcome)
        except Exception:
            logger.debug("failed to append audit log", exc_info=True)

    return outcome


def _append_audit(path: Path, issue_key: str, outcome: SetRequestTypeResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": int(time.time()),
        "issue_key": issue_key,
        "ok": outcome.ok,
        "attempts": outcome.attempts,
        "last_status": outcome.last_status,
        "message": outcome.message,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def default_audit_path() -> Path:
    override = os.environ.get("JRT_AUDIT_LOG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".jira-release-tool" / "audit" / "request-type.log"


__all__ = [
    "SetRequestTypeResult",
    "RequestTransport",
    "set_request_type",
    "default_audit_path",
]
