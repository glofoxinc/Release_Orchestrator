"""MCP tools: onboarding."""

from __future__ import annotations

from typing import Any

import config
import jira_client
from release_mcp import (
    browser_ops,
    gate_ops,
    release_ops,
    sharepoint_ops,
    slack_mcp_ops,
    slack_ops,
    teams_ops,
    wizard,
)
from release_mcp.operator_guide import enrich_tool_response
from release_mcp.server.bootstrap import logger, mcp

@mcp.tool()
def quickstart() -> dict:
    """Complete operator guide summary (orchestrator/zones/knowledge/guides/GUIDE.md).

    Say **guide** or **quickstart** in chat. No credentials required.
    """
    from release_mcp import quickstart as qs

    payload = qs.quickstart_payload()
    payload["markdown"] = qs.quickstart_markdown()
    payload["say_to_user"] = payload["markdown"]
    return enrich_tool_response(payload, tool="quickstart")


@mcp.tool()
def onboarding_guide() -> dict:
    """First-time onboarding — MCP catalog, phrase cheat sheet, setup checklist.

    Safe without credentials. New colleagues: read ``intro``, enable MCPs in
    ``mcp_catalog``, then say **welcome onboard** in ``release_orchestrator``.
    Covers Jira .env, Release Orchestrator MCP, Slack MCP, Playwright MCP,
    and every chat phrase per release step.
    """
    from release_mcp import onboarding

    assessment = onboarding.assess_setup(from_mcp=True)
    payload = onboarding.full_onboarding_guide(assessment=assessment)
    return enrich_tool_response(payload, tool="onboarding_guide")


@mcp.tool()
def onboarding_wizard(message: str = "welcome onboard") -> dict:
    """Beginner linear onboarding — one step at a time, auto-install where possible.

    Say **welcome onboard** — auto-runs venv, pip, `.env`, MCP merge in one burst.
    Pauses only for Jira credentials, one MCP reload, and Playwright sign-in.

    Args:
        message: welcome onboard, continue, release only, use glofox, env inputs, etc.
    """
    from release_mcp import beginner_wizard

    payload = beginner_wizard.process_message(message)
    return enrich_tool_response(payload, tool="onboarding_wizard")


@mcp.tool()
def install_mcp_config(track: str = "release") -> dict:
    """Merge Release Orchestrator + Playwright MCP blocks into Cursor mcp.json.

    Uses detected repo paths — no hard-coded usernames. Backs up existing mcp.json.
    Reload Cursor MCP after this tool returns ok.

    Args:
        track: release, daily_review, or both (adds teams server when both).
    """
    from release_mcp import mcp_installer

    key = (track or "release").strip().lower()
    if key not in {"release", "daily_review", "both"}:
        key = "release"
    result = mcp_installer.merge_starter_servers(track=key, backup=True)
    return enrich_tool_response(result, tool="install_mcp_config")


@mcp.tool(name="onboarding_preflight")
def onboarding_preflight(track: str = "release", apply_fix: bool = False) -> dict:
    """Run onboarding preflight before welcome onboard — Node, venv, MCP JSON, deprecated servers.

    Args:
        track: release, daily_review, or both.
        apply_fix: When true, merge MCP blocks and strip deprecated servers in project mcp.json.
    """
    from release_mcp import onboarding_preflight as opf

    key = (track or "release").strip().lower()
    if key not in {"release", "daily_review", "both"}:
        key = "release"
    if apply_fix:
        payload = opf.apply_safe_fixes(track=key)
    else:
        report = opf.run_preflight(track=key)
        payload = {"report": report, "markdown": opf.format_preflight_markdown(report)}
    return enrich_tool_response(payload, tool="onboarding_preflight")


@mcp.tool()
def onboarding_env(message: str = "") -> dict:
    """Natural-language `.env` onboarding — parse chat inputs and show required params.

    Users can say random phrases (org name, email, use glofox, projects pic an).
    The tool writes recognized keys to local ``.env`` and returns what is still missing.

    Args:
        message: Free-form chat, or empty for full checklist. Examples:
            ``env checklist``, ``org is abcfinancial``, ``email you@abcfitness.com``,
            ``use glofox``, ``projects pic an``.
    """
    from release_mcp import env_onboarding as env_ob

    if not (message or "").strip():
        payload = {
            "prompt": env_ob.format_env_checklist(),
            "status": env_ob.assess_env_params(),
        }
    else:
        payload = env_ob.process_env_message(message)
    return enrich_tool_response(payload, tool="onboarding_env")


@mcp.tool()
def slack_reference(reference_key: str = "") -> dict:
    """Operator-approved Slack deployment announce references (SHIPIT-17191 gold standard).

    Returns per-channel example messages, CC rules, body structure, and parity
    check when the engine re-renders the reference ticket. Use before Step 6
    live post so copy matches squad vs buddies format.

    Args:
        reference_key: Optional SHIPIT key (default SHIPIT-17191). Empty = full status.
    """
    return enrich_tool_response(
        slack_mcp_ops.slack_reference(reference_key=reference_key),
        tool="slack_reference",
    )


