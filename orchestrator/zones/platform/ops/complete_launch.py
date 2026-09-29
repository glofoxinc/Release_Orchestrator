#!/usr/bin/env python3
"""Final launch completion â€” automated checks + optional SHIPIT dry-run sign-off.

Usage:
    python orchestrator/zones/platform/ops/complete_launch.py
    python orchestrator/zones/platform/ops/complete_launch.py --dry-run-version 2026.3.09.11 \\
        --sharepoint-url "https://abcfinancial.sharepoint.com/.../Release%20Notes.docx"
    python orchestrator/zones/platform/ops/complete_launch.py --confirm-slack "Posted to #insights-customize-squad"

Exit 0 when automated readiness passes; records operator sign-offs when flags succeed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


def _run_pytest(quick: bool) -> tuple[bool, str]:
    py = sys.executable
    cmd = [py, "-m", "pytest", "-q", "--tb=no"]
    if quick:
        cmd.extend([
            "orchestrator/zones/quality/tests/test_production_readiness.py",
            "orchestrator/zones/quality/tests/test_mcp_onboarding.py",
            "orchestrator/zones/quality/tests/test_shipit_preflight.py",
            "orchestrator/zones/quality/tests/test_schedule_time.py",
        ])
    else:
        cmd.append("orchestrator/zones/quality/tests/")
    proc = subprocess.run(cmd, cwd=_ROOT, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    line = out.strip().splitlines()[-1] if out.strip() else f"exit {proc.returncode}"
    return proc.returncode == 0, line


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete Release Orchestrator launch.")
    parser.add_argument("--quick", action="store_true", help="Run focused pytest subset.")
    parser.add_argument("--dry-run-version", default="", help="SHIPIT dry-run fix version.")
    parser.add_argument("--sharepoint-url", default="", help="SharePoint URL for dry-run.")
    parser.add_argument("--confirm-slack", default="", help="Record Slack live confirm with note.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    import config
    import operator_signoff as osign
    import production_readiness as pr
    import shipit_preflight as sp

    config.ensure_workspace_loaded()

    results: dict[str, object] = {}
    ok = True

    tests_ok, tests_line = _run_pytest(args.quick)
    results["pytest"] = {"ok": tests_ok, "detail": tests_line}
    ok = ok and tests_ok

    readiness = pr.assess_production_readiness(surface="both")
    results["production_readiness"] = {
        "production_ready": readiness.get("production_ready"),
        "automated_score_pct": readiness.get("automated_score_pct"),
    }
    ok = ok and bool(readiness.get("production_ready"))

    meta = sp.preflight_service_desk_metadata()
    results["shipit_metadata"] = meta
    ok = ok and meta.get("status") == "ok"

    if args.dry_run_version and args.sharepoint_url:
        dr = sp.preflight_shipit_create_dry_run(
            version_name=args.dry_run_version.strip(),
            sharepoint_url=args.sharepoint_url.strip(),
        )
        results["shipit_dry_run"] = dr
        if dr.get("status") == "dry_run":
            rec = osign.record_signoff(
                osign.SIGNOFF_SHIPIT_DRY_RUN,
                detail=f"version={args.dry_run_version.strip()}",
            )
            results["shipit_signoff_recorded"] = rec
        else:
            ok = False

    if args.confirm_slack.strip():
        rec = osign.record_signoff(
            osign.SIGNOFF_SLACK_LIVE,
            detail=args.confirm_slack.strip(),
        )
        results["slack_signoff_recorded"] = rec

    signoffs = osign.signoff_status()
    results["operator_signoffs"] = signoffs
    results["launch_complete"] = bool(signoffs.get("launch_complete")) and ok

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("=" * 60)
        print("Release Orchestrator â€” Launch Completion")
        print("=" * 60)
        print(f"Pytest: {'PASS' if tests_ok else 'FAIL'} â€” {tests_line}")
        print(f"Production ready (automated): {readiness.get('production_ready')}")
        print(f"SHIPIT metadata: {meta.get('status')} â€” {meta.get('detail', '')[:80]}")
        print(f"Operator sign-offs: {signoffs.get('signoffs')}")
        if signoffs.get("missing"):
            print(f"Still needed: {', '.join(signoffs['missing'])}")
        print(f"Launch complete: {results['launch_complete']}")

    return 0 if results["launch_complete"] else (1 if not ok else 2)


if __name__ == "__main__":
    raise SystemExit(main())
