"""Ticket Review team filter — wrapper around shared ui/jira_team_filter."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from release_platform.ui import jira_team_filter as jtf

PREFIX = "tr_"


def team_filter_cache_suffix(project_key: str) -> str:
    return jtf.team_filter_cache_suffix(PREFIX, project_key)


def clear_ticket_review_fetch_caches() -> None:
    jtf.clear_issue_caches_for_prefix(PREFIX)


def clear_ticket_review_issue_caches() -> None:
    jtf.clear_issue_caches_for_prefix(PREFIX, extra_clear=_clear_tr_step2_state)


def _clear_tr_step2_state() -> None:
    st.session_state.pop("tr_grouped", None)
    st.session_state.pop("tr_selected_keys", None)
    st.session_state.pop("tr_issues_fp", None)
    for key in list(st.session_state.keys()):
        if key.startswith("tr_chk_"):
            st.session_state.pop(key, None)


def is_team_filter_locked() -> bool:
    return jtf.is_team_filter_locked(PREFIX)


def get_selected_team_ids(project_key: str) -> list[str]:
    return jtf.get_selected_team_ids(PREFIX, project_key)


def get_all_selected_team_ids() -> dict[str, list[str]]:
    return {proj["key"]: get_selected_team_ids(proj["key"]) for proj in __import__("config").PROJECTS}


def format_snapshot_team_filters(snapshot: dict[str, Any] | None) -> str:
    return jtf.format_snapshot_team_filters(snapshot)


def team_filter_summary() -> str:
    return jtf.team_filter_summary(PREFIX)


def team_filters_for_snapshot() -> dict[str, list[dict[str, str]]]:
    return jtf.team_filters_for_snapshot(PREFIX)


def apply_snapshot_team_filters(snapshot: dict[str, Any] | None) -> None:
    jtf.apply_snapshot_team_filters(PREFIX, snapshot)


def lock_team_filter() -> None:
    jtf.lock_team_filter(PREFIX, on_change_clear=_clear_tr_step2_state)


def ensure_team_filter_locked() -> None:
    jtf.ensure_team_filter_locked(PREFIX, on_change_clear=_clear_tr_step2_state)


def unlock_team_filter() -> None:
    jtf.unlock_team_filter(PREFIX, on_change_clear=_clear_tr_step2_state)


def clear_team_filter_lock() -> None:
    jtf._clear_session_team_lock()
    import config

    for proj in config.PROJECTS:
        st.session_state.pop(jtf._sel_key(PREFIX, proj["key"]), None)
    clear_ticket_review_issue_caches()


def snapshot_team_filter_matches(current: dict[str, list[dict[str, str]]] | None) -> bool:
    snap = st.session_state.get("shared_snapshot") or {}
    stored = snap.get("jira_team_filters") or {}
    if not stored and not current:
        return True
    if not stored or not current:
        return False

    def _norm(data: dict) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for pk, entries in data.items():
            if not isinstance(entries, list):
                continue
            ids = {
                str(e.get("id") or "").strip()
                for e in entries
                if isinstance(e, dict) and str(e.get("id") or "").strip()
            }
            if ids:
                out[str(pk).upper()] = ids
        return out

    return _norm(stored) == _norm(current)


def render_team_filter_panel() -> None:
    jtf.render_team_filter_panel(PREFIX, on_change_clear=_clear_tr_step2_state)
