"""Archived integration helpers — Slack, Teams, SharePoint Graph feature flags."""

from __future__ import annotations

from typing import Any

import config


def archived_response(integration_id: str, *, detail: str = "") -> dict[str, Any]:
    """Standard MCP/UI payload when an integration is archived."""
    restore = config.archived_integration_restore_path(integration_id)
    default_detail = (
        f"Integration `{integration_id}` is archived. "
        f"Restore settings from `{restore}` and set enabled=true when IT is ready."
    )
    return {
        "archived": True,
        "status": "disabled",
        "enabled": False,
        "restore": restore,
        "detail": detail or default_detail,
    }


def is_archived(integration_id: str) -> bool:
    checks = {
        "slack_announce": config.slack_archived,
        "teams_schedule": config.teams_archived,
        "sharepoint_upload": config.sharepoint_upload_archived,
    }
    fn = checks.get(integration_id)
    return bool(fn()) if fn else False
