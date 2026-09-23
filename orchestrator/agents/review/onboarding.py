"""User-friendly onboarding checks and setup guide for Daily Review Agent."""

from __future__ import annotations

from typing import Any

from daily_review_agent.config_loader import AgentConfig, load_agent_config, readiness_report


def _step(name: str, ok: bool, detail: str, fix: str = "") -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def run_onboarding(*, verbose: bool = True) -> dict[str, Any]:
    """Run all setup checks and return a human-friendly report."""
    import os
    from pathlib import Path

    cfg = load_agent_config()
    readiness = readiness_report(cfg)
    steps: list[dict[str, Any]] = []

    # Python package
    steps.append(_step("Python package", True, "daily_review_agent importable"))

    # Jira
    jira_blockers = readiness.get("hard_blockers_for_jira_fetch") or []
    steps.append(
        _step(
            "Jira credentials",
            not jira_blockers,
            "PIC/AN fetch ready" if not jira_blockers else "; ".join(jira_blockers),
            "Set JIRA_EMAIL + JIRA_API_TOKEN in jira-release-tool/.env",
        )
    )

    # Node + Teams bridge
    from daily_review_agent.paths import SCRIPTS_DIR, script

    bridge = script("teams_bridge.mjs")
    node_modules = SCRIPTS_DIR / "node_modules" / "@shayanline" / "msteams-mcp"
    steps.append(
        _step(
            "Teams bridge (npm)",
            bridge.is_file() and node_modules.is_dir(),
            "teams_bridge.mjs + @shayanline/msteams-mcp installed"
            if node_modules.is_dir()
            else "Run: npm install in orchestrator/ops/daily_review",
            "cd orchestrator/ops/daily_review; npm install",
        )
    )

    # Calendar backend
    backend = (cfg.calendar_backend or "auto").strip().lower()
    if backend == "graph_delegated":
        graph = readiness.get("graph_delegated") or {}
        blockers = graph.get("blockers") or []
        steps.append(
            _step(
                "Calendar (Graph delegated — ABC tenant often blocked)",
                bool(graph.get("can_schedule")),
                "Not recommended on ABC tenant (AADSTS65002). Use calendar_backend: auto"
                if blockers
                else "Graph token available",
                "Set calendar_backend: auto in agent.yaml; python -m daily_review_agent --outlook-login",
            )
        )
    elif backend == "auto":
        from daily_review_agent.calendar_orchestrator import orchestrator_readiness

        orch = orchestrator_readiness(cfg)
        steps.append(
            _step(
                "Calendar (browser auto — Edge/Playwright)",
                bool(orch.get("can_schedule_any")),
                "Embedded Playwright → Outlook web schedules ONE meeting per 6 PM run. "
                "Fallback: Playwright MCP — daily review calendar playwright"
                if orch.get("can_schedule_any")
                else "; ".join(orch.get("blockers") or [])[:120],
                "python -m daily_review_agent --outlook-login; teams_login in Cursor; enable Playwright plugin",
            )
        )
    elif backend == "outlook_com":
        outlook = readiness.get("outlook_com") or {}
        steps.append(
            _step(
                "Calendar (Outlook desktop — NOT recommended)",
                False,
                "Creates local-only invites — does not sync to Teams/web calendar",
                "Set calendar_backend: auto in agent.yaml",
            )
        )
    else:
        teams = readiness.get("teams_mcp") or {}
        steps.append(
            _step(
                "Calendar (Teams MCP browser)",
                bool(teams.get("can_schedule")),
                "Requires teams_login in Cursor; Graph token often fails on ABC tenant",
                "Use calendar_backend: auto + --outlook-login (embedded Playwright primary)",
            )
        )

    steps.append(
        _step(
            "Playwright MCP calendar fallback",
            True,
            "Manual backup when embedded calendar fails — say daily review calendar playwright",
            "Enable Playwright plugin; MCP: daily_review_calendar_playwright_handoff(dry_run=True)",
        )
    )

    # Teams summary chat
    if cfg.teams_post_summary:
        teams = readiness.get("teams_mcp") or {}
        chat_ok = bool(cfg.teams_summary_conversation_id)
        msg_ok = bool(teams.get("can_message") or teams.get("authenticated"))
        steps.append(
            _step(
                "Teams summary chat",
                chat_ok and msg_ok,
                f"Post to group chat after 6 PM run"
                if chat_ok and msg_ok
                else (
                    "Missing conversation ID"
                    if not chat_ok
                    else "Run teams_login in Cursor (Teams MCP) for chat only"
                ),
                "teams.summary_conversation_id in agent.yaml; teams_login in Cursor",
            )
        )

    from daily_review_agent.preflight import run_preflight

    live_preflight = run_preflight(cfg, dry_run=False, force=True)
    steps.append(
        _step(
            "Production gate (live preflight)",
            bool(live_preflight.get("ready")),
            "Ready for daily_review_run_live"
            if live_preflight.get("ready")
            else "; ".join(live_preflight.get("blockers") or [])[:120],
            "; ".join(live_preflight.get("fix_commands") or []) or "daily_review_preflight(live=true) in Cursor",
        )
    )

    # Agent enabled
    steps.append(
        _step(
            "Agent enabled",
            cfg.enabled,
            "Live 6 PM runs allowed" if cfg.enabled else "Dry-run / --force only",
            "Set enabled: true in orchestrator/agents/review/agent.yaml when ready",
        )
    )

    # Schedule window
    sched = readiness.get("schedule") or {}
    steps.append(
        _step(
            "Schedule window",
            bool(sched.get("configured")),
            f"Active until {sched.get('schedule', {}).get('active_until', '?')}"
            if sched.get("configured")
            else "No end date — runs every day until you stop",
            'Say in Cursor: "schedule daily review for 2 weeks" or MCP daily_review_schedule',
        )
    )

    # MCP
    from daily_review_agent.setup_mcp import validate_cursor_mcp_config

    mcp_val = validate_cursor_mcp_config()
    present = mcp_val.get("servers_present") or {}
    mcp_ok = bool(present.get("release-orchestrator")) and not [
        i for i in (mcp_val.get("issues") or []) if "release-orchestrator" in i.lower()
    ]
    steps.append(
        _step(
            "Cursor MCP registered",
            mcp_ok,
            "release-orchestrator MCP configured"
            if mcp_ok
            else "; ".join((mcp_val.get("issues") or mcp_val.get("missing_servers") or ["Not in mcp.json"])[:2]),
            "Add release-orchestrator block from daily_review_mcp_config — args: [\"-m\", \"release_mcp\"]",
        )
    )

    jira_ok = steps[1]["ok"]
    calendar_ok = any(s["ok"] for s in steps if "Calendar" in s["name"])

    return {
        "ready_for_dry_run": jira_ok,
        "ready_for_live": jira_ok and calendar_ok and cfg.enabled,
        "calendar_backend": backend,
        "steps": steps,
        "readiness": readiness,
        "quick_commands": {
            "status": "python -m daily_review_agent --status",
            "onboard": "python -m daily_review_agent --onboard",
            "graph_login": "python -m daily_review_agent --graph-login",
            "dry_run": "python -m daily_review_agent --dry-run --force",
            "demo_call": "python -m daily_review_agent --demo-call --minutes 30",
            "schedule_2_weeks": 'Cursor: daily_review_schedule(weeks=2)',
        },
    }


def format_onboarding_text(report: dict[str, Any]) -> str:
    """Plain-text onboarding report for CLI / Slack."""
    lines = [
        "Daily Review Agent — Setup Check",
        "================================",
        "",
    ]
    for step in report.get("steps") or []:
        mark = "OK" if step.get("ok") else "!!"
        lines.append(f"[{mark}] {step.get('name')}: {step.get('detail')}")
        if not step.get("ok") and step.get("fix"):
            lines.append(f"     Fix: {step.get('fix')}")
    lines.extend(
        [
            "",
            f"Ready for dry-run: {report.get('ready_for_dry_run')}",
            f"Ready for live 6 PM: {report.get('ready_for_live')}",
            "",
            "Quick commands:",
        ]
    )
    for label, cmd in (report.get("quick_commands") or {}).items():
        lines.append(f"  {label}: {cmd}")
    return "\n".join(lines)
