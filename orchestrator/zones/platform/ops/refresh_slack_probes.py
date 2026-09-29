#!/usr/bin/env python3
"""Persist live Slack MCP channel probe results for slack_mcp_verify.

After slack_read_channel succeeds in Cursor, record results:

  python orchestrator/zones/platform/ops/refresh_slack_probes.py \\
    --channel insights-customize-squad --id C08HB93PEVD --accessible true

Or paste JSON array:

  python orchestrator/zones/platform/ops/refresh_slack_probes.py --json-file probes.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_PROBE_FILE = os.path.join(_ROOT, ".launch", "slack_channel_probes.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh cached Slack MCP channel probes.")
    parser.add_argument("--channel", help="Channel name without #")
    parser.add_argument("--id", dest="channel_id", help="Slack channel ID")
    parser.add_argument("--accessible", choices=("true", "false"), help="Probe result")
    parser.add_argument("--error", default="", help="Error message if inaccessible")
    parser.add_argument("--json-file", help="JSON file with channel_checks list")
    parser.add_argument("--verify", action="store_true", help="Run slack_mcp_verify after save")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(_PROBE_FILE), exist_ok=True)
    checks: list[dict] = []
    if args.json_file:
        raw = json.loads(open(args.json_file, encoding="utf-8").read())
        checks = raw if isinstance(raw, list) else raw.get("channel_checks") or []
    elif args.channel and args.channel_id and args.accessible:
        checks = [{
            "name": args.channel,
            "channel_id": args.channel_id,
            "accessible": args.accessible == "true",
            "error": args.error,
        }]
    else:
        parser.error("Provide --json-file or --channel + --id + --accessible")

    with open(_PROBE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"channel_checks": checks, "user_checks": []}, handle, indent=2)
    print(f"Wrote {len(checks)} probe(s) to {_PROBE_FILE}")

    if args.verify:
        from release_mcp import slack_mcp_ops

        payload = slack_mcp_ops.slack_mcp_verify(
            channel_checks=checks,
            user_checks=None,
        )
        print(f"e2e_ready: {payload.get('e2e_ready')}")
        for b in payload.get("blockers") or []:
            print(f"BLOCKER: {b}")
        return 0 if payload.get("e2e_ready") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
