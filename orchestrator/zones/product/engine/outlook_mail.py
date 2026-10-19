"""Send Outlook mail via Microsoft Graph (application or delegated token)."""

from __future__ import annotations

import os
from typing import Any

from ms_graph import GraphClient


def mail_from_upn(explicit: str = "") -> str:
    value = (explicit or "").strip() or (os.environ.get("RELEASE_NOTIFY_MAIL_FROM") or "").strip()
    if value:
        return value
    try:
        import config

        teams = getattr(config, "TEAMS_SCHEDULE", {}) or {}
        return str(teams.get("organizer_upn") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def send_mail(
    *,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    dry_run: bool = True,
    from_upn: str = "",
    graph: GraphClient | None = None,
) -> dict[str, Any]:
    """Send one HTML/plain mail. dry_run=True never calls Graph."""
    recipients = [e.strip() for e in to if str(e).strip()]
    cc_list = [e.strip() for e in (cc or []) if str(e).strip()]
    sender = mail_from_upn(from_upn)
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in recipients],
            "ccRecipients": [{"emailAddress": {"address": addr}} for addr in cc_list],
        },
        "saveToSentItems": True,
    }
    preview = {
        "ok": True,
        "dry_run": dry_run,
        "from": sender,
        "to": recipients,
        "cc": cc_list,
        "subject": subject,
        "body": body,
        "outlook_mcp_handoff": {
            "tool": "outlook_send_email",
            "to": recipients,
            "subject": subject,
            "body": body,
        },
    }
    if not recipients:
        return {**preview, "ok": False, "error": "No Outlook recipients (email missing)."}
    if dry_run:
        return preview

    client = graph or GraphClient()
    if not client.configured():
        return {
            **preview,
            "ok": False,
            "sent": False,
            "error": "Microsoft Graph is not configured (MS_GRAPH_*). Use outlook_mcp_handoff.",
        }
    if not sender:
        return {
            **preview,
            "ok": False,
            "sent": False,
            "error": "Set RELEASE_NOTIFY_MAIL_FROM or teams_schedule.organizer_upn.",
        }
    status, response = client.request(
        "POST",
        f"/users/{sender}/sendMail",
        json_body=payload,
    )
    ok = status in (202, 200)
    return {
        **preview,
        "ok": ok,
        "sent": ok,
        "http_status": status,
        "error": None if ok else str(response)[:400],
    }
