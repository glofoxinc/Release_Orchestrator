"""Post-deployment Slack / Teams notifications.

.. deprecated::
    This incoming-webhook helper is **legacy**. Customize BI deployment
    announcements must use :mod:`slack_announce` with ``SLACK_BOT_TOKEN`` and
    ``workspace.yaml`` → ``slack_announce`` (channels + CC). Do not configure
    ``SLACK_DEPLOY_WEBHOOK`` expecting it to drive the Service Ticket / MCP
    announce step — that path uses the Bot API only.

Thin project-level wrapper over :mod:`common.notify`. Builds a generic
deployment announcement payload from a completed TCKT draft, and dispatches
to one or more configured webhooks when explicitly invoked.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from common import notify as _notify

logger = logging.getLogger(__name__)


@dataclass
class NotifyConfig:
    """Which legacy webhooks should receive the announcement.

    Prefer ``slack_announce`` + ``SLACK_BOT_TOKEN`` for Customize BI releases.
    """

    slack_url: str = ""
    teams_url: str = ""
    extra: str = ""

    @classmethod
    def from_env(cls) -> "NotifyConfig":
        return cls(
            slack_url=os.environ.get("SLACK_DEPLOY_WEBHOOK", ""),
            teams_url=os.environ.get("TEAMS_DEPLOY_WEBHOOK", ""),
            extra=os.environ.get("DEPLOY_NOTIFY_FOOTER", ""),
        )

    def any_configured(self) -> bool:
        return bool(self.slack_url or self.teams_url)


@dataclass
class NotifyOutcome:
    slack: _notify.NotifyResult | None = None
    teams: _notify.NotifyResult | None = None
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        results = [r for r in (self.slack, self.teams) if r is not None]
        return bool(results) and all(r.ok for r in results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "slack": self.slack.to_dict() if self.slack else None,
            "teams": self.teams.to_dict() if self.teams else None,
            "skipped": list(self.skipped),
        }


def build_deploy_context(ticket: dict[str, Any]) -> dict[str, Any]:
    """Flatten a draft dict into the subset the Slack/Teams payloads need."""
    key = ticket.get("ticket_key") or ticket.get("key") or ""
    summary = ticket.get("summary") or ""
    url = ticket.get("jira_url") or ""
    if not url and key:
        base = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
        url = f"{base}/browse/{key}" if base else ""

    approvers = ticket.get("approvers") or []
    if approvers and isinstance(approvers[0], dict):
        approvers = [a.get("displayName") or a.get("name") or a.get("accountId") or "" for a in approvers]
    approvers = [a for a in approvers if a]

    start = ticket.get("planned_start") or ""
    end = ticket.get("planned_end") or ""
    window = f"{start} – {end}".strip(" –") if start or end else ""

    return {
        "ticket_key": key,
        "summary": summary,
        "url": url,
        "approvers": approvers,
        "window": window,
    }


def announce_deployment(
    ticket: dict[str, Any],
    config: NotifyConfig | None = None,
    *,
    transport: _notify.Transport | None = None,
) -> NotifyOutcome:
    """Build and dispatch legacy webhook announcements.

    Deprecated for Customize BI: use :mod:`slack_announce` instead.
    """
    cfg = config or NotifyConfig.from_env()
    outcome = NotifyOutcome()
    context = build_deploy_context(ticket)

    if not cfg.any_configured():
        outcome.skipped.append("no webhooks configured")
        return outcome

    logger.warning(
        "announce_deployment() uses the legacy webhook notifier; "
        "prefer slack_announce + SLACK_BOT_TOKEN for Customize BI announces."
    )

    if cfg.slack_url:
        payload = _notify.slack_deploy_payload(
            ticket_key=context["ticket_key"],
            summary=context["summary"],
            url=context["url"],
            approvers=context["approvers"],
            window=context["window"],
            extra=cfg.extra,
        )
        outcome.slack = _notify.post_webhook(cfg.slack_url, payload, transport=transport)
    else:
        outcome.skipped.append("slack")

    if cfg.teams_url:
        payload = _notify.teams_deploy_payload(
            ticket_key=context["ticket_key"],
            summary=context["summary"],
            url=context["url"],
            approvers=context["approvers"],
            window=context["window"],
        )
        outcome.teams = _notify.post_webhook(cfg.teams_url, payload, transport=transport)
    else:
        outcome.skipped.append("teams")

    return outcome


__all__ = [
    "NotifyConfig",
    "NotifyOutcome",
    "build_deploy_context",
    "announce_deployment",
]
