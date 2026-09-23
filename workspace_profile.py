"""Summarize org workspace profiles for rollout (templates, integrations, apps)."""

from __future__ import annotations

from typing import Any

import config


def _section(name: str) -> dict[str, Any]:
    raw = getattr(config, name.upper(), None)
    if isinstance(raw, dict):
        return raw
    return {}


def summarize_active_workspace() -> dict[str, Any]:
    """Return a JSON-safe profile of the active workspace for UI / MCP diagnostics."""
    teams = _section("TEAMS_SCHEDULE")
    slack = _section("SLACK_ANNOUNCE")
    gates = _section("RELEASE_GATES")
    sp = _section("SHAREPOINT_UPLOAD")
    rn = _section("RELEASE_NOTES")

    team_templates = teams.get("templates") if isinstance(teams.get("templates"), dict) else {}
    review_tpl = team_templates.get("review") if isinstance(team_templates.get("review"), dict) else {}
    deploy_tpl = team_templates.get("deployment") if isinstance(
        team_templates.get("deployment"), dict
    ) else {}

    return {
        "workspace_id": config.active_workspace_name() or "root",
        "display_name": config.WORKSPACE_NAME,
        "jira_base_url": config.JIRA_BASE_URL,
        "projects": [str(p.get("key", "")).strip() for p in config.PROJECTS if p.get("key")],
        "integrations": {
            "slack_announce": {
                "enabled": bool(slack.get("enabled", False)),
                "channel_count": len(slack.get("channels") or []),
                "template": (slack.get("templates") or {}).get("body")
                if isinstance(slack.get("templates"), dict)
                else "slack/deploy_announce.txt.j2",
            },
            "teams_schedule": {
                "enabled": bool(teams.get("enabled", False)),
                "organizer_upn": str(teams.get("organizer_upn") or ""),
                "review_slot": {
                    "default_day_offset": review_tpl.get("default_day_offset", -3),
                    "default_time": review_tpl.get("default_time", "15:00"),
                },
                "deployment_slot": {
                    "default_day_offset": deploy_tpl.get("default_day_offset", 0),
                    "default_time": deploy_tpl.get("default_time", "10:00"),
                },
            },
            "sharepoint_upload": {"enabled": bool(sp.get("enabled", False))},
            "release_gates": {
                "enabled": bool(gates.get("enabled", True)),
                "pre_review": bool((gates.get("pre_review") or {}).get("enabled", True)),
                "post_qa": bool((gates.get("post_qa") or {}).get("enabled", True)),
            },
        },
        "release_notes": {
            "enabled": bool(rn.get("enabled", False)),
            "team_name": str(rn.get("team_name") or ""),
        },
        "apps": dict(getattr(config, "APPS", {}) or {}),
        "available_workspaces": config.list_workspaces(),
    }


def list_org_profiles() -> list[dict[str, Any]]:
    """Summarize root + each workspaces/* profile (read-only; does not switch active)."""
    profiles: list[dict[str, Any]] = []
    for team in config.list_all_teams():
        profiles.append({
            "id": team.get("id") or "",
            "name": team.get("name") or "",
            "active": team.get("id") == config.active_workspace_name(),
        })
    return profiles


__all__ = ["list_org_profiles", "summarize_active_workspace"]
