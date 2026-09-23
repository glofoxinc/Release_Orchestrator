"""Install / merge Release Orchestrator MCP blocks into Cursor mcp.json."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from release_mcp.mcp_templates import starter_mcp_servers

_DEPRECATED = ("daily-review-agent",)


def _mcp_config_path() -> Path:
    import os

    raw = (os.environ.get("CURSOR_MCP_CONFIG") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cursor" / "mcp.json"


def _servers_root(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if isinstance(raw.get("mcpServers"), dict):
        return "mcpServers", raw["mcpServers"]
    if isinstance(raw.get("servers"), dict):
        return "servers", raw["servers"]
    return "mcpServers", {}


def load_mcp_config() -> dict[str, Any]:
    path = _mcp_config_path()
    if not path.is_file():
        return {"path": str(path), "raw": None, "parse_error": None, "servers": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"path": str(path), "raw": None, "parse_error": str(exc), "servers": {}}
    if not isinstance(raw, dict):
        return {"path": str(path), "raw": raw, "parse_error": "Root must be object", "servers": {}}
    _, servers = _servers_root(raw)
    return {"path": str(path), "raw": raw, "parse_error": None, "servers": servers}


def merge_starter_servers(*, track: str = "release", backup: bool = True) -> dict[str, Any]:
    """Merge starter blocks into ~/.cursor/mcp.json (keeps unrelated servers)."""
    path = _mcp_config_path()
    starter = starter_mcp_servers(track=track)
    loaded = load_mcp_config()

    if loaded.get("parse_error"):
        return {
            "ok": False,
            "path": str(path),
            "error": loaded["parse_error"],
            "action": "Fix JSON syntax in mcp.json first, then say continue.",
        }

    if loaded["raw"] is None:
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
    return {
        "ok": True,
        "path": str(path),
        "installed": sorted(starter.keys()),
        "backup": str(bak_path) if bak_path else None,
        "message": (
            f"Merged {', '.join(starter.keys())} into mcp.json. "
            "Reload Cursor MCP (Settings → MCP → reload), then say **continue**."
        ),
    }


def install_status(*, track: str = "release") -> dict[str, Any]:
    loaded = load_mcp_config()
    starter = starter_mcp_servers(track=track)
    present = loaded.get("servers") or {}
    missing = [k for k in starter if k not in present]
    return {
        "config_path": loaded.get("path"),
        "parse_error": loaded.get("parse_error"),
        "installed": [k for k in starter if k in present],
        "missing": missing,
        "ready": not loaded.get("parse_error") and not missing,
    }
