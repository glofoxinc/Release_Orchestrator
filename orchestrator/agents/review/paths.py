"""Central path helpers — review agent inside Release Orchestrator."""

from __future__ import annotations

from pathlib import Path

from orchestrator.paths import OPS_DIR, REPO_ROOT

DAILY_REVIEW_DIR = REPO_ROOT / "orchestrator" / "agents" / "review"
SCRIPTS_DIR = OPS_DIR / "daily_review"
STATE_DIR = DAILY_REVIEW_DIR / ".state"
PLAYWRIGHT_PROFILE_DIR = STATE_DIR / "playwright-outlook-profile"


def script(name: str) -> Path:
    return SCRIPTS_DIR / name
