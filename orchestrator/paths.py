"""Repository root and standard directory paths (single source of truth)."""

from __future__ import annotations

from pathlib import Path

# orchestrator/paths.py -> repo root is one level up
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "profiles"
ASSETS_DIR = REPO_ROOT / "assets"
TEMPLATES_DIR = ASSETS_DIR / "templates"
OPS_DIR = REPO_ROOT / "orchestrator" / "ops"

WORKSPACE_FILE = CONFIG_DIR / "workspace.yaml"
WORKSPACES_DIR = CONFIG_DIR / "workspaces"
