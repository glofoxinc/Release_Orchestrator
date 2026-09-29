"""MCP server package — bootstrap + tool registration."""

from __future__ import annotations

import sys

from release_mcp.server import bootstrap
from release_mcp.server import implementation as _impl

mcp = bootstrap.mcp

_mod = sys.modules[__name__]
for _name in dir(_impl):
    if _name.startswith("__"):
        continue
    setattr(_mod, _name, getattr(_impl, _name))

main = _impl.main
