"""Slack delivery for Daily Review Agent — channel post, scheduled reminder, huddle link."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from slack_announce import SlackChannelTarget, resolve_channel_id, send_channel_message

logger = logging.getLogger(__name__)


@dataclass
class SlackDeliveryConfig:
    enabled: bool = False
    channel_name: str = ""
    channel_id: str = ""
    team_id: str = ""
    post_summary: bool = True
    schedule_reminder: bool = False
    reminder_minutes_before: int = 15
    huddle_enabled: bool = False
    huddle_post_link: bool = True
    cc_user_ids: list[str] | None = None

    def bot_token(self) -> str:
        return (os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_TOKEN") or "").strip()

    def can_send(self) -> bool:
        return bool(self.enabled and self.bot_token() and (self.channel_id or self.channel_name))


def build_huddle_url(*, team_id: str, channel_id: str) -> str:
    """Deep link to join/start a Slack Huddle in a channel (manual click required)."""
    return f"https://app.slack.com/huddle/{team_id}/{channel_id}"


def _resolve_team_id(token: str, configured: str) -> str:
    if configured.strip():
        return configured.strip()
    from slack_announce import _slack_api

    data = _slack_api("auth.test", token)
    return str(data.get("team_id") or "")


def _mentions(cfg: SlackDeliveryConfig) -> str:
    ids = cfg.cc_user_ids or []
    if not ids:
        return ""
    return " ".join(f"<@{uid}>" for uid in ids if uid) + "\n"


def format_slack_review_message(
    *,
    text_report: str,
    meeting_start: datetime,
    meeting_end: datetime,
    teams_join_url: str = "",
    huddle_url: str = "",
    include_huddle: bool = False,
    mentions: str = "",
) -> str:
    lines: list[str] = []
    if mentions.strip():
        lines.append(mentions.strip())
    lines.extend(
        [
            "*Daily ticket review*",
            f"When: {meeting_start.strftime('%a %d %b %Y, %I:%M %p')} – {meeting_end.strftime('%I:%M %p')} IST",
            "",
            text_report,
        ]
    )
    if teams_join_url:
        lines.extend(["", f"*Teams meeting:* {teams_join_url}"])
    if include_huddle and huddle_url:
        lines.extend(
            [
                "",
                f"*Slack Huddle (optional):* {huddle_url}",
                "_Slack has no API to auto-start huddles — click the link or use the headphones icon in the channel._",
            ]
        )
    return "\n".join(lines)


def post_review_message(
    cfg: SlackDeliveryConfig,
    *,
    text_report: str,
    meeting_start: datetime,
    meeting_end: datetime,
    teams_join_url: str = "",
    channel_id: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Post ticket digest (+ optional Teams / huddle links) to Slack channel."""
    if not cfg.can_send() and not dry_run:
        return {"ok": False, "error": "Slack not configured (enabled + SLACK_BOT_TOKEN + channel)"}

    token = cfg.bot_token()
    cid = channel_id or cfg.channel_id
    huddle_url = ""
    if cfg.huddle_enabled and cfg.huddle_post_link and token and not dry_run:
        try:
            resolved_cid = resolve_channel_id(token, cfg.channel_name, cid)
            team_id = _resolve_team_id(token, cfg.team_id)
            if team_id and resolved_cid:
                huddle_url = build_huddle_url(team_id=team_id, channel_id=resolved_cid)
                cid = resolved_cid
        except Exception as exc:
            logger.warning("Huddle link resolution failed: %s", exc)

    body = format_slack_review_message(
        text_report=text_report,
        meeting_start=meeting_start,
        meeting_end=meeting_end,
        teams_join_url=teams_join_url,
        huddle_url=huddle_url,
        include_huddle=cfg.huddle_enabled,
        mentions=_mentions(cfg),
    )

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "channel": cfg.channel_name or cid,
            "text_preview": body[:500],
            "huddle_url": huddle_url or None,
        }

    target = SlackChannelTarget(key="review", name=cfg.channel_name, channel_id=cid)
    result = send_channel_message(token, target, body)
    return {
        "ok": result.ok,
        "dry_run": False,
        "channel": result.channel_name,
        "permalink": result.permalink,
        "ts": result.ts,
        "error": result.error,
        "huddle_url": huddle_url or None,
    }


def schedule_slack_reminder(
    cfg: SlackDeliveryConfig,
    *,
    meeting_start: datetime,
    teams_join_url: str = "",
    huddle_url: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Schedule a Slack channel message before the review (chat.scheduleMessage)."""
    if not cfg.schedule_reminder:
        return {"ok": True, "skipped": True, "reason": "schedule_reminder disabled"}

    token = cfg.bot_token()
    if not token and not dry_run:
        return {"ok": False, "error": "SLACK_BOT_TOKEN missing"}

    post_at = meeting_start - timedelta(minutes=max(1, cfg.reminder_minutes_before))
    post_at_unix = int(post_at.timestamp())
    if post_at_unix <= int(datetime.now(meeting_start.tzinfo or ZoneInfo("UTC")).timestamp()):
        return {"ok": False, "error": "Reminder time is in the past — skip scheduling"}

    cid = cfg.channel_id
    reminder_lines = []
    m = _mentions(cfg)
    if m.strip():
        reminder_lines.append(m.strip())
    reminder_lines.extend(
        [
            f"*Review starting in {cfg.reminder_minutes_before} min*",
            f"Time: {meeting_start.strftime('%I:%M %p')} IST",
        ]
    )
    if teams_join_url:
        reminder_lines.append(f"Teams: {teams_join_url}")
    if huddle_url:
        reminder_lines.append(f"Huddle: {huddle_url}")
    text = "\n".join(reminder_lines)

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "post_at": post_at.isoformat(),
            "text_preview": text[:300],
        }

    from slack_announce import _slack_api

    channel_id = resolve_channel_id(token, cfg.channel_name, cid)
    data = _slack_api(
        "chat.scheduleMessage",
        token,
        {
            "channel": channel_id,
            "text": text,
            "post_at": post_at_unix,
        },
    )
    return {
        "ok": True,
        "dry_run": False,
        "scheduled_message_id": data.get("scheduled_message_id"),
        "post_at": post_at.isoformat(),
        "channel_id": channel_id,
    }


def run_slack_delivery(
    cfg: SlackDeliveryConfig,
    *,
    text_report: str,
    meeting_start: datetime,
    meeting_end: datetime,
    teams_join_url: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Post summary now + optionally schedule pre-meeting reminder."""
    if not cfg.enabled:
        return {"ok": True, "skipped": True, "reason": "slack.enabled is false"}

    post = post_review_message(
        cfg,
        text_report=text_report,
        meeting_start=meeting_start,
        meeting_end=meeting_end,
        teams_join_url=teams_join_url,
        dry_run=dry_run,
    )
    huddle_url = str(post.get("huddle_url") or "")
    sched = schedule_slack_reminder(
        cfg,
        meeting_start=meeting_start,
        teams_join_url=teams_join_url,
        huddle_url=huddle_url,
        dry_run=dry_run,
    )
    return {"post": post, "schedule": sched, "ok": bool(post.get("ok")) and bool(sched.get("ok", True))}


def slack_readiness(cfg: SlackDeliveryConfig) -> dict[str, Any]:
    """Blockers for live Slack delivery."""
    blockers: list[str] = []
    notes: list[str] = []

    if not cfg.enabled:
        return {"enabled": False, "can_send": False, "blockers": [], "notes": ["slack.enabled is false"]}

    if not cfg.bot_token():
        blockers.append("SLACK_BOT_TOKEN missing in .env")
    if not (cfg.channel_id or cfg.channel_name):
        blockers.append("slack.channel_id or slack.channel_name in agent.yaml")

    if cfg.schedule_reminder:
        notes.append("Requires bot scope chat:scheduleMessage")
    if cfg.huddle_enabled:
        notes.append(
            "Slack Huddle: no schedule/start API — agent posts huddle deep link only; users click to join"
        )

    can_send = not blockers
    if can_send and cfg.bot_token():
        try:
            from slack_announce import _slack_api

            _slack_api("auth.test", cfg.bot_token())
        except Exception as exc:
            blockers.append(f"auth.test failed: {exc}")
            can_send = False

    return {
        "enabled": cfg.enabled,
        "can_send": can_send and cfg.can_send(),
        "channel": cfg.channel_name or cfg.channel_id,
        "blockers": blockers,
        "notes": notes,
    }
