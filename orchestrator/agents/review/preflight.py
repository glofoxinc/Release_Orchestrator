"""Pre-flight checks before live Daily Review Agent runs."""

from __future__ import annotations

from typing import Any

from daily_review_agent.config_loader import AgentConfig, readiness_report
from daily_review_agent.schedule_registry import schedule_is_active


def run_preflight(cfg: AgentConfig, *, dry_run: bool = True, force: bool = False) -> dict[str, Any]:
    """Return readiness blockers and fix commands before side effects."""
    readiness = readiness_report(cfg)
    blockers: list[str] = []
    warnings: list[str] = []
    fix_commands: list[str] = []

    jira_blockers = list(readiness.get("hard_blockers_for_jira_fetch") or [])
    if jira_blockers:
        blockers.extend(jira_blockers)
        fix_commands.append("Set JIRA_EMAIL + JIRA_API_TOKEN in jira-release-tool/.env")

    if dry_run:
        return {
            "ready": len(blockers) == 0,
            "blockers": blockers,
            "fix_commands": _dedupe(fix_commands),
            "readiness": readiness,
            "mode": "dry_run",
        }

    if not cfg.enabled and not force:
        blockers.append("Agent disabled — set enabled: true in agent.yaml or use force=true")
        fix_commands.append("Set enabled: true in orchestrator/agents/review/agent.yaml")

    if not force and not schedule_is_active(timezone=cfg.timezone):
        blockers.append("Today is outside active_from/active_until schedule window")
        fix_commands.append('Cursor: daily_review_schedule(weeks=2) or pass force=true')

    backend = (cfg.calendar_backend or "auto").strip().lower()
    if backend == "auto":
        from daily_review_agent.calendar_orchestrator import orchestrator_readiness

        orch = orchestrator_readiness(cfg)
        if not orch.get("can_schedule_any"):
            blockers.extend(orch.get("blockers") or ["No calendar backend available"])
            if getattr(cfg, "playwright_mcp_primary_enabled", True):
                fix_commands.append(
                    "Cursor → Settings → MCP → enable Playwright — sign in to M365 once, then say playwright confirmed"
                )
            else:
                fix_commands.append("python -m daily_review_agent --outlook-login  — one-time abcfitness.com sign-in")
    else:
        calendar_blockers = list(readiness.get("hard_blockers_for_live_calendar") or [])
        if calendar_blockers:
            blockers.extend(calendar_blockers)
            if backend == "graph_delegated":
                fix_commands.append(
                    "ABC tenant: --graph-login fails (AADSTS65002) — use calendar_backend: auto, or IT Entra app"
                )
            elif backend == "outlook_com":
                fix_commands.append("Outlook desktop must be running")
            elif backend == "teams_mcp":
                fix_commands.append("Run teams_login in Cursor (Teams MCP)")

    calendar_ready = False
    if backend == "auto":
        from daily_review_agent.calendar_orchestrator import orchestrator_readiness

        calendar_ready = bool(orchestrator_readiness(cfg).get("can_schedule_any"))
    else:
        calendar_ready = not list(readiness.get("hard_blockers_for_live_calendar") or [])

    if cfg.teams_post_summary and cfg.teams_mcp_enabled:
        teams_blockers = list(readiness.get("hard_blockers_for_live_teams") or [])
        if teams_blockers:
            if calendar_ready:
                warnings.append(
                    "Teams bridge not authenticated — summary post may fail. "
                    "Run teams_login in Cursor, then retry daily_review_run_live."
                )
                fix_commands.append("Run teams_login in Cursor (Teams MCP)")
            else:
                blockers.extend(teams_blockers)
                fix_commands.append("Run teams_login in Cursor (Teams MCP)")

    if cfg.alerting.on_schedule_failure and cfg.teams_mcp_enabled:
        teams_auth = readiness.get("teams_mcp") or {}
        if not teams_auth.get("authenticated"):
            msg = "Teams session required for organizer failure alerts"
            if calendar_ready:
                warnings.append(msg)
            else:
                blockers.append(msg)
            fix_commands.append("Run teams_login in Cursor (Teams MCP)")

    if cfg.playwright_mcp_fallback_enabled:
        for msg in readiness.get("playwright_mcp_fallback_warnings") or []:
            if msg and msg not in warnings:
                warnings.append(str(msg))

    if not cfg.required_attendees and (cfg.calendar_backend or "").strip().lower() == "graph_delegated":
        pass  # assignees may come from Jira at runtime

    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "fix_commands": _dedupe(fix_commands),
        "readiness": readiness,
        "mode": "live",
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def live_schedule_ok(schedule: dict[str, Any] | None, *, dry_run: bool) -> bool:
    """True when scheduling succeeded — join URL or Playwright Outlook Send confirmed."""
    if not isinstance(schedule, dict) or not schedule.get("ok"):
        return False
    if dry_run:
        return True
    if str(schedule.get("join_url") or "").strip():
        return True
    if schedule.get("backend") == "playwright_outlook" and schedule.get("sent"):
        return True
    return False
