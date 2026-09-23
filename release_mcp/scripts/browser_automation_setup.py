#!/usr/bin/env python3
"""Print browser automation setup checklist for Release Orchestrator MCP.

Usage:
    python scripts/browser_automation_setup.py
    python scripts/browser_automation_setup.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

import config  # noqa: E402
from release_mcp import browser_ops  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Browser automation setup status")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    config.ensure_workspace_loaded()
    report = browser_ops.browser_automation_status()

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report.get("ready") else 1

    print("Release Orchestrator  Browser automation setup")
    print("=" * 50)
    print(f"Workspace: {config.active_workspace_name() or 'root'}")
    print(f"Ready: {'YES' if report.get('ready') else 'NO'}")
    print(f"Playwright MCP server id: {report.get('playwright_mcp')}")
    print(f"Slack delivery mode: {report.get('slack_delivery_mode')}")
    print(f"Recommended Slack path: {report.get('recommended_slack_path')}")
    print()
    print("Setup steps:")
    for idx, line in enumerate(report.get("setup") or [], start=1):
        print(f"  {idx}. {line}")
    issues = report.get("config_issues") or []
    if issues:
        print()
        print("Config notes:")
        for item in issues:
            print(f"  [{item.get('level', '').upper()}] {item.get('message')}")
    sp = report.get("sharepoint") or {}
    if sp.get("folder_browse_url"):
        print()
        print("SharePoint folder URL:")
        print(f"  {sp['folder_browse_url']}")
    print()
    print("Wizard phrases:")
    print("  SharePoint: upload sharepoint -> sharepoint done <url>")
    print("  Slack:      send slack -> slack done  (or send slack playwright)")
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
