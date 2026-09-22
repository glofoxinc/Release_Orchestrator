"""Tenant-safe team ticket scope for release-version queries.

Every release fetch becomes::

    project = <key> AND fixVersion = <id> AND (<team scope>)

Workspaces must configure board, saved filter, labels, components, custom JQL,
or an explicit project-wide acknowledgement before ticket reads succeed.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

import config

_BOARD_ID_RE = re.compile(r"(?:/boards/|^)(\d+)", re.IGNORECASE)
_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)

# board_id -> (monotonic_expiry, filter_id)
_board_filter_cache: dict[str, tuple[float, str]] = {}
_board_cache_lock = threading.Lock()
_BOARD_FILTER_TTL = 300.0


class TeamScopeError(Exception):
    """Raised when team scope is missing, invalid, or blocks an operation."""

    def __init__(self, message: str, *, project_key: str = "", errors: list[str] | None = None):
        self.project_key = project_key
        self.errors = list(errors or [])
        super().__init__(message)


@dataclass(frozen=True)
class TeamScope:
    board_id: str = ""
    filter_id: str = ""
    labels_any: tuple[str, ...] = ()
    components_any: tuple[str, ...] = ()
    jql: str = ""
    allow_project_wide: bool = False
    owns_version: bool = False


def default_scope_dict() -> dict[str, Any]:
    return {
        "board_id": "",
        "filter_id": "",
        "labels_any": [],
        "components_any": [],
        "jql": "",
        "allow_project_wide": False,
        "owns_version": False,
    }


def get_project_config(project_key: str) -> dict[str, Any] | None:
    needle = (project_key or "").strip().upper()
    for proj in config.PROJECTS:
        if str(proj.get("key", "")).strip().upper() == needle:
            return proj
    return None


def parse_scope(raw: dict[str, Any] | None) -> TeamScope:
    data = raw if isinstance(raw, dict) else {}
    labels = data.get("labels_any") or []
    components = data.get("components_any") or []
    if not isinstance(labels, list):
        labels = []
    if not isinstance(components, list):
        components = []
    return TeamScope(
        board_id=_normalize_id(data.get("board_id")),
        filter_id=_normalize_id(data.get("filter_id")),
        labels_any=tuple(str(x).strip() for x in labels if str(x).strip()),
        components_any=tuple(str(x).strip() for x in components if str(x).strip()),
        jql=str(data.get("jql") or "").strip(),
        allow_project_wide=bool(data.get("allow_project_wide", False)),
        owns_version=bool(data.get("owns_version", False)),
    )


def scope_from_project(project_key: str) -> TeamScope:
    proj = get_project_config(project_key)
    if not proj:
        raise TeamScopeError(
            f"Unknown project '{project_key}'.",
            project_key=project_key,
        )
    return parse_scope(proj.get("scope"))


def _normalize_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = _BOARD_ID_RE.search(text)
    if match:
        return match.group(1)
    if text.isdigit():
        return text
    return text


def normalize_scope_id(value: Any) -> str:
    return _normalize_id(value)


def _jql_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def has_team_criterion(scope: TeamScope) -> bool:
    return bool(
        scope.board_id
        or scope.filter_id
        or scope.labels_any
        or scope.components_any
        or scope.jql
        or scope.allow_project_wide
    )


def scope_is_ready(scope: TeamScope) -> bool:
    return has_team_criterion(scope)


def validate_scope_structure(scope: TeamScope, *, project_key: str = "") -> list[str]:
    errors: list[str] = []
    if not scope_is_ready(scope):
        errors.append(
            "Team scope is not configured. Set a board, saved filter, labels, "
            "components, custom JQL, or explicitly allow project-wide scope."
        )
        return errors

    if scope.allow_project_wide and (
        scope.board_id
        or scope.filter_id
        or scope.labels_any
        or scope.components_any
        or scope.jql
    ):
        errors.append(
            "allow_project_wide cannot be combined with board, filter, labels, "
            "components, or custom JQL."
        )

    if scope.jql and _ORDER_BY_RE.search(scope.jql):
        errors.append("Custom scope JQL must not contain ORDER BY.")

    if scope.board_id and not scope.board_id.isdigit():
        errors.append(f"Board id '{scope.board_id}' is not numeric.")

    if scope.filter_id and not scope.filter_id.isdigit():
        errors.append(f"Filter id '{scope.filter_id}' is not numeric.")

    for label in scope.labels_any:
        if not label or any(ch.isspace() for ch in label):
            errors.append(f"Invalid label '{label}'.")

    for component in scope.components_any:
        if not component:
            errors.append("Component names cannot be empty.")

    if scope.owns_version and not scope.allow_project_wide:
        errors.append(
            "owns_version requires allow_project_wide=true — scoped teams must not "
            "mark whole project versions released."
        )

    if project_key and scope.jql:
        upper = scope.jql.upper()
        if "PROJECT =" in upper and project_key.upper() not in upper:
            errors.append(
                "Custom scope JQL must not pin a different project; "
                f"project = {project_key} is added automatically."
            )

    return errors


def scope_type_label(scope: TeamScope, *, resolved_filter_id: str = "") -> str:
    parts: list[str] = []
    if scope.allow_project_wide and not (
        scope.board_id or scope.filter_id or scope.labels_any or scope.components_any or scope.jql
    ):
        return "project_wide"
    if scope.board_id:
        parts.append("board")
    elif scope.filter_id or resolved_filter_id:
        parts.append("filter")
    if scope.labels_any:
        parts.append("labels")
    if scope.components_any:
        parts.append("components")
    if scope.jql:
        parts.append("jql")
    if not parts:
        return "none"
    if len(parts) == 1:
        return parts[0]
    return "mixed"


def build_team_scope_clause(scope: TeamScope, *, resolved_filter_id: str = "") -> str:
    errors = validate_scope_structure(scope)
    if errors:
        raise TeamScopeError(errors[0], errors=errors)

    if scope.allow_project_wide and not (
        scope.board_id or scope.filter_id or scope.labels_any or scope.components_any or scope.jql
    ):
        return ""

    parts: list[str] = []
    filter_id = resolved_filter_id or scope.filter_id
    if filter_id:
        parts.append(f"filter = {filter_id}")
    if scope.labels_any:
        quoted = ", ".join(_jql_quote(label) for label in scope.labels_any)
        parts.append(f"labels in ({quoted})")
    if scope.components_any:
        quoted = ", ".join(_jql_quote(name) for name in scope.components_any)
        parts.append(f"component in ({quoted})")
    if scope.jql:
        parts.append(f"({scope.jql})")

    if not parts:
        raise TeamScopeError(
            "Team scope has no effective JQL clause.",
            errors=["No scope criteria after validation."],
        )
    return " AND ".join(parts)


def build_scoped_version_jql(
    project_key: str,
    version_id: str,
    scope: TeamScope,
    *,
    resolved_filter_id: str = "",
    order_by: str = "key ASC",
) -> str:
    pk = project_key.strip()
    vid = str(version_id).strip()
    if not pk or not vid:
        raise TeamScopeError("project_key and version_id are required.")

    base = f"project = {pk} AND fixVersion = {vid}"
    team_clause = build_team_scope_clause(scope, resolved_filter_id=resolved_filter_id)
    if team_clause:
        jql = f"{base} AND ({team_clause})"
    else:
        jql = base
    if order_by:
        jql = f"{jql} ORDER BY {order_by}"
    return jql


def build_scoped_status_jql(
    project_key: str,
    statuses: Iterable[str],
    scope: TeamScope,
    *,
    resolved_filter_id: str = "",
    order_by: str = "updated DESC",
) -> str:
    """Build JQL for project + status filter + team scope."""
    pk = project_key.strip()
    status_list = [str(s).strip() for s in statuses if str(s).strip()]
    if not pk:
        raise TeamScopeError("project_key is required.")
    if not status_list:
        raise TeamScopeError("At least one Jira status is required.")

    quoted = ", ".join(_jql_quote(name) for name in status_list)
    base = f"project = {pk} AND status in ({quoted})"
    team_clause = build_team_scope_clause(scope, resolved_filter_id=resolved_filter_id)
    if team_clause:
        jql = f"{base} AND ({team_clause})"
    else:
        jql = base
    if order_by:
        jql = f"{jql} ORDER BY {order_by}"
    return jql


def scope_config_fingerprint(project_key: str, scope: TeamScope) -> str:
    """Fingerprint from workspace.yaml only — stable across board filter resolution."""
    return scope_fingerprint(project_key, scope, resolved_filter_id="")


def scope_fingerprint(
    project_key: str,
    scope: TeamScope,
    *,
    resolved_filter_id: str = "",
) -> str:
    canonical = {
        "project": project_key.strip().upper(),
        "board_id": scope.board_id,
        "filter_id": resolved_filter_id or scope.filter_id,
        "labels_any": list(scope.labels_any),
        "components_any": list(scope.components_any),
        "jql": scope.jql,
        "allow_project_wide": scope.allow_project_wide,
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def scope_status(
    project_key: str,
    *,
    scope: TeamScope | None = None,
    resolved_filter_id: str = "",
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    sc = scope if scope is not None else scope_from_project(project_key)
    errors = list(validation_errors or validate_scope_structure(sc, project_key=project_key))
    if sc.allow_project_wide and not errors:
        state = "project_wide"
    elif errors:
        state = "invalid" if has_team_criterion(sc) else "blocking"
    else:
        state = "configured"
    return {
        "project_key": project_key.strip().upper(),
        "state": state,
        "scope_type": scope_type_label(sc, resolved_filter_id=resolved_filter_id),
        "fingerprint": scope_fingerprint(project_key, sc, resolved_filter_id=resolved_filter_id)
        if not errors
        else "",
        "owns_version": sc.owns_version,
        "allow_project_wide": sc.allow_project_wide,
        "errors": errors,
        "configured": state in {"configured", "project_wide"},
        "blocking": state in {"blocking", "invalid"},
    }


def clear_board_filter_cache() -> None:
    with _board_cache_lock:
        _board_filter_cache.clear()


def cache_board_filter(board_id: str, filter_id: str, *, ttl: float = _BOARD_FILTER_TTL) -> None:
    with _board_cache_lock:
        _board_filter_cache[str(board_id)] = (time.monotonic() + ttl, str(filter_id))


def cached_board_filter(board_id: str) -> str | None:
    with _board_cache_lock:
        entry = _board_filter_cache.get(str(board_id))
        if not entry:
            return None
        expires, filter_id = entry
        if time.monotonic() > expires:
            _board_filter_cache.pop(str(board_id), None)
            return None
        return filter_id


def resolve_filter_id(
    scope: TeamScope,
    *,
    board_resolver: Callable[[str], str] | None = None,
) -> str:
    if scope.board_id:
        cached = cached_board_filter(scope.board_id)
        if cached:
            return cached
        if board_resolver is None:
            raise TeamScopeError(
                f"Board {scope.board_id} requires live Jira resolution.",
                errors=[f"Unresolved board id {scope.board_id}."],
            )
        filter_id = board_resolver(scope.board_id)
        cache_board_filter(scope.board_id, filter_id)
        return filter_id
    return scope.filter_id


def ensure_scope_ready(project_key: str) -> TeamScope:
    scope = scope_from_project(project_key)
    errors = validate_scope_structure(scope, project_key=project_key)
    if errors:
        raise TeamScopeError(
            f"{project_key}: {errors[0]}",
            project_key=project_key,
            errors=errors,
        )
    return scope


def assert_can_mark_version_released(project_key: str) -> None:
    scope = ensure_scope_ready(project_key)
    if not scope.owns_version:
        raise TeamScopeError(
            f"{project_key}: marking the Jira fix version released is blocked. "
            "This action affects the entire project version, not only your board. "
            "Set scope.owns_version: true only when your team owns the whole version.",
            project_key=project_key,
            errors=["owns_version is false for this scoped team."],
        )


def projects_missing_scope() -> list[str]:
    missing: list[str] = []
    for proj in config.PROJECTS:
        pk = str(proj.get("key", "")).strip().upper()
        if not pk:
            continue
        scope = parse_scope(proj.get("scope"))
        if validate_scope_structure(scope, project_key=pk):
            missing.append(pk)
    return missing


def all_projects_scoped() -> bool:
    return not projects_missing_scope()


def scope_dict_from_scope(scope: TeamScope) -> dict[str, Any]:
    return {
        "board_id": scope.board_id,
        "filter_id": scope.filter_id,
        "labels_any": list(scope.labels_any),
        "components_any": list(scope.components_any),
        "jql": scope.jql,
        "allow_project_wide": scope.allow_project_wide,
        "owns_version": scope.owns_version,
    }


def collect_scope_fingerprints() -> dict[str, str]:
    """Config-stable scope fingerprints for draft/snapshot persistence."""
    fps: dict[str, str] = {}
    for proj in config.PROJECTS:
        pk = str(proj.get("key", "")).strip().upper()
        if not pk:
            continue
        scope = parse_scope(proj.get("scope"))
        errors = validate_scope_structure(scope, project_key=pk)
        if errors:
            fps[pk] = ""
            continue
        fps[pk] = scope_config_fingerprint(pk, scope)
    return fps


def collect_runtime_scope_fingerprints() -> dict[str, str]:
    """Scope fingerprints including resolved board filters (JQL cache keys)."""
    fps: dict[str, str] = {}
    for proj in config.PROJECTS:
        pk = str(proj.get("key", "")).strip().upper()
        if not pk:
            continue
        scope = parse_scope(proj.get("scope"))
        errors = validate_scope_structure(scope, project_key=pk)
        if errors:
            fps[pk] = ""
            continue
        try:
            filter_id = resolve_filter_id(scope)
        except TeamScopeError:
            filter_id = scope.filter_id
        fps[pk] = scope_fingerprint(pk, scope, resolved_filter_id=filter_id)
    return fps


def fingerprint_compatible_with_config(
    project_key: str,
    stored_fp: str,
    *,
    current_config_fp: str = "",
) -> bool:
    """True when a saved fingerprint matches current config or resolved runtime scope."""
    prev = (stored_fp or "").strip()
    if not prev:
        return True
    pk = project_key.strip().upper()
    config_fp = current_config_fp or scope_config_fingerprint(pk, scope_from_project(pk))
    if prev == config_fp:
        return True
    try:
        scope = scope_from_project(pk)
    except TeamScopeError:
        return False
    try:
        resolved = resolve_filter_id(scope)
    except TeamScopeError:
        resolved = scope.filter_id
    runtime_fp = scope_fingerprint(pk, scope, resolved_filter_id=resolved)
    return prev == runtime_fp


def snapshot_scope_matches(
    stored: dict[str, str] | None,
    *,
    lenient: bool = False,
) -> tuple[bool, list[str]]:
    """Return (matches, changed_project_keys) using config-stable fingerprints."""
    if not stored:
        return (True, [])
    current = collect_scope_fingerprints()
    stored = stored or {}
    changed: list[str] = []
    for pk, fp in current.items():
        if not fp:
            if stored.get(pk):
                changed.append(pk)
            continue
        prev = stored.get(pk, "")
        if prev and prev != fp:
            if lenient and fingerprint_compatible_with_config(pk, prev, current_config_fp=fp):
                continue
            changed.append(pk)
    for pk in stored:
        if pk not in current:
            changed.append(pk)
    return (not changed, sorted(set(changed)))


def keys_outside_scoped_version(
    project_key: str,
    version_id: str,
    keys: Iterable[str],
    scoped_keys: Iterable[str] | None = None,
) -> list[str]:
    wanted = {str(k).strip().upper() for k in keys if str(k).strip()}
    if not wanted:
        return []
    if scoped_keys is None:
        import jira_client

        scoped_keys = jira_client.get_issue_keys_for_version(project_key, version_id)
    allowed = {str(k).strip().upper() for k in scoped_keys}
    return sorted(k for k in wanted if k not in allowed)


def assert_keys_in_scoped_version(
    project_key: str,
    version_id: str,
    keys: Iterable[str],
    *,
    scoped_keys: Iterable[str] | None = None,
) -> None:
    outside = keys_outside_scoped_version(
        project_key, version_id, keys, scoped_keys=scoped_keys,
    )
    if outside:
        raise TeamScopeError(
            f"{project_key}: ticket(s) outside team scope: {', '.join(outside)}",
            project_key=project_key,
            errors=[f"Out-of-scope keys: {', '.join(outside)}"],
        )
