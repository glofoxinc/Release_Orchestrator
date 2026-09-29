"""Central path helpers — review agent inside Release Orchestrator."""

from __future__ import annotations

from pathlib import Path

from orchestrator.paths import (
    AGENTS_DIR,
    ASSETS_DIR,
    ENV_FILE,
    OPS_DIR,
    ORCH_ROOT,
    REPO_ROOT,
    STATE_DIR as RUNTIME_STATE_DIR,
)

DAILY_REVIEW_DIR = AGENTS_DIR / "review"
SCRIPTS_DIR = OPS_DIR / "daily_review"
ARCHIVE_DIR = ASSETS_DIR / "archive"
STATE_DIR = RUNTIME_STATE_DIR / "daily_review"
PLAYWRIGHT_PROFILE_DIR = STATE_DIR / "playwright-outlook-profile"


def script(name: str) -> Path:
    return SCRIPTS_DIR / name


def orchestrator_root() -> Path:
    """Repo root (bootstrap compat). Prefer orchestrator.paths helpers for new code."""
    return REPO_ROOT
