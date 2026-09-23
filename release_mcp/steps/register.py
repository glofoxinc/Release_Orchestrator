"""Register one MCP tool per release step on the server instance."""

from __future__ import annotations

import sys
from typing import Any, Callable

from release_mcp.steps.catalog import RELEASE_STEPS
from release_mcp.steps.step_tools import release_step_status


def register_release_step_tools(mcp: Any, *, enrich: Callable[..., dict]) -> None:
    """Add ``release_step_<id>`` tool for each catalog step plus ``release_step_catalog``."""
    server_mod = sys.modules.get("release_mcp.server")

    @mcp.tool()
    def release_step_catalog() -> dict:
        """Full release step map — onboarding + steps 1–8 with phrases and MCP tools."""
        payload = release_step_status("")
        return enrich(payload, tool="release_step_catalog")

    if server_mod is not None:
        setattr(server_mod, "release_step_catalog", release_step_catalog)

    for row in RELEASE_STEPS:
        sid = str(row["id"])
        title = str(row["title"])
        tname = f"release_step_{sid}"

        def _bind(step_id: str, step_title: str, tool_name: str) -> None:
            @mcp.tool(name=tool_name)
            def _step_tool() -> dict:
                payload = release_step_status(step_id)
                return enrich(payload, tool=tool_name)

            _step_tool.__doc__ = (
                f"Release step `{step_id}` — {step_title}. "
                "User phrases, related MCP tools, readiness. "
                "Pair with `release_orchestrator` for the live workflow."
            )
            if server_mod is not None:
                setattr(server_mod, tool_name, _step_tool)

        _bind(sid, title, tname)
