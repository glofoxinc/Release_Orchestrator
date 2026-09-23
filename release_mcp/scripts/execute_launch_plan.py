#!/usr/bin/env python3
"""Execute Release Orchestrator launch plan phases and write .launch/launch_evidence.json."""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS in sys.path:
    sys.path.remove(_SCRIPTS)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
elif sys.path[0] != _ROOT:
    sys.path.remove(_ROOT)
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


PHASES = {
    "0": "phase0_preflight",
    "1": "phase1_slack_e2e",
    "2": "phase2_onboarding_validation",
    "3": "phase3_release_dry_run",
    "4": "phase4_daily_review_pilot",
    "5": "phase5_production_readiness",
    "6": "phase6_pr_rollout",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run launch plan phases.")
    parser.add_argument("--phase", choices=list(PHASES.keys()), help="Run single phase (0-6).")
    parser.add_argument("--all", action="store_true", help="Run all phases.")
    parser.add_argument("--full-tests", action="store_true", help="Full pytest in phase 0.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from release_mcp import launch_plan_runner as lpr

    if args.all or not args.phase:
        summary = lpr.run_all_phases(quick_tests=not args.full_tests)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print("Launch plan summary")
            for pid, row in (summary.get("phases") or {}).items():
                mark = "PASS" if row.get("exit_gate") else "PENDING"
                print(f"  [{mark}] {pid}")
            print(f"Evidence: {summary.get('evidence_path')}")
        return 0 if summary.get("all_exit_gates_met") else 1

    runners = {
        "0": lambda: lpr.phase0_preflight(quick_tests=not args.full_tests),
        "1": lpr.phase1_slack_e2e,
        "2": lpr.phase2_onboarding_validation,
        "3": lpr.phase3_release_dry_run,
        "4": lpr.phase4_daily_review_pilot,
        "5": lpr.phase5_production_readiness,
        "6": lpr.phase6_pr_rollout,
    }
    result = runners[args.phase]()
    evidence = lpr.load_evidence()
    lpr._record_phase(evidence, str(result.get("phase")), result)
    lpr.save_evidence(evidence)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        mark = "PASS" if result.get("exit_gate") else "PENDING"
        print(f"[{mark}] {result.get('phase')}")
        for note in result.get("operator_notes") or []:
            print(f"  -> {note}")
        for blocker in result.get("blockers") or []:
            print(f"  BLOCKER: {blocker}")
    return 0 if result.get("exit_gate") else 1


if __name__ == "__main__":
    raise SystemExit(main())
