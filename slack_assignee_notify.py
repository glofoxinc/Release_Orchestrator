"""Slack DM notifications to Jira assignees (release gate reminders)."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any, Callable

import requests

import config
from release_gates import GateTicket

logger = logging.getLogger(__name__)


def _bot_token() -> str:
    return (
        os.environ.get("SLACK_BOT_TOKEN", "").strip()
        or os.environ.get("SLACK_TOKEN", "").strip()
    )


def _token_usable() -> bool:
    token = _bot_token()
    return bool(token) and not config.is_placeholder_credential(token)


def _slack_api(method: str, *, params: dict | None = None, payload: dict | None = None) -> dict:
    token = _bot_token()
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is not configured.")
    url = f"https://slack.com/api/{method}"
    headers = {"Authorization": f"Bearer {token}"}
    get_methods = {"users.lookupByEmail", "conversations.open"}
    if method in get_methods:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=20)
    else:
        headers["Content-Type"] = "application/json; charset=utf-8"
        resp = requests.post(url, headers=headers, json=payload or {}, timeout=20)
    data = resp.json() if resp.content else {}
    if not resp.ok:
        raise RuntimeError(f"Slack HTTP {resp.status_code}: {(resp.text or '')[:200]}")
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or f"Slack {method} failed")
    return data


def lookup_user_id_by_email(email: str) -> str:
    email = (email or "").strip()
    if not email:
        return ""
    data = _slack_api("users.lookupByEmail", params={"email": email})
    user = data.get("user") or {}
    return str(user.get("id") or "")


def open_dm_channel(user_id: str) -> str:
    data = _slack_api("conversations.open", payload={"users": user_id})
    channel = data.get("channel") or {}
    return str(channel.get("id") or "")


def send_dm(user_id: str, text: str) -> dict[str, Any]:
    channel_id = open_dm_channel(user_id)
    data = _slack_api(
        "chat.postMessage",
        payload={"channel": channel_id, "text": text, "mrkdwn": True},
    )
    return {
        "ok": True,
        "channel_id": channel_id,
        "ts": str(data.get("ts") or ""),
        "user_id": user_id,
    }


def notify_gate_tickets(
    tickets: list[GateTicket],
    message_builder: Callable[[GateTicket], str],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Notify assignees — one DM per assignee with all their blocked tickets grouped."""
    if not tickets:
        return {"status": "skipped", "reason": "no tickets", "results": []}

    if not _token_usable():
        return {
            "status": "error",
            "error": "SLACK_BOT_TOKEN is missing or placeholder.",
            "results": [],
        }

    by_assignee: dict[str, list[GateTicket]] = defaultdict(list)
    for ticket in tickets:
        bucket = ticket.assignee_email or ticket.assignee_name or ticket.key
        by_assignee[bucket].append(ticket)

    previews: list[dict[str, Any]] = []
    for _, group in by_assignee.items():
        sample = group[0]
        parts = [message_builder(t) for t in group]
        combined = "\n\n---\n\n".join(parts)
        previews.append({
            "assignee_name": sample.assignee_name,
            "assignee_email": sample.assignee_email,
            "ticket_keys": [t.key for t in group],
            "message_preview": combined,
        })

    if dry_run:
        return {
            "status": "dry_run",
            "recipient_count": len(previews),
            "ticket_count": len(tickets),
            "previews": previews,
        }

    results: list[dict[str, Any]] = []
    for preview in previews:
        email = str(preview.get("assignee_email") or "")
        name = str(preview.get("assignee_name") or "")
        text = str(preview.get("message_preview") or "")
        try:
            user_id = lookup_user_id_by_email(email) if email else ""
            if not user_id:
                results.append({
                    "assignee_name": name,
                    "assignee_email": email,
                    "ok": False,
                    "error": "Could not resolve Slack user (missing email or lookup failed).",
                })
                continue
            sent = send_dm(user_id, text)
            results.append({
                "assignee_name": name,
                "assignee_email": email,
                "ok": True,
                **sent,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("Slack assignee notify failed for %s: %s", email or name, exc)
            results.append({
                "assignee_name": name,
                "assignee_email": email,
                "ok": False,
                "error": str(exc),
            })

    ok_count = sum(1 for r in results if r.get("ok"))
    status = "ok" if ok_count == len(results) else ("partial" if ok_count else "error")
    return {
        "status": status,
        "recipient_count": len(results),
        "ok_count": ok_count,
        "results": results,
    }


def gate_slack_status() -> dict[str, Any]:
    enabled = bool(getattr(config, "SLACK_ANNOUNCE", {}).get("enabled", True))
    token_ok = _token_usable()
    return {
        "slack_announce_enabled": enabled,
        "bot_token_configured": token_ok,
        "can_dm_assignees": token_ok,
        "workspace": config.WORKSPACE_NAME,
        "scopes_hint": "im:write, chat:write, users:read.email",
    }
