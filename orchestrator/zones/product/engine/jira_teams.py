"""Jira issue Team field (Atlassian Teams / customfield_10700) helpers."""

from __future__ import annotations

import re
from typing import Any

import config

_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]+")
_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)


def normalize_team_display_name(name: str) -> str:
    """Strip lock emoji / non-ASCII decoration from Atlassian Team titles."""
    cleaned = _NON_ASCII_RE.sub("", name or "").strip()
    return cleaned or (name or "").strip()


def known_teams_for_project(project_key: str) -> list[dict[str, Any]]:
    """Workspace catalog entries applicable to ``project_key``."""
    pk = (project_key or "").strip().upper()
    teams: list[dict[str, Any]] = []
    for entry in config.KNOWN_JIRA_TEAMS:
        projects = [str(p).strip().upper() for p in (entry.get("projects") or [])]
        if pk in projects:
            teams.append(
                {
                    "id": str(entry.get("id") or "").strip(),
                    "name": normalize_team_display_name(str(entry.get("name") or "")),
                }
            )
    return [t for t in teams if t["id"] and t["name"]]


def merge_team_catalog(
    project_key: str,
    discovered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge workspace-known teams with live Jira discovery (dedupe by id)."""
    merged: dict[str, dict[str, Any]] = {}
    for entry in known_teams_for_project(project_key) + list(discovered or []):
        tid = str(entry.get("id") or "").strip()
        if not tid:
            continue
        name = normalize_team_display_name(str(entry.get("name") or tid))
        merged[tid] = {"id": tid, "name": name}
    return sorted(merged.values(), key=lambda t: t["name"].lower())


def build_team_jql_clause(team_ids: list[str]) -> str:
    """Build JQL for the configured issue Team field."""
    ids = [str(t).strip() for t in team_ids if str(t).strip()]
    if not ids:
        return ""
    field = config.JIRA_ISSUE_TEAM_JQL or "cf[10700]"
    if len(ids) == 1:
        return f'{field} = "{ids[0]}"'
    quoted = ", ".join(f'"{tid}"' for tid in ids)
    return f"{field} in ({quoted})"


def append_issue_team_filter(jql: str, team_ids: list[str] | None) -> str:
    """Append optional Team-field filter before any ORDER BY clause."""
    clause = build_team_jql_clause(list(team_ids or []))
    if not clause:
        return jql
    match = _ORDER_BY_RE.search(jql)
    if match:
        base = jql[: match.start()].rstrip()
        order = jql[match.start() :].strip()
        return f"{base} AND ({clause}) {order}"
    return f"{jql} AND ({clause})"
