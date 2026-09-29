"""Capture sanitized production baseline evidence for Release Orchestrator hardening."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.paths import OPS_DIR, REPO_ROOT

_LAUNCH = REPO_ROOT / ".launch"
_BASELINE = _LAUNCH / "baseline_evidence.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run(cmd: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    tail = out.splitlines()[-1] if out else f"exit {proc.returncode}"
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "detail": tail}


def capture_baseline(*, quick: bool = False) -> dict[str, Any]:
    """Run offline checks and write sanitized evidence (no secrets)."""
    import production_readiness as pr
    from release_mcp import unified_onboarding as uo

    py = sys.executable
    checks: dict[str, Any] = {
        "pytest_full": _run([py, "-m", "pytest", "orchestrator/zones/quality/tests/", "-q", "--tb=no"]),
    }
    if not quick:
        checks["ruff"] = _run([py, "-m", "ruff", "check", "."])
        checks["release_notes_e2e"] = _run([py, str(OPS_DIR / "test_release_notes_e2e.py")])

    track = uo.get_stored_track() or uo.TRACK_RELEASE
    readiness = pr.assess_readiness_tiers(track=track, surface="mcp")

    payload: dict[str, Any] = {
        "version": "1.0",
        "captured_at": _utc_now(),
        "repo_root": str(REPO_ROOT),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "track": track,
        "checks": checks,
        "readiness": {
            "release_capable": readiness.get("release_capable"),
            "integration_ready": readiness.get("integration_ready"),
            "launch_evidence_complete": readiness.get("launch_evidence_complete"),
            "automated_score_pct": readiness.get("automated_score_pct"),
            "unverified_count": len(readiness.get("unverified") or []),
            "operator_required_count": len(readiness.get("operator_required") or []),
        },
        "note": "Sanitized — no tokens, browser state, or message contents.",
    }
    _LAUNCH.mkdir(parents=True, exist_ok=True)
    _BASELINE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["baseline_path"] = str(_BASELINE)
    return payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Capture RO baseline evidence")
    parser.add_argument("--quick", action="store_true", help="Skip ruff and RN E2E")
    args = parser.parse_args()
    result = capture_baseline(quick=args.quick)
    print(json.dumps(result, indent=2))
    checks = result.get("checks") or {}
    ok = all(bool(row.get("ok")) for row in checks.values())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
