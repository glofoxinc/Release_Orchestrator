"""python -m daily_review_agent — CLI for daily review, onboarding, demo call."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    from daily_review_agent.bootstrap import bootstrap

    bootstrap()

    parser = argparse.ArgumentParser(
        description="Daily Review Agent — Glofox PIC/AN daily ticket review + Teams meeting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m daily_review_agent --onboard          Setup checklist
  python -m daily_review_agent --preflight        Pre-flight before live run
  python -m daily_review_agent --outlook-login    One-time Outlook web sign-in (calendar)
  python -m daily_review_agent --teams-login      One-time Teams sign-in (summary chat bridge)
  python -m daily_review_agent --graph-login      Legacy Graph sign-in (not used on ABC)
  python -m daily_review_agent --dry-run --force
  python -m daily_review_agent --demo-call --minutes 30
  python -m daily_review_agent --schedule-weeks 2
        """,
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    parser.add_argument("--live", action="store_true", help="Create real meeting + post summary")
    parser.add_argument("--force", action="store_true", help="Run even when enabled: false")
    parser.add_argument("--status", action="store_true", help="JSON readiness report")
    parser.add_argument("--onboard", action="store_true", help="Friendly setup checklist")
    parser.add_argument("--setup", action="store_true", help="First-user setup (MCP config + deps checklist)")
    parser.add_argument("--setup-install", action="store_true", help="Run setup + npm/pip install")
    parser.add_argument("--mcp-config", action="store_true", help="Print Cursor mcp.json blocks (JSON)")
    parser.add_argument("--preflight", action="store_true", help="Pre-flight gate (use --live for live checks)")
    parser.add_argument("--preflight-live", action="store_true", help="Pre-flight gate for live run")
    parser.add_argument(
        "--outlook-login",
        action="store_true",
        help="One-time Outlook web sign-in (Playwright Edge profile, abcfitness.com)",
    )
    parser.add_argument(
        "--graph-login",
        action="store_true",
        help="Legacy Graph MSAL sign-in (blocked on ABC tenant — use --outlook-login)",
    )
    parser.add_argument(
        "--teams-login",
        action="store_true",
        help="One-time Teams sign-in for summary chat bridge (opens Edge, abcfitness.com)",
    )
    parser.add_argument("--demo-call", action="store_true", help="Schedule 2-person demo meeting")
    parser.add_argument("--minutes", type=int, default=30, help="Demo call starts N minutes from now")
    parser.add_argument("--schedule-weeks", type=int, metavar="N", help="Register N-week run window")
    parser.add_argument(
        "--schedule-batch",
        action="store_true",
        help="Schedule multiple back-to-back calls (use with --date, --start-at, --count, --duration)",
    )
    parser.add_argument("--date", default="", help="Batch date YYYY-MM-DD (default today IST)")
    parser.add_argument("--start-at", default="20:00", help="Batch start HH:MM IST")
    parser.add_argument("--count", type=int, default=5, help="Number of consecutive meetings")
    parser.add_argument("--duration", type=int, default=10, help="Each meeting duration in minutes")
    args = parser.parse_args()

    from daily_review_agent.config_loader import load_agent_config, readiness_report
    from daily_review_agent.runner import run_daily_agent

    if args.outlook_login:
        from daily_review_agent.playwright_outlook_auth import run_outlook_login

        print("Opening Edge — sign in to Outlook with abcfitness.com when prompted...")
        result = run_outlook_login(wait_minutes=10)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.graph_login:
        from daily_review_agent.graph_calendar import acquire_graph_token

        print("Opening browser for legacy Graph sign-in (ABC tenant usually blocks this)...")
        token = acquire_graph_token(interactive=True)
        print(json.dumps({"ok": bool(token), "message": "Graph token saved"}))
        return 0

    if args.teams_login:
        from daily_review_agent.teams_mcp import run_teams_bridge_login

        print("Opening Edge — sign in to Teams with abcfitness.com when prompted...")
        result = run_teams_bridge_login()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.setup or args.setup_install or args.mcp_config:
        from daily_review_agent.setup_mcp import format_setup_text, generate_mcp_snippets, run_setup

        if args.mcp_config:
            from daily_review_agent.setup_mcp import validate_cursor_mcp_config

            print(
                json.dumps(
                    {"validation": validate_cursor_mcp_config(), **generate_mcp_snippets()},
                    indent=2,
                    default=str,
                )
            )
            return 0
        report = run_setup(install=args.setup_install)
        print(format_setup_text(report))
        return 0 if report.get("ready_for_dry_run") else 1

    if args.onboard:
        from daily_review_agent.setup_mcp import format_setup_text, run_setup

        report = run_setup(install=False)
        print(format_setup_text(report))
        return 0 if report.get("ready_for_dry_run") else 1

    if args.preflight or args.preflight_live:
        from daily_review_agent.preflight import run_preflight

        cfg = load_agent_config()
        live_check = args.preflight_live or args.live
        report = run_preflight(cfg, dry_run=not live_check, force=args.force)
        print(json.dumps(report, indent=2))
        return 0 if report.get("ready") else 2

    if args.schedule_weeks:
        from daily_review_agent.schedule_registry import schedule_for_weeks

        cfg = load_agent_config()
        reg = schedule_for_weeks(weeks=max(1, args.schedule_weeks), timezone=cfg.timezone, run_at=cfg.run_at)
        print(json.dumps({"ok": True, "schedule": reg}, indent=2))
        return 0

    if args.schedule_batch:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from daily_review_agent.batch_schedule import build_evening_slots, run_batch_schedule

        cfg = load_agent_config()
        tz = ZoneInfo(cfg.timezone)
        date_str = args.date.strip() or datetime.now(tz).date().isoformat()
        slots = build_evening_slots(
            date_str=date_str,
            start_hhmm=args.start_at,
            count=max(1, args.count),
            duration_minutes=max(5, args.duration),
            timezone=cfg.timezone,
        )
        emails = [cfg.organizer_upn] + [a.email for a in cfg.demo_attendees if a.email]
        emails = list(dict.fromkeys(e for e in emails if e))
        result = run_batch_schedule(
            slots=slots,
            attendee_emails=emails,
            subject_prefix="Daily Review Agent — Mohan sync",
        )
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") == "ok" else 1

    if args.demo_call:
        from daily_review_agent.demo_call import run_demo_call

        result = run_demo_call(
            dry_run=not args.live,
            minutes_from_now=max(5, args.minutes),
            force=args.force,
        )
        print(json.dumps(result, indent=2, default=str))
        status = result.get("status")
        return 0 if status == "ok" else 2 if status == "preflight_failed" else 1

    if args.status:
        print(json.dumps(readiness_report(load_agent_config()), indent=2))
        return 0

    dry_run = not args.live
    result = run_daily_agent(dry_run=dry_run, force=args.force)
    print(json.dumps(result, indent=2, default=str))
    status = result.get("status")
    if status == "disabled":
        return 2
    if status == "preflight_failed":
        return 2
    if status == "schedule_failed":
        return 1
    if result.get("fetch", {}).get("errors") and not result.get("fetch", {}).get("total"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
