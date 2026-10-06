#!/usr/bin/env python3
"""CLI: onboarding preflight — run before welcome onboard.

Usage:
  python orchestrator/zones/platform/ops/onboarding_preflight.py
  python orchestrator/zones/platform/ops/onboarding_preflight.py --fix --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from release_mcp import onboarding_preflight as opf


def main() -> int:
    parser = argparse.ArgumentParser(description="Release Orchestrator onboarding preflight")
    parser.add_argument("--track", default="release", choices=["release", "daily_review", "both"])
    parser.add_argument("--fix", action="store_true", help="Merge MCP blocks into project .cursor/mcp.json")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.fix:
        payload = opf.apply_safe_fixes(track=args.track)
    else:
        report = opf.run_preflight(track=args.track)
        payload = report

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        if args.fix:
            pf = payload.get("preflight") or {}
            print(opf.format_preflight_markdown(pf))
            merge = payload.get("merge") or {}
            if merge.get("message"):
                print()
                print(merge["message"])
        else:
            print(opf.format_preflight_markdown(payload))

    status = (payload.get("preflight") or payload).get("status") if args.fix else payload.get("status")
    if status == "ready":
        return 0
    if status == "needs_fix":
        return 2
    if status == "blocked":
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
