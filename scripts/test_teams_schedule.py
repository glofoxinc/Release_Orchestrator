"""End-to-end Teams scheduling test (dry-run or live Graph).

Usage
-----
    python scripts/test_teams_schedule.py --dry-run
    python scripts/test_teams_schedule.py --kind review --dry-run
    python scripts/test_teams_schedule.py --kind deployment --live
    python scripts/test_teams_schedule.py --status

Exit codes: 0 success, 1 failure, 2 bad args.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Teams meeting scheduling via Microsoft Graph.")
    parser.add_argument(
        "--kind",
        choices=("review", "deployment"),
        default="review",
        help="Meeting kind (default: review)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview Graph payload without calling Graph (default when --live omitted).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Create a real Teams meeting (requires MS_GRAPH_* + organizer_upn).",
    )
    parser.add_argument("--status", action="store_true", help="Print readiness only and exit.")
    parser.add_argument("--version", default="2026.3.08.21", help="Release label for subject/body.")
    parser.add_argument(
        "--start",
        default="",
        help="ISO start datetime (default: now + 1 hour).",
    )
    args = parser.parse_args()

    import config
    import teams_schedule

    config.reload_workspace()
    cfg = teams_schedule.load_schedule_config(config.TEAMS_SCHEDULE)
    st = teams_schedule.status(cfg)

    print("=== Teams schedule E2E ===")
    print(json.dumps({k: v for k, v in st.items() if k != "graph"}, indent=2))
    print("Graph:", json.dumps(st.get("graph") or {}, indent=2))

    if args.status:
        return 0 if st.get("can_schedule") else 1

    dry_run = not args.live
    if args.live and not cfg.can_schedule():
        print("\nERROR: Live schedule not ready. Fix readiness steps above.", file=sys.stderr)
        return 1

    if args.start.strip():
        start_dt = datetime.fromisoformat(args.start.strip())
    else:
        start_dt = datetime.now().replace(second=0, microsecond=0) + timedelta(hours=1)

    draft = teams_schedule.build_meeting_draft(
        cfg,
        kind=args.kind,  # type: ignore[arg-type]
        subject="",
        start=start_dt,
        version=args.version,
    )
    result = teams_schedule.schedule_meeting(cfg, draft, dry_run=dry_run)
    out = result.to_dict()

    print(f"\n--- {'DRY-RUN' if dry_run else 'LIVE'} result ---")
    print(json.dumps({k: v for k, v in out.items() if k != "graph_payload"}, indent=2))
    if out.get("graph_payload"):
        print("\nGraph payload:")
        print(json.dumps(out["graph_payload"], indent=2))

    if not result.ok:
        print(f"\nFAILED: {result.error}", file=sys.stderr)
        return 1
    if not dry_run and result.join_url:
        print(f"\nJoin URL: {result.join_url}")
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
