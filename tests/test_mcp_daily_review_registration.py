"""Verify daily_review_* tools register on the unified MCP server."""

from __future__ import annotations

import importlib


def test_daily_review_tools_registered():
    import release_mcp.server as srv

    importlib.reload(srv)
    tool_mgr = getattr(srv.mcp, "_tool_manager", None) or getattr(srv.mcp, "tool_manager", None)
    assert tool_mgr is not None
    tools = tool_mgr._tools if hasattr(tool_mgr, "_tools") else {}
    names = set(tools.keys()) if tools else set()
    if not names and hasattr(tool_mgr, "list_tools"):
        names = {t.name for t in tool_mgr.list_tools()}
    expected = {
        "daily_review_orchestrator",
        "daily_review_setup",
        "daily_review_preflight",
        "daily_review_run_live",
        "daily_review_outlook_login",
        "daily_review_status",
    }
    missing = expected - names
    assert not missing, f"Missing daily_review MCP tools: {sorted(missing)}"


def test_release_orchestrator_routes_daily_review_phrase():
    from release_mcp import guided

    plan = guided.interpret_message("daily review welcome")
    assert plan.get("action") == "daily_review"
    assert plan.get("intent") == "daily_review"
