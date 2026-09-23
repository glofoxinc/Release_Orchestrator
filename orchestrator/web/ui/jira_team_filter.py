"""Jira Team field filter with lock / unlock — shared across TR, RN, SHIPIT."""

from __future__ import annotations

import hashlib
from typing import Any, Callable

import streamlit as st

import config
import jira_client
import jira_teams
from release_platform.ui.helpers import esc


def _norm_prefix(prefix: str) -> str:
    return prefix if prefix.endswith("_") else f"{prefix}_"


WORKFLOW_PREFIXES: tuple[str, ...] = ("tr_", "rn_", "stk_")

SHARED_LOCK_KEY = "shared_jira_teams_locked"
SHARED_LOCKED_VALUES_KEY = "shared_jira_teams_locked_values"


def _lock_key(prefix: str) -> str:
    return f"{_norm_prefix(prefix)}jira_teams_locked"


def _locked_values_key(prefix: str) -> str:
    return f"{_norm_prefix(prefix)}jira_teams_locked_values"


def _restored_key(prefix: str) -> str:
    return f"{_norm_prefix(prefix)}jira_teams_restored"


def _sel_key(prefix: str, project_key: str) -> str:
    return f"{_norm_prefix(prefix)}jira_teams_sel_{project_key}"


def _catalog_cache_key(project_key: str) -> str:
    return f"_jira_team_catalog_{project_key}"


def team_filter_cache_suffix(prefix: str, project_key: str) -> str:
    ids = sorted(get_selected_team_ids(prefix, project_key))
    if not ids:
        return "allteams"
    digest = hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest()[:10]
    return f"teams_{digest}"


def team_filter_fingerprint(prefix: str) -> str:
    parts: list[str] = []
    for proj in config.PROJECTS:
        pk = proj["key"]
        ids = get_selected_team_ids(prefix, pk)
        if ids:
            parts.append(f"{pk}:{','.join(ids)}")
    return "teams:" + ("|".join(parts) if parts else "all")


def clear_issue_caches_for_prefix(
    prefix: str,
    *,
    extra_clear: Callable[[], None] | None = None,
) -> None:
    """Drop cached issue lists for an app prefix after team/source change."""
    p = _norm_prefix(prefix).rstrip("_")
    for key in list(st.session_state.keys()):
        if key.startswith(f"_{p}_issues_") or key.startswith(f"_{p}_status_issues_"):
            st.session_state.pop(key, None)
    if extra_clear:
        extra_clear()


def _session_team_lock_active() -> bool:
    return bool(st.session_state.get(SHARED_LOCK_KEY))


def _locked_values_for_prefix(prefix: str) -> dict[str, list[dict[str, str]]]:
    shared = st.session_state.get(SHARED_LOCKED_VALUES_KEY)
    if isinstance(shared, dict) and shared:
        return shared
    per_prefix = st.session_state.get(_locked_values_key(prefix))
    return per_prefix if isinstance(per_prefix, dict) else {}


def sync_team_filter_from_session(prefix: str) -> None:
    """Apply session-wide team lock to this app prefix (TR / RN / SHIPIT)."""
    if not _session_team_lock_active():
        return
    locked_values = _locked_values_for_prefix(prefix)
    st.session_state[_lock_key(prefix)] = True
    st.session_state[_locked_values_key(prefix)] = dict(locked_values)
    for proj in config.PROJECTS:
        pk = proj["key"]
        entries = locked_values.get(pk) or []
        st.session_state[_sel_key(prefix, pk)] = [
            str(entry.get("id") or "").strip()
            for entry in entries
            if isinstance(entry, dict) and str(entry.get("id") or "").strip()
        ]


def _propagate_team_lock(locked: dict[str, list[dict[str, str]]]) -> None:
    """Persist team filter lock for the full Streamlit session across all apps."""
    st.session_state[SHARED_LOCK_KEY] = True
    st.session_state[SHARED_LOCKED_VALUES_KEY] = dict(locked)
    for workflow_prefix in WORKFLOW_PREFIXES:
        st.session_state[_lock_key(workflow_prefix)] = True
        st.session_state[_locked_values_key(workflow_prefix)] = dict(locked)
        for proj in config.PROJECTS:
            pk = proj["key"]
            entries = locked.get(pk) or []
            st.session_state[_sel_key(workflow_prefix, pk)] = [
                str(entry.get("id") or "").strip()
                for entry in entries
                if isinstance(entry, dict) and str(entry.get("id") or "").strip()
            ]


def _clear_session_team_lock() -> None:
    st.session_state.pop(SHARED_LOCK_KEY, None)
    st.session_state.pop(SHARED_LOCKED_VALUES_KEY, None)
    for workflow_prefix in WORKFLOW_PREFIXES:
        st.session_state.pop(_lock_key(workflow_prefix), None)
        st.session_state.pop(_locked_values_key(workflow_prefix), None)
        st.session_state.pop(_restored_key(workflow_prefix), None)


def is_team_filter_locked(prefix: str) -> bool:
    sync_team_filter_from_session(prefix)
    return _session_team_lock_active() or bool(st.session_state.get(_lock_key(prefix)))


def load_team_catalog(project_key: str, *, force: bool = False) -> list[dict[str, Any]]:
    cache_key = _catalog_cache_key(project_key)
    if force or cache_key not in st.session_state:
        discovered: list[dict[str, Any]] = []
        try:
            discovered = jira_client.discover_project_teams(project_key)
        except Exception:
            discovered = []
        st.session_state[cache_key] = jira_teams.merge_team_catalog(project_key, discovered)
    return list(st.session_state[cache_key] or [])


def get_selected_team_ids(prefix: str, project_key: str) -> list[str]:
    if is_team_filter_locked(prefix):
        locked = _locked_values_for_prefix(prefix)
        entries = locked.get(project_key) or []
        return [str(e.get("id") or "").strip() for e in entries if str(e.get("id") or "").strip()]
    raw = st.session_state.get(_sel_key(prefix, project_key)) or []
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def team_filter_summary(prefix: str) -> str:
    parts: list[str] = []
    for proj in config.PROJECTS:
        pk = proj["key"]
        ids = get_selected_team_ids(prefix, pk)
        if not ids:
            continue
        catalog = {t["id"]: t["name"] for t in load_team_catalog(pk)}
        names = [catalog.get(tid, tid) for tid in ids]
        parts.append(f"{pk}: {', '.join(names)}")
    if not parts:
        return "All teams (no Team filter)"
    return " + ".join(parts)


def team_filters_for_snapshot(prefix: str) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for proj in config.PROJECTS:
        pk = proj["key"]
        ids = get_selected_team_ids(prefix, pk)
        if not ids:
            continue
        catalog = {t["id"]: t["name"] for t in load_team_catalog(pk)}
        out[pk] = [{"id": tid, "name": catalog.get(tid, tid)} for tid in ids]
    return out


def format_snapshot_team_filters(snapshot: dict[str, Any] | None) -> str:
    if snapshot is None:
        return ""
    filters = snapshot.get("jira_team_filters") or {}
    if not isinstance(filters, dict) or not filters:
        return "All teams (no Team filter)"
    parts: list[str] = []
    for proj in config.PROJECTS:
        pk = proj["key"]
        entries = filters.get(pk) or []
        if not isinstance(entries, list) or not entries:
            continue
        names = [
            jira_teams.normalize_team_display_name(str(e.get("name") or e.get("id") or ""))
            for e in entries
            if isinstance(e, dict) and str(e.get("id") or e.get("name") or "").strip()
        ]
        names = [n for n in names if n]
        if names:
            parts.append(f"{pk}: {', '.join(names)}")
    if not parts:
        return "All teams (no Team filter)"
    return " + ".join(parts)


def apply_snapshot_team_filters(prefix: str, snapshot: dict[str, Any] | None) -> None:
    if not snapshot or st.session_state.get(_restored_key(prefix)):
        return
    filters = snapshot.get("jira_team_filters") or {}
    if not isinstance(filters, dict) or not filters:
        return
    locked_values: dict[str, list[dict[str, str]]] = {}
    for proj in config.PROJECTS:
        pk = proj["key"]
        entries = filters.get(pk) or []
        if not isinstance(entries, list):
            continue
        ids = [str(e.get("id") or "").strip() for e in entries if isinstance(e, dict)]
        ids = [i for i in ids if i]
        st.session_state[_sel_key(prefix, pk)] = ids
        if ids:
            locked_values[pk] = [
                {"id": tid, "name": str(e.get("name") or tid)}
                for tid, e in zip(ids, entries)
                if isinstance(e, dict)
            ]
    if locked_values:
        _propagate_team_lock(locked_values)
        st.session_state[_restored_key(prefix)] = True


def _collect_locked_values(prefix: str) -> dict[str, list[dict[str, str]]]:
    locked: dict[str, list[dict[str, str]]] = {}
    for proj in config.PROJECTS:
        pk = proj["key"]
        catalog = {t["id"]: t["name"] for t in load_team_catalog(pk)}
        if is_team_filter_locked(prefix):
            entries = _locked_values_for_prefix(prefix).get(pk) or []
            picked = {
                str(entry.get("id") or "").strip(): str(entry.get("name") or entry.get("id") or "")
                for entry in entries
                if isinstance(entry, dict) and str(entry.get("id") or "").strip()
            }
        else:
            picked = {
                tid: catalog.get(tid, tid)
                for tid in (st.session_state.get(_sel_key(prefix, pk)) or [])
                if str(tid).strip()
            }
        if picked:
            locked[pk] = [{"id": tid, "name": name} for tid, name in picked.items()]
    return locked


def lock_team_filter(prefix: str, *, on_change_clear: Callable[[], None] | None = None) -> None:
    locked = _collect_locked_values(prefix)
    _propagate_team_lock(locked)
    for workflow_prefix in WORKFLOW_PREFIXES:
        clear_issue_caches_for_prefix(
            workflow_prefix,
            extra_clear=on_change_clear if workflow_prefix == _norm_prefix(prefix) else None,
        )


def ensure_team_filter_locked(
    prefix: str,
    *,
    on_change_clear: Callable[[], None] | None = None,
) -> None:
    """Lock team filter for the session when teams are selected (Continue / lock-in)."""
    sync_team_filter_from_session(prefix)
    if is_team_filter_locked(prefix):
        return
    locked = _collect_locked_values(prefix)
    if not locked:
        return
    _propagate_team_lock(locked)
    clear_issue_caches_for_prefix(prefix, extra_clear=on_change_clear)


def unlock_team_filter(prefix: str, *, on_change_clear: Callable[[], None] | None = None) -> None:
    locked = _locked_values_for_prefix(prefix)
    _clear_session_team_lock()
    for workflow_prefix in WORKFLOW_PREFIXES:
        for proj in config.PROJECTS:
            pk = proj["key"]
            entries = locked.get(pk) or []
            st.session_state[_sel_key(workflow_prefix, pk)] = [
                str(e.get("id") or "").strip()
                for e in entries
                if str(e.get("id") or "").strip()
            ]
        clear_issue_caches_for_prefix(
            workflow_prefix,
            extra_clear=on_change_clear if workflow_prefix == _norm_prefix(prefix) else None,
        )


def render_team_filter_panel(
    prefix: str,
    *,
    on_change_clear: Callable[[], None] | None = None,
) -> None:
    """Pick Jira Team(s) per project; optional lock."""
    sync_team_filter_from_session(prefix)
    p = _norm_prefix(prefix).rstrip("_")
    st.markdown("### Jira Team filter")
    st.caption(
        "Filter tickets by the Jira **Team** field (e.g. Glofox Insights Customize vs "
        "Ignite Insights Customize). Leave empty to include all teams."
    )

    _, refresh_col = st.columns([5, 1])
    with refresh_col:
        if st.button("Refresh teams", key=f"{p}_teams_refresh", use_container_width=True):
            for proj in config.PROJECTS:
                st.session_state.pop(_catalog_cache_key(proj["key"]), None)
            clear_issue_caches_for_prefix(prefix, extra_clear=on_change_clear)
            st.rerun()

    if is_team_filter_locked(prefix):
        summary = team_filter_summary(prefix)
        st.markdown(
            '<div class="jt-banner jt-banner--info" style="margin-bottom:12px">'
            f"<strong>Team filter locked for this session</strong> — {esc(summary)}. "
            "Applies across Ticket Review, Release Notes, and SHIPIT until you click "
            "<strong>Unlock team filter</strong>."
            "</div>",
            unsafe_allow_html=True,
        )
        confirm_key = f"{p}_teams_unlock_confirm"
        if st.session_state.get(confirm_key):
            if st.button("Confirm unlock (all apps)", key=f"{p}_teams_unlock_yes", type="primary"):
                st.session_state.pop(confirm_key, None)
                unlock_team_filter(prefix, on_change_clear=on_change_clear)
                st.rerun()
            if st.button("Cancel", key=f"{p}_teams_unlock_no"):
                st.session_state.pop(confirm_key, None)
                st.rerun()
        elif st.button("Unlock team filter", key=f"{p}_teams_unlock"):
            st.session_state[confirm_key] = True
            st.warning(
                "Unlocking clears the session-wide team lock for **Ticket Review, "
                "Release Notes, and SHIPIT**. Confirm to broaden ticket scope."
            )
            st.rerun()
        return

    for proj in config.PROJECTS:
        pk = proj["key"]
        catalog = load_team_catalog(pk)
        if not catalog:
            st.info(f"No Team values for {pk} yet. Click **Refresh teams**.")
            continue
        options = [t["id"] for t in catalog]
        labels = {t["id"]: t["name"] for t in catalog}
        st.markdown(f"**{pk}** ({proj.get('name', pk)})")
        st.multiselect(
            f"{pk} Team(s)",
            options=options,
            format_func=lambda tid: labels.get(tid, tid),
            key=_sel_key(prefix, pk),
        )
        picked = get_selected_team_ids(prefix, pk)
        if picked:
            st.caption("Selected: " + ", ".join(labels.get(t, t) for t in picked))

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Lock team filter", key=f"{p}_teams_lock", use_container_width=True):
            lock_team_filter(prefix, on_change_clear=on_change_clear)
            st.rerun()
    with c2:
        st.caption(
            "Locking saves your team split for the entire session (all apps). "
            "Unlock only when you need to change teams."
        )

    if any(get_selected_team_ids(prefix, p["key"]) for p in config.PROJECTS):
        st.markdown(f"**Active filter:** {esc(team_filter_summary(prefix))}")
