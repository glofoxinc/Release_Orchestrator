"""Shared infrastructure helpers for jira-release-tool and weekly-update-tool.

Exposed:

* :mod:`common.adf` — Atlassian Document Format builders.
* :mod:`common.atlassian` — injectable REST client.
* :mod:`common.ai` — optional OpenAI / Azure OpenAI enhancement.
* :mod:`common.cli` — shared CLI scaffolding.
* :mod:`common.logger` — structured logging.
* :mod:`common.notify` — Slack / Teams webhook builders.
* :mod:`common.retry` — exponential backoff.
"""

from . import adf, ai, atlassian, cli, notify, retry
from .logger import (
    JsonFormatter,
    clear_log_context,
    get_log_context,
    redact_secrets,
    set_log_context,
    setup_logging,
)

__all__ = [
    "JsonFormatter",
    "adf",
    "ai",
    "atlassian",
    "clear_log_context",
    "cli",
    "get_log_context",
    "notify",
    "redact_secrets",
    "retry",
    "set_log_context",
    "setup_logging",
]
