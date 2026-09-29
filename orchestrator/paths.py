"""Repository root and standard directory paths (single source of truth)."""

from __future__ import annotations

import sys
from pathlib import Path

# orchestrator/paths.py
ORCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = ORCH_ROOT.parent
ZONES_ROOT = ORCH_ROOT / "zones"

# --- zones/config ---
CONFIG_DIR = ZONES_ROOT / "config" / "profiles"
ASSETS_DIR = ZONES_ROOT / "config" / "assets"
TEMPLATES_DIR = ASSETS_DIR / "templates"
ALIASES_DIR = ZONES_ROOT / "config" / "aliases"
DEPS_DIR = ZONES_ROOT / "config" / "deps"

WORKSPACE_FILE = CONFIG_DIR / "workspace.yaml"
WORKSPACES_DIR = CONFIG_DIR / "workspaces"

# --- zones/product ---
PRODUCT_ROOT = ZONES_ROOT / "product"
ENGINE_DIR = PRODUCT_ROOT / "engine"
MCP_DIR = PRODUCT_ROOT / "mcp"
UI_DIR = PRODUCT_ROOT / "ui"
AGENTS_DIR = PRODUCT_ROOT / "agents"
GENERATORS_DIR = PRODUCT_ROOT / "generators"
LIB_DIR = PRODUCT_ROOT / "lib"

# --- zones/platform ---
OPS_DIR = ZONES_ROOT / "platform" / "ops"
AUTOMATION_DIR = ZONES_ROOT / "platform" / "automation"
CI_DIR = ZONES_ROOT / "platform" / "ci"

# --- zones/knowledge / quality ---
KNOWLEDGE_DIR = ZONES_ROOT / "knowledge"
GUIDES_DIR = KNOWLEDGE_DIR / "guides"
TESTS_DIR = ZONES_ROOT / "quality" / "tests"
ENTRY_DIR = ORCH_ROOT / "entry"

# --- zones/runtime (gitignored) ---
RUNTIME_ROOT = ZONES_ROOT / "runtime"
CACHE_DIR = RUNTIME_ROOT / "cache"
STATE_DIR = RUNTIME_ROOT / "state"
LOCAL_DIR = RUNTIME_ROOT / "local"
ENV_FILE = LOCAL_DIR / ".env"
ENV_EXAMPLE_FILE = LOCAL_DIR / ".env.example"
STATE_WORKSPACES_DIR = STATE_DIR / "workspaces"
WIZARD_SESSIONS_DIR = STATE_DIR / "mcp_wizard_sessions"
ONBOARDING_STATE_FILE = STATE_DIR / "mcp_onboarding_state.json"
DEPLOY_DRAFT_FILE = STATE_DIR / "deploy_draft.json"
DEPLOY_DRAFT_SIDECAR_FILE = STATE_DIR / "deploy_draft.rn_docx.bin"
OPERATOR_SIGNOFF_FILE = STATE_DIR / "operator_signoff.json"
DEPLOYMENT_HISTORY_FILE = STATE_DIR / "deployment_history.json"
LAUNCH_DIR = RUNTIME_ROOT / "launch"
STREAMLIT_CONFIG_DIR = RUNTIME_ROOT / "streamlit"

PROJECT_MCP_CONFIG = ORCH_ROOT / ".cursor" / "mcp.json"
DAILY_REVIEW_OPS_DIR = OPS_DIR / "daily_review"

# Back-compat names used in older code
WORKSPACE_ROOT = ZONES_ROOT


def is_windows() -> bool:
    return sys.platform.startswith("win")


def venv_python(*, repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    if is_windows():
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def venv_pip_argv(*, repo_root: Path | None = None) -> list[str]:
    py = venv_python(repo_root=repo_root)
    return [str(py), "-m", "pip"]


def json_path(path: Path | str) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


LEGACY_SESSION_DIRS = (
    REPO_ROOT / ".mcp_wizard_sessions",
    ORCH_ROOT / ".mcp_wizard_sessions",
    REPO_ROOT / "workspace" / ".state" / "mcp_wizard_sessions",
    REPO_ROOT / ".state" / "mcp_wizard_sessions",
)
LEGACY_STATE_DIRS = (
    (REPO_ROOT / ".state", STATE_DIR),
    (REPO_ROOT / "workspace" / ".state", STATE_DIR),
)
LEGACY_CONFIG_DIRS = (
    (REPO_ROOT / "profiles", CONFIG_DIR),
    (REPO_ROOT / "assets", ASSETS_DIR),
    (ORCH_ROOT / "config" / "profiles", CONFIG_DIR),
)
LEGACY_STATE_FILES = (
    (REPO_ROOT / ".mcp_onboarding_state.json", ONBOARDING_STATE_FILE),
    (REPO_ROOT / ".deploy_draft.json", DEPLOY_DRAFT_FILE),
    (REPO_ROOT / ".operator_signoff.json", OPERATOR_SIGNOFF_FILE),
    (REPO_ROOT / ".deployment_history.json", DEPLOYMENT_HISTORY_FILE),
    (ORCH_ROOT / "zones" / "product" / "engine" / ".deploy_draft.json", DEPLOY_DRAFT_FILE),
)


def state_workspace_dir(workspace_name: str) -> Path:
    return STATE_WORKSPACES_DIR / workspace_name


def wizard_sessions_dir(*, workspace_name: str | None = None) -> Path:
    if workspace_name:
        return state_workspace_dir(workspace_name) / "mcp_wizard_sessions"
    return WIZARD_SESSIONS_DIR


def deploy_draft_path(*, workspace_name: str | None = None) -> Path:
    if workspace_name:
        return state_workspace_dir(workspace_name) / "deploy_draft.json"
    return DEPLOY_DRAFT_FILE


def deploy_draft_sidecar_path(*, workspace_name: str | None = None) -> Path:
    if workspace_name:
        return state_workspace_dir(workspace_name) / "deploy_draft.rn_docx.bin"
    return DEPLOY_DRAFT_SIDECAR_FILE


def operator_signoff_path(*, workspace_name: str | None = None) -> Path:
    if workspace_name:
        return state_workspace_dir(workspace_name) / "operator_signoff.json"
    return OPERATOR_SIGNOFF_FILE


def deployment_history_path(*, workspace_name: str | None = None) -> Path:
    if workspace_name:
        return state_workspace_dir(workspace_name) / "deployment_history.json"
    return DEPLOYMENT_HISTORY_FILE
