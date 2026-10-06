"""Invoke Teams browser-session MCP (@shayanline/msteams-mcp) from Python."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from daily_review_agent.paths import REPO_ROOT, SCRIPTS_DIR, script

_PROJECT_ROOT = REPO_ROOT
_BRIDGE = script("teams_bridge.mjs")


def _node_exe() -> str:
    raw = (os.environ.get("NODE_EXE") or "").strip()
    if raw and Path(raw).is_file():
        return raw
    from daily_review_agent.setup_mcp import _detect_node

    detected = _detect_node()
    if detected is not None and detected.is_file():
        return str(detected)
    return "node"


def _bridge_cwd() -> Path:
    raw = (os.environ.get("TEAMS_MCP_ROOT") or "").strip()
    if raw:
        return Path(raw).resolve()
    return SCRIPTS_DIR


def teams_mcp_call(command: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run teams_bridge.mjs and return parsed JSON from stdout."""
    if not _BRIDGE.is_file():
        return {"ok": False, "error": f"teams_bridge missing: {_BRIDGE}"}
    env = os.environ.copy()
    env.setdefault("LOG_LEVEL", "error")
    proc = subprocess.run(
        [_node_exe(), str(_BRIDGE), command, json.dumps(payload or {})],
        cwd=str(_bridge_cwd()),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if stderr:
        logger.debug("teams_bridge stderr: %s", stderr[-500:])
    if not stdout:
        return {
            "ok": False,
            "error": stderr or f"teams_bridge exited {proc.returncode}",
            "exit_code": proc.returncode,
        }
    try:
        data = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"Invalid bridge output: {exc}", "raw": stdout[:500]}
    data.setdefault("exit_code", proc.returncode)
    return data


def run_teams_bridge_login(*, timeout: int = 600) -> dict[str, Any]:
    """Interactive Teams sign-in for Python bridge (same session store as Cursor MCP)."""
    if not _BRIDGE.is_file():
        return {"ok": False, "error": f"teams_bridge missing: {_BRIDGE}"}
    env = os.environ.copy()
    env.setdefault("LOG_LEVEL", "error")
    proc = subprocess.run(
        [_node_exe(), str(_BRIDGE), "login", "{}"],
        cwd=str(_bridge_cwd()),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if not stdout:
        return {
            "ok": False,
            "error": stderr or f"teams_bridge login exited {proc.returncode}",
            "exit_code": proc.returncode,
        }
    try:
        data = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"Invalid bridge output: {exc}", "raw": stdout[:500]}
    data.setdefault("exit_code", proc.returncode)
    return data


def teams_session_ready() -> bool:
    out = teams_mcp_call("status")
    return bool(out.get("ok") and out.get("authenticated"))


def teams_readiness() -> dict[str, Any]:
    out = teams_mcp_call("status")
    blockers: list[str] = []
    if not out.get("authenticated"):
        blockers.append("Teams session missing or expired — run teams_login in Cursor (Teams MCP)")
    return {
        "enabled": True,
        "authenticated": bool(out.get("authenticated")),
        "can_schedule": bool(out.get("authenticated")),
        "can_message": bool(out.get("authenticated")),
        "blockers": blockers,
        "detail": out,
    }
