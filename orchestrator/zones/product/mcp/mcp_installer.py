"""Install / merge Release Orchestrator MCP blocks into Cursor mcp.json."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from orchestrator.paths import PROJECT_MCP_CONFIG, REPO_ROOT
from release_mcp.mcp_templates import starter_mcp_servers

_DEPRECATED = ("daily-review-agent",)


def project_mcp_config_path() -> Path:
    return PROJECT_MCP_CONFIG


def user_mcp_config_path() -> Path:
    import os

    raw = (os.environ.get("CURSOR_MCP_CONFIG") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cursor" / "mcp.json"


def resolve_mcp_config_path(*, prefer_project: bool = True) -> Path:
    """Project `.cursor/mcp.json` first, then user-global."""
    if prefer_project and project_mcp_config_path().is_file():
        return project_mcp_config_path()
    user = user_mcp_config_path()
    if user.is_file():
        return user
    if prefer_project:
        return project_mcp_config_path()
    return user


def _servers_root(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if isinstance(raw.get("mcpServers"), dict):
        return "mcpServers", raw["mcpServers"]
    if isinstance(raw.get("servers"), dict):
        return "servers", raw["servers"]
    return "mcpServers", {}


def load_mcp_config(*, prefer_project: bool = True) -> dict[str, Any]:
    path = resolve_mcp_config_path(prefer_project=prefer_project)
    if not path.is_file():
        return {
            "path": str(path),
            "source": "project" if path == project_mcp_config_path() else "user",
            "raw": None,
            "parse_error": None,
            "servers": {},
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(path),
            "source": "project" if path == project_mcp_config_path() else "user",
            "raw": None,
            "parse_error": str(exc),
            "servers": {},
        }
    if not isinstance(raw, dict):
        return {
            "path": str(path),
            "source": "project" if path == project_mcp_config_path() else "user",
            "raw": raw,
            "parse_error": "Root must be object",
            "servers": {},
        }
    _, servers = _servers_root(raw)
    return {
        "path": str(path),
        "source": "project" if path == project_mcp_config_path() else "user",
        "raw": raw,
        "parse_error": None,
        "servers": servers,
    }


def merge_starter_servers(*, track: str = "release", backup: bool = True) -> dict[str, Any]:
    """Merge starter blocks into project `.cursor/mcp.json` (preferred)."""
    path = project_mcp_config_path()
    starter = starter_mcp_servers(track=track)
    loaded = load_mcp_config(prefer_project=True)

    if loaded.get("parse_error") and path.is_file():
        return {
            "ok": False,
            "path": str(path),
            "error": loaded["parse_error"],
            "action": "Fix JSON syntax in .cursor/mcp.json first, then say continue.",
        }

    if loaded["raw"] is None or not path.is_file():
        raw: dict[str, Any] = {"mcpServers": dict(starter)}
        key = "mcpServers"
    else:
        raw = dict(loaded["raw"])
        key, servers = _servers_root(raw)
        merged = dict(servers)
        for dep in _DEPRECATED:
            merged.pop(dep, None)
        for name, block in starter.items():
            merged[name] = block
        raw[key] = merged

    path.parent.mkdir(parents=True, exist_ok=True)
    bak_path: Path | None = None
    existed = path.is_file()
    if backup and existed:
        bak_path = path.with_suffix(".json.bak-release-orchestrator")
        shutil.copy2(path, bak_path)

    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    user_path = user_mcp_config_path()
    user_note = ""
    if user_path.is_file() and user_path.resolve() != path.resolve():
        user_note = f" Note: user-global config also exists at {user_path} — project file takes precedence when opened in Cursor."

    return {
        "ok": True,
        "path": str(path),
        "installed": sorted(starter.keys()),
        "backup": str(bak_path) if bak_path else None,
        "message": (
            f"Merged {', '.join(starter.keys())} into .cursor/mcp.json. "
            "Reload Cursor MCP (Settings → MCP → reload), then say **continue**."
            f"{user_note}"
        ),
    }


def install_status(*, track: str = "release") -> dict[str, Any]:
    loaded = load_mcp_config(prefer_project=True)
    starter = starter_mcp_servers(track=track)
    present = loaded.get("servers") or {}
    missing = [k for k in starter if k not in present]
    return {
        "config_path": loaded.get("path"),
        "config_source": loaded.get("source"),
        "parse_error": loaded.get("parse_error"),
        "installed": [k for k in starter if k in present],
        "missing": missing,
        "ready": not loaded.get("parse_error") and not missing,
    }
