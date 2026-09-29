"""Jira HTTP transport, retries, and API error parsing."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, TypeVar

import requests
from requests.auth import HTTPBasicAuth

import config
import jira_teams
import team_scope
from shipit_test_mode import is_test_shipit_summary

_MAX_RETRIES = 3
_BACKOFF_BASE = 2
_DEFAULT_TIMEOUT = 30
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Recent-comments window for duplicate deployment-marker checks before full scan.
_RECENT_COMMENT_WINDOW = 25

_logger = logging.getLogger(__name__)

_T = TypeVar("_T")
_R = TypeVar("_R")

# Inter-call pause (JIRA_RATE_LIMIT_PAUSE) — shared across threads.
_rate_lock = threading.Lock()
_last_call_mono: float = 0.0

# Read-only version metadata cache (single-user Streamlit / MCP process).
_version_cache_lock = threading.Lock()
_version_cache: dict[tuple[Any, ...], tuple[float, list[dict]]] = {}


def rate_limit_pause_seconds() -> float:
    """Seconds to wait between Jira HTTP calls (``JIRA_RATE_LIMIT_PAUSE``).

    Default ``0`` (off). Under persistent 429s, set e.g. ``0.5`` in ``.env``.
    """
    raw = os.environ.get("JIRA_RATE_LIMIT_PAUSE", "0").strip() or "0"
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def readonly_concurrency() -> int:
    """Max workers for **read-only** preflight fan-out (``JIRA_READONLY_CONCURRENCY``).

    Default ``1`` (sequential). Writes always stay sequential regardless of this.
    """
    raw = os.environ.get("JIRA_READONLY_CONCURRENCY", "1").strip() or "1"
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 1


def version_cache_ttl_seconds() -> float:
    """TTL for ``get_project_versions`` cache (``JIRA_VERSION_CACHE_TTL``, default 300s)."""
    raw = os.environ.get("JIRA_VERSION_CACHE_TTL", "300").strip() or "300"
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 300.0


def clear_version_cache() -> None:
    """Drop cached project version lists (tests / after mark-released)."""
    with _version_cache_lock:
        _version_cache.clear()


def reset_client() -> None:
    """Clear HTTP-layer Jira client caches after credential or workspace changes."""
    clear_version_cache()


def _maybe_inter_call_pause() -> None:
    """Sleep so successive Jira calls respect ``JIRA_RATE_LIMIT_PAUSE``."""
    pause = rate_limit_pause_seconds()
    if pause <= 0:
        return
    global _last_call_mono
    with _rate_lock:
        now = time.monotonic()
        wait = pause - (now - _last_call_mono)
        if wait > 0:
            time.sleep(wait)
        _last_call_mono = time.monotonic()


def readonly_map(
    fn: Callable[[_T], _R],
    items: Iterable[_T],
    *,
    max_workers: int | None = None,
) -> list[_R]:
    """Map ``fn`` over ``items`` preserving order; optional bounded concurrency.

    Only use for **read-only** work. ``max_workers`` defaults to
    :func:`readonly_concurrency`.
    """
    seq = list(items)
    if not seq:
        return []
    workers = readonly_concurrency() if max_workers is None else max(1, max_workers)
    if workers <= 1 or len(seq) == 1:
        return [fn(item) for item in seq]
    results: list[Any] = [None] * len(seq)
    with ThreadPoolExecutor(max_workers=min(workers, len(seq))) as pool:
        future_map = {pool.submit(fn, item): idx for idx, item in enumerate(seq)}
        for fut in as_completed(future_map):
            results[future_map[fut]] = fut.result()
    return results  # type: ignore[return-value]


class RequestTypeStatus:
    """Structured result of an attempt to auto-set the Service Desk request type."""

    OK = "ok"
    DISABLED = "disabled"  # missing env vars / config
    FAILED = "failed"      # API call failed
    SKIPPED = "skipped"    # not attempted

    def __init__(
        self,
        status: str,
        message: str = "",
        *,
        http_status: int | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.http_status = http_status

    @property
    def ok(self) -> bool:
        return self.status == self.OK

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "message": self.message,
            "http_status": self.http_status,
        }


class JiraApiError(Exception):
    """User-friendly wrapper for Jira API failures."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        original: Exception | None = None,
        field_errors: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self.original = original
        self.field_errors = dict(field_errors or {})
        super().__init__(message)


_FRIENDLY_MESSAGES: dict[int, str] = {
    400: (
        "Jira rejected the request (HTTP 400) — one or more field values are "
        "invalid for this issue type or request form."
    ),
    401: "Jira authentication failed — check your email and API token in Settings.",
    403: "Permission denied — your Jira account lacks access to this resource.",
    404: "Not found — the Jira resource does not exist or has been moved.",
    429: "Jira rate limit exceeded — too many requests. Please try again in a moment.",
    500: "Jira server error — the Jira instance is experiencing issues. Try again shortly.",
    502: "Jira is temporarily unreachable (bad gateway). Try again in a few seconds.",
    503: "Jira is temporarily unavailable (maintenance or overload). Try again shortly.",
    504: "Jira request timed out on the server side. Try again shortly.",
}


def _redact_auth(headers: dict) -> dict:
    """Return headers dict with auth values redacted for safe logging."""
    redacted = dict(headers)
    for key in ("Authorization", "authorization", "X-API-Key", "x-api-key"):
        if key in redacted:
            redacted[key] = "***REDACTED***"
    return redacted


def _auth() -> HTTPBasicAuth:
    return HTTPBasicAuth(config.JIRA_EMAIL, config.JIRA_API_TOKEN)


def is_mock_mode() -> bool:
    """Return True when MOCK_MODE env var is set to a truthy value."""
    return os.environ.get("MOCK_MODE", "").lower() in {"1", "true", "yes", "on"}


def _block_mock_writes(method: str, path: str) -> None:
    if is_mock_mode():
        raise JiraApiError(
            f"Mock mode is enabled — {method} {path} was blocked. "
            "Unset MOCK_MODE to write to Jira.",
        )


def _headers() -> dict[str, str]:
    return {"Accept": "application/json", "Content-Type": "application/json"}


def _should_retry(resp: requests.Response, attempt: int) -> bool:
    """Return True and sleep if the response is retryable and retries remain."""
    if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
        if resp.status_code == 429:
            delay = int(resp.headers.get("Retry-After", _BACKOFF_BASE ** attempt))
        else:
            delay = _BACKOFF_BASE ** attempt
        time.sleep(delay)
        return True
    return False


_MAX_ERROR_DETAIL_CHARS = 800

_FIELD_ID_PATTERNS = (
    re.compile(r"[Ff]ield with id '([^']+)'"),
    re.compile(r"\b(customfield_\d+)\b"),
)


def _field_ids_in_message(message: str) -> list[str]:
    """Pull field ids out of Service Desk prose.

    Example: ``Field with id 'customfield_14549' named 'Business Impact' has
    these errors : []``.
    """
    found: list[str] = []
    for pattern in _FIELD_ID_PATTERNS:
        for match in pattern.findall(message):
            if match not in found:
                found.append(match)
    return found


def _parse_api_error_body(resp: requests.Response) -> tuple[list[str], dict[str, str]]:
    """Extract messages and per-field errors from a Jira or Service Desk error body.

    Jira REST replies with ``errorMessages`` plus an ``errors`` map keyed by field id;
    the Service Desk API replies with ``errorMessage``. Without this, a 400 tells the
    user nothing about which field Jira actually refused.
    """
    try:
        payload = resp.json()
    except Exception:
        payload = None

    if not isinstance(payload, dict):
        text = getattr(resp, "text", "")
        if isinstance(text, str) and text.strip():
            return [text.strip()[:_MAX_ERROR_DETAIL_CHARS]], {}
        return [], {}

    messages: list[str] = []
    raw_messages = payload.get("errorMessages")
    if isinstance(raw_messages, list):
        messages.extend(str(m).strip() for m in raw_messages if str(m).strip())
    for key in ("errorMessage", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            messages.append(value.strip())

    field_errors: dict[str, str] = {}
    raw_errors = payload.get("errors")
    if isinstance(raw_errors, dict):
        for field_id, reason in raw_errors.items():
            field_errors[str(field_id)] = str(reason).strip()
    elif isinstance(raw_errors, list):
        messages.extend(str(m).strip() for m in raw_errors if str(m).strip())

    seen: set[str] = set()
    unique = [m for m in messages if not (m in seen or seen.add(m))]

    # The Service Desk API names the offending field in prose rather than in an
    # ``errors`` map, so recover the ids to keep per-field handling working.
    if not field_errors:
        for message in unique:
            for field_id in _field_ids_in_message(message):
                field_errors.setdefault(field_id, message)

    return unique, field_errors


def field_label(field_id: str) -> str:
    """Return ``customfield_11763 (planned start)`` when the id maps to a known TCKT field."""
    for logical, mapped in config.TCKT_FIELDS.items():
        if mapped and mapped == field_id:
            return f"{field_id} ({logical.replace('_', ' ')})"
    return field_id


def _format_error_detail(messages: list[str], field_errors: dict[str, str]) -> str:
    parts = list(messages)
    parts.extend(
        f"{field_label(field_id)}: {reason}"
        for field_id, reason in sorted(field_errors.items())
    )
    return " | ".join(p for p in parts if p)[:_MAX_ERROR_DETAIL_CHARS]


def _friendly_raise(resp: requests.Response) -> None:
    """Raise a user-friendly JiraApiError that keeps Jira's own explanation."""
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        messages, field_errors = _parse_api_error_body(resp)
        detail = _format_error_detail(messages, field_errors)
        _logger.error(
            "Jira API error: %s %s -> HTTP %s%s",
            resp.request.method,
            resp.request.path_url,
            resp.status_code,
            f" | {detail}" if detail else "",
        )
        base = _FRIENDLY_MESSAGES.get(resp.status_code) or (
            f"Jira API request failed (HTTP {resp.status_code})."
        )
        raise JiraApiError(
            f"{base} Jira said: {detail}" if detail else base,
            status_code=resp.status_code,
            original=exc,
            field_errors=field_errors,
        ) from exc


def _handle_connection_error(exc: Exception, path: str) -> None:
    """Convert network-level errors to user-friendly JiraApiError."""
    _logger.error("Jira connection error for %s: %s", path, exc)
    if isinstance(exc, requests.Timeout):
        raise JiraApiError(
            "Jira request timed out after 30 seconds. Check your network or try again.",
            original=exc,
        ) from exc
    if isinstance(exc, requests.ConnectionError):
        raise JiraApiError(
            "Cannot reach Jira — check your network connection and Jira URL in Settings.",
            original=exc,
        ) from exc
    raise JiraApiError(f"Unexpected error communicating with Jira: {exc}", original=exc) from exc


def _get(path: str, params: dict | None = None) -> Any:
    url = f"{config.JIRA_API_URL}{path}"
    for attempt in range(_MAX_RETRIES + 1):
        _maybe_inter_call_pause()
        try:
            resp = requests.get(url, headers=_headers(), auth=_auth(), params=params or {}, timeout=_DEFAULT_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            _handle_connection_error(exc, path)
        if _should_retry(resp, attempt):
            continue
        _friendly_raise(resp)
        return resp.json()


def _post(path: str, json_body: dict) -> Any:
    _block_mock_writes("POST", path)
    url = f"{config.JIRA_API_URL}{path}"
    for attempt in range(_MAX_RETRIES + 1):
        _maybe_inter_call_pause()
        try:
            resp = requests.post(url, headers=_headers(), auth=_auth(), json=json_body, timeout=_DEFAULT_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            _handle_connection_error(exc, path)
        if _should_retry(resp, attempt):
            continue
        _friendly_raise(resp)
        return resp.json() if resp.content else None


def _put(path: str, json_body: dict) -> requests.Response:
    _block_mock_writes("PUT", path)
    url = f"{config.JIRA_API_URL}{path}"
    for attempt in range(_MAX_RETRIES + 1):
        _maybe_inter_call_pause()
        try:
            resp = requests.put(url, headers=_headers(), auth=_auth(), json=json_body, timeout=_DEFAULT_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            _handle_connection_error(exc, path)
        if _should_retry(resp, attempt):
            continue
        _friendly_raise(resp)
        return resp


def _delete(path: str) -> bool:
    _block_mock_writes("DELETE", path)
    url = f"{config.JIRA_API_URL}{path}"
    for attempt in range(_MAX_RETRIES + 1):
        _maybe_inter_call_pause()
        try:
            resp = requests.delete(url, headers=_headers(), auth=_auth(), timeout=_DEFAULT_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            _handle_connection_error(exc, path)
        if _should_retry(resp, attempt):
            continue
        return resp.status_code == 204
    return False


