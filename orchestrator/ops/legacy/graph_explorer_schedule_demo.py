"""Schedule demo after pasting Graph Explorer access token (works with corp SSO).

Steps for you (one time):
  1. Graph Explorer → Sign in with work account (SSO/MFA OK)
  2. Modify permissions → Calendars.ReadWrite → Consent
  3. Copy Access Token from sidebar
  4. Run:  python scripts/graph_explorer_schedule_demo.py --token "eyJ..."
     Or set MS_GRAPH_ACCESS_TOKEN in .env and run without --token
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[2]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default="", help="Graph Explorer access token")
    parser.add_argument("--minutes-from-now", type=int, default=20)
    args = parser.parse_args()

    token = (args.token or os.environ.get("MS_GRAPH_ACCESS_TOKEN") or "").strip()
    if not token:
        print(
            "No token. Open Graph Explorer, sign in with SSO, consent Calendars.ReadWrite,\n"
            "copy Access Token, then:\n"
            '  python scripts/graph_explorer_schedule_demo.py --token "PASTE_HERE"\n'
        )
        return 2

    os.environ["MS_GRAPH_ACCESS_TOKEN"] = token

    from daily_review_agent.demo_call import run_demo_call

    result = run_demo_call(dry_run=False, minutes_from_now=args.minutes_from_now)
    print(json.dumps(result, indent=2, default=str))
    sched = (result.get("meeting") or {}).get("schedule") or {}
    if sched.get("join_url"):
        print(f"\nTeams join link:\n{sched['join_url']}")
        out = _APP_ROOT / "orchestrator" / "agents" / "review" / ".state" / "demo_meeting_result.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"join_url": sched["join_url"], "schedule": sched}, indent=2), encoding="utf-8")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
