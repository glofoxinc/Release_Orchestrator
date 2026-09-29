"""Headless Slack preview/send helpers for the Release Orchestrator wizard."""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

import config
from integration_archive import archived_response, is_archived
from slack_announce import (
    SlackChannelMessage,
    SlackChannelTarget,
    build_channel_messages,
    draft_from_session,
    ensure_canonical_cc,
    load_announce_config,
    send_announce_messages,
    validate_announce_config,
)


def build_slack_preview(
    *,
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
) -> dict[str, Any]:
    """Build both channel messages without sending."""
    if is_archived("slack_announce"):
        return archived_response("slack_announce")
    parsed_date = date.fromisoformat(deploy_date)
    draft = draft_from_session(
        ticket_key=ticket_key,
        summary=summary,
        ticket_url=ticket_url,
        planned_start=parsed_date,
        sharepoint_url=sharepoint_url,
        version_hint=version_name,
        environments=environments,
    )
    cfg = load_announce_config({"slack_announce": config.SLACK_ANNOUNCE})
    messages = build_channel_messages(draft, cfg.channels)
    issues = validate_announce_config(cfg)
    import browser_automation

    channel_payloads = []
    for message in messages:
        channel_payloads.append(
            {
                "key": message.channel.key,
                "name": message.channel.name,
                "channel_id": message.channel.channel_id,
                "preview": message.preview,
                "text": message.text,
                "cc": [
                    {
                        "name": person.name,
                        "user_id": person.user_id,
                        "email": person.email,
                    }
                    for person in message.channel.cc
                ],
                "playwright_compose": browser_automation.build_playwright_slack_compose(
                    draft,
                    message.channel,
                ),
            }
        )
    return {
        "enabled": cfg.enabled,
        "can_send": cfg.can_send(),
        "config_issues": [{"level": i.level, "code": i.code, "message": i.message} for i in issues],
        "draft": {
            "ticket_key": draft.ticket_key,
            "ticket_summary": draft.ticket_summary,
            "ticket_url": draft.ticket_url,
            "sharepoint_url": draft.sharepoint_url,
            "sharepoint_label": draft.sharepoint_label,
            "sharepoint_download_url": draft.sharepoint_download_url,
            "sharepoint_folder_url": draft.sharepoint_folder_url,
            "sharepoint_folder_label": draft.sharepoint_folder_label,
            "version": draft.version,
            "deploy_date": deploy_date,
        },
        "channels": channel_payloads,
    }


def apply_slack_message_edits(
    preview: dict[str, Any],
    edits: dict[str, Any] | None,
    channels: list[SlackChannelTarget] | None = None,
) -> dict[str, Any]:
    """Apply optional per-channel edits while reappending required CC mentions.

    Operators may safely edit the message body. Trailing ``CC:`` lines are
    stripped and replaced with the canonical channel CC list so required user
    mentions cannot be removed by MCP ``slack_messages`` edits.
    """
    if not edits:
        return preview
    cfg_channels = channels
    if cfg_channels is None:
        cfg = load_announce_config({"slack_announce": config.SLACK_ANNOUNCE})
        cfg_channels = cfg.channels
    by_key = {c.key: c for c in cfg_channels}
    by_name = {c.name.lstrip("#"): c for c in cfg_channels}
    for item in preview.get("channels") or []:
        key = str(item.get("key") or "")
        name = str(item.get("name") or "").lstrip("#")
        channel = by_key.get(key) or by_name.get(name)
        if channel is None:
            continue
        raw = edits.get(key) or edits.get(name) or edits.get(f"#{name}")
        if raw is None or raw == "":
            continue
        text = str(raw)
        item["text"] = ensure_canonical_cc(text, channel, for_preview=False)
        item["preview"] = ensure_canonical_cc(text, channel, for_preview=True)
    return preview


def send_slack_preview(
    preview: dict[str, Any],
    *,
    skip_channel_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Send a previously previewed payload to its configured channels.

    Channels listed in ``skip_channel_keys`` (already posted successfully) are
    recorded as skipped without calling Slack again — used for partial retries.
    Message text is always passed through ``ensure_canonical_cc`` so required
    mentions survive MCP edits.
    """
    if is_archived("slack_announce"):
        return {**archived_response("slack_announce"), "results": [], "sent_keys": [], "failed_keys": []}
    cfg = load_announce_config({"slack_announce": config.SLACK_ANNOUNCE})
    if not cfg.enabled:
        return {
            "status": "skipped",
            "reason": "Slack announce is disabled.",
            "results": [],
            "sent_keys": [],
            "failed_keys": [],
        }

    skip = {str(key) for key in (skip_channel_keys or []) if str(key).strip()}
    configured = {channel.key: channel for channel in cfg.channels}
    messages: list[SlackChannelMessage] = []
    draft = {str(item.get("key") or ""): item for item in preview.get("channels") or []}
    prior_ok = {
        str(item.get("key") or item.get("channel_key") or ""): item
        for item in (preview.get("prior_results") or [])
        if item.get("ok")
    }
    # Rebuild with the configured channel objects so resolution and CC metadata
    # cannot be injected through persisted wizard state.
    skipped_payload: list[dict[str, Any]] = []
    for key, channel in configured.items():
        item = draft.get(key)
        if not item:
            continue
        if key in skip:
            previous = prior_ok.get(key) or {}
            skipped_payload.append(
                {
                    "key": key,
                    "channel_name": channel.name,
                    "ok": True,
                    "error": None,
                    "permalink": previous.get("permalink"),
                    "ts": previous.get("ts"),
                    "skipped_already_sent": True,
                }
            )
            continue
        raw_text = str(item.get("text") or "")
        safe_text = ensure_canonical_cc(raw_text, channel, for_preview=False)
        safe_preview = ensure_canonical_cc(
            str(item.get("preview") or raw_text),
            channel,
            for_preview=True,
        )
        messages.append(
            SlackChannelMessage(
                channel=channel,
                text=safe_text,
                preview=safe_preview,
            )
        )

    results = send_announce_messages(cfg, messages) if messages else []
    payload = list(skipped_payload)
    # Map send results back onto configured channel keys by name order.
    pending_keys = [key for key in configured if key not in skip and draft.get(key)]
    for key, result in zip(pending_keys, results):
        payload.append(
            {
                "key": key,
                "channel_name": result.channel_name,
                "ok": result.ok,
                "error": result.error,
                "permalink": result.permalink,
                "ts": result.ts,
            }
        )
    ok_all = bool(payload) and all(item["ok"] for item in payload)
    return {
        "status": "sent" if ok_all else ("partial" if payload else "skipped"),
        "results": payload,
        "sent_keys": [item["key"] for item in payload if item.get("ok")],
        "failed_keys": [item["key"] for item in payload if not item.get("ok")],
    }


def slack_delivery_mode() -> str:
    """``cursor_slack_mcp`` when channels are configured — no bot token required in Cursor."""
    if is_archived("slack_announce"):
        return "disabled"
    cfg = load_announce_config({"slack_announce": config.SLACK_ANNOUNCE})
    if not cfg.enabled:
        return "disabled"
    if (cfg.bot_token or "").strip():
        return "bot_token"
    if cfg.channels and all(c.channel_id for c in cfg.channels):
        return "cursor_slack_mcp"
    return "not_configured"


def handoff_for_slack_mcp(preview: dict[str, Any]) -> dict[str, Any]:
    """Ready-to-post payloads for Cursor Slack MCP ``slack_send_message``."""
    posts: list[dict[str, str]] = []
    for item in preview.get("channels") or []:
        channel_id = str(item.get("channel_id") or "").strip()
        message = str(item.get("text") or "").strip()
        if not channel_id or not message:
            continue
        posts.append({
            "channel_id": channel_id,
            "channel_name": str(item.get("name") or ""),
            "message": message,
            "mcp": "plugin-slack-slack",
            "mcp_tool": "slack_send_message",
        })
    return {
        "delivery": "cursor_slack_mcp",
        "instruction": (
            "Post each item below using Cursor **Slack MCP** → `slack_send_message`. "
            "No SLACK_BOT_TOKEN in .env is required. Then say **slack done** to continue."
        ),
        "posts": posts,
    }


def enrich_preview_with_delivery(preview: dict[str, Any]) -> dict[str, Any]:
    """Attach delivery mode and Slack MCP handoff to a preview payload."""
    mode = slack_delivery_mode()
    enriched = dict(preview)
    enriched["delivery_mode"] = mode
    enriched["can_send"] = mode == "bot_token" and bool(preview.get("can_send"))
    enriched["can_post_via_slack_mcp"] = mode == "cursor_slack_mcp"
    if mode == "cursor_slack_mcp":
        enriched["slack_mcp"] = handoff_for_slack_mcp(preview)
    return enriched


def slack_announce_status() -> dict[str, Any]:
    """Feature/config status for deployment Slack announce — safe without credentials."""
    if is_archived("slack_announce"):
        return archived_response("slack_announce")
    cfg = load_announce_config({"slack_announce": config.SLACK_ANNOUNCE})
    issues = validate_announce_config(cfg)
    token = (cfg.bot_token or "").strip()
    mode = slack_delivery_mode()
    from slack_announce import never_post_unless_asked

    return {
        "enabled": cfg.enabled,
        "never_post_unless_asked": never_post_unless_asked(),
        "can_send": cfg.can_send(),
        "delivery_mode": mode,
        "can_post_via_slack_mcp": mode == "cursor_slack_mcp",
        "bot_token_set": bool(token),
        "channel_count": len(cfg.channels),
        "channels": [
            {
                "key": channel.key,
                "name": channel.name,
                "channel_id": channel.channel_id,
                "cc": [person.name for person in channel.cc],
            }
            for channel in cfg.channels
        ],
        "config_issues": [
            {"level": issue.level, "code": issue.code, "message": issue.message}
            for issue in issues
        ],
    }
