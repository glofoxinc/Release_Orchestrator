"""Central path helpers — daily review lives inside jira-release-tool (Release Orchestrator)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DAILY_REVIEW_DIR = REPO_ROOT / "daily_review_agent"
SCRIPTS_DIR = REPO_ROOT / "release_mcp" / "scripts" / "daily_review"
STATE_DIR = DAILY_REVIEW_DIR / ".state"
PLAYWRIGHT_PROFILE_DIR = STATE_DIR / "playwright-outlook-profile"


def script(name: str) -> Path:
    return SCRIPTS_DIR / name
