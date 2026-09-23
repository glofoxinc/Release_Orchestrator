"""Snapshot lock, drift detection, and headless Jira fetch for locked lists."""

from __future__ import annotations

import logging

import config
import jira_client

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "shared_snapshot"


def snapshot_key() -> str:
    return _SNAPSHOT_KEY


def snapshot_team_ids(snap: dict, project_key: str) -> list[str] | None:
    """Team IDs stored on the Ticket Review snapshot for one project."""
    raw = (snap.get("jira_team_filters") or {}).get(project_key) or []
    ids = [
        str(entry.get("id", "")).strip()
        for entry in raw
        if isinstance(entry, dict) and str(entry.get("id", "")).strip()
    ]
    return ids if ids else None


def snapshot_selection_mode(snap: dict) -> str:
    return str(snap.get("selection_mode") or "fix_version")


def fetch_issues_for_snapshot(snap: dict) -> list[dict]:
    """Headless Jira fetch matching the locked snapshot source (fix version or status)."""
    mode = snapshot_selection_mode(snap)
    all_issues: list[dict] = []
    seen: set[str] = set()

    if mode == "status":
        status_filters = snap.get("status_filters") or {}
        for proj in config.PROJECTS:
            pk = proj["key"]
            statuses = status_filters.get(pk) or []
            if not statuses:
                continue
            team_ids = snapshot_team_ids(snap, pk)
            batch = jira_client.get_issues_for_statuses(
                pk, statuses, jira_team_ids=team_ids,
            )
            for iss in batch:
                key = iss.get("key")
                if key and key not in seen:
                    seen.add(key)
                    all_issues.append(iss)
        return all_issues

    for proj in config.PROJECTS:
        pk = proj["key"]
        rel = snap.get(f"release_{pk}", {})
        if not rel:
            continue
        team_ids = snapshot_team_ids(snap, pk)
        batch = jira_client.get_issues_for_version(
            pk, rel["id"], jira_team_ids=team_ids,
        )
        for iss in batch:
            key = iss.get("key")
            if key and key not in seen:
                seen.add(key)
                all_issues.append(iss)
    return all_issues


__all__ = [
    "fetch_issues_for_snapshot",
    "snapshot_key",
    "snapshot_selection_mode",
    "snapshot_team_ids",
]
