"""Schedule a 2-person demo Teams call (Lakshmi + Mohan Krishna Sai).

Usage:
  python scripts/demo_daily_review_teams_call.py --dry-run
  python scripts/demo_daily_review_teams_call.py --live
  python scripts/demo_daily_review_teams_call.py --status

Set MOHAN_DEMO_EMAIL in .env if not filled in daily_review_agent/agent.yaml.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo Teams call for Daily Review Agent")
    parser.add_argument("--dry-run", action="store_true", help="Preview Graph payload only")
    parser.add_argument("--live", action="store_true", help="Create real demo meeting")
    parser.add_argument("--status", action="store_true", help="Readiness check")
    parser.add_argument(
        "--minutes-from-now",
        type=int,
        default=30,
        help="Schedule demo this many minutes from now (default 30)",
    )
    args = parser.parse_args()

    import config

    config.reload_workspace()

    from daily_review_agent.config_loader import load_agent_config, readiness_report
    from daily_review_agent.demo_call import run_demo_call

    if args.status:
        print(json.dumps(readiness_report(load_agent_config()), indent=2))
        return 0

    dry_run = not args.live
    result = run_demo_call(dry_run=dry_run, minutes_from_now=args.minutes_from_now)
    print(json.dumps(result, indent=2, default=str))

    if result.get("status") == "needs_input":
        return 2
    sched = (result.get("meeting") or {}).get("schedule") or {}
    if not dry_run and not sched.get("ok"):
        return 1
    if dry_run and sched.get("ok"):
        print("\nDry-run OK — re-run with --live after MS Graph credentials are set.")
    if not dry_run and sched.get("join_url"):
        print(f"\nJoin URL: {sched['join_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
