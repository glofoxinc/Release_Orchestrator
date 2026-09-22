"""Slack MCP E2E dry-run — verification + preview + post handoff."""

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
    parser = argparse.ArgumentParser(description="Slack MCP E2E dry-run for Release Orchestrator Step 6")
    parser.add_argument("--verify-only", action="store_true", help="Print slack_mcp_verify only")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--ticket-key", default="SHIPIT-17191")
    parser.add_argument("--version", default="2026.2.04.14")
    parser.add_argument("--deploy-date", default="2026-04-14")
    args = parser.parse_args()

    import config

    config.ensure_workspace_loaded()
    from release_mcp import slack_mcp_ops

    if args.verify_only:
        payload = slack_mcp_ops.slack_mcp_verify()
    else:
        sharepoint = (
            "https://abcfinancial.sharepoint.com/:w:/r/teams/ABCFitnessSolutionsLLC-Glofox-Customize"
            "/_layouts/15/Doc.aspx?file=Release%20Notes%20{version}.docx"
        ).format(version=args.version)
        payload = slack_mcp_ops.slack_mcp_e2e_handoff(
            ticket_key=args.ticket_key,
            summary=f"Production Deployment – Insights Customize BI - Glofox - Report Updates (v{args.version})",
            ticket_url=f"https://abcfinancial.atlassian.net/browse/{args.ticket_key}",
            version_name=args.version,
            sharepoint_url=sharepoint,
            deploy_date=args.deploy_date,
        )

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    if args.verify_only:
        v = payload
        print("Slack MCP verification")
        print(f"  delivery_mode: {v.get('delivery_mode')}")
        print(f"  e2e_ready: {v.get('e2e_ready')}")
        for ch in v.get("channels") or []:
            flag = ch.get("mcp_accessible")
            mark = "OK" if flag is True else ("BLOCKED" if flag is False else "?")
            print(f"  #{ch.get('name')}: {ch.get('configured_channel_id')} [{mark}]")
        for user in v.get("cc_users") or []:
            mark = "OK" if user.get("mcp_match") else ("FAIL" if user.get("mcp_match") is False else "?")
            print(f"  CC {user.get('name')}: {user.get('configured_user_id')} [{mark}]")
        for item in v.get("blockers") or []:
            print(f"  BLOCKER: {item}")
        for item in v.get("warnings") or []:
            print(f"  warn: {item}")
        return 1 if v.get("blockers") else 0

    v = payload.get("verification") or {}
    print("Slack MCP E2E handoff")
    print(f"  e2e_ready: {payload.get('e2e_ready')}")
    print(f"  instruction: {payload.get('instruction')}")
    for post in (payload.get("slack_mcp") or {}).get("posts") or []:
        print(f"\n--- #{post.get('channel_name')} ({post.get('channel_id')}) ---")
        print(post.get("message") or "")
    for item in v.get("blockers") or []:
        print(f"\nBLOCKER: {item}")
    return 1 if v.get("blockers") else 0


if __name__ == "__main__":
    raise SystemExit(main())
