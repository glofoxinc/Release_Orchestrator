"""Dry-run / live test for release gates and assignee Slack DMs.

Usage
-----
    python scripts/test_release_gates.py --status
    python scripts/test_release_gates.py --gate pre_review --dry-run
    python scripts/test_release_gates.py --gate post_qa --version 2026.3.08.21 --dry-run
    python scripts/test_release_gates.py --gate pre_review --live --notify

Requires JIRA_* credentials for live version fetch. Slack notify uses SLACK_BOT_TOKEN.
"""

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
    parser = argparse.ArgumentParser(description="Test release gates (pre-review / post-QA).")
    parser.add_argument(
        "--gate",
        choices=("pre_review", "post_qa", "both"),
        default="both",
        help="Which gate to exercise",
    )
    parser.add_argument("--version", default="", help="Fix version name (required for live fetch).")
    parser.add_argument("--status", action="store_true", help="Print gate config only.")
    parser.add_argument("--dry-run", action="store_true", help="Classify + Slack preview (default).")
    parser.add_argument("--live", action="store_true", help="Live Slack DMs (requires SLACK_BOT_TOKEN).")
    parser.add_argument("--notify", action="store_true", help="Include Slack assignee notify step.")
    args = parser.parse_args()

    import config
    from release_mcp import gate_ops

    config.reload_workspace()
    status = gate_ops.release_gate_status()
    print("=== Release gates E2E ===")
    print(json.dumps(status, indent=2))

    if args.status:
        return 0

    version = (args.version or "").strip()
    if not version:
        print("\nERROR: pass --version (fix version name) for gate classification.", file=sys.stderr)
        return 2

    dry_run = not args.live
    notify = args.notify or args.live

    gates = ["pre_review", "post_qa"] if args.gate == "both" else [args.gate]
    exit_code = 0
    for gate in gates:
        print(f"\n--- {gate} ---")
        if gate == "pre_review":
            out = gate_ops.pre_review_gate(version, notify=notify, dry_run=dry_run)
        else:
            out = gate_ops.post_qa_gate(version, notify=notify, dry_run=dry_run)
        print(json.dumps(out, indent=2))
        if out.get("status") == "error":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
