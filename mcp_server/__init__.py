"""Compatibility shim — prefer ``python -m release_mcp``.

Legacy Cursor configs may still use ``-m mcp_server``; both delegate to the same server.
"""

from __future__ import annotations

from release_mcp import (  # noqa: F401
    browser_ops,
    daily_review_guided,
    daily_review_ops,
    gate_ops,
    guided,
    mcp_readiness,
    onboarding,
    onboarding_guide,
    onboarding_store,
    onboarding_team_flow,
    operator_guide,
    release_notes_preview,
    release_ops,
    sharepoint_ops,
    slack_mcp_ops,
    slack_ops,
    step_ux,
    teams_ops,
    welcome,
    wizard,
    wizard_store,
    workflow_modes,
)

__all__ = [
    "browser_ops",
    "daily_review_guided",
    "daily_review_ops",
    "gate_ops",
    "guided",
    "mcp_readiness",
    "onboarding",
    "onboarding_guide",
    "onboarding_store",
    "onboarding_team_flow",
    "operator_guide",
    "release_notes_preview",
    "release_ops",
    "sharepoint_ops",
    "slack_mcp_ops",
    "slack_ops",
    "step_ux",
    "teams_ops",
    "welcome",
    "wizard",
    "wizard_store",
    "workflow_modes",
]
