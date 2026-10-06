"""Generic Cursor MCP server blocks — no personal paths (filled at install time)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

from orchestrator.paths import (
    DAILY_REVIEW_OPS_DIR,
    REPO_ROOT as _PROJECT_ROOT,
    json_path,
    venv_python,
)

# Pinned — avoid @latest surprises during onboarding (Playwright MCP server).
PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@0.0.39"


def detect_python() -> str:
    venv = venv_python()
    if venv.is_file():
        return json_path(venv)
    if sys.executable:
        return json_path(sys.executable)
    return "{{PYTHON_EXE}}"


def detect_npx() -> str:
    for name in ("npx.cmd", "npx"):
        found = shutil.which(name)
        if found:
            return json_path(found)
    node = detect_node()
    if node and "{{" not in node:
        sibling = Path(node.replace("/", os.sep)).parent / "npx.cmd"
        if sibling.is_file():
            return json_path(sibling)
    for candidate in (
        Path.home() / "nodejs" / "npx.cmd",
        Path("C:/Program Files/nodejs/npx.cmd"),
    ):
        if candidate.is_file():
            return json_path(candidate)
    return "npx"


def detect_node() -> str:
    raw = (os.environ.get("NODE_EXE") or "").strip()
    if raw and Path(raw).is_file():
        return json_path(raw)
    found = shutil.which("node")
    if found:
        return json_path(found)
    for candidate in (
        Path.home() / "nodejs" / "node.exe",
        Path("C:/Program Files/nodejs/node.exe"),
    ):
        if candidate.is_file():
            return json_path(candidate)
    return "{{NODE_EXE}}"


def mcp_node_path_env() -> dict[str, str]:
    """Ensure Node/npm directory is on PATH for Cursor MCP child processes."""
    base = os.environ.get("PATH", "")
    dirs: list[str] = []
    for cmd in (detect_node(), detect_npx()):
        if not cmd or "{{" in cmd or cmd in {"node", "npx"}:
            continue
        parent = str(Path(cmd.replace("/", os.sep)).parent)
        if parent and parent not in dirs:
            dirs.append(parent)
    if not dirs:
        return {}
    merged = os.pathsep.join(dirs)
    if base:
        merged = merged + os.pathsep + base
    return {"PATH": merged}


def detect_teams_mcp_root() -> str:
    raw = (os.environ.get("TEAMS_MCP_PROJECT") or os.environ.get("TEAMS_MCP_ROOT") or "").strip()
    if raw and Path(raw).is_dir():
        return json_path(Path(raw))
    sibling = _PROJECT_ROOT.parent / "teams-mcp"
    if sibling.is_dir():
        return json_path(sibling)
    if DAILY_REVIEW_OPS_DIR.is_dir():
        return json_path(DAILY_REVIEW_OPS_DIR)
    return "{{TEAMS_MCP_ROOT}}"


def starter_mcp_servers(*, track: str = "release") -> dict[str, Any]:
    """Minimal MCP blocks for Release Orchestrator onboarding (placeholders resolved)."""
    py = detect_python()
    repo = json_path(_PROJECT_ROOT)
    teams_ops = json_path(DAILY_REVIEW_OPS_DIR)
    npx = detect_npx()
    node_path_env = mcp_node_path_env()

    servers: dict[str, Any] = {
        "release-orchestrator": {
            "_description": "Release Orchestrator — welcome onboard / week release",
            "type": "stdio",
            "command": py,
            "args": ["-m", "release_mcp"],
            "cwd": repo,
            "env": {
                "TEAMS_MCP_ROOT": teams_ops,
                "RELEASE_ORCHESTRATOR_ROOT": repo,
            },
        },
        "playwright": {
            "_description": "Playwright MCP — SharePoint, Slack, calendar",
            "type": "stdio",
            "command": npx,
            "args": ["-y", PLAYWRIGHT_MCP_PACKAGE, "--browser", "msedge"],
            "env": dict(node_path_env),
        },
    }

    if track in {"daily_review", "both"}:
        teams_root = detect_teams_mcp_root()
        run_mjs = str(Path(teams_root.replace("/", os.sep)) / "run.mjs")
        bridge = DAILY_REVIEW_OPS_DIR / "teams_bridge.mjs"
        if "{{" not in teams_root and Path(run_mjs).is_file():
            teams_env = {"LOG_LEVEL": "error"}
            teams_env.update(node_path_env)
            servers["teams"] = {
                "_description": "Teams MCP — Daily Review summary chat + alerts. First: teams_login.",
                "type": "stdio",
                "command": detect_node(),
                "args": [json_path(Path(run_mjs))],
                "cwd": teams_root,
                "env": teams_env,
            }
        elif bridge.is_file():
            servers["teams"] = {
                "_description": "Teams bridge (Daily Review chat)",
                "type": "stdio",
                "command": detect_node(),
                "args": [json_path(bridge)],
                "cwd": json_path(DAILY_REVIEW_OPS_DIR),
                "env": {"LOG_LEVEL": "error", **node_path_env},
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
