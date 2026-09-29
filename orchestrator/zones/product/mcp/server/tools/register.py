"""Import all tool modules so @mcp.tool decorators register handlers."""

from __future__ import annotations

import sys
from types import ModuleType

TOOL_MODULES: tuple[str, ...] = (
    "jira",
    "release",
    "gates",
    "service_ticket",
    "sharepoint",
    "teams",
    "slack",
    "onboarding",
    "workflow",
    "history",
    "confluence",
    "deploy",
    "readiness",
)


def load_tool_modules() -> list[ModuleType]:
    from release_mcp.server.tools import (  # noqa: WPS433
        jira,
        release,
        gates,
        service_ticket,
        sharepoint,
        teams,
        slack,
        onboarding,
        workflow,
        history,
        confluence,
        deploy,
        readiness,
    )
    return [
        jira,
        release,
        gates,
        service_ticket,
        sharepoint,
        teams,
        slack,
        onboarding,
        workflow,
        history,
        confluence,
        deploy,
        readiness,
    ]


def export_tools(target: ModuleType) -> None:
    """Copy tool functions from tool modules onto *target* (mock/test surface)."""
    import inspect

    for mod in load_tool_modules():
        for name, obj in vars(mod).items():
            if name.startswith("_"):
                continue
            if inspect.isfunction(obj) and obj.__module__ == mod.__name__:
                setattr(target, name, obj)

