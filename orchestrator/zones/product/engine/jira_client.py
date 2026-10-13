"""Jira API client with retry/backoff, parsing, and deployment helpers."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, TypeVar

import requests
from requests.auth import HTTPBasicAuth

import config
import jira_teams
import team_scope
from shipit_test_mode import is_test_shipit_summary

import jira_client_http as _http
from jira_client_http import (  # noqa: F401
    JiraApiError,
    RequestTypeStatus,
    _BACKOFF_BASE,
    _DEFAULT_TIMEOUT,
    _MAX_RETRIES,
    _RECENT_COMMENT_WINDOW,
    _auth,
    _block_mock_writes,
    _delete,
    _friendly_raise,
    _get,
    _handle_connection_error,
    _headers,
    _logger,
    _maybe_inter_call_pause,
    _post,
    _put,
    _should_retry,
    _version_cache,
    _version_cache_lock,
    clear_version_cache,
    field_label,
    is_mock_mode,
    rate_limit_pause_seconds,
    readonly_concurrency,
    readonly_map,
    version_cache_ttl_seconds,
)

# Re-export remaining HTTP-layer private symbols for unittest.mock.patch targets.
for _http_name, _http_value in vars(_http).items():
    if _http_name.startswith("_") and _http_name not in {"__builtins__"} and _http_name not in globals():
        globals()[_http_name] = _http_value


# ── Versions / Releases ─────────────────────────────────────────────

def get_project_versions(project_key: str, released: bool | None = None) -> list[dict]:
    """Return versions for the given project, newest first.

    Caches successful responses for ``JIRA_VERSION_CACHE_TTL`` seconds (default
    300). Safe for the single-user Streamlit desktop target; call
    :func:`clear_version_cache` after marking a version released.
    """
    ttl = version_cache_ttl_seconds()
    cache_key = (
        config.JIRA_BASE_URL,
        config.JIRA_EMAIL,
        project_key,
        released,
    )
    if ttl > 0:
        with _version_cache_lock:
            hit = _version_cache.get(cache_key)
            if hit is not None:
                expires_at, cached = hit
                if time.monotonic() < expires_at:
                    return list(cached)

    versions = _get(f"/project/{project_key}/versions")
    if released is not None:
        versions = [v for v in versions if v.get("released") == released]
    versions = sorted(
        versions,
        key=lambda v: v.get("startDate", v.get("releaseDate", "")),
        reverse=True,
    )
    if ttl > 0:
        with _version_cache_lock:
            _version_cache[cache_key] = (time.monotonic() + ttl, list(versions))
    return versions


def create_project_version(
    project_key: str,
    name: str,
    *,
    description: str = "",
    released: bool = False,
) -> dict[str, Any]:
    """Create a Jira fix version on a project. Caller must confirm before live create."""
    pk = (project_key or "").strip().upper()
    version_name = (name or "").strip()
    if not pk or not version_name:
        raise ValueError("project_key and name are required")
    existing = get_project_versions(pk)
    for row in existing:
        if str(row.get("name") or "").strip() == version_name:
            return {"created": False, "existing": True, "version": row}
    body: dict[str, Any] = {
        "name": version_name,
        "project": pk,
        "released": released,
    }
    if description.strip():
        body["description"] = description.strip()
    created = _post("/version", body)
    clear_version_cache()
    return {"created": True, "existing": False, "version": created}


def _search_jql_paginated(
    jql: str,
    *,
    fields: list[str],
    max_results: int | None = None,
    page_size: int = 100,
) -> list[dict]:
    """Shared POST /search/jql pagination used by version and generic searches."""
    all_issues: list[dict] = []
    next_token: str | None = None
    while True:
        if max_results is not None:
            remaining = max_results - len(all_issues)
            if remaining <= 0:
                break
            this_page = min(page_size, remaining)
        else:
            this_page = page_size
        body: dict[str, Any] = {
            "jql": jql,
            "maxResults": this_page,
            "fields": fields,
        }
        if next_token:
            body["nextPageToken"] = next_token
        data = _post("/search/jql", body)
        all_issues.extend(data.get("issues", []))
        next_token = data.get("nextPageToken")
        if not next_token:
            break
    if max_results is not None:
        return all_issues[:max_results]
    return all_issues


# ── Team scope / board-filter resolution ───────────────────────────

def _agile_get(path: str) -> Any:
    """GET against Jira Agile REST (read-only)."""
    base = config.JIRA_BASE_URL.rstrip("/")
    url = f"{base}/rest/agile/1.0{path}"
    for attempt in range(_MAX_RETRIES + 1):
        _maybe_inter_call_pause()
        try:
            resp = requests.get(
                url, headers=_headers(), auth=_auth(), timeout=_DEFAULT_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            _handle_connection_error(exc, path)
        if _should_retry(resp, attempt):
            continue
        _friendly_raise(resp)
        return resp.json()


def get_board_filter_id(board_id: str) -> str:
    """Resolve a Jira board id to its saved filter id."""
    bid = team_scope.normalize_scope_id(board_id)
    if not bid or not bid.isdigit():
        raise team_scope.TeamScopeError(f"Invalid board id '{board_id}'.")
    data = _agile_get(f"/board/{bid}/configuration")
    filter_obj = data.get("filter") or {}
    filter_id = str(filter_obj.get("id") or "").strip()
    if not filter_id:
        raise team_scope.TeamScopeError(
            f"Board {bid} has no saved filter in Jira Agile configuration.",
        )
    return filter_id


def get_saved_filter(filter_id: str) -> dict[str, Any]:
    """Return Jira saved-filter metadata including its JQL."""
    fid = team_scope.normalize_scope_id(filter_id)
    if not fid or not fid.isdigit():
        raise team_scope.TeamScopeError(f"Invalid filter id '{filter_id}'.")
    data = _get(f"/filter/{fid}")
    if not isinstance(data, dict):
        raise team_scope.TeamScopeError(f"Filter {fid} returned an unexpected response.")
    return data


def build_scoped_version_jql(project_key: str, version_id: str) -> str:
    """Build tenant-safe release JQL or raise :class:`team_scope.TeamScopeError`."""
    scope = team_scope.ensure_scope_ready(project_key)
    resolved_filter = team_scope.resolve_filter_id(
        scope, board_resolver=get_board_filter_id,
    )
    return team_scope.build_scoped_version_jql(
        project_key,
        version_id,
        scope,
        resolved_filter_id=resolved_filter,
    )


def validate_team_scope(
    project_key: str,
    *,
    version_id: str = "",
    sample_limit: int = 5,
) -> dict[str, Any]:
    """Preflight team scope: structure, board/filter resolution, optional sample."""
    pk = project_key.strip().upper()
    try:
        scope = team_scope.scope_from_project(pk)
    except team_scope.TeamScopeError as exc:
        return team_scope.scope_status(pk, validation_errors=[str(exc)])

    errors = team_scope.validate_scope_structure(scope, project_key=pk)
    resolved_filter = ""
    if not errors:
        try:
            resolved_filter = team_scope.resolve_filter_id(
                scope, board_resolver=get_board_filter_id,
            )
        except team_scope.TeamScopeError as exc:
            errors.extend(exc.errors or [str(exc)])

    status = team_scope.scope_status(
        pk,
        scope=scope,
        resolved_filter_id=resolved_filter,
        validation_errors=errors,
    )
    if errors:
        status["sample_count"] = 0
        status["sample_keys"] = []
        return status

    if scope.filter_id and not scope.board_id:
        try:
            meta = get_saved_filter(scope.filter_id)
            filter_jql = str(meta.get("jql") or "")
            if filter_jql and pk.upper() not in filter_jql.upper():
                status.setdefault("warnings", []).append(
                    "Saved filter JQL does not mention this project; "
                    "results are still constrained by project = clause."
                )
        except team_scope.TeamScopeError as exc:
            errors.append(str(exc))
            status["errors"] = errors
            status["state"] = "invalid"
            status["blocking"] = True
            status["configured"] = False
            return status

    team_clause = team_scope.build_team_scope_clause(scope, resolved_filter_id=resolved_filter)
    if version_id:
        jql = team_scope.build_scoped_version_jql(
            pk, version_id, scope, resolved_filter_id=resolved_filter, order_by="",
        )
    else:
        base = f"project = {pk}"
        jql = f"{base} AND ({team_clause})" if team_clause else base

    try:
        data = _post("/search/jql", {"jql": jql, "maxResults": 0, "fields": ["summary"]})
        status["preflight_total"] = data.get("total", 0)
    except Exception as exc:  # noqa: BLE001 — surface to caller
        status["errors"] = [f"Scope JQL preflight failed: {exc}"]
        status["state"] = "invalid"
        status["blocking"] = True
        status["configured"] = False
        return status

    if sample_limit > 0:
        sample_jql = f"{jql} ORDER BY updated DESC"
        try:
            sample = _search_jql_paginated(
                sample_jql,
                fields=["summary", "status"],
                max_results=sample_limit,
            )
        except Exception:
            sample = []
        status["sample_keys"] = [iss.get("key") for iss in sample if iss.get("key")]
        status["sample_count"] = len(status["sample_keys"])
    else:
        status["sample_keys"] = []
        status["sample_count"] = 0

    status["resolved_filter_id"] = resolved_filter
    if version_id:
        status["effective_jql_template"] = team_scope.build_scoped_version_jql(
            pk, "<version-id>", scope, resolved_filter_id=resolved_filter, order_by="key ASC",
        ).replace("<version-id>", "<version-id>")
    else:
        status["effective_jql_template"] = (
            f"project = {pk} AND fixVersion = <version-id>"
            + (f" AND ({team_clause})" if team_clause else "")
            + " ORDER BY key ASC"
        )
    return status


def scoped_version_metadata(project_key: str, version_id: str) -> dict[str, Any]:
    """Scope fingerprint/type for a project version fetch."""
    scope = team_scope.ensure_scope_ready(project_key)
    resolved_filter = team_scope.resolve_filter_id(
        scope, board_resolver=get_board_filter_id,
    )
    st = team_scope.scope_status(
        project_key,
        scope=scope,
        resolved_filter_id=resolved_filter,
    )
    st["version_id"] = str(version_id)
    return st


# ── Tickets in a release ────────────────────────────────────────────

def discover_project_teams(
    project_key: str,
    *,
    sample_limit: int = 200,
) -> list[dict[str, Any]]:
    """Discover distinct Atlassian Team values on recent project tickets."""
    field = config.JIRA_ISSUE_TEAM_FIELD or "customfield_10700"
    team_jql = config.JIRA_ISSUE_TEAM_JQL or "cf[10700]"
    jql = (
        f"project = {project_key.strip()} AND {team_jql} is not EMPTY "
        "ORDER BY updated DESC"
    )
    issues = _search_jql_paginated(
        jql,
        fields=[field],
        max_results=sample_limit,
    )
    teams: dict[str, dict[str, str]] = {}
    for iss in issues:
        raw = (iss.get("fields") or {}).get(field)
        if not isinstance(raw, dict):
            continue
        tid = str(raw.get("id") or "").strip()
        if not tid:
            continue
        name = jira_teams.normalize_team_display_name(str(raw.get("name") or tid))
        teams[tid] = {"id": tid, "name": name}
    return sorted(teams.values(), key=lambda t: t["name"].lower())


def get_issues_for_version(
    project_key: str,
    version_id: str,
    *,
    jira_team_ids: list[str] | None = None,
) -> list[dict]:
    """Fetch all issues via POST /search/jql with nextPageToken pagination."""
    jql = build_scoped_version_jql(project_key, version_id)
    jql = jira_teams.append_issue_team_filter(jql, jira_team_ids)
    team_field = config.JIRA_ISSUE_TEAM_FIELD or "customfield_10700"
    search_fields = [
        "summary",
        "description",
        "status",
        "issuetype",
        "assignee",
        "priority",
        "fixVersions",
        "labels",
        "parent",
        team_field,
    ]
    return _search_jql_paginated(jql, fields=search_fields)


def build_scoped_status_jql(project_key: str, statuses: Iterable[str]) -> str:
    """Build tenant-safe status JQL or raise :class:`team_scope.TeamScopeError`."""
    scope = team_scope.ensure_scope_ready(project_key)
    resolved_filter = team_scope.resolve_filter_id(
        scope, board_resolver=get_board_filter_id,
    )
    return team_scope.build_scoped_status_jql(
        project_key,
        statuses,
        scope,
        resolved_filter_id=resolved_filter,
    )


def get_project_status_names(project_key: str) -> list[str]:
    """Return distinct workflow status names for a Jira project (all issue types)."""
    data = _get(f"/project/{project_key}/statuses")
    names: set[str] = set()
    for issue_type in data if isinstance(data, list) else []:
        for status in issue_type.get("statuses") or []:
            name = str(status.get("name") or "").strip()
            if name:
                names.add(name)
    return sorted(names, key=str.lower)


def get_issues_for_statuses(
    project_key: str,
    statuses: Iterable[str],
    *,
    jira_team_ids: list[str] | None = None,
) -> list[dict]:
    """Fetch issues matching one or more Jira statuses within team scope."""
    status_list = [str(s).strip() for s in statuses if str(s).strip()]
    if not status_list:
        return []
    jql = build_scoped_status_jql(project_key, status_list)
    jql = jira_teams.append_issue_team_filter(jql, jira_team_ids)
    team_field = config.JIRA_ISSUE_TEAM_FIELD or "customfield_10700"
    search_fields = [
        "summary",
        "description",
        "status",
        "issuetype",
        "assignee",
        "priority",
        "fixVersions",
        "labels",
        "parent",
        team_field,
    ]
    return _search_jql_paginated(jql, fields=search_fields)


def get_issue_keys_for_version(project_key: str, version_id: str) -> list[str]:
    """Lightweight fetch — returns only ticket keys for a version (no fields)."""
    jql = build_scoped_version_jql(project_key, version_id)
    return [iss["key"] for iss in _search_jql_paginated(jql, fields=[])]


# ── Client name extraction ──────────────────────────────────────────

_CLIENT_SEPARATOR = re.compile(r"\s*[-–—]\s*")


def extract_client_name(summary: str, extraction: str = "title_prefix", project_key: str = "") -> str:
    """Extract the client name from a ticket summary."""
    if extraction == "none":
        return project_key or "All"

    parts = _CLIENT_SEPARATOR.split(summary, maxsplit=1)
    if len(parts) <= 1:
        return "Unknown"
    raw = parts[0].strip()
    if not raw:
        return "Unknown"
    return raw


def _normalize_client_groups(groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Merge groups where a longer name extends a shorter one with a word boundary.

    E.g. \"Jetts\" + \"Jetts Monthly report\" merge; \"Li\" does NOT merge into \"Lift\".
    """
    sorted_names = sorted(groups.keys(), key=lambda n: len(n))
    merge_map: dict[str, str] = {}

    for i, short in enumerate(sorted_names):
        if len(short) < 4:
            continue
        short_lower = short.lower()
        for long in sorted_names[i + 1:]:
            long_lower = long.lower()
            if long_lower.startswith(short_lower + " "):
                merge_map[long] = short

    if not merge_map:
        return groups

    merged: dict[str, list[dict]] = defaultdict(list)
    for name, issues in groups.items():
        canonical = merge_map.get(name, name)
        merged[canonical].extend(issues)

    return dict(sorted(merged.items()))


def group_issues_by_client(
    issues: list[dict],
    project_key: str | None = None,
) -> dict[str, list[dict]]:
    extraction = "title_prefix"
    pk = project_key or ""
    if not pk and issues:
        key = issues[0].get("key", "")
        if "-" in key:
            pk = key.split("-", 1)[0].upper()
    for proj in config.PROJECTS:
        if proj["key"].upper() == pk.upper():
            extraction = proj.get("client_extraction", "title_prefix")
            break

    groups: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        summary = issue.get("fields", {}).get("summary", "")
        client = extract_client_name(summary, extraction, pk)
        groups[client].append(issue)
    return _normalize_client_groups(dict(groups))


# ── Smart deployment input parser ────────────────────────────────────

_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_TIME_12H_RE = re.compile(r"(\d{1,2})[\s:](\d{2})\s*(AM|PM)\s*(IST|UTC|EST|CST|PST)?", re.IGNORECASE)
_TIME_24H_RE = re.compile(r"(\d{1,2}):(\d{2})(?:\s*(IST|UTC|EST|CST|PST))?")
_DATE_SLASH_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
_DATE_DASH_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_DATE_NAMED_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)
_CLIENT_STRIP_RE = re.compile(r"[\s=:|,\-]*(Deployment\s*ID)?[\s=:|,\-]*$", re.IGNORECASE)
_CLIENT_LINE_RE = re.compile(r"^[\s=:|,\-]*$")

_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_MONTH_LOOKUP = {m.lower(): i for i, m in enumerate(_MONTH_NAMES) if m}


@dataclass
class ParsedDeployment:
    client: str
    deployment_id: str
    deployment_date: str
    deployment_time: str
    matched_jira_client: str = ""
    ticket_keys: list[str] = field(default_factory=list)
    error: str = ""


def _parse_date(text: str) -> str | None:
    """Try to extract a date from text and return 'Month DD YYYY' or None."""
    m = _DATE_NAMED_RE.search(text)
    if m:
        return f"{m.group(1).capitalize()} {int(m.group(2)):02d} {m.group(3)}"

    m = _DATE_DASH_RE.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{_MONTH_NAMES[mo]} {d:02d} {y}"

    m = _DATE_SLASH_RE.search(text)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = c + 2000 if c < 100 else c
        if a > 12:
            day, month = a, b
        elif b > 12:
            day, month = b, a
        else:
            month, day = a, b
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{_MONTH_NAMES[month]} {day:02d} {year}"

    return None


def _parse_time(text: str) -> str | None:
    """Try to extract a time from text and return 'HH:MM AM/PM IST' or None."""
    m = _TIME_12H_RE.search(text)
    if m:
        h, mi, ampm = int(m.group(1)), m.group(2), m.group(3).upper()
        tz = m.group(4) or "IST"
        return f"{h}:{mi} {ampm} {tz.upper()}"

    m = _TIME_24H_RE.search(text)
    if m:
        h, mi = int(m.group(1)), m.group(2)
        tz = m.group(3) or "IST"
        ampm = "AM" if h < 12 else "PM"
        h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
        return f"{h12}:{mi} {ampm} {tz.upper()}"

    return None


def _is_only_date_or_time(text: str) -> bool:
    """Return True if the line is purely a date/time with no useful client name."""
    stripped = text.strip()
    if not stripped:
        return True
    if _UUID_RE.search(stripped):
        return True
    has_date = _parse_date(stripped) is not None
    has_time = _parse_time(stripped) is not None
    leftover = stripped
    for pat in [_DATE_SLASH_RE, _DATE_DASH_RE, _DATE_NAMED_RE, _TIME_12H_RE, _TIME_24H_RE]:
        leftover = pat.sub("", leftover)
    leftover = re.sub(r"[\s,;/\-:]+", "", leftover)
    if (has_date or has_time) and len(leftover) <= 3:
        return True
    return False


def parse_deployment_input(raw_text: str) -> list[ParsedDeployment]:
    """Parse rough/natural multi-line deployment input.

    Looks both BACKWARD and FORWARD from each UUID line to find:
    - Client name (on the same line before UUID, or on preceding lines)
    - Date and time (on the same line, or on surrounding lines)
    """
    lines = [ln.strip() for ln in raw_text.strip().splitlines()]

    uuid_indices: list[int] = []
    for i, line in enumerate(lines):
        if _UUID_RE.search(line):
            uuid_indices.append(i)

    results: list[ParsedDeployment] = []

    for pos, ui in enumerate(uuid_indices):
        line = lines[ui]
        uuid_match = _UUID_RE.search(line)
        if not uuid_match:
            continue
        deployment_id = uuid_match.group()

        prev_boundary = (uuid_indices[pos - 1] + 1) if pos > 0 else 0
        next_boundary = uuid_indices[pos + 1] if (pos + 1) < len(uuid_indices) else len(lines)

        # -- Client name: same line before UUID, else look backward
        client_raw = line[:uuid_match.start()]
        client_name = _CLIENT_STRIP_RE.sub("", client_raw).strip()

        if not client_name:
            for j in range(ui - 1, prev_boundary - 1, -1):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                if _is_only_date_or_time(candidate):
                    continue
                cleaned = re.sub(r"[\s:,=\-|]+$", "", candidate).strip()
                if cleaned:
                    client_name = cleaned
                    break

        # -- Date & time: same line, then BACKWARD, then limited forward
        after_uuid = line[uuid_match.end():]
        date_str = _parse_date(line)
        time_str = _parse_time(after_uuid) or _parse_time(line)

        for j in range(ui - 1, prev_boundary - 1, -1):
            if date_str and time_str:
                break
            prev = lines[j].strip()
            if not prev:
                continue
            if not date_str:
                date_str = _parse_date(prev)
            if not time_str:
                time_str = _parse_time(prev)

        # Forward scan: skip blanks, but stop at lines that look like a
        # client name (non-date/time text) to avoid leaking into the next block.
        for j in range(ui + 1, next_boundary):
            if date_str and time_str:
                break
            nxt = lines[j].strip()
            if not nxt:
                continue
            if not _is_only_date_or_time(nxt):
                break
            if not date_str:
                date_str = _parse_date(nxt)
            if not time_str:
                time_str = _parse_time(nxt)

        results.append(ParsedDeployment(
            client=client_name or "???",
            deployment_id=deployment_id,
            deployment_date=date_str or "",
            deployment_time=time_str or "",
        ))

    return results


def _normalize_client_key(name: str) -> str:
    """Collapse spaces/punctuation for fuzzy client comparison (BD Gyms == BDGyms)."""
    return re.sub(r"[\s\-_]+", "", name.strip().lower())


def fuzzy_match_client(parsed_name: str, jira_clients: list[str]) -> str | None:
    norm = parsed_name.strip().lower()
    if not norm:
        return None
    norm_key = _normalize_client_key(parsed_name)

    # Exact match (case)
    for jc in jira_clients:
        if jc.strip().lower() == norm:
            return jc

    # Normalized exact match (BD Gyms -> BDGyms)
    for jc in jira_clients:
        if _normalize_client_key(jc) == norm_key:
            return jc

    # Prefix typo match (jets -> Jetts) on normalized keys
    min_prefix = min(3, len(norm_key))
    if min_prefix >= 3:
        for jc in jira_clients:
            jc_key = _normalize_client_key(jc)
            if (
                jc_key[:min_prefix] == norm_key[:min_prefix]
                and abs(len(jc_key) - len(norm_key)) <= 2
            ):
                return jc
    return None


def match_deployments_to_tickets(
    parsed: list[ParsedDeployment],
    grouped_issues: dict[str, list[dict]],
) -> list[ParsedDeployment]:
    jira_clients = list(grouped_issues.keys())
    for p in parsed:
        matched = fuzzy_match_client(p.client, jira_clients)
        if matched:
            p.matched_jira_client = matched
            p.ticket_keys = [iss["key"] for iss in grouped_issues[matched]]
        elif p.client and p.client != "???":
            p.error = f"No matching client in release (tried: '{p.client}')"
    return parsed


# ── Add deployment comment ──────────────────────────────────────────

def build_deployment_comment_adf(deployment_date: str, deployment_time: str, deployment_id: str) -> dict:
    import template_engine

    env = config.DEPLOY_ENVIRONMENT
    try:
        rendered = template_engine.render_template(
            "deployment_comment.j2",
            environment=env,
            deployment_date=deployment_date,
            deployment_time=deployment_time,
            deployment_id=deployment_id,
        )
    except Exception:
        _logger.debug("deployment_comment.j2 render failed, using built-in ADF", exc_info=True)
        rendered = (
            f"The change has been deployed to {env} on {deployment_date} at {deployment_time}.\n\n"
            f"and changes are reflecting the {env} and verified\n\n"
            f"Deployment ID: {deployment_id}"
        )

    content: list[dict] = []
    for block in rendered.strip().split("\n\n"):
        text = block.strip()
        if not text:
            continue
        if text.startswith("Deployment ID:"):
            content.append({
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Deployment ID: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": text.split(":", 1)[1].strip()},
                ],
            })
        else:
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            })

    if not content:
        content = [{
            "type": "paragraph",
            "content": [{"type": "text", "text": f"Deployed to {env}."}],
        }]

    return {"type": "doc", "version": 1, "content": content}


def add_deployment_comment(
    issue_key: str,
    deployment_date: str,
    deployment_time: str,
    deployment_id: str,
) -> dict | None:
    body = build_deployment_comment_adf(deployment_date, deployment_time, deployment_id)
    return _post(f"/issue/{issue_key}/comment", {"body": body})


def build_schedule_window_comment_adf(window: dict[str, str]) -> dict:
    """ADF comment that spells out the agreed window with timezone labels.

    Jira's Planned start / Planned end fields render in each viewer's profile
    timezone. Spelling IST (and the Central equivalent) in a comment stops the
    ticket being closed early when those fields look like the previous night.
    """
    title = (window.get("comment_title") or "Deployment window").strip()
    body = (window.get("comment_body") or window.get("sentence") or "").strip()
    paragraphs: list[dict] = [
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": title, "marks": [{"type": "strong"}]},
            ],
        },
    ]
    for block in body.split("\n\n"):
        text = block.strip()
        if not text:
            continue
        paragraphs.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        })
    if len(paragraphs) == 1:
        paragraphs.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": "See Planned start / Planned end."}],
        })
    return {"type": "doc", "version": 1, "content": paragraphs}


def add_schedule_window_comment(issue_key: str, window: dict[str, str]) -> dict | None:
    """Post the dual-timezone deployment window clarification on a TCKT."""
    if not (window.get("comment_body") or window.get("sentence")):
        return None
    body = build_schedule_window_comment_adf(window)
    return _post(f"/issue/{issue_key}/comment", {"body": body})


# ── Check for existing deployment comment ────────────────────────────

class CommentCheckError(Exception):
    """Raised when we cannot reliably check for existing deployment comments."""


def _comment_plain_text(body: dict | str) -> str:
    """Extract lowercase plain text from an ADF or wiki comment body."""
    if isinstance(body, str):
        return body.lower()
    parts: list[str] = []
    for block in body.get("content", []):
        for item in block.get("content", []):
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
    return " ".join(parts).lower()


def is_verified_deployment_comment(body: dict | str) -> bool:
    """True only for a completed deployment comment matching our template."""
    text = _comment_plain_text(body)
    if "the change has been deployed to" not in text:
        return False
    if "deployment id:" not in text:
        return False
    if "changes are reflecting" not in text and "changes are reflected" not in text:
        return False

    blocked_phrases = (
        "on hold",
        "on-hold",
        "pending deploy",
        "not deployed",
        "will be deployed",
        "to be deployed",
        "awaiting deploy",
        "deployment pending",
    )
    return not any(phrase in text for phrase in blocked_phrases)


def _fetch_comments_page(
    issue_key: str,
    *,
    start_at: int,
    max_results: int,
) -> dict:
    return _get(
        f"/issue/{issue_key}/comment",
        params={"startAt": start_at, "maxResults": max_results},
    )


def get_issue_comments(issue_key: str) -> list[dict]:
    """Return all comments for an issue (paginated)."""
    return _iter_all_comments(issue_key)


def _iter_all_comments(issue_key: str) -> list[dict]:
    """Fetch all comments for an issue, paginating if necessary."""
    start_at = 0
    page_size = 100
    all_comments: list[dict] = []
    while True:
        data = _fetch_comments_page(
            issue_key, start_at=start_at, max_results=page_size,
        )
        comments = data.get("comments", [])
        all_comments.extend(comments)
        total = data.get("total", len(all_comments))
        if len(all_comments) >= total or not comments:
            break
        start_at += len(comments)
    return all_comments


def has_deployment_comment(issue_key: str) -> bool:
    """Return True if the issue already has a verified deployment comment."""
    return get_verified_deployment_comment_id(issue_key) is not None


def get_verified_deployment_comment_id(issue_key: str) -> str | None:
    """Return the comment ID of a verified deployment comment, or None.

    Checks the most recent ``_RECENT_COMMENT_WINDOW`` comments first (typical
    deploy markers are newest). Falls back to a full comment scan when the
    marker is older than the window so correctness is preserved.
    """
    try:
        probe = _fetch_comments_page(issue_key, start_at=0, max_results=1)
        total = int(probe.get("total", 0) or len(probe.get("comments", [])))
        if total <= 0:
            return None

        def _find(comments: list[dict]) -> str | None:
            for comment in reversed(comments):
                if is_verified_deployment_comment(comment.get("body", {})):
                    return comment.get("id")
            return None

        window = min(_RECENT_COMMENT_WINDOW, total)
        start = max(0, total - window)
        if start == 0 and total == 1:
            return _find(list(probe.get("comments", [])))

        recent = _fetch_comments_page(
            issue_key, start_at=start, max_results=window,
        )
        found = _find(list(recent.get("comments", [])))
        if found is not None or start == 0:
            return found

        # Marker not among recent comments — full scan for correctness.
        return _find(_iter_all_comments(issue_key))
    except CommentCheckError:
        raise
    except Exception as exc:
        raise CommentCheckError(
            f"Cannot check comments for {issue_key}: {exc}"
        ) from exc


def check_deployment_comments(
    issue_keys: Iterable[str],
    *,
    max_workers: int | None = None,
) -> tuple[dict[str, bool], dict[str, Exception]]:
    """Read-only batch duplicate-marker check with optional bounded concurrency.

    Returns ``(already_by_key, errors_by_key)``. Order of ``issue_keys`` is
    preserved for callers that rebuild logs sequentially. Never writes.
    """
    keys = [str(k) for k in issue_keys]
    already: dict[str, bool] = {}
    errors: dict[str, Exception] = {}

    def _one(key: str) -> tuple[str, bool | None, Exception | None]:
        try:
            return key, has_deployment_comment(key), None
        except CommentCheckError as exc:
            return key, None, exc
        except Exception as exc:  # noqa: BLE001 — surface as check error
            return key, None, CommentCheckError(str(exc))

    for key, value, err in readonly_map(_one, keys, max_workers=max_workers):
        if err is not None:
            errors[key] = err
        else:
            already[key] = bool(value)
    return already, errors


# ── Transition to Done ──────────────────────────────────────────────

def get_transitions(issue_key: str) -> list[dict]:
    return _get(f"/issue/{issue_key}/transitions").get("transitions", [])


def find_done_transition(issue_key: str) -> str | None:
    for t in get_transitions(issue_key):
        cat = t.get("to", {}).get("statusCategory", {}).get("key", "")
        if cat == "done":
            return t["id"]
    return None


def add_label(issue_key: str, label: str) -> None:
    """Add a label to an issue without replacing existing labels."""
    _put(f"/issue/{issue_key}", {"update": {"labels": [{"add": label}]}})


def transition_to_done(issue_key: str) -> bool:
    tid = find_done_transition(issue_key)
    if tid is None:
        return False
    return transition_issue(issue_key, tid)


def transition_issue(issue_key: str, transition_id: str) -> bool:
    path = f"/issue/{issue_key}/transitions"
    _block_mock_writes("POST", path)
    url = f"{config.JIRA_API_URL}{path}"
    for attempt in range(_MAX_RETRIES + 1):
        _maybe_inter_call_pause()
        try:
            resp = requests.post(
                url, headers=_headers(), auth=_auth(),
                json={"transition": {"id": transition_id}},
                timeout=_DEFAULT_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            _handle_connection_error(exc, f"/issue/{issue_key}/transitions")
        if _should_retry(resp, attempt):
            continue
        if resp.status_code == 204:
            return True
        _friendly_raise(resp)
    return False


def find_transition_by_name(issue_key: str, target_name: str) -> str | None:
    """Find a transition whose target status matches *target_name* (case-insensitive)."""
    target_lower = target_name.strip().lower()
    for t in get_transitions(issue_key):
        if t.get("to", {}).get("name", "").strip().lower() == target_lower:
            return t["id"]
    return None


def transition_to_status(issue_key: str, status_name: str) -> tuple[bool, str | None]:
    """Transition *issue_key* to *status_name*; return (success, error_message)."""
    tid = find_transition_by_name(issue_key, status_name)
    if not tid:
        return False, f"No transition to '{status_name}' available for {issue_key}"
    if transition_issue(issue_key, tid):
        return True, None
    return False, f"Transition to '{status_name}' failed for {issue_key}"


def get_current_user() -> dict[str, Any]:
    """Return the Jira user for the configured API credentials."""
    return _get("/myself")


def set_assignee(issue_key: str, account_id: str) -> bool:
    """Set issue assignee by Atlassian accountId."""
    aid = (account_id or "").strip()
    if not aid:
        return False
    edit_issue(issue_key, {"assignee": {"accountId": aid}})
    return True


def get_issue_status_name(issue_key: str) -> str:
    """Return current workflow status name for an issue."""
    issue = get_issue(issue_key)
    status = (issue.get("fields") or {}).get("status") or {}
    return str(status.get("name") or "")


def create_issue_link(
    outward_key: str,
    inward_key: str,
    link_type_name: str,
) -> dict[str, Any]:
    """Link two issues — SHIPIT outward ``connects to`` release ticket inward (17036 pattern)."""
    path = "/issueLink"
    _block_mock_writes("POST", path)
    body = {
        "type": {"name": link_type_name},
        "inwardIssue": {"key": inward_key.strip().upper()},
        "outwardIssue": {"key": outward_key.strip().upper()},
    }
    return _post(path, body)


def add_plain_comment(issue_key: str, text: str) -> dict[str, Any]:
    """Post a simple ADF paragraph comment on an issue."""
    from adf_builder import doc, paragraph, text as adf_text

    body = doc(paragraph(adf_text((text or "").strip())))
    return _post(f"/issue/{issue_key}/comment", {"body": body})


def add_adf_comment(issue_key: str, body: dict[str, Any]) -> dict[str, Any]:
    """Post a pre-built ADF document as an issue comment."""
    return _post(f"/issue/{issue_key}/comment", {"body": body})


def delete_issue(issue_key: str) -> bool:
    """Delete a Jira issue (requires delete permission on the project)."""
    return _delete(f"/issue/{issue_key}")


def dispose_test_shipit_ticket(
    issue_key: str,
    *,
    comment: str = (
        "Test demo ticket — Release Orchestrator validation only. "
        "DO NOT DEPLOY. Safe to cancel and delete."
    ),
    cancel_status_names: tuple[str, ...] = ("Canceled", "Cancelled", "Declined"),
) -> dict[str, Any]:
    """Comment, cancel, and best-effort delete a TEST / demo SHIPIT ticket."""
    key = (issue_key or "").strip().upper()
    if not key:
        return {"status": "error", "error": "issue_key is required"}

    issue = get_issue(key)
    summary = (issue.get("fields") or {}).get("summary") or ""
    if not is_test_shipit_summary(summary):
        return {
            "status": "blocked",
            "key": key,
            "error": (
                f"{key} does not look like a TEST/demo SHIPIT "
                f"(summary must include TEST SHIPIT or DO NOT DEPLOY)."
            ),
        }

    comment_result: dict[str, Any] | None = None
    try:
        comment_result = add_plain_comment(key, comment)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "key": key, "error": f"Comment failed: {exc}"}

    canceled = False
    transition_id: str | None = None
    for name in cancel_status_names:
        transition_id = find_transition_by_name(key, name)
        if transition_id:
            canceled = transition_issue(key, transition_id)
            if canceled:
                break

    deleted = False
    delete_error = ""
    if canceled:
        try:
            deleted = delete_issue(key)
        except Exception as exc:  # noqa: BLE001
            delete_error = str(exc)

    status = "deleted" if deleted else ("canceled" if canceled else "commented")
    return {
        "status": status,
        "key": key,
        "summary": summary,
        "comment_id": (comment_result or {}).get("id"),
        "canceled": canceled,
        "transition_id": transition_id,
        "deleted": deleted,
        "delete_error": delete_error or None,
        "message": (
            f"{key} deleted after cancel comment."
            if deleted
            else (
                f"{key} canceled with closing comment (delete not permitted or failed)."
                if canceled
                else f"Comment added on {key}; could not find cancel transition."
            )
        ),
    }


# ── Undo helpers ─────────────────────────────────────────────────────

def get_latest_deployment_comment_id(issue_key: str) -> str | None:
    """Return the comment ID of the most recent verified deployment comment, or None."""
    try:
        return get_verified_deployment_comment_id(issue_key)
    except CommentCheckError:
        _logger.debug("Failed to fetch comments for %s", issue_key, exc_info=True)
        return None


def delete_comment(issue_key: str, comment_id: str) -> bool:
    return _delete(f"/issue/{issue_key}/comment/{comment_id}")


# ── Issue count (lightweight) ────────────────────────────────────────

def get_issue_count_for_version(project_key: str, version_id: str) -> int:
    """Return the total number of issues in a version without fetching them."""
    jql = build_scoped_version_jql(project_key, version_id)
    data = _post("/search/jql", {"jql": jql, "maxResults": 0, "fields": ["summary"]})
    return data.get("total", 0)


# ── Release version ──────────────────────────────────────────────────

def release_version(version_id: str) -> bool:
    """Mark a Jira version as released with today's date."""
    body = {
        "released": True,
        "releaseDate": datetime.now().strftime("%Y-%m-%d"),
    }
    _put(f"/version/{version_id}", body)
    clear_version_cache()
    return True


# ── Ticket info extraction ────────────────────────────────────────

def _is_multi_client_project(ticket_key: str) -> bool:
    """Check if the ticket belongs to a project marked as multi_client."""
    prefix = ticket_key.split("-")[0].upper() if "-" in ticket_key else ""
    for proj in config.PROJECTS:
        if proj["key"].upper() == prefix:
            return proj.get("multi_client", False)
    return False


def extract_ticket_info(summary: str, ticket_key: str) -> dict:
    """Extract type, client, report, and description from a ticket summary."""
    prefix = ticket_key.split("-")[0].upper() if "-" in ticket_key else ""
    extraction = "title_prefix"
    for proj in config.PROJECTS:
        if proj["key"].upper() == prefix:
            extraction = proj.get("client_extraction", "title_prefix")
            break

    is_custom = _is_multi_client_project(ticket_key)
    ticket_type = "Custom" if is_custom else "Analyze"
    refine_summary = summary

    if is_custom:
        client = extract_client_name(summary, extraction, prefix)
        remainder = _CLIENT_SEPARATOR.split(summary, maxsplit=1)
        if len(remainder) > 1:
            after_client = remainder[1].strip()
            sub = _CLIENT_SEPARATOR.split(after_client, maxsplit=1)
            report = sub[0].strip() if sub else after_client
            description = sub[1].strip() if len(sub) > 1 else report
        else:
            report = summary
            description = summary
        # Prefer a known client prefix when the title embeds the report in the
        # client segment (e.g. "FWBC Customize Pulse Report - Minor …").
        try:
            from generators.release_notes_quality import match_known_client

            matched = match_known_client(client)
            if matched:
                known_client, rest = matched
                client = known_client
                if rest:
                    # "FWBC Customize Pulse Report - Minor Reconfiguration Needed"
                    # → client=FWBC, report=Customize Pulse Report, description=Minor…
                    if not report or report == summary:
                        report = rest
                        description = remainder[1].strip() if len(remainder) > 1 else rest
                    elif rest.lower() not in report.lower():
                        if not description or description.lower() == report.lower():
                            description = report
                        report = rest
        except ImportError:
            # Quality helpers are optional; the raw split above is still usable.
            _logger.debug("release_notes_quality unavailable for %s", ticket_key)
    else:
        client = "Standard"
        parts = _CLIENT_SEPARATOR.split(summary, maxsplit=1)
        report = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else report
        # Strip a leading "Analyze"/"Standard" label so dashboards don't become
        # "Analyze- Analyze".
        report = re.sub(
            r"^(?:analyze|standard(?:\s*\(analyze\))?|an)\s*$",
            "",
            report,
            flags=re.IGNORECASE,
        ).strip()
        if not report and description:
            sub = _CLIENT_SEPARATOR.split(description, maxsplit=1)
            report = sub[0].strip()
            description = sub[1].strip() if len(sub) > 1 else description

    if is_custom and report and description and description.lower() != report.lower():
        refine_summary = f"{report} - {description}"
    elif is_custom and len(_CLIENT_SEPARATOR.split(summary, maxsplit=1)) > 1:
        refine_summary = _CLIENT_SEPARATOR.split(summary, maxsplit=1)[1].strip()

    try:
        from generators.ticket_title_parse import refine_ticket_title_fields

        refined = refine_ticket_title_fields(
            refine_summary,
            report=report,
            description=description,
        )
        report = refined.get("report") or report
        description = refined.get("description") or description
        asset_type = refined.get("asset_type") or ""
        display_report = refined.get("display_report") or report
    except ImportError:
        asset_type = ""
        display_report = report

    payload = {
        "type": ticket_type,
        "client": client,
        "report": report,
        "description": description,
    }
    if asset_type:
        payload["asset_type"] = asset_type
    if display_report and display_report != report:
        payload["display_report"] = display_report
    elif display_report:
        payload["display_report"] = display_report
    return payload


# ── Group by assignee ────────────────────────────────────────────

def group_issues_by_assignee(issues: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        assignee = issue.get("fields", {}).get("assignee")
        name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
        groups[name].append(issue)
    return dict(sorted(groups.items()))


# ── Issue creation / editing ─────────────────────────────────────

_issue_type_cache: dict[str, dict[str, str]] = {}


def resolve_issue_type_id(project_key: str, type_name: str) -> str:
    """Resolve a Jira issue type name to its ID for a project (cached)."""
    cache_key = project_key.upper()
    if cache_key not in _issue_type_cache:
        data = _get(
            "/issue/createmeta",
            params={
                "projectKeys": project_key,
                "expand": "projects.issuetypes",
            },
        )
        type_map: dict[str, str] = {}
        for proj in data.get("projects", []):
            for issue_type in proj.get("issuetypes", []):
                name = issue_type.get("name", "")
                issue_id = issue_type.get("id")
                if name and issue_id is not None:
                    type_map[name.lower()] = str(issue_id)
        if not type_map:
            raise JiraApiError(
                f"Could not load issue types for project {project_key}. "
                "Check project key and permissions.",
            )
        _issue_type_cache[cache_key] = type_map

    resolved = _issue_type_cache[cache_key].get(type_name.strip().lower())
    if resolved:
        return resolved

    for fallback in ("task", "story", "bug"):
        resolved = _issue_type_cache[cache_key].get(fallback)
        if resolved:
            return resolved

    raise JiraApiError(
        f"Issue type '{type_name}' is not available in project {project_key}.",
    )


_component_cache: dict[str, dict[str, str]] = {}


def reset_client() -> None:
    """Clear Jira client caches after credential or workspace changes."""
    _http.reset_client()
    _issue_type_cache.clear()
    _component_cache.clear()


def resolve_component(project_key: str, component_name: str) -> dict | None:
    """Resolve a Jira component label to ``{"name": ...}`` for issue creation."""
    label = (component_name or "").strip()
    if not label or label.lower() == "general":
        return None

    cache_key = project_key.upper()
    if cache_key not in _component_cache:
        data = _get(f"/project/{project_key}/components")
        mapping: dict[str, str] = {}
        for item in data or []:
            name = (item.get("name") or "").strip()
            if name:
                mapping[name.lower()] = name
        _component_cache[cache_key] = mapping

    exact = _component_cache[cache_key].get(label.lower())
    if exact:
        return {"name": exact}

    for key, name in _component_cache[cache_key].items():
        if label.lower() in key or key in label.lower():
            return {"name": name}

    return None


_field_option_cache: dict[str, dict[str, str]] = {}


def _field_meta_from_createmeta(data: dict, field_id: str) -> dict:
    """Extract one field's createmeta from dict- or list-shaped Jira responses."""
    if not isinstance(data, dict):
        return {}

    fields = data.get("fields")
    if isinstance(fields, dict):
        meta = fields.get(field_id)
        return meta if isinstance(meta, dict) else {}

    if isinstance(fields, list):
        for item in fields:
            if not isinstance(item, dict):
                continue
            fid = item.get("fieldId") or item.get("key") or item.get("id")
            if str(fid) == str(field_id):
                return item
        return {}

    results = data.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            fid = item.get("fieldId") or item.get("key") or item.get("id")
            if str(fid) == str(field_id):
                return item
    return {}


def resolve_custom_field_option(
    project_key: str,
    issue_type_id: str,
    field_id: str,
    option_label: str,
) -> dict | None:
    """Resolve a Jira select-list option label to ``{id: ...}`` via createmeta."""
    if not field_id or not option_label or not issue_type_id:
        return None

    cache_key = f"{project_key}:{issue_type_id}:{field_id}"
    if cache_key not in _field_option_cache:
        data = _get(
            f"/issue/createmeta/{project_key}/issuetypes/{issue_type_id}",
            params={"fieldIds": field_id},
        )
        field_meta = _field_meta_from_createmeta(data, field_id)
        allowed = field_meta.get("allowedValues") or []
        mapping: dict[str, str] = {}
        for item in allowed:
            if not isinstance(item, dict):
                continue
            name = (item.get("value") or item.get("name") or "").strip()
            opt_id = item.get("id")
            if name and opt_id is not None:
                mapping[name.lower()] = str(opt_id)
        _field_option_cache[cache_key] = mapping

    opt_id = _field_option_cache[cache_key].get(option_label.strip().lower())
    return {"id": opt_id} if opt_id else None


def create_issue(project_key: str, issue_type_id: str, summary: str, fields: dict) -> dict:
    body = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": {"id": issue_type_id},
            "summary": summary,
            **fields,
        }
    }
    return _post("/issue", body)


def edit_issue(issue_key: str, fields: dict) -> bool:
    _put(f"/issue/{issue_key}", {"fields": fields})
    return True


def remove_fix_version_from_issue(
    issue_key: str,
    version_id: str,
    issue: dict | None = None,
) -> bool:
    """Remove one fix version from an issue. Returns False if the version was not assigned."""
    fields = (issue or {}).get("fields", {})
    fix_versions = fields.get("fixVersions")
    if fix_versions is None:
        data = _get(f"/issue/{issue_key}", params={"fields": "fixVersions"})
        fix_versions = data.get("fields", {}).get("fixVersions", [])

    remaining = [
        {"id": v["id"]}
        for v in fix_versions
        if str(v.get("id")) != str(version_id)
    ]
    if len(remaining) == len(fix_versions):
        return False

    edit_issue(issue_key, {"fixVersions": remaining})
    return True


def remove_fix_version_from_issues(
    issue_keys: list[str],
    version_id: str,
    issues_by_key: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Remove a fix version from multiple issues. Returns success/skipped/error lists."""
    issues_by_key = issues_by_key or {}
    success: list[str] = []
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    for key in issue_keys:
        try:
            removed = remove_fix_version_from_issue(
                key,
                version_id,
                issue=issues_by_key.get(key),
            )
            if removed:
                success.append(key)
            else:
                skipped.append(key)
        except JiraApiError as exc:
            errors.append((key, str(exc)))
        except Exception as exc:
            errors.append((key, str(exc)))

    return {"success": success, "skipped": skipped, "errors": errors}


def _sd_get(path: str, params: dict | None = None) -> Any:
    """GET against the Jira Service Desk API (not /rest/api/3)."""
    url = f"{config.JIRA_SD_API_URL}{path}"
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url, headers=_headers(), auth=_auth(), params=params or {}, timeout=_DEFAULT_TIMEOUT
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            _handle_connection_error(exc, path)
        if _should_retry(resp, attempt):
            continue
        _friendly_raise(resp)
        return resp.json()


def _sd_post(path: str, json_body: dict) -> Any:
    """POST against the Jira Service Desk API (not /rest/api/3)."""
    _block_mock_writes("POST", path)
    url = f"{config.JIRA_SD_API_URL}{path}"
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url, headers=_headers(), auth=_auth(), json=json_body, timeout=_DEFAULT_TIMEOUT
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            _handle_connection_error(exc, path)
        if _should_retry(resp, attempt):
            continue
        _friendly_raise(resp)
        return resp.json() if resp.content else {}


def list_service_desks() -> list[dict[str, Any]]:
    """Return all service desks visible to the authenticated user."""
    data = _sd_get("/servicedesk")
    values = data.get("values", []) if isinstance(data, dict) else []
    return [v for v in values if isinstance(v, dict)]


def list_request_types(service_desk_id: str) -> list[dict[str, Any]]:
    """Return request types for a service desk."""
    if not service_desk_id:
        return []
    data = _sd_get(f"/servicedesk/{service_desk_id}/requesttype")
    values = data.get("values", []) if isinstance(data, dict) else []
    return [v for v in values if isinstance(v, dict)]


def find_service_desk_for_project(project_key: str) -> dict[str, Any] | None:
    """Find a service desk whose projectKey matches (case-insensitive)."""
    key = (project_key or "").strip().upper()
    if not key:
        return None
    for desk in list_service_desks():
        if str(desk.get("projectKey", "")).upper() == key:
            return desk
    return None


# ── Service Desk: create request (sets Request Type at create time) ─

def get_issue_request_type_id(issue_key: str) -> str | None:
    """Return the Service Desk request type ID for an existing issue, if any."""
    if not issue_key:
        return None
    try:
        data = _sd_get(f"/request/{issue_key}")
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    rt = data.get("requestType")
    if isinstance(rt, dict) and rt.get("id") is not None:
        return str(rt["id"])
    rt_id = data.get("requestTypeId")
    return str(rt_id) if rt_id is not None else None


def _normalize_team_value(value: Any) -> Any:
    """Normalize Jira Team field values for REST edit/create.

    abcfinancial's ``atlassian-team`` field rejects ``{\"id\": \"...\"}`` on edit
    (``Team id 'JsonData{data={id=...}}' is not valid``). A plain team UUID string
    is accepted and is what editmeta returns after a successful set.
    """
    if value is None or value == "":
        return value
    if isinstance(value, dict):
        team_id = value.get("id")
        return str(team_id) if team_id else value
    return str(value)


# Field routing is config-driven (see workspace.yaml ``create_mode``):
#   summary_only — Service Desk create sends summary only; everything else post-create REST edit
#   full_form    — legacy TCKT: form fields on create + post-create for rich text / approvers


def _service_desk_create_mode() -> str:
    return (config.SERVICE_DESK_CREATE_MODE or "full_form").strip()


def _post_create_logical_fields() -> tuple[str, ...]:
    if _service_desk_create_mode() == "summary_only":
        return (
            "approver_groups",
            "team",
            "change_type",
            "change_risk",
            "impact",
            "urgency",
            "planned_start",
            "planned_end",
            "affected_services",
            "assignment_group",
            "unplanned",
            "reason_for_change",
        )
    return (
        "approvers",
        "approver_groups",
        "team",
        "change_type",
    )


def _rich_text_logical_fields() -> tuple[str, ...]:
    if _service_desk_create_mode() == "summary_only":
        return (
            "implementation_steps",
            "verification_steps",
            "rollback_steps",
            "business_impact",
            "communication_plan",
        )
    return (
        "implementation_plan",
        "test_plan",
        "backout_plan",
        "business_impact",
    )


def _reasserted_logical_fields() -> tuple[str, ...]:
    if _service_desk_create_mode() == "summary_only":
        return ()
    return (
        "assignment_group",
        "affects_pf",
        "outage_required",
    )


def _all_supplemental_logical_fields() -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for name in (
        *_post_create_logical_fields(),
        *_rich_text_logical_fields(),
        *_reasserted_logical_fields(),
    ):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return tuple(out)


def resolve_assignment_group_value(defaults: dict[str, Any] | None = None) -> dict[str, str] | None:
    """Return assignment group payload — group name on SHIPIT, option id on legacy TCKT."""
    src = defaults if defaults is not None else config.TCKT_DEFAULTS
    name = str(src.get("assignment_group_name") or "").strip()
    if name:
        return {"name": name}
    ag = src.get("assignment_group") or {}
    if isinstance(ag, dict):
        if ag.get("name"):
            return {"name": str(ag["name"])}
        if ag.get("id"):
            return {"id": str(ag["id"])}
    return None


def _build_supplemental_tckt_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Fields applied by a REST edit after the Service Desk create.

    Covers what the request form cannot take at all (approvers, team, change type,
    priority) plus the rich-text fields, which reach the form as plain text and get
    their ADF back here.
    """
    cf = config.TCKT_FIELDS
    edit: dict[str, Any] = {}

    if fields.get("priority") is not None:
        edit["priority"] = fields["priority"]

    description = fields.get("description")
    if isinstance(description, dict) and description.get("type") == "doc":
        edit["description"] = description

    for logical in _all_supplemental_logical_fields():
        field_id = config.service_desk_field(logical)
        if not field_id:
            continue
        value = fields.get(field_id)
        if value is None:
            continue
        if logical == "team":
            value = _normalize_team_value(value)
        edit[field_id] = value

    return edit


def _supplemental_edit_batches(fields: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Split post-create fields so one bad value cannot block the others."""
    cf = config.TCKT_FIELDS
    if _service_desk_create_mode() == "summary_only":
        plan_keys = {
            cf[k]
            for k in (
                "implementation_steps",
                "verification_steps",
                "rollback_steps",
                "business_impact",
            )
            if cf.get(k)
        }
        comm_keys = {
            cf[k] for k in ("communication_plan",) if cf.get(k)
        }
        reason_key = cf.get("reason_for_change") or ""
        metadata_keys = {
            cf[k]
            for k in (
                "approver_groups",
                "change_type",
                "change_risk",
                "impact",
                "urgency",
                "planned_start",
                "planned_end",
                "affected_services",
                "team",
                "unplanned",
            )
            if cf.get(k)
        }
        assignment_key = cf.get("assignment_group") or ""
        batches: list[tuple[str, dict[str, Any]]] = []
        desc = {k: v for k, v in fields.items() if k == "description"}
        if desc:
            batches.append(("description ADF", desc))
        plans = {k: v for k, v in fields.items() if k in plan_keys}
        if plans:
            batches.append(("implementation / verification / rollback / business impact", plans))
        comm_reason: dict[str, Any] = {}
        comm_reason.update({k: v for k, v in fields.items() if k in comm_keys})
        if reason_key and reason_key in fields:
            comm_reason[reason_key] = fields[reason_key]
        if comm_reason:
            batches.append(("communication plan / reason for change", comm_reason))
        metadata = {k: v for k, v in fields.items() if k in metadata_keys}
        if metadata:
            batches.append(("approvals / schedule / classification", metadata))
        if assignment_key and assignment_key in fields:
            batches.append(("assignment group", {assignment_key: fields[assignment_key]}))
        if "priority" in fields:
            batches.append(("priority", {"priority": fields["priority"]}))
        other = {
            k: v
            for k, v in fields.items()
            if k not in desc | plans | comm_reason | metadata
            and k != "priority"
        }
        if other:
            batches.append(("other supplemental fields", other))
        return batches

    assignment_keys = {
        cf[k] for k in ("approvers", "approver_groups", "change_type") if cf.get(k)
    }
    team_key = cf.get("team") or ""
    reassert_keys = {cf[k] for k in _reasserted_logical_fields() if cf.get(k)}
    rich_keys = {cf[k] for k in _rich_text_logical_fields() if cf.get(k)} | {"description"}

    assignment = {k: v for k, v in fields.items() if k in assignment_keys}
    team = {k: v for k, v in fields.items() if team_key and k == team_key}
    reassert = {k: v for k, v in fields.items() if k in reassert_keys}
    rich = {k: v for k, v in fields.items() if k in rich_keys}
    other = {
        k: v
        for k, v in fields.items()
        if k not in assignment_keys | reassert_keys | rich_keys
        and k != team_key
        and k != "priority"
    }
    priority = {"priority": fields["priority"]} if "priority" in fields else {}

    batches: list[tuple[str, dict[str, Any]]] = []
    if assignment:
        batches.append(("approvers / groups / change type", assignment))
    if team:
        batches.append(("team", team))
    if reassert:
        batches.append(("assignment group / affects PF / outage", reassert))
    if priority:
        batches.append(("priority", priority))
    if rich:
        batches.append(("plans / description ADF", rich))
    if other:
        batches.append(("other supplemental fields", other))
    return batches


def apply_supplemental_tckt_fields(
    issue_key: str,
    fields: dict[str, Any],
) -> list[str]:
    """Apply post-create fields in isolated batches. Returns per-batch warnings."""
    warnings: list[str] = []
    for label, batch in _supplemental_edit_batches(fields):
        if not batch:
            continue
        try:
            edit_issue(issue_key, batch)
        except Exception as exc:
            _logger.warning(
                "Post-create %s update failed for %s: %s", label, issue_key, exc,
            )
            warnings.append(f"{label}: {exc}")
    return warnings


def _build_service_desk_request_field_values(
    summary: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Map Jira REST create fields to Service Desk ``requestFieldValues``."""
    from adf_builder import adf_to_plain_text

    if _service_desk_create_mode() == "summary_only":
        return {"summary": summary}

    cf = config.TCKT_FIELDS
    rest_only = {config.service_desk_field(k) for k in _post_create_logical_fields()}
    rest_only.add("priority")

    out: dict[str, Any] = {"summary": summary}

    for field_id, value in fields.items():
        if field_id in rest_only:
            continue
        if value is None:
            continue
        if isinstance(value, dict) and value.get("type") == "doc":
            plain = adf_to_plain_text(value)
            if plain.strip():
                out[field_id] = plain
        elif isinstance(value, str) and not value.strip():
            continue
        else:
            out[field_id] = value

    return out


def _empty_request_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False


def get_request_type_fields(
    *,
    service_desk_id: str | None = None,
    request_type_id: str | None = None,
) -> list[dict[str, Any]]:
    """Live request-type field schema. Read-only."""
    sd_id = service_desk_id or config.TCKT_SERVICE_DESK_ID
    rt_id = request_type_id or config.TCKT_REQUEST_TYPE_ID
    if not sd_id or not rt_id:
        return []
    data = _sd_get(f"/servicedesk/{sd_id}/requesttype/{rt_id}/field")
    return list((data or {}).get("requestTypeFields") or [])


def validate_service_desk_create_payload(
    summary: str,
    fields: dict[str, Any],
) -> list[str]:
    """Return human-readable problems with the Service Desk create payload.

    Checks the live request-type form so missing required fields are caught
    before Jira returns HTTP 400.
    """
    if not (config.SERVICE_DESK_ENABLED and config.service_desk_request_type_configured()):
        return []

    problems: list[str] = []
    try:
        form_fields = get_request_type_fields()
    except Exception as exc:
        project = config.TCKT_PROJECT_KEY
        return [f"Could not load the {project} request form schema: {exc}"]

    if not form_fields:
        project = config.TCKT_PROJECT_KEY
        return [f"{project} request form schema returned no fields — check Service Desk IDs."]

    payload = _build_service_desk_request_field_values(summary, fields)
    if _service_desk_create_mode() == "summary_only":
        if not (summary or "").strip():
            problems.append("Summary is required for Service Desk create.")
        return problems
    for form_field in form_fields:
        if not form_field.get("required"):
            continue
        field_id = str(form_field.get("fieldId") or "")
        name = str(form_field.get("name") or field_id)
        if not field_id:
            continue
        if field_id not in payload or _empty_request_value(payload.get(field_id)):
            problems.append(f"Required form field is missing: {name} ({field_id})")
            continue

        schema = form_field.get("jiraSchema") or {}
        if schema.get("type") == "string" and not isinstance(payload.get(field_id), str):
            problems.append(
                f"Required form field has the wrong type: {name} "
                f"(expected string, got {type(payload[field_id]).__name__})"
            )

        valid = form_field.get("validValues") or []
        if not valid:
            continue
        allowed = {str(v.get("value")) for v in valid if v.get("value") is not None}
        value = payload[field_id]
        option_ids: list[str] = []
        if isinstance(value, dict) and value.get("id") is not None:
            option_ids = [str(value["id"])]
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("id") is not None:
                    option_ids.append(str(item["id"]))
        if option_ids and any(oid not in allowed for oid in option_ids):
            bad = [oid for oid in option_ids if oid not in allowed]
            problems.append(
                f"Required form field has an invalid option: {name} "
                f"(id(s) {', '.join(bad)} not in the request form)"
            )

    return problems


def create_service_desk_request(
    summary: str,
    fields: dict[str, Any],
    *,
    service_desk_id: str | None = None,
    request_type_id: str | None = None,
) -> dict[str, Any]:
    """Create a service-desk change ticket via POST ``/rest/servicedeskapi/request``.

    This is the only supported way to set Request Type on abcfinancial JSM Cloud;
    plain ``POST /rest/api/3/issue`` cannot attach a request type.
    """
    sd_id = service_desk_id or config.TCKT_SERVICE_DESK_ID
    rt_id = request_type_id or config.TCKT_REQUEST_TYPE_ID
    if not sd_id or not rt_id:
        raise JiraApiError(
            "Service Desk IDs must be configured (TCKT_SERVICE_DESK_ID / "
            "TCKT_REQUEST_TYPE_ID or workspace.yaml) for Service Desk create."
        )

    # No isAdfRequest: the request form takes plain strings, and claiming ADF while
    # sending text is what Jira rejected with "has these errors : []".
    body = {
        "serviceDeskId": str(sd_id),
        "requestTypeId": str(rt_id),
        "requestFieldValues": _build_service_desk_request_field_values(summary, fields),
    }
    return _sd_post("/request", body)


def find_recent_service_ticket_issues(within_minutes: int = 60) -> list[dict[str, Any]]:
    """Service-desk project issues the current user reported recently. Read-only."""
    minutes = max(1, int(within_minutes))
    jql = (
        f"project = {config.TCKT_PROJECT_KEY} AND reporter = currentUser() "
        f"AND created >= -{minutes}m ORDER BY created DESC"
    )
    data = _post(
        "/search/jql",
        {"jql": jql, "maxResults": 20, "fields": ["summary", "created", "status"]},
    )
    return (data or {}).get("issues") or []


def find_recent_tckt_issues(within_minutes: int = 60) -> list[dict[str, Any]]:
    """Backward-compatible alias for :func:`find_recent_service_ticket_issues`."""
    return find_recent_service_ticket_issues(within_minutes)


def find_service_ticket_by_summary(
    summary: str,
    within_minutes: int = 60,
) -> dict[str, Any] | None:
    """Find a recently created service ticket with this exact summary."""
    target = (summary or "").strip().casefold()
    if not target:
        return None
    for issue in find_recent_service_ticket_issues(within_minutes):
        existing = str((issue.get("fields") or {}).get("summary") or "").strip()
        if existing.casefold() == target:
            return issue
    return None


def find_tckt_by_summary(
    summary: str,
    within_minutes: int = 60,
) -> dict[str, Any] | None:
    """Backward-compatible alias for :func:`find_service_ticket_by_summary`."""
    return find_service_ticket_by_summary(summary, within_minutes)


def _deferrable_rejected_fields(
    exc: JiraApiError,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Values a 400 blamed on named fields that a post-create REST edit can still set.

    Fields the form reports as *required* are excluded — dropping one of those from
    the retry only trades one 400 for another.
    """
    if exc.status_code != 400:
        return {}
    return {
        field_id: fields[field_id]
        for field_id, reason in exc.field_errors.items()
        if field_id in fields
        and field_id not in ("summary", "description")
        and "required" not in reason.lower()
    }


def create_tckt_issue(summary: str, fields: dict[str, Any]) -> tuple[dict[str, Any], RequestTypeStatus]:
    """Create a TCKT and ensure Request Type is set when configured.

    Uses the Service Desk create API when ``TCKT_SERVICE_DESK_ID`` and
    ``TCKT_REQUEST_TYPE_ID`` are configured; otherwise falls back to plain Jira
    REST create plus a best-effort post-create request-type update.
    """
    defaults = config.TCKT_DEFAULTS
    enriched = dict(fields)
    test_ticket = is_test_shipit_summary(summary)
    # SHIPIT prod (Rekha / 16769): approver groups only — never auto-inject Team.
    default_keys = ("assignment_group", "unplanned")
    if _service_desk_create_mode() != "summary_only":
        default_keys = ("assignment_group", "affects_pf", "outage_required")
    for key in default_keys:
        if test_ticket and key == "assignment_group":
            continue
        field_id = config.service_desk_field(key)
        if field_id and field_id not in enriched and defaults.get(key):
            if key == "team":
                enriched[field_id] = _normalize_team_value(defaults[key])
            elif key == "assignment_group":
                resolved = resolve_assignment_group_value(defaults)
                if resolved:
                    enriched[field_id] = resolved
            else:
                enriched[field_id] = defaults[key]
    if test_ticket:
        for logical in ("team", "assignment_group", "approver_groups", "affected_services"):
            field_id = config.service_desk_field(logical)
            if field_id:
                enriched.pop(field_id, None)

    label = config.TCKT_REQUEST_TYPE_NAME or "Manual Change"

    if config.SERVICE_DESK_ENABLED and config.service_desk_request_type_configured():
        problems = validate_service_desk_create_payload(summary, enriched)
        if problems:
            raise JiraApiError(
                f"{config.TCKT_PROJECT_KEY} create blocked by preflight — the payload "
                "would be rejected by the Service Desk form:\n- "
                + "\n- ".join(problems),
                status_code=400,
            )

        deferred: dict[str, Any] = {}
        try:
            result = create_service_desk_request(summary, enriched)
        except JiraApiError as exc:
            deferred = _deferrable_rejected_fields(exc, enriched)
            if not deferred:
                raise
            _logger.warning(
                "Service Desk form rejected %s — retrying without them and "
                "setting them after create.",
                ", ".join(sorted(deferred)),
            )
            try:
                result = create_service_desk_request(
                    summary,
                    {k: v for k, v in enriched.items() if k not in deferred},
                )
            except JiraApiError:
                # The first failure describes the real problem; the retry's does not.
                raise exc from None

        issue_key = str(result.get("issueKey") or "")
        if not issue_key:
            raise JiraApiError(
                f"Service Desk create returned unexpected response: {result!r}"
            )

        created: dict[str, Any] = {"key": issue_key, **result}
        supplemental = {**_build_supplemental_tckt_fields(enriched), **deferred}
        if supplemental:
            # Isolated batches — a bad Team value must not wipe Approvers.
            warnings = apply_supplemental_tckt_fields(issue_key, supplemental)
            if warnings:
                created["supplementalWarning"] = (
                    f"{issue_key} was created, but some fields could not be set "
                    f"automatically: " + " | ".join(warnings)
                )
                created["supplementalFailures"] = warnings
        return (
            created,
            RequestTypeStatus(
                RequestTypeStatus.OK,
                f'Request Type set to "{label}".',
            ),
        )

    result = create_issue(
        config.TCKT_PROJECT_KEY,
        config.TCKT_ISSUE_TYPE_ID,
        summary,
        fields,
    )
    issue_key = result.get("key", "")
    rt_status = set_request_type_detailed(issue_key) if issue_key else RequestTypeStatus(
        RequestTypeStatus.SKIPPED,
        "Ticket key missing; Request Type not updated.",
    )
    return result, rt_status


# ── Service Desk: set request type ───────────────────────────────

def set_request_type(issue_key: str) -> bool:
    """Try to set the TCKT request type via the Service Desk API.

    Returns True on success, False if IDs are not configured or the call fails.
    Kept for backwards compatibility; prefer :func:`set_request_type_detailed`
    for structured status reporting (needed by the ticket-create UI).
    """
    return set_request_type_detailed(issue_key).ok


def set_request_type_detailed(issue_key: str) -> RequestTypeStatus:
    """Verify or attach the configured Service Desk request type on an existing TCKT.

    Many JSM Cloud instances (including abcfinancial) do not expose a post-create
    request-type endpoint. In that case this returns FAILED unless the ticket
    already has the configured type — use :func:`create_tckt_issue` instead.
    """
    from request_type_setter import default_audit_path
    from request_type_setter import set_request_type as rt_set

    sd_id = config.TCKT_SERVICE_DESK_ID
    rt_id = config.TCKT_REQUEST_TYPE_ID
    if not sd_id or not rt_id:
        return RequestTypeStatus(
            RequestTypeStatus.DISABLED,
            "TCKT_SERVICE_DESK_ID and/or TCKT_REQUEST_TYPE_ID are not configured.",
        )

    label = config.TCKT_REQUEST_TYPE_NAME or "Submit A Normal or Emergency Change"
    existing = get_issue_request_type_id(issue_key)
    if existing == str(rt_id):
        return RequestTypeStatus(
            RequestTypeStatus.OK,
            f'Request Type already set to "{label}".',
        )

    def transport(method: str, path: str, payload: dict | None) -> tuple[int, str]:
        if method != "POST":
            raise ValueError(f"unsupported method {method}")
        _block_mock_writes("POST", path)
        url = f"{config.JIRA_BASE_URL}{path}"
        resp = requests.post(
            url,
            headers=_headers(),
            auth=_auth(),
            json=payload or {},
            timeout=_DEFAULT_TIMEOUT,
        )
        return resp.status_code, resp.text or ""

    result = rt_set(
        issue_key,
        service_desk_id=str(sd_id),
        request_type_id=str(rt_id),
        transport=transport,
        audit_path=default_audit_path(),
    )
    if result.ok:
        return RequestTypeStatus(
            RequestTypeStatus.OK,
            f'Request Type set to "{label}".',
            http_status=result.last_status or None,
        )
    if "missing issue_key" in result.message:
        return RequestTypeStatus(RequestTypeStatus.DISABLED, result.message)
    if result.last_status == 404:
        return RequestTypeStatus(
            RequestTypeStatus.FAILED,
            "This Jira instance does not support setting Request Type after create. "
            f'Use Service Desk create (configured) so Request Type is "{label}" at creation.',
            http_status=404,
        )
    return RequestTypeStatus(
        RequestTypeStatus.FAILED,
        result.message or "Service Desk API rejected the request-type update.",
        http_status=result.last_status or None,
    )


# ── User / Group lookup (approver validation) ────────────────────

class ApproverValidationError(Exception):
    """Raised when we cannot contact Jira at all to validate an approver."""


def get_user(account_id: str) -> dict | None:
    """Return the Jira user object for ``account_id`` or ``None`` if not found.

    Raises :class:`JiraApiError` on HTTP errors other than 404.
    """
    if not account_id:
        return None
    try:
        return _get("/user", params={"accountId": account_id})
    except JiraApiError as exc:
        if exc.status_code == 404:
            return None
        raise


def get_group(group_name: str) -> dict | None:
    """Return the Jira group with ``group_name`` or ``None`` if missing."""
    if not group_name:
        return None
    try:
        return _get("/group", params={"groupName": group_name})
    except JiraApiError as exc:
        if exc.status_code == 404:
            return None
        raise


# ── Generic issue fetch (used by diff & history detail views) ────

def get_issue(issue_key: str, *, expand: str | None = None) -> dict:
    """Fetch one issue with all fields; optional ``expand=renderedFields``."""
    params: dict[str, Any] = {}
    if expand:
        params["expand"] = expand
    return _get(f"/issue/{issue_key}", params=params or None)


# ── User-reported history (for the release timeline) ─────────────

def search_my_service_desk_tickets(
    project_key: str,
    *,
    max_results: int = 100,
    jql_extra: str = "",
) -> list[dict]:
    """Return tickets in ``project_key`` reported by the current user."""
    jql = f"reporter = currentUser() AND project = {project_key}"
    if jql_extra:
        jql += f" AND {jql_extra}"
    jql += " ORDER BY created DESC"
    return search_issues_jql(
        jql,
        fields=["summary", "status", "created", "updated", "priority"],
        max_results=max_results,
    )


def search_issues_jql(
    jql: str,
    *,
    fields: list[str] | None = None,
    max_results: int = 100,
) -> list[dict]:
    """Paginated JQL search via POST /search/jql."""
    search_fields = fields or [
        "summary", "status", "created", "updated", "priority",
    ]
    return _search_jql_paginated(
        jql, fields=search_fields, max_results=max_results,
    )


# ── Confluence (optional companion page) ─────────────────────────

class ConfluenceError(Exception):
    """Raised when the Confluence REST API returns an unexpected response."""


def _confluence_url() -> str:
    base = os.environ.get("CONFLUENCE_URL") or config.JIRA_BASE_URL
    return base.rstrip("/") + "/wiki/rest/api"


def _confluence_auth() -> HTTPBasicAuth:
    token = os.environ.get("CONFLUENCE_TOKEN") or config.JIRA_API_TOKEN
    return HTTPBasicAuth(config.JIRA_EMAIL, token)


def confluence_find_page_by_title(space_key: str, title: str) -> dict | None:
    """Find a Confluence page by exact title in a space (v1 REST)."""
    import urllib.parse as ul

    url = f"{_confluence_url()}/content"
    params = {
        "spaceKey": space_key,
        "title": title,
        "expand": "version",
    }
    resp = requests.get(
        url,
        headers=_headers(),
        auth=_confluence_auth(),
        params=params,
        timeout=_DEFAULT_TIMEOUT,
    )
    if not resp.ok:
        return None
    data = resp.json()
    results = data.get("results") if isinstance(data, dict) else []
    return results[0] if results else None


def confluence_update_page(
    page_id: str,
    *,
    title: str,
    body_storage: str,
    version_number: int,
) -> dict:
    """Update an existing Confluence page (storage format)."""
    url = f"{_confluence_url()}/content/{page_id}"
    body = {
        "type": "page",
        "title": title,
        "version": {"number": version_number},
        "body": {"storage": {"value": body_storage, "representation": "storage"}},
    }
    resp = requests.put(
        url,
        headers=_headers(),
        auth=_confluence_auth(),
        json=body,
        timeout=_DEFAULT_TIMEOUT,
    )
    if not resp.ok:
        raise ConfluenceError(
            f"Confluence update returned HTTP {resp.status_code}: {(resp.text or '')[:200]}"
        )
    return resp.json()


def confluence_create_page(
    space_key: str,
    title: str,
    body_storage: str,
    parent_id: str | None = None,
) -> dict:
    """Create a Confluence page (storage format body).

    Retries transient errors; raises :class:`ConfluenceError` on non-success.
    """
    url = f"{_confluence_url()}/content"
    body: dict[str, Any] = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {"storage": {"value": body_storage, "representation": "storage"}},
    }
    if parent_id:
        body["ancestors"] = [{"id": parent_id}]
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                headers=_headers(),
                auth=_confluence_auth(),
                json=body,
                timeout=_DEFAULT_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)
                continue
            raise ConfluenceError(f"Could not reach Confluence: {exc}") from exc
        if _should_retry(resp, attempt):
            continue
        if not resp.ok:
            raise ConfluenceError(
                f"Confluence API returned HTTP {resp.status_code}: {(resp.text or '')[:200]}"
            )
        return resp.json()
    raise ConfluenceError("Confluence API retries exhausted")
