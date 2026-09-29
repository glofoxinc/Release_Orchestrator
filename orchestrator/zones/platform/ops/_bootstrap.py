"""Ensure repo root is on sys.path and load runtime .env for ops scripts."""

from __future__ import annotations

import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError(f"Could not find repo root from {start}")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    from orchestrator.paths import ENV_FILE

    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=True)
    else:
        load_dotenv(override=True)
except ImportError:
    pass
