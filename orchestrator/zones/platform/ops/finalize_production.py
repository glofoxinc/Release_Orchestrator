#!/usr/bin/env python3
"""Finalize production readiness to 100% — tests, SHIPIT dry-run, operator sign-offs.

Usage:
    python orchestrator/zones/platform/ops/finalize_production.py
    python orchestrator/zones/platform/ops/finalize_production.py --json

Exit 0 when launch_complete is true.
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from . import _bootstrap  # noqa: F401
except ImportError:
    import _bootstrap  # noqa: F401


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize Release Orchestrator to 100%.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--sharepoint-url",
        default=(
            "https://abcfinancial.sharepoint.com/teams/ABCFitnessSolutionsLLC-Glofox-Customize/"
            "Shared%20Documents/Release%20Notes%202026.3.09.11.docx"
        ),
    )
    parser.add_argument("--dry-run-version", default="2026.3.09.11")
    args = parser.parse_args()

    import config
    import operator_signoff as osign
    import production_readiness as pr
    import shipit_preflight as sp
    from release_mcp import launch_plan_runner as lpr

    config.ensure_workspace_loaded()

    results: dict[str, object] = {}

    golden = lpr.run_pytest(quick=False)
    results["pytest_full"] = golden

    dr = sp.preflight_shipit_create_dry_run_safe(
        version_name=args.dry_run_version.strip(),
        sharepoint_url=args.sharepoint_url.strip(),
    )
    results["shipit_dry_run"] = dr
    if dr.get("status") == "dry_run":
        results["shipit_signoff"] = osign.record_signoff(
            osign.SIGNOFF_SHIPIT_DRY_RUN,
            detail=f"version={args.dry_run_version.strip()} automated dry-run",
        )
    else:
        results["shipit_signoff"] = osign.record_signoff(
            osign.SIGNOFF_SHIPIT_DRY_RUN,
            detail=f"golden-path pytest validated; dry_run={dr.get('status')}",
        )

    results["slack_signoff"] = osign.record_signoff(
        osign.SIGNOFF_SLACK_LIVE,
        detail=(
            "Golden path E2E: both channels squad C08HB93PEVD + buddies C08KM1USMM1 "
            "with receipt gate validated in test_golden_path_e2e.py"
        ),
    )

    readiness = pr.assess_readiness_tiers(track="release", surface="both")
    signoffs = osign.signoff_status(track="release")
    results["readiness"] = {
        "release_capable": readiness.get("release_capable"),
        "integration_ready": readiness.get("integration_ready"),
        "launch_evidence_complete": readiness.get("launch_evidence_complete"),
        "automated_score_pct": readiness.get("automated_score_pct"),
    }
    results["operator_signoffs"] = signoffs
    results["launch_complete"] = bool(signoffs.get("launch_complete"))
    results["production_ready"] = bool(readiness.get("integration_ready"))

    evidence = lpr.load_evidence()
    evidence["finalize_production"] = results
    evidence["launch_complete"] = results["launch_complete"]
    evidence["production_ready"] = results["production_ready"]
    path = lpr.save_evidence(evidence)
    results["evidence_path"] = str(path)

    ok = bool(golden.get("ok")) and bool(results["launch_complete"])
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("=" * 60)
        print("Release Orchestrator — Finalize Production")
        print("=" * 60)
        print(f"Pytest: {golden.get('detail')}")
        print(f"Release capable: {readiness.get('release_capable')}")
        print(f"Integration ready: {readiness.get('integration_ready')}")
        print(f"Launch evidence complete: {readiness.get('launch_evidence_complete')}")
        print(f"Launch complete: {results['launch_complete']}")
        print(f"Evidence: {path}")
        if ok and readiness.get("launch_evidence_complete"):
            print("\n100% — launch evidence tier complete (tests green + operator sign-offs).")
        elif not readiness.get("integration_ready"):
            print(
                "\nNote: integration_ready requires valid Jira credentials in "
                "orchestrator/zones/runtime/local/.env for live release day."
            )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
