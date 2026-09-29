"""Wire Daily Review Agent to Release Orchestrator shared libraries (.env, Jira client)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from daily_review_agent.paths import ENV_FILE, REPO_ROOT


def orchestrator_root() -> Path:
    raw = (os.environ.get("RELEASE_ORCHESTRATOR_ROOT") or "").strip()
    if raw:
        return Path(raw).resolve()
    return REPO_ROOT


def bootstrap(*, load_env: bool = True) -> Path:
    """Add Release Orchestrator repo to sys.path and load credentials once."""
    orch = orchestrator_root()
    if not orch.is_dir():
        raise FileNotFoundError(
            f"Release Orchestrator not found at {orch}. "
            "Set RELEASE_ORCHESTRATOR_ROOT to jira-release-tool repo root."
        )
    orch_str = str(orch)
    if orch_str not in sys.path:
        sys.path.insert(0, orch_str)
    if load_env:
        try:
            from dotenv import load_dotenv

            env_path = ENV_FILE if ENV_FILE.is_file() else orch / ".env"
            load_dotenv(env_path, override=True)
        except ImportError:
            pass
        import config

        config.ensure_workspace_loaded()
    return orch
