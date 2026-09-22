"""Structured logging setup for jira-release-tool.

Provides a JSON formatter that activates when ``LOG_FORMAT=json`` is set, and
a plain-text formatter otherwise. Import and call :func:`setup_logging` once
during application startup; module-level loggers obtained via
``logging.getLogger(__name__)`` will inherit the root handler/formatter.

Safe context helpers attach workflow/release correlation IDs without logging
secrets. A redacting filter masks tokens and Authorization material.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

_workflow_id: ContextVar[str] = ContextVar("jrt_workflow_id", default="")
_release_id: ContextVar[str] = ContextVar("jrt_release_id", default="")
_extra_context: ContextVar[dict[str, Any]] = ContextVar("jrt_log_extra", default={})

_REDACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(xox[baprs]-)[0-9A-Za-z-]{8,}", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-+=/]{8,}", re.IGNORECASE),
    re.compile(r"(Basic\s+)[A-Za-z0-9+/=]{8,}", re.IGNORECASE),
    re.compile(
        r"((?:JIRA_API_TOKEN|SLACK_BOT_TOKEN|SLACK_TOKEN|OPENAI_API_KEY"
        r"|AZURE_OPENAI_API_KEY|CONFLUENCE_TOKEN)\s*[=:]\s*)\S+",
        re.IGNORECASE,
    ),
    re.compile(r"(api[_-]?token\s*[=:]\s*)\S+", re.IGNORECASE),
)


def redact_secrets(text: str) -> str:
    """Mask known secret patterns in a log message string."""
    if not text:
        return text
    out = text
    for pattern in _REDACT_PATTERNS:
        out = pattern.sub(r"\1***", out)
    return out


def set_log_context(
    *,
    workflow_id: str | None = None,
    release_id: str | None = None,
    **extra: Any,
) -> None:
    """Attach safe correlation fields for subsequent log records."""
    if workflow_id is not None:
        _workflow_id.set(str(workflow_id))
    if release_id is not None:
        _release_id.set(str(release_id))
    if extra:
        merged = dict(_extra_context.get())
        for key, value in extra.items():
            if value is None:
                continue
            # Never stash raw credentials into context.
            if any(s in key.lower() for s in ("token", "password", "secret", "authorization")):
                continue
            merged[key] = value
        _extra_context.set(merged)


def clear_log_context() -> None:
    """Reset correlation context (call at end of a request/workflow)."""
    _workflow_id.set("")
    _release_id.set("")
    _extra_context.set({})


def get_log_context() -> dict[str, Any]:
    """Return the current safe logging context dict."""
    ctx: dict[str, Any] = {}
    wf = _workflow_id.get()
    rel = _release_id.get()
    if wf:
        ctx["workflow_id"] = wf
    if rel:
        ctx["release_id"] = rel
    extra = _extra_context.get()
    if extra:
        ctx.update(extra)
    return ctx


class RedactingFilter(logging.Filter):
    """Filter that redacts secrets from the rendered message and exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 — never break logging
            return True
        redacted = redact_secrets(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)
        return True


class ContextFilter(logging.Filter):
    """Inject correlation IDs from contextvars onto each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_log_context()
        record.workflow_id = ctx.get("workflow_id", "")  # type: ignore[attr-defined]
        record.release_id = ctx.get("release_id", "")  # type: ignore[attr-defined]
        record.jrt_context = ctx  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON suitable for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        log: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        ctx = getattr(record, "jrt_context", None) or get_log_context()
        if ctx:
            log["context"] = ctx
        if record.exc_info:
            log["exception"] = redact_secrets(self.formatException(record.exc_info))
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            safe = {
                k: v
                for k, v in extra.items()
                if not any(s in str(k).lower() for s in ("token", "password", "secret"))
            }
            log.update(safe)
        return json.dumps(log, default=str)


class ContextTextFormatter(logging.Formatter):
    """Plain-text formatter that appends correlation IDs when present."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        parts: list[str] = []
        wf = getattr(record, "workflow_id", "") or ""
        rel = getattr(record, "release_id", "") or ""
        if wf:
            parts.append(f"workflow_id={wf}")
        if rel:
            parts.append(f"release_id={rel}")
        if not parts:
            return redact_secrets(base)
        return redact_secrets(f"{base} [{', '.join(parts)}]")


def setup_logging(
    level: int | str = logging.INFO,
    json_format: bool | None = None,
) -> None:
    """Configure the root logger.

    Parameters
    ----------
    level:
        Log level name or numeric level. Accepts strings like ``"DEBUG"``.
        When omitted as env, ``LOG_LEVEL`` is honoured if present.
    json_format:
        If ``None`` (default), JSON output is enabled when the ``LOG_FORMAT``
        environment variable equals ``"json"`` (case-insensitive). Pass a
        boolean to override the environment.
    """

    if json_format is None:
        json_format = os.environ.get("LOG_FORMAT", "").lower() == "json"

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    else:
        env_level = os.environ.get("LOG_LEVEL", "").strip()
        if env_level and level == logging.INFO:
            level = getattr(logging, env_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactingFilter())
    handler.addFilter(ContextFilter())
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            ContextTextFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
