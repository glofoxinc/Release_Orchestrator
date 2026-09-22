"""Dry-run or live Slack post for Daily Review Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    from daily_review_agent.config_loader import load_agent_config, readiness_report
    from daily_review_agent.report import format_text_report
    from daily_review_agent.schedule import meeting_window
    from daily_review_agent.slack_notify import run_slack_delivery, slack_readiness

    cfg = load_agent_config()
    if args.status:
        print(json.dumps({"readiness": readiness_report(cfg), "slack": slack_readiness(cfg.slack)}, indent=2))
        return 0

    dry_run = not args.live
    start, end = meeting_window(cfg)
    sample = format_text_report(
        [{"key": "PIC-1", "status": "Review", "assignee": "Dev", "summary": "Sample ticket", "link": ""}],
        team_name=cfg.jira_team_name,
        by_project={"PIC": {"statuses": ["Review"], "count": 1}},
    )
    result = run_slack_delivery(
        cfg.slack,
        text_report=sample,
        meeting_start=start,
        meeting_end=end,
        teams_join_url="https://teams.microsoft.com/l/meetup-join/example",
        dry_run=dry_run,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
