"""Capture sanitized launch-week evidence for production readiness sign-off."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.paths import LAUNCH_DIR, REPO_ROOT


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_pytest_summary() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "orchestrator/zones/quality/tests/", "-q", "--tb=no"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "summary_line": tail[-1] if tail else "",
    }


def capture_launch_evidence(*, include_pytest: bool = True) -> dict[str, Any]:
    """Write launch evidence JSON under orchestrator/zones/runtime/launch/."""
    import production_readiness as pr
    from release_mcp import unified_onboarding as uo

    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    track = uo.get_stored_track() or uo.TRACK_RELEASE
    payload: dict[str, Any] = {
        "captured_at": _utc_now(),
        "repo": str(REPO_ROOT),
        "readiness": pr.assess_readiness_tiers(track=track, surface="mcp"),
        "onboarding": uo.assess_unified_setup(),
    }
    if include_pytest:
        payload["pytest"] = _run_pytest_summary()

    out = LAUNCH_DIR / "launch_evidence.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["written_to"] = str(out)
    return payload


def main() -> int:
    result = capture_launch_evidence()
    print(json.dumps({k: v for k, v in result.items() if k != "readiness"}, indent=2))
    print(f"\nWrote: {result['written_to']}")
    return 0 if result.get("pytest", {}).get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
