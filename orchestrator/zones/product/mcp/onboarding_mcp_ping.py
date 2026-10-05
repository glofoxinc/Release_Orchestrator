"""Best-effort live readiness for Release Orchestrator MCP (stdio smoke + config)."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.paths import PROJECT_MCP_CONFIG, REPO_ROOT, json_path, venv_python


def _tool_count_script() -> str:
    return (
        "import release_mcp.server as s; "
        "tm = getattr(s.mcp, '_tool_manager', None) or getattr(s.mcp, 'tool_manager', None); "
        "tools = getattr(tm, '_tools', None) or {}; "
        "print(len(tools))"
    )


def ping_release_mcp_module(*, timeout: int = 90) -> dict[str, Any]:
    """Import release_mcp.server and count registered tools (stdio server smoke)."""
    py = venv_python()
    if not py.is_file():
        return {"ok": False, "stage": "venv", "error": "Python venv not found"}
    try:
        proc = subprocess.run(
            [str(py), "-c", _tool_count_script()],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "stage": "import", "error": f"MCP module import timed out ({timeout}s)"}
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[:500]
        return {"ok": False, "stage": "import", "error": err or f"exit {proc.returncode}"}
    try:
        count = int((proc.stdout or "").strip().splitlines()[-1])
    except ValueError:
        return {"ok": False, "stage": "import", "error": "Could not parse tool count", "raw": proc.stdout[:200]}
    if count < 5:
        return {"ok": False, "stage": "tools", "error": f"Too few MCP tools registered ({count})"}
    return {"ok": True, "stage": "tools", "tool_count": count, "python": json_path(py)}


def mcp_config_fresh(*, max_age_seconds: int = 86400) -> dict[str, Any]:
    path = PROJECT_MCP_CONFIG
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "Project .cursor/mcp.json missing"}
    stat = path.stat()
    age = datetime.now(timezone.utc).timestamp() - stat.st_mtime
    return {
        "ok": True,
        "path": str(path),
        "mtime_iso": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "age_seconds": int(age),
        "recently_merged": age < max_age_seconds,
    }


def live_mcp_ready(*, require_config: bool = True) -> dict[str, Any]:
    """Config on disk + release_mcp import smoke (proxy for post-reload health)."""
    from release_mcp import mcp_installer

    track = "release"
    install = mcp_installer.install_status(track=track)
    cfg = mcp_config_fresh()
    ping = ping_release_mcp_module()
    config_ok = bool(install.get("ready")) and not install.get("parse_error")
    if require_config and not config_ok:
        return {
            "ok": False,
            "config_ok": config_ok,
            "ping": ping,
            "install_status": install,
            "config_file": cfg,
            "hint": "Merge MCP blocks then reload Cursor MCP once.",
        }
    ok = bool(ping.get("ok")) and (config_ok or not require_config)
    return {
        "ok": ok,
        "config_ok": config_ok,
        "ping": ping,
        "install_status": install,
        "config_file": cfg,
        "hint": "Reload Cursor MCP if Playwright/release-orchestrator still red in Settings.",
    }
