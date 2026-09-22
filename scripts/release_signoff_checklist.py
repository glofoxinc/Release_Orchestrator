#!/usr/bin/env python3
"""Release Orchestrator v3.0.1+ sign-off runner — tests, verify, SHIPIT, DOCX compare.

Usage:
    python scripts/release_signoff_checklist.py
    python scripts/release_signoff_checklist.py --quick
    python scripts/release_signoff_checklist.py --live-jira
    python scripts/release_signoff_checklist.py --dry-run-version 2026.3.09.09 \\
        --sharepoint-url "https://..."

Prints VERIFIED vs UNVERIFIED table for operator sign-off.
Exit: 0 all automated checks pass, 1 any fail.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


def _run(cmd: list[str], *, env: dict | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=_ROOT,
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Release Orchestrator automated sign-off.")
    parser.add_argument("--quick", action="store_true", help="Skip full pytest (parity subset only).")
    parser.add_argument("--live-jira", action="store_true", help="Run live Jira auth/search (read-only).")
    parser.add_argument("--dry-run-version", default="", help="Optional SHIPIT dry-run fix version.")
    parser.add_argument("--sharepoint-url", default="", help="SharePoint URL for SHIPIT dry-run.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    py = sys.executable
    results: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str, *, operator: bool = False) -> None:
        results.append({
            "name": name,
            "verified": ok and not operator,
            "operator_required": operator,
            "detail": detail,
        })

    _section("1. Pytest")
    if args.quick:
        code, out = _run([
            py, "-m", "pytest",
            "tests/test_shipit_preflight.py",
            "tests/test_release_notes_compare.py",
            "tests/test_release_critical_parity.py",
            "tests/test_integration_readiness.py",
            "-q", "--tb=no",
        ])
    else:
        code, out = _run([py, "-m", "pytest", "tests/", "-q", "--tb=no"])
    record("pytest", code == 0, out.splitlines()[-1] if out else f"exit {code}")

    _section("2. Release Notes E2E")
    code, out = _run([py, "scripts/test_release_notes_e2e.py"])
    record("release_notes_e2e", code == 0, "OK" if code == 0 else out[-500:])

    _section("3. Integration verify")
    checks = ["readiness", "service_desk", "release_notes", "team_scope"]
    env = os.environ.copy()
    if not args.live_jira:
        env["MOCK_MODE"] = "true"
    for check in checks:
        code, out = _run([py, "scripts/verify_integrations.py", f"--check={check}"], env=env)
        record(f"verify_{check}", code == 0, out.splitlines()[-1] if out else f"exit {code}")

    _section("4. DOCX compare (sample vs reference)")
    code, out = _run([py, "scripts/compare_release_notes_docx.py", "--generate-sample"])
    record("docx_compare_sample", code == 0, out.splitlines()[-3:] and "\n".join(out.splitlines()[-3:]) or out)

    _section("5. SHIPIT preflight")
    import shipit_preflight as sp

    meta = sp.preflight_service_desk_metadata()
    record("shipit_metadata", meta.get("status") == "ok", meta.get("detail", ""))
    assign = sp.preflight_assignment_group()
    record(
        "shipit_assignment_group",
        assign.get("status") in {"ok", "skip", "mock", "warn"},
        assign.get("detail", ""),
    )
    if args.dry_run_version and args.sharepoint_url:
        dr = sp.preflight_shipit_create_dry_run(
            version_name=args.dry_run_version.strip(),
            sharepoint_url=args.sharepoint_url.strip(),
        )
        record(
            "shipit_dry_run_create",
            dr.get("status") == "dry_run",
            dr.get("summary") or str(dr.get("status")),
        )

    _section("6. Operator-only (cannot automate)")
    operator_items = [
        ("Cancel test SHIPIT-16710 in Jira portal", "Manual portal action"),
        ("Real SHIPIT create on sandbox/small release", "Requires explicit operator confirm"),
        ("Visual DOCX compare vs org SharePoint template", "Org Release Notes 2026.3.09.09.docx not in repo"),
        ("Deployer live comment + Done + undo", "Requires production/staging release window"),
    ]
    for name, detail in operator_items:
        record(name, False, detail, operator=True)

    verified = [r for r in results if r["verified"]]
    unverified = [r for r in results if not r["verified"] and not r["operator_required"]]
    operator = [r for r in results if r["operator_required"]]

    summary = {
        "verified_count": len(verified),
        "unverified_automated_count": len(unverified),
        "operator_pending_count": len(operator),
        "automated_pass": len(unverified) == 0,
        "results": results,
    }

    _section("SIGN-OFF SUMMARY")
    print(f"VERIFIED (automated): {len(verified)}")
    for r in verified:
        print(f"  [x] {r['name']} — {r['detail'][:100]}")
    if unverified:
        print(f"\nUNVERIFIED (automated failures): {len(unverified)}")
        for r in unverified:
            print(f"  [ ] {r['name']} — {r['detail'][:120]}")
    print(f"\nOPERATOR REQUIRED: {len(operator)}")
    for r in operator:
        print(f"  [ ] {r['name']} — {r['detail']}")

    if args.json:
        print(json.dumps(summary, indent=2))

    print(
        "\nDrawbacks to watch: assignment group optional; Testing Evidence = ticket keys only; "
        "Customize BI field map; Teams/Graph upload archived; live SHIPIT + Slack need operator sign-off."
    )
    return 0 if summary["automated_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
