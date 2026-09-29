"""Slack MCP verification helpers for Release Orchestrator Step 6.

Cursor Slack MCP (``slack_read_channel``, ``slack_send_message``) is the primary
delivery path when ``SLACK_BOT_TOKEN`` is not set. This module documents
configured targets, merges optional live MCP probe results, and builds the
agent E2E post plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import config
from slack_announce import (
    CANONICAL_CHANNEL_REQUIREMENTS,
    SlackAnnounceConfig,
    default_cc_people,
    load_announce_config,
    validate_announce_config,
)


@dataclass(frozen=True)
class McpChannelProbe:
    """Result of probing one channel via Cursor Slack MCP."""

    name: str
    channel_id: str
    accessible: bool
    error: str = ""


@dataclass(frozen=True)
class McpUserProbe:
    """Result of resolving one CC person via Cursor Slack MCP."""

    key: str
    name: str
    configured_user_id: str
    resolved_user_id: str = ""
    match: bool = False
    error: str = ""


@dataclass
class SlackMcpVerificationReport:
    """Offline config + optional MCP probe merge."""

    delivery_mode: str
    enterprise_host: str
    mcp_user_id: str
    channels: list[dict[str, Any]] = field(default_factory=list)
    cc_users: list[dict[str, Any]] = field(default_factory=list)
    config_ready: bool = False
    send_ready: bool = False
    e2e_ready: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    agent_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivery_mode": self.delivery_mode,
            "enterprise_host": self.enterprise_host,
            "mcp_user_id": self.mcp_user_id,
            "channels": self.channels,
            "cc_users": self.cc_users,
            "config_ready": self.config_ready,
            "send_ready": self.send_ready,
            "e2e_ready": self.e2e_ready,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "agent_steps": self.agent_steps,
        }


def parse_channel_id_from_slack_url(url: str) -> str:
    """Extract ``C…`` / ``G…`` channel id from a Slack archive permalink."""
    raw = (url or "").strip()
    if not raw:
        return ""
    path = urlparse(raw).path.strip("/")
    parts = path.split("/")
    for part in parts:
        if part.startswith(("C", "G")) and len(part) >= 9:
            return part
    return ""


def _slack_mcp_section() -> dict[str, Any]:
    config.ensure_workspace_loaded()
    root = getattr(config, "_ws", {}) or {}
    section = root.get("slack_mcp") if isinstance(root.get("slack_mcp"), dict) else {}
    return dict(section or {})


def enterprise_host() -> str:
    return str(_slack_mcp_section().get("enterprise_host") or "grid-abcfitness.enterprise.slack.com").strip()


def configured_mcp_user_id() -> str:
    return str(_slack_mcp_section().get("mcp_user_id") or "U08N0KDPSDU").strip()


def build_verification_report(
    cfg: SlackAnnounceConfig | None = None,
    *,
    channel_probes: list[McpChannelProbe] | None = None,
    user_probes: list[McpUserProbe] | None = None,
    delivery_mode: str = "",
) -> SlackMcpVerificationReport:
    """Build verification report from workspace config and optional MCP probes."""
    cfg = cfg or load_announce_config({"slack_announce": config.SLACK_ANNOUNCE})
    issues = validate_announce_config(cfg)
    probe_by_id = {p.channel_id: p for p in (channel_probes or [])}
    probe_by_name = {p.name.lstrip("#"): p for p in (channel_probes or [])}
    user_probe_by_key = {p.key: p for p in (user_probes or [])}

    blockers: list[str] = []
    warnings: list[str] = []
    channel_rows: list[dict[str, Any]] = []
    cc_rows: list[dict[str, Any]] = []

    if not cfg.enabled:
        blockers.append("slack_announce.enabled=false in workspace.yaml")

    cc_people = default_cc_people()
    for spec in CANONICAL_CHANNEL_REQUIREMENTS:
        channel = next(
            (c for c in cfg.channels if c.key == spec["key"] or c.name.lstrip("#") == spec["name"]),
            None,
        )
        configured_id = channel.channel_id if channel else ""
        probe = probe_by_id.get(configured_id) or probe_by_name.get(spec["name"])
        accessible = probe.accessible if probe else None
        row: dict[str, Any] = {
            "key": spec["key"],
            "name": spec["name"],
            "configured_channel_id": configured_id,
            "mcp_accessible": accessible,
            "mcp_error": (probe.error if probe else ""),
            "required_cc_keys": list(spec["cc_keys"]),
        }
        if not configured_id:
            blockers.append(f"Missing channel_id for #{spec['name']} in workspace.yaml")
        elif accessible is False:
            warnings.append(
                f"Read probe failed for #{spec['name']} ({configured_id}) — "
                "slack_send_message may still work if you are a channel member."
            )
        elif accessible is None:
            warnings.append(
                f"Channel #{spec['name']} ({configured_id}) not yet probed via slack_read_channel."
            )
        channel_rows.append(row)

    for key, person in sorted(cc_people.items()):
        probe = user_probe_by_key.get(key)
        configured_id = person.user_id
        resolved_id = probe.resolved_user_id if probe else ""
        match = probe.match if probe else None
        row = {
            "key": key,
            "name": person.name,
            "configured_user_id": configured_id,
            "resolved_user_id": resolved_id,
            "mcp_match": match,
            "mcp_error": (probe.error if probe else ""),
        }
        if match is False:
            blockers.append(
                f"CC user {person.name} ({key}): configured {configured_id}, "
                f"MCP resolved {resolved_id or '?'}"
            )
        elif match is True:
            pass
        elif configured_id:
            warnings.append(f"CC user {person.name} ({key}) not yet verified via slack_search_users.")
        cc_rows.append(row)

    for issue in issues:
        if issue.level == "error":
            blockers.append(issue.message)
        elif issue.level == "warning":
            warnings.append(issue.message)

    mode = delivery_mode or ("cursor_slack_mcp" if cfg.channels and all(c.channel_id for c in cfg.channels) else "not_configured")
    if mode == "not_configured":
        blockers.append("Slack delivery mode is not_configured — set channel_ids in workspace.yaml")

    agent_steps = [
        "1. Call slack_mcp_verify (this tool) — review blockers before live post.",
        "2. slack_preview(...) — build both channel messages.",
        "3. For each post in slack_mcp.posts: Cursor Slack MCP slack_send_message(channel_id, message).",
        "4. If channel_not_found: open Slack, Copy link on #channel, update workspace.yaml channel_ids.",
        "5. Say **slack done** in release_orchestrator when both channels are posted.",
    ]
    if any(r.get("mcp_accessible") is False for r in channel_rows):
        agent_steps.insert(
            3,
            "Fallback: slack_playwright_handoff(...) or **send slack playwright** in guided chat.",
        )

    config_ready = cfg.enabled and mode == "cursor_slack_mcp" and not any(
        "Missing channel_id" in b or "not_configured" in b for b in blockers
    )
    send_ready = config_ready
    e2e_ready = config_ready
    return SlackMcpVerificationReport(
        delivery_mode=mode,
        enterprise_host=enterprise_host(),
        mcp_user_id=configured_mcp_user_id(),
        channels=channel_rows,
        cc_users=cc_rows,
        config_ready=config_ready,
        send_ready=send_ready,
        e2e_ready=e2e_ready,
        blockers=blockers,
        warnings=warnings,
        agent_steps=agent_steps,
    )


def merge_mcp_probe_results(
    *,
    channel_checks: list[dict[str, Any]] | None = None,
    user_checks: list[dict[str, Any]] | None = None,
    delivery_mode: str = "",
) -> dict[str, Any]:
    """Merge agent-supplied Slack MCP probe results into a verification report."""
    channel_probes = [
        McpChannelProbe(
            name=str(item.get("name") or ""),
            channel_id=str(item.get("channel_id") or ""),
            accessible=bool(item.get("accessible")),
            error=str(item.get("error") or ""),
        )
        for item in (channel_checks or [])
    ]
    user_probes = [
        McpUserProbe(
            key=str(item.get("key") or ""),
            name=str(item.get("name") or ""),
            configured_user_id=str(item.get("configured_user_id") or ""),
            resolved_user_id=str(item.get("resolved_user_id") or ""),
            match=bool(item.get("match")),
            error=str(item.get("error") or ""),
        )
        for item in (user_checks or [])
    ]
    report = build_verification_report(
        channel_probes=channel_probes,
        user_probes=user_probes,
        delivery_mode=delivery_mode,
    )
    return report.to_dict()
