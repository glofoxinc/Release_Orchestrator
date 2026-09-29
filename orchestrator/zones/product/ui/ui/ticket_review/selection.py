"""Ticket Review selection — thin wrapper around shared ticket_source (prefix=tr)."""

from __future__ import annotations

import config
from release_platform.ui import ticket_source as ts

PREFIX = "tr_"

MODE_FIX_VERSION = ts.MODE_FIX_VERSION
MODE_STATUS = ts.MODE_STATUS
MODE_SESSION_KEY = ts.mode_session_key(PREFIX)


def get_selection_mode() -> str:
    return ts.get_selection_mode(PREFIX)


def status_session_key(project_key: str) -> str:
    return ts.status_session_key(PREFIX, project_key)


def status_issues_cache_key(project_key: str, statuses: tuple[str, ...]) -> str:
    return ts.status_issues_cache_key(PREFIX, project_key, statuses)


def get_selected_statuses(project_key: str) -> list[str]:
    return ts.get_selected_statuses(PREFIX, project_key)


def apply_default_status_selections(*, force: bool = False) -> None:
    ts.apply_default_status_selections(PREFIX, force=force)


def apply_snapshot_selection_context(snapshot: dict | None) -> None:
    ts.apply_snapshot_selection_context(PREFIX, snapshot)


def has_fix_version_selection(*, prefix: str = PREFIX) -> bool:
    return ts.has_fix_version_selection(prefix=prefix)


def has_status_selection() -> bool:
    return ts.has_status_selection(prefix=PREFIX)


def has_step1_selection(*, prefix: str = PREFIX) -> bool:
    return ts.has_step1_selection(prefix=prefix)


def clear_fix_version_selection(*, prefix: str = PREFIX) -> None:
    ts.clear_fix_version_selection(prefix=prefix)


def clear_status_selection() -> None:
    ts.clear_status_selection(prefix=PREFIX)


def on_mode_change() -> None:
    ts.on_mode_change(PREFIX)


def load_project_status_options(project_key: str) -> list[str]:
    return ts.load_project_status_options(project_key)


def initial_ticket_selection(
    issues: list[dict],
    locked_keys: set[str] | None,
    *,
    mode: str = MODE_FIX_VERSION,
) -> set[str]:
    """Default Step 2 checkbox state."""
    all_keys = {str(iss.get("key") or "") for iss in issues}
    all_keys.discard("")
    if locked_keys is not None:
        return locked_keys & all_keys
    if mode == MODE_STATUS:
        return all_keys
    return set()


def default_checked_keys_for_status_mode(issues: list[dict]) -> set[str]:
    """Auto-check Review (PIC) / Passed QA (AN) tickets in status mode."""
    selected: set[str] = set()
    for iss in issues:
        key = str(iss.get("key") or "").strip()
        if not key:
            continue
        pk = key.split("-", 1)[0].strip().upper() if "-" in key else ""
        targets = config.ticket_review_default_checked_statuses(pk)
        if not targets:
            continue
        status = str((iss.get("fields") or {}).get("status", {}).get("name") or "").strip()
        target_set = {t.casefold() for t in targets}
        if status.casefold() in target_set:
            selected.add(key)
    return selected


def get_effective_selection_mode() -> str:
    return ts.get_effective_selection_mode(PREFIX)


def effective_selection_summary(*, prefix: str = PREFIX) -> str:
    return ts.effective_selection_summary(prefix=prefix)


def lock_ticket_source() -> dict:
    return ts.lock_ticket_source(PREFIX)


def apply_locked_ticket_source() -> dict | None:
    return ts.apply_locked_ticket_source(PREFIX)


def clear_locked_ticket_source() -> None:
    ts.clear_locked_ticket_source(PREFIX)


def fetch_combined_issues(*, force: bool = False) -> list[dict]:
    from release_platform.ui.ticket_review.jira_team_filter import get_selected_team_ids

    def team_ids(pk: str) -> list[str] | None:
        ids = get_selected_team_ids(pk)
        return ids if ids else None

    return ts.fetch_combined_issues(
        PREFIX,
        issues_cache_prefix="_tr_issues_",
        team_ids_for_project=team_ids,
        force=force,
    )


def selection_summary(*, prefix: str = PREFIX) -> str:
    return ts.selection_summary(prefix=prefix)
