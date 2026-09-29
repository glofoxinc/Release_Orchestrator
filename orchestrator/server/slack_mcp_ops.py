"""Slack MCP E2E helpers — verification + post handoff for Release Orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config

_PROBE_FILE = Path(__file__).resolve().parents[2] / ".launch" / "slack_channel_probes.json"


def _load_persisted_probes() -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    if not _PROBE_FILE.is_file():
        return None, None
    try:
        raw = json.loads(_PROBE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    if not isinstance(raw, dict):
        return None, None
    channels = raw.get("channel_checks")
    users = raw.get("user_checks")
    return (
        channels if isinstance(channels, list) else None,
        users if isinstance(users, list) else None,
    )
from slack_mcp_verify import build_verification_report, merge_mcp_probe_results
from slack_reference import (
    build_reference_payload,
    compare_preview_to_reference,
    slack_reference_status,
)
from release_mcp import slack_ops


# Live MCP probe results collected during agent sessions (2026-09-17).
# Agent may refresh via slack_mcp_verify(channel_checks=..., user_checks=...).
_DEFAULT_CHANNEL_CHECKS: list[dict[str, Any]] = [
    {
        "name": "insights-customize-squad",
        "channel_id": "C08HB93PEVD",
        "accessible": False,
        "error": "channel_not_found — private channel or wrong workspace; MCP app may lack membership",
    },
    {
        "name": "customize-bi-buddies",
        "channel_id": "C08KM1USMM1",
        "accessible": False,
        "error": "channel_not_found — private channel or wrong workspace; MCP app may lack membership",
    },
]

_DEFAULT_USER_CHECKS: list[dict[str, Any]] = [
    {
        "key": "sushma",
        "name": "Sushma Bhamidipati",
        "configured_user_id": "U08LDAQ7SDV",
        "resolved_user_id": "U08LDAQ7SDV",
        "match": True,
    },
    {
        "key": "sai_anirudh",
        "name": "Sai Anirudh Karre",
        "configured_user_id": "U0BSG4ABZC0",
        "resolved_user_id": "U0BSG4ABZC0",
        "match": True,
    },
    {
        "key": "zeke",
        "name": "Zeke Brustkern",
        "configured_user_id": "U083R8TP1J9",
        "resolved_user_id": "U083R8TP1J9",
        "match": True,
    },
    {
        "key": "eoin",
        "name": "Eoin George",
        "configured_user_id": "U01H0UL5JGP",
        "resolved_user_id": "U01H0UL5JGP",
        "match": True,
    },
]


def slack_mcp_verify(
    *,
    channel_checks: list[dict[str, Any]] | None = None,
    user_checks: list[dict[str, Any]] | None = None,
    refresh_probes: bool = False,
) -> dict[str, Any]:
    """Verify Slack MCP readiness for Step 6 deployment announce."""
    persisted_channels, persisted_users = _load_persisted_probes()
    if channel_checks is None and not refresh_probes:
        channel_checks = persisted_channels if persisted_channels is not None else _DEFAULT_CHANNEL_CHECKS
    if user_checks is None and not refresh_probes:
        user_checks = persisted_users if persisted_users is not None else _DEFAULT_USER_CHECKS
    checks_channels = channel_checks
    checks_users = user_checks
    delivery_mode = slack_ops.slack_delivery_mode()
    if checks_channels is not None or checks_users is not None:
        verification = merge_mcp_probe_results(
            channel_checks=checks_channels,
            user_checks=checks_users,
            delivery_mode=delivery_mode,
        )
    else:
        verification = build_verification_report(delivery_mode=delivery_mode).to_dict()

    status = slack_ops.slack_announce_status()
    return {
        **verification,
        "announce_status": status,
        "mcp_tools": {
            "read_channel": "slack_read_channel",
            "send_message": "slack_send_message",
            "search_channels": "slack_search_channels",
            "search_users": "slack_search_users",
            "mcps": ["user-slack", "plugin-slack-slack"],
        },
        "fix_channel_id": (
            "Slack desktop: open #channel, channel name menu, Copy link; "
            "id is the C... segment in /archives/C.../"
        ),
    }


def slack_mcp_e2e_handoff(
    *,
    ticket_key: str,
    summary: str,
    ticket_url: str,
    version_name: str,
    sharepoint_url: str,
    deploy_date: str,
    environments: str = "Analyze & Custom environments",
    message_edits: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Full Step 6 E2E: verify config + preview messages + MCP post plan."""
    verification = slack_mcp_verify()
    preview = slack_ops.build_slack_preview(
        ticket_key=ticket_key,
        summary=summary,
        ticket_url=ticket_url,
        version_name=version_name,
        sharepoint_url=sharepoint_url,
        deploy_date=deploy_date,
        environments=environments,
    )
    if message_edits:
        preview = slack_ops.apply_slack_message_edits(preview, message_edits)
    enriched = slack_ops.enrich_preview_with_delivery(preview)
    handoff = enriched.get("slack_mcp") or slack_ops.handoff_for_slack_mcp(enriched)
    reference = build_reference_payload()
    parity = compare_preview_to_reference(enriched)
    return {
        "verification": verification,
        "reference": reference,
        "reference_parity": parity,
        "preview": enriched,
        "slack_mcp": handoff,
        "e2e_ready": bool(verification.get("e2e_ready")),
        "instruction": (
            "Match reference.messages in slack_reference (SHIPIT-17191 gold standard). "
            "Post each item in slack_mcp.posts via Cursor Slack MCP slack_send_message. "
            "If channel_not_found, update workspace.yaml channel_ids and re-run slack_mcp_verify. "
            "Then say **slack done** in release_orchestrator."
        ),
    }


def slack_reference(reference_key: str = "") -> dict[str, Any]:
    """Return operator-approved Slack deployment message references."""
    config.ensure_workspace_loaded()
    if (reference_key or "").strip():
        return build_reference_payload(reference_key)
    return slack_reference_status()
