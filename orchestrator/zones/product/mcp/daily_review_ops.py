"""Daily Review Agent MCP tools — merged into Release Orchestrator server."""

from __future__ import annotations

import json
from typing import Any

from daily_review_agent.bootstrap import bootstrap

bootstrap()


def _json(data: object) -> str:
    return json.dumps(data, indent=2, default=str)


def _setup_block_if_missing_mcp() -> str | None:
    from daily_review_agent.setup_mcp import validate_cursor_mcp_config

    mcp_val = validate_cursor_mcp_config()
    if mcp_val.get("missing_servers"):
        return _json(
            {
                "status": "setup_required",
                "message": "Missing MCP servers — run daily_review_mcp_config first.",
                "missing_servers": mcp_val.get("missing_servers"),
                "next": "daily_review_setup(install=true)",
            }
        )
    return None


def register(mcp: Any) -> None:
    """Register daily_review_* tools on the unified Release Orchestrator MCP server."""

    @mcp.tool()
    def daily_review_status() -> str:
        """Readiness: Jira, calendar backend, Teams chat, schedule window, demo attendees."""
        from daily_review_agent.config_loader import load_agent_config, readiness_report

        return _json(readiness_report(load_agent_config()))

    @mcp.tool()
    def daily_review_preflight(live: bool = False, force: bool = False) -> str:
        """Pre-flight gate before live run — blockers and fix commands."""
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.preflight import run_preflight

        cfg = load_agent_config()
        report = run_preflight(cfg, dry_run=not live, force=force)
        return _json(report)

    @mcp.tool()
    def daily_review_outlook_login(wait_minutes: int = 10) -> str:
        """One-time Outlook web sign-in for calendar scheduling (opens Edge, abcfitness.com)."""
        from daily_review_agent.playwright_outlook_auth import run_outlook_login

        return _json(run_outlook_login(wait_minutes=max(1, wait_minutes)))

    @mcp.tool()
    def daily_review_teams_login() -> str:
        """One-time Teams sign-in for summary chat bridge (opens Edge, abcfitness.com)."""
        from daily_review_agent.teams_mcp import run_teams_bridge_login

        return _json(run_teams_bridge_login())

    @mcp.tool()
    def daily_review_setup(install: bool = False) -> str:
        """FIRST-TIME SETUP — full checklist, MCP validation, optional install."""
        from daily_review_agent.setup_mcp import format_setup_text, run_setup

        report = run_setup(install=install)
        return format_setup_text(report) + "\n\n" + _json(report)

    @mcp.tool(name="dr_mcp_config")
    def daily_review_mcp_config() -> str:
        """Copy-paste Cursor mcp.json blocks for release-orchestrator + teams (+ Playwright/Slack plugins)."""
        from daily_review_agent.setup_mcp import generate_mcp_snippets, validate_cursor_mcp_config

        snippets = generate_mcp_snippets()
        validation = validate_cursor_mcp_config()
        payload = {
            "validation": validation,
            "how_to": snippets.get("instructions"),
            "paste_into": snippets.get("mcp_config_path"),
            "mcpServers": snippets.get("mcpServers"),
            "cursor_plugins": snippets.get("cursor_plugins"),
        }
        lines = [
            "Release Orchestrator + Daily Review — Cursor MCP config",
            "=======================================================",
            f"File: {snippets.get('mcp_config_path')}",
            "",
            "Add release-orchestrator + teams under mcpServers. Enable Slack + Playwright plugins in Cursor.",
            "",
        ]
        if validation.get("issues"):
            lines.append("Current issues:")
            for issue in validation["issues"]:
                lines.append(f"  - {issue}")
            lines.append("")
        return "\n".join(lines) + "\n\n" + _json(payload)

    @mcp.tool()
    def daily_review_onboard() -> str:
        """Setup checklist (legacy alias). Prefer daily_review_setup."""
        from daily_review_agent.setup_mcp import format_setup_text, run_setup

        report = run_setup(install=False)
        return format_setup_text(report) + "\n\n" + _json(report)

    @mcp.tool()
    def daily_review_schedule(weeks: int = 2, run_at: str = "18:00") -> str:
        """Auto-schedule window disabled — Daily Review is on-demand only."""
        return _json(
            {
                "ok": False,
                "status": "disabled",
                "reason": "on_demand_only",
                "message": (
                    "Automatic schedule windows are disabled. Say daily review welcome "
                    "or call daily_review_run_live(force=true) when you want a run."
                ),
            }
        )

    @mcp.tool()
    def daily_review_stop_schedule() -> str:
        """Clear the active schedule window."""
        from daily_review_agent.schedule_registry import clear_schedule

        clear_schedule()
        return _json({"ok": True, "message": "Schedule cleared. Use --force or daily_review_run to run anyway."})

    @mcp.tool(name="dr_attendee_policy")
    def daily_review_attendee_policy(force: bool = True) -> str:
        """Preview Daily Review ticket scope + meeting invite policy.

        Tickets: in-squad assignees only (Gabriel/Erasmo skipped unless opted in).
        Invites: required = leadership + QA + in-squad assignees; optional = review/release crew.
        """
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.meeting_attendees import attendee_policy_summary
        from daily_review_agent.ticket_pipeline import resolve_review_issues

        cfg = load_agent_config()
        fetch = resolve_review_issues(cfg)
        issues = fetch.get("issues") or []
        policy = attendee_policy_summary(cfg, issues)
        return _json(
            {
                "ok": True,
                "ticket_count": len(issues),
                "raw_ticket_count": fetch.get("raw_total", len(issues)),
                "skipped_outside_squad": fetch.get("skipped_outside_squad") or [],
                "ticket_scope": fetch.get("ticket_scope") or {},
                "invite_policy": policy,
                "hint": "Run daily_review_run_dry for full preview including meeting draft.",
            }
        )

    @mcp.tool()
    def daily_review_run_dry(force: bool = False) -> str:
        """Preview today's review (no side effects). force=true bypasses enabled:false for setup previews."""
        from daily_review_agent.runner import run_daily_agent

        return _json(run_daily_agent(dry_run=True, force=force))

    @mcp.tool()
    def daily_review_run_live(force: bool = False) -> str:
        """Live run (on-demand): requires force=true or guided confirm — schedules meeting + posts summary."""
        from daily_review_agent.runner import run_daily_agent

        blocked = _setup_block_if_missing_mcp()
        if blocked:
            return blocked
        result = run_daily_agent(dry_run=False, force=force)
        if result.get("status") == "preflight_failed":
            result["setup_hint"] = "Run daily_review_setup() — complete fix_commands before retrying."
        return _json(result)

    @mcp.tool()
    def daily_review_demo_call(dry_run: bool = False, minutes_from_now: int = 30, force: bool = False) -> str:
        """Demo Teams call — Playwright Outlook web when live."""
        from daily_review_agent.demo_call import run_demo_call

        blocked = _setup_block_if_missing_mcp()
        if blocked and not dry_run:
            return blocked
        result = run_demo_call(dry_run=dry_run, minutes_from_now=minutes_from_now, force=force)
        if result.get("status") == "preflight_failed":
            result["setup_hint"] = "Run daily_review_setup() — complete fix_commands first."
        return _json(result)

    @mcp.tool(name="dr_sched_batch")
    def daily_review_schedule_batch(
        date: str = "",
        start_at: str = "20:00",
        count: int = 5,
        duration_minutes: int = 10,
        attendee_emails: list[str] | None = None,
    ) -> str:
        """Schedule N back-to-back calls in ONE Playwright Outlook session (idempotent)."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from daily_review_agent.batch_schedule import build_evening_slots, run_batch_schedule
        from daily_review_agent.config_loader import load_agent_config

        cfg = load_agent_config()
        tz = ZoneInfo(cfg.timezone)
        date_str = date.strip() or datetime.now(tz).date().isoformat()
        slots = build_evening_slots(
            date_str=date_str,
            start_hhmm=start_at,
            count=max(1, count),
            duration_minutes=max(5, duration_minutes),
            timezone=cfg.timezone,
        )
        if attendee_emails:
            emails = list(dict.fromkeys(e.strip() for e in attendee_emails if e and e.strip()))
        else:
            emails = [a.email for a in cfg.demo_attendees if a.email]
            emails = list(dict.fromkeys(e for e in emails if e))
        return _json(
            run_batch_schedule(
                slots=slots,
                attendee_emails=emails,
                subject_prefix="Daily Review Agent — Mohan sync",
                replace_existing=True,
                playwright_only=True,
            )
        )

    @mcp.tool(name="dr_sched_adhoc")
    def daily_review_schedule_ad_hoc(
        subject: str,
        start_iso: str,
        end_iso: str,
        attendee_emails: list[str],
        dry_run: bool = True,
        force: bool = False,
    ) -> str:
        """Schedule arbitrary Teams meeting via Playwright Outlook web."""
        from daily_review_agent.ad_hoc import run_ad_hoc_schedule

        return _json(
            run_ad_hoc_schedule(
                subject=subject,
                start_iso=start_iso,
                end_iso=end_iso,
                attendee_emails=attendee_emails,
                dry_run=dry_run,
                force=force,
            )
        )

    @mcp.tool(name="dr_cal_handoff")
    def daily_review_calendar_playwright_handoff(
        dry_run: bool = True,
        force: bool = True,
    ) -> str:
        """Playwright MCP — primary path for Teams review-call scheduling in Cursor.

        Builds handoff from today's fetched review tickets (one meeting, next business day window).
        Execute steps via Playwright MCP; say **calendar done** when invite is sent.
        """
        from daily_review_agent.calendar_playwright_handoff import handoff_from_run_context
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.runner import run_daily_agent
        from daily_review_agent.schedule import collect_meeting_attendees, meeting_window
        from daily_review_agent.ticket_pipeline import resolve_review_issues

        cfg = load_agent_config()
        if dry_run:
            start, end = meeting_window(cfg)
            meeting_date = start.strftime("%Y-%m-%d")
            subject = f"{cfg.meeting_subject} — {meeting_date}"
            fetch = resolve_review_issues(cfg)
            issues = fetch.get("issues") or []
            attendees = collect_meeting_attendees(cfg, issues)
            handoff = handoff_from_run_context(
                subject=subject,
                start=start,
                end=end,
                attendees=attendees,
                body_text=f"Preview handoff — {len(issues)} ticket(s) in scope.",
                timezone=cfg.timezone,
            )
            handoff["dry_run"] = True
            handoff["ticket_count"] = len(issues)
            return _json(handoff)

        preview = run_daily_agent(dry_run=True, force=force)
        meeting = preview.get("meeting") or {}
        start_s = meeting.get("start") or ""
        end_s = meeting.get("end") or ""
        if not start_s or not end_s:
            return _json({"ok": False, "error": "Could not resolve meeting window from dry run preview."})

        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(cfg.timezone)
        start = datetime.fromisoformat(start_s)
        end = datetime.fromisoformat(end_s)
        if start.tzinfo is None:
            start = start.replace(tzinfo=tz)
        if end.tzinfo is None:
            end = end.replace(tzinfo=tz)
        subject = f"{cfg.meeting_subject} — {start.strftime('%Y-%m-%d')}"
        fetch = preview.get("fetch") or {}
        attendees_specs = collect_meeting_attendees(cfg, fetch.get("issues") or [])
        handoff = handoff_from_run_context(
            subject=subject,
            start=start,
            end=end,
            attendees=attendees_specs,
            body_text=str(preview.get("text_report") or ""),
            timezone=cfg.timezone,
        )
        handoff["dry_run"] = False
        return _json(handoff)

    @mcp.tool()
    def daily_review_orchestrator(message: str = "daily review welcome", workflow_id: str | None = None) -> str:
        """Guided Daily Review E2E — say **daily review welcome**, then **yes** step by step.

        Walks: setup → MCP (release-orchestrator + teams + Playwright/Slack plugins) →
        Teams login → Outlook login → preflight → dry run → live → 2-week schedule.

        Same MCP server as releases. SharePoint/Slack browser paths use Playwright MCP on release flow.
        """
        from release_mcp import daily_review_guided

        return _json(daily_review_guided.run_daily_review_guided(message, workflow_id=workflow_id))
