"""MCP tools: isolated program packs (Glofox vs Ignite vs ETL)."""

from __future__ import annotations

import program_pack as pp
from release_mcp.operator_guide import enrich_tool_response
from release_mcp.server.bootstrap import mcp


@mcp.tool()
def program_status() -> dict:
    """Show the active trained program (Glofox vs Ignite vs ETL) and isolation rules.

    Glofox is trained. Ignite/ETL stay empty until trained on their own roster.
    """
    return enrich_tool_response(
        {
            "ok": True,
            "active": pp.active_program_key(),
            "programs": pp.list_programs(),
            "context": pp.program_context(),
        },
        tool="program_status",
    )


@mcp.tool()
def train_program(program: str = "glofox", lock_env: bool = False) -> dict:
    """Bind MCP to a trained program pack (crew, QA, leaders, review-call rules).

    Glofox is already trained in-repo. Ignite/ETL refuse until their own pack is filled —
    they will not inherit Glofox people.

    Args:
        program: glofox (default), ignite, or etl
        lock_env: Also write TEAM_CREW_* + RELEASE_PROGRAM for this pack into .env
    """
    payload = pp.train_program(program, lock_env=lock_env)
    return enrich_tool_response(payload, tool="train_program")


@mcp.tool()
def switch_program(program: str) -> dict:
    """Switch RELEASE_PROGRAM. Untrained packs (Ignite/ETL) are blocked — no Glofox fallback.

    Args:
        program: glofox, ignite, or etl
    """
    payload = pp.switch_program(program)
    return enrich_tool_response(payload, tool="switch_program")
