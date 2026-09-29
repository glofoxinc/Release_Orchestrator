"""Generic Cursor MCP server blocks — no personal paths (filled at install time)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from orchestrator.paths import REPO_ROOT as _PROJECT_ROOT


def _json_path(path: Path | str) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def detect_python() -> str:
    venv = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv.is_file():
        return _json_path(venv)
    import sys

    if sys.executable:
        return _json_path(sys.executable)
    return "{{PYTHON_EXE}}"


def detect_npx() -> str:
    for name in ("npx.cmd", "npx"):
        found = shutil.which(name)
        if found:
            return _json_path(found)
    return "npx"


def detect_node() -> str:
    raw = (os.environ.get("NODE_EXE") or "").strip()
    if raw and Path(raw).is_file():
        return _json_path(raw)
    found = shutil.which("node")
    if found:
        return _json_path(found)
    return "{{NODE_EXE}}"


def detect_teams_mcp_root() -> str:
    raw = (os.environ.get("TEAMS_MCP_PROJECT") or "").strip()
    if raw and Path(raw).is_dir():
        return _json_path(Path(raw))
    sibling = _PROJECT_ROOT.parent / "teams-mcp"
    if sibling.is_dir():
        return _json_path(sibling)
    return "{{TEAMS_MCP_ROOT}}"


def starter_mcp_servers(*, track: str = "release") -> dict[str, Any]:
    """Minimal MCP blocks for Release Orchestrator onboarding (placeholders resolved)."""
    py = detect_python()
    repo = _json_path(_PROJECT_ROOT)
    scripts = _json_path(_PROJECT_ROOT / "release_mcp" / "scripts" / "daily_review")
    npx = detect_npx()

    servers: dict[str, Any] = {
        "release-orchestrator": {
            "_description": (
                "Release Orchestrator — weekly PIC/AN release + optional Daily Review. "
                "Say welcome onboard or fetch review tickets."
            ),
            "type": "stdio",
            "command": py,
            "args": ["-m", "release_mcp"],
            "cwd": repo,
            "env": {
                "TEAMS_MCP_ROOT": scripts,
                "RELEASE_ORCHESTRATOR_ROOT": repo,
            },
        },
        "playwright": {
            "_description": (
                "Playwright MCP — SharePoint upload, Slack Step 6, review-call calendar. "
                "Sign in to M365 + Slack web once after enable."
            ),
            "type": "stdio",
            "command": npx,
            "args": ["-y", "@playwright/mcp@latest", "--browser", "msedge"],
            "env": {},
        },
    }

    if track in {"daily_review", "both"}:
        teams_root = detect_teams_mcp_root()
        run_mjs = str(Path(teams_root.replace("/", os.sep)) / "run.mjs")
        if "{{" not in teams_root and Path(run_mjs).is_file():
            servers["teams"] = {
                "_description": "Teams MCP — Daily Review summary chat + alerts. First: teams_login.",
                "type": "stdio",
                "command": detect_node(),
                "args": [_json_path(Path(run_mjs))],
                "cwd": teams_root,
                "env": {"LOG_LEVEL": "error"},
            }
        else:
            servers["teams"] = {
                "_description": "Teams MCP — set TEAMS_MCP_PROJECT or clone teams-mcp sibling repo.",
                "_setup": "Clone teams-mcp → npm install → update command/cwd paths.",
                "type": "stdio",
                "command": "{{NODE_EXE}}",
                "args": ["{{TEAMS_MCP_ROOT}}/run.mjs"],
                "cwd": "{{TEAMS_MCP_ROOT}}",
                "env": {"LOG_LEVEL": "error"},
            }

    return servers


def starter_template_json(*, track: str = "release", indent: int = 2) -> str:
    """Full mcp.json starter (merge this block into your existing file)."""
    import json

    payload = {"mcpServers": starter_mcp_servers(track=track)}
    return json.dumps(payload, indent=indent)
