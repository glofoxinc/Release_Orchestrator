"""MCP server bootstrap — env, logging, workspace, MCPServer instance."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv
from orchestrator.paths import ENV_FILE

load_dotenv(ENV_FILE, override=True)

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "The MCP server requires mcp>=2.0.0, which provides "
        "'mcp.server.mcpserver'. The interpreter running this module has an "
        "older mcp (or none). Launch it with the project virtualenv "
        r"(.venv\Scripts\python.exe -m release_mcp) or install the pinned "
        "dependencies with 'pip install -r orchestrator/zones/config/deps/requirements.txt'."
    ) from exc

import config
from common.logger import set_log_context, setup_logging

setup_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
for _handler in logging.getLogger().handlers:
    if isinstance(_handler, logging.StreamHandler):
        _handler.stream = sys.stderr

config.ensure_workspace_loaded()
set_log_context(workspace=config.active_workspace_name() or "root", surface="mcp")

mcp = MCPServer("release-orchestrator")
