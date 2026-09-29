"""MCP server entry — bootstrap, tool registration, and main()."""

from __future__ import annotations

import sys

import config
import jira_client
from release_mcp import daily_review_ops
from release_mcp.server import bootstrap
from release_mcp.server.tools.register import export_tools, load_tool_modules
from release_mcp.steps.register import register_release_step_tools
from release_mcp.operator_guide import enrich_tool_response

mcp = bootstrap.mcp
logger = bootstrap.logger

load_tool_modules()
export_tools(sys.modules[__name__])

register_release_step_tools(mcp, enrich=enrich_tool_response)
daily_review_ops.register(mcp)


def main() -> None:
    """Run the MCP server via stdio transport."""
    mcp.run(transport="stdio")
