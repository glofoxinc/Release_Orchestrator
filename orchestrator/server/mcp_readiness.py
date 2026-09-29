"""MCP production readiness — thin wrapper over shared production_readiness."""

from __future__ import annotations

from typing import Any

import production_readiness


def assess_mcp_production(*, include_operator: bool = True) -> dict[str, Any]:
    """Return VERIFIED / UNVERIFIED / OPERATOR REQUIRED for MCP launch."""
    del include_operator  # operator items always included in shared assessor
    return production_readiness.assess_production_readiness(surface="mcp")


def format_readiness_message(**kwargs: Any) -> str:
    return production_readiness.format_production_readiness_message(**kwargs)


__all__ = ["assess_mcp_production", "format_readiness_message"]
