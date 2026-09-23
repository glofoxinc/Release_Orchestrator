"""Slack and Microsoft Teams webhook notifiers.

Both surfaces use incoming-webhook endpoints that accept a single JSON
payload. This module exposes a transport-injectable wrapper so the tool can
announce deployments and weekly updates without adding a networking
dependency to the test surface.

Example
-------
>>> payload = slack_deploy_payload(
...     ticket_key="TCKT-1",
...     summary="Production release",
...     url="https://example.atlassian.net/browse/TCKT-1",
...     approvers=["alice", "bob"],
...     window="10:00 - 13:00 CT",
... )
>>> "TCKT-1" in json.dumps(payload)
True
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


# Transport signature: (url, json_body) -> (status, body)
Transport = Callable[[str, dict[str, Any]], tuple[int, str]]


@dataclass
class NotifyResult:
    ok: bool
    status: int = 0
    body: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "status": self.status, "body": self.body, "error": self.error}


def default_transport() -> Transport:
    """Lazy-loaded default transport using ``requests``."""

    def _call(url: str, payload: dict[str, Any]) -> tuple[int, str]:
        import requests  # lazy

        resp = requests.post(url, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=15)
        return resp.status_code, resp.text

    return _call


def _approvers_mention(approvers: list[str], *, prefix: str) -> str:
    return " ".join(f"{prefix}{a.strip()}" for a in approvers if a and a.strip())


# ── Slack ───────────────────────────────────────────────────────────────────

def slack_deploy_payload(
    *,
    ticket_key: str,
    summary: str,
    url: str = "",
    approvers: list[str] | None = None,
    window: str = "",
    extra: str = "",
) -> dict[str, Any]:
    """Build a Slack ``blocks`` payload for a deployment announcement."""
    approver_list = approvers or []
    header_text = f":rocket: {ticket_key}: {summary}" if ticket_key else summary or "Deployment"
    fields: list[dict[str, Any]] = []
    if window:
        fields.append({"type": "mrkdwn", "text": f"*Window:*\n{window}"})
    if approver_list:
        mentions = _approvers_mention(approver_list, prefix="@")
        fields.append({"type": "mrkdwn", "text": f"*Approvers:*\n{mentions}"})

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header_text[:140]}},
    ]
    if fields:
        blocks.append({"type": "section", "fields": fields})
    if extra:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": extra}})
    if url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open Ticket"},
                        "url": url,
                    }
                ],
            }
        )
    return {"text": header_text, "blocks": blocks}


def slack_weekly_payload(
    *,
    period: str,
    highlights: list[str],
    blockers: list[str],
    url: str = "",
) -> dict[str, Any]:
    """Build a Slack payload summarising a weekly update."""
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Weekly Update — {period}"[:140]}},
    ]
    if highlights:
        text = "*Highlights*\n" + "\n".join(f"• {h}" for h in highlights[:10])
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    if blockers:
        text = "*Blockers*\n" + "\n".join(f"• {b}" for b in blockers[:10])
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    if url:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"<{url}|Full update>"}})
    return {"text": f"Weekly Update {period}", "blocks": blocks}


# ── Microsoft Teams ─────────────────────────────────────────────────────────

def teams_deploy_payload(
    *,
    ticket_key: str,
    summary: str,
    url: str = "",
    approvers: list[str] | None = None,
    window: str = "",
) -> dict[str, Any]:
    """Build a MS Teams ``MessageCard`` payload."""
    facts: list[dict[str, str]] = []
    if window:
        facts.append({"name": "Window", "value": window})
    if approvers:
        facts.append({"name": "Approvers", "value": ", ".join(approvers)})
    actions: list[dict[str, Any]] = []
    if url:
        actions.append(
            {
                "@type": "OpenUri",
                "name": "Open Ticket",
                "targets": [{"os": "default", "uri": url}],
            }
        )
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": f"{ticket_key}: {summary}".strip(": "),
        "themeColor": "0076D7",
        "title": f"{ticket_key}: {summary}".strip(": "),
        "sections": [{"facts": facts}],
        "potentialAction": actions,
    }


# ── Dispatch ────────────────────────────────────────────────────────────────

def post_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    transport: Transport | None = None,
) -> NotifyResult:
    """Post ``payload`` to ``url`` through ``transport``.

    Returns a :class:`NotifyResult` — never raises. Any exception raised by
    the transport is captured as an error string.
    """
    if not url:
        return NotifyResult(ok=False, error="webhook URL is empty")
    call = transport or default_transport()
    try:
        status, body = call(url, payload)
    except Exception as exc:
        logger.debug("webhook post raised", exc_info=True)
        return NotifyResult(ok=False, error=str(exc))
    if 200 <= status < 300:
        return NotifyResult(ok=True, status=status, body=body)
    return NotifyResult(ok=False, status=status, body=body, error=f"HTTP {status}")


__all__ = [
    "NotifyResult",
    "Transport",
    "default_transport",
    "slack_deploy_payload",
    "slack_weekly_payload",
    "teams_deploy_payload",
    "post_webhook",
]
