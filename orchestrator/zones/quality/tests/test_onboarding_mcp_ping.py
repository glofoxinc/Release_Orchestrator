"""MCP smoke ping and tool name length guard."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import release_mcp.server as srv
from release_mcp import onboarding_mcp_ping as ping

_MAX_TOOL_LEN = 60
_LEGACY_PATH = re.compile(r"orchestrator/ops/", re.I)
_SCAN_ROOTS = (
    Path("orchestrator/zones/product/mcp"),
    Path("orchestrator/zones/product/agents"),
)


def test_ping_release_mcp_module():
    result = ping.ping_release_mcp_module(timeout=120)
    assert result.get("ok"), result
    assert int(result.get("tool_count") or 0) >= 5


def test_mcp_tool_names_under_limit():
    importlib.reload(srv)
    tm = getattr(srv.mcp, "_tool_manager", None) or getattr(srv.mcp, "tool_manager", None)
    assert tm is not None, "FastMCP tool manager missing — cannot enforce MCP 60-char name limit"
    tools = getattr(tm, "_tools", None)
    assert isinstance(tools, dict) and tools, "No MCP tools registered on release_mcp.server"
    names = sorted(tools.keys())
    long_names = [n for n in names if len(n) > _MAX_TOOL_LEN]
    assert not long_names, f"Tool names exceed {_MAX_TOOL_LEN} chars: {long_names}"


def test_no_legacy_orchestrator_ops_paths_in_onboarding_code():
    repo = Path(__file__).resolve().parents[4]
    offenders: list[str] = []
    for rel in _SCAN_ROOTS:
        root = repo / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if _LEGACY_PATH.search(text):
                offenders.append(str(path.relative_to(repo)))
    assert not offenders, f"Legacy path orchestrator/ops/ in: {offenders[:10]}"
