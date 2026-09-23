"""Shared production readiness — MCP + platform use the same checks."""

from __future__ import annotations

from datetime import date, time
from typing import Any, Literal

import config
import integration_readiness
import operator_signoff as osign
import schedule_time
from release_mcp import onboarding

Surface = Literal["mcp", "platform", "both"]


def _assess_daily_review_readiness() -> dict[str, list[dict[str, str]]]:
    """Daily Review Agent checks (merged in jira-release-tool v3.3+)."""
    verified: list[dict[str, str]] = []
    unverified: list[dict[str, str]] = []
    operator: list[dict[str, str]] = []

    try:
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.playwright_outlook_auth import outlook_readiness
        from daily_review_agent.setup_mcp import validate_cursor_mcp_config

        cfg = load_agent_config()
        mcp_val = validate_cursor_mcp_config()
        outlook = outlook_readiness()
        mcp_ok = not mcp_val.get("missing_servers") and not mcp_val.get("issues")

        if mcp_ok:
            verified.append(
                {"name": "daily_review_mcp", "detail": "release-orchestrator + teams MCP configured"}
            )
        else:
            unverified.append(
                {
                    "name": "daily_review_mcp",
                    "detail": "; ".join((mcp_val.get("issues") or mcp_val.get("missing_servers") or [])[:3]),
                }
            )

        if outlook.get("can_schedule"):
            verified.append({"name": "daily_review_outlook", "detail": "Outlook web Playwright profile ready"})
        else:
            unverified.append(
                {
                    "name": "daily_review_outlook",
                    "detail": "Run daily_review_outlook_login or python -m daily_review_agent --outlook-login",
                }
            )

        if cfg.teams_summary_conversation_id:
            verified.append({"name": "daily_review_teams_chat", "detail": "Teams summary conversation configured"})
        else:
            unverified.append({"name": "daily_review_teams_chat", "detail": "Set teams.summary_conversation_id in agent.yaml"})

        operator.append(
            {
                "name": "daily_review_pilot_signoff",
                "detail": "Run .\\release_mcp\\scripts\\daily_review\\pilot_signoff.ps1 before Task Scheduler",
            }
        )
    except Exception as exc:  # noqa: BLE001
        unverified.append({"name": "daily_review_module", "detail": str(exc)[:200]})

    return {"verified": verified, "unverified": unverified, "operator_required": operator}


def _schedule_model_ok() -> tuple[bool, str]:
    try:
        jira = schedule_time.resolve_jira_schedule(
            date(2026, 9, 11), time(10, 30),
            date(2026, 9, 11), time(11, 30),
        )
        agreed = str(jira.get("agreed_range") or "")
        reviewer = str(jira.get("reviewer_range") or "")
        if "IST" not in agreed or "10:30 AM" not in agreed:
            return False, f"Agreed range wrong: {agreed}"
        iso = str(jira.get("start_iso") or "")
        if not reviewer or not (iso.endswith("-0500") or iso.endswith("-0600")):
            return False, f"Jira ISO not US Central: {iso}"
        return True, f"{agreed} → {reviewer}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def slack_delivery_mode() -> str:
    """How Step 6 posts: Cursor Slack MCP (default) or optional bot token."""
    from release_mcp import slack_ops

    return slack_ops.slack_delivery_mode()


def assess_production_readiness(*, surface: Surface = "both") -> dict[str, Any]:
    """VERIFIED / UNVERIFIED / OPERATOR REQUIRED — same report for MCP and platform."""
    setup = onboarding.assess_setup()
    integ = integration_readiness.summarize_readiness(include_excluded=True)
    delivery = slack_delivery_mode()
    signoffs = osign.signoff_status()

    verified: list[dict[str, str]] = []
    unverified: list[dict[str, str]] = []
    operator: list[dict[str, str]] = []

    def _add(name: str, ok: bool, detail: str, *, op: bool = False) -> None:
        row = {"name": name, "detail": detail}
        if op:
            operator.append(row)
        elif ok:
            verified.append(row)
        else:
            unverified.append(row)

    _add(
        "jira_credentials",
        setup.get("jira_ready") is True,
        "JIRA_EMAIL + JIRA_API_TOKEN in .env"
        if setup.get("jira_ready")
        else "Missing Jira credentials — copy .env.example → .env",
    )

    if surface in {"mcp", "both"}:
        _add(
            "mcp_configured",
            setup.get("fully_ready") is True,
            "Cursor MCP + .env ready"
            if setup.get("fully_ready")
            else "Finish onboarding — MCP JSON + Jira token",
        )

    sched_ok, sched_detail = _schedule_model_ok()
    _add("schedule_ist_to_cst", sched_ok, sched_detail)

    _add(
        "shipit_metadata",
        bool(config.SERVICE_DESK_ENABLED and config.TCKT_ISSUE_TYPE_ID),
        f"SHIPIT project configured ({config.TCKT_PROJECT_KEY or 'SHIPIT'})",
    )

    for item in integ.get("items") or []:
        iid = str(item.get("id") or "")
        status = str(item.get("status") or "")
        detail = str(item.get("detail") or "")
        if iid in {"team_scope", "service_desk", "release_notes"}:
            _add(f"integration_{iid}", status == "ready", detail)

    slack_verify: dict[str, Any] = {}
    if delivery == "cursor_slack_mcp":
        from release_mcp import slack_mcp_ops

        slack_verify = slack_mcp_ops.slack_mcp_verify()

    if delivery == "disabled":
        _add("slack_announce", False, "Slack announce disabled in workspace.yaml")
    elif delivery == "cursor_slack_mcp":
        import browser_automation

        e2e = bool(slack_verify.get("e2e_ready"))
        blockers = slack_verify.get("blockers") or []
        playwright_slack = (
            browser_automation.prefer_playwright_slack()
            and bool((browser_automation.slack_section().get("team_id") or "").strip())
        )
        if e2e:
            detail = "Step 6 via Cursor Slack MCP — channels verified"
            _add("slack_delivery", True, detail)
        elif playwright_slack:
            detail = (
                "Step 6 via Playwright MCP (Glofox private channels) — say **send slack** → **slack done**"
            )
            _add("slack_delivery", True, detail)
            if blockers:
                _add(
                    "slack_mcp_e2e",
                    False,
                    "Slack MCP blocked on private channels — Playwright path is configured (OK for v1)",
                    op=True,
                )
        else:
            detail = "Channel access blocked: " + "; ".join(str(b) for b in blockers[:2])
            _add("slack_delivery", False, detail)
            if blockers:
                _add("slack_mcp_e2e", False, blockers[0][:200])
    elif delivery == "bot_token":
        _add(
            "slack_delivery",
            True,
            "Step 6 auto-send via SLACK_BOT_TOKEN (platform headless)",
        )
    else:
        _add(
            "slack_delivery",
            False,
            "Slack channels missing channel_id in workspace.yaml",
        )

    shipit_detail = (
        (signoffs.get("signoffs") or {}).get(osign.SIGNOFF_SHIPIT_DRY_RUN, {}).get("detail")
        or "Recorded"
    )
    slack_detail = (
        (signoffs.get("signoffs") or {}).get(osign.SIGNOFF_SLACK_LIVE, {}).get("detail")
        or "Recorded"
    )
    if signoffs.get("shipit_dry_run"):
        _add("live_shipit_dry_run", True, shipit_detail)
    else:
        _add(
            "live_shipit_dry_run",
            False,
            "Run: python orchestrator/ops/complete_launch.py --dry-run-version VERSION --sharepoint-url URL",
            op=True,
        )
    if signoffs.get("slack_live_confirm"):
        _add("live_slack_confirm", True, slack_detail)
    else:
        _add(
            "live_slack_confirm",
            False,
            "After Step 6 Slack MCP post: python orchestrator/ops/complete_launch.py --confirm-slack \"posted\"",
            op=True,
        )
    _add(
        "teams_scheduling",
        False,
        "Optional — Teams archived until MS_GRAPH_* authorized",
        op=True,
    )

    dr = _assess_daily_review_readiness()
    for row in dr.get("verified") or []:
        verified.append(row)
    for row in dr.get("unverified") or []:
        unverified.append(row)
    for row in dr.get("operator_required") or []:
        operator.append(row)

    blocking = integ.get("blocking_pending") or []
    code_ready = sched_ok and not blocking and setup.get("jira_ready")
    mcp_ready = code_ready and (surface == "platform" or setup.get("fully_ready"))
    import browser_automation

    slack_ok = delivery in {"cursor_slack_mcp", "bot_token", "disabled"}
    if delivery == "cursor_slack_mcp":
        playwright_slack_ok = (
            browser_automation.prefer_playwright_slack()
            and bool((browser_automation.slack_section().get("team_id") or "").strip())
        )
        slack_ok = slack_ok and (
            bool(slack_verify.get("e2e_ready")) or playwright_slack_ok
        )
    production_ready = mcp_ready and slack_ok and delivery != "not_configured"
    launch_complete = (
        code_ready
        and slack_ok
        and delivery != "not_configured"
        and bool(signoffs.get("launch_complete"))
    )

    total_auto = len(verified) + len(unverified)
    pct = round(100 * len(verified) / total_auto) if total_auto else 0

    return {
        "version": "3.4.0",
        "surface": surface,
        "production_ready": production_ready,
        "launch_complete": launch_complete,
        "mcp_e2e_ready": mcp_ready,
        "platform_ready": code_ready,
        "automated_score_pct": pct,
        "slack_delivery": delivery,
        "operator_signoffs": signoffs,
        "verified": verified,
        "unverified": unverified,
        "operator_required": operator,
        "setup": setup,
        "integrations": integ,
        "schedule_defaults": {
            "agreed": "10:30–11:30 AM IST (Asia/Kolkata)",
            "jira_storage": "US Central (America/Chicago) — same instant",
        },
        "say_to_user": format_production_readiness_message(
            production_ready=production_ready,
            launch_complete=launch_complete,
            mcp_e2e_ready=mcp_ready,
            pct=pct,
            delivery=delivery,
            verified=verified,
            unverified=unverified,
            operator=operator,
            surface=surface,
        ),
    }


def format_production_readiness_message(
    *,
    production_ready: bool,
    launch_complete: bool = False,
    mcp_e2e_ready: bool,
    pct: int,
    delivery: str,
    verified: list[dict[str, str]],
    unverified: list[dict[str, str]],
    operator: list[dict[str, str]],
    surface: Surface = "both",
) -> str:
    title = "Production readiness"
    if surface == "mcp":
        title = "MCP production readiness"
    elif surface == "platform":
        title = "Platform production readiness"

    lines = [f"**{title}**", ""]
    if launch_complete:
        lines.append("**Status: Launch complete** — automated + operator sign-offs done. Project closed for prod.")
    elif production_ready:
        lines.append(
            f"**Status: Production ready ({pct}% automated)** — Jira, SHIPIT, schedule, Slack path OK."
        )
    elif mcp_e2e_ready:
        lines.append(
            f"**Status: E2E ready ({pct}% automated)** — run releases; complete operator checks before prod."
        )
    else:
        lines.append(f"**Status: Setup incomplete ({pct}% automated)** — fix items below.")

    if delivery == "cursor_slack_mcp":
        lines.append("")
        lines.append(
            "**Slack (simple):** At Step 6 the agent posts using **Cursor Slack MCP** — "
            "you do **not** need `SLACK_BOT_TOKEN` in `.env`."
        )

    lines.append("")
    lines.append("**VERIFIED:**")
    for row in verified:
        lines.append(f"- {row['name']}: {row['detail']}")
    if unverified:
        lines.append("")
        lines.append("**UNVERIFIED:**")
        for row in unverified:
            lines.append(f"- {row['name']}: {row['detail']}")
    if operator:
        lines.append("")
        lines.append("**OPERATOR REQUIRED (once before prod):**")
        for row in operator:
            lines.append(f"- {row['name']}: {row['detail']}")

    lines.append("")
    lines.append(
        "**Deploy window:** 10:30–11:30 AM IST → Jira stores US Central (CST/CDT); ticket shows both."
    )
    if launch_complete:
        lines.append("")
        lines.append("**What's next:** **welcome** to run releases. Project is fully signed off.")
    elif production_ready:
        lines.append("")
        lines.append(
            "**What's next:** Complete operator sign-offs (`complete_launch.py`) or say "
            "**shipit confirmed** / **slack confirmed** in MCP."
        )
    elif mcp_e2e_ready:
        lines.append("")
        lines.append("**What's next:** **welcome** to start; say **production ready** anytime to refresh.")
    else:
        lines.append("")
        lines.append("**What's next:** **onboarding** to finish setup.")
    return "\n".join(lines)


__all__ = [
    "assess_production_readiness",
    "format_production_readiness_message",
    "slack_delivery_mode",
]
