"""Step 1 — Select tickets by fix version or Jira status for the SHIPIT ticket."""

from __future__ import annotations

import streamlit as st

import config
import jira_client
from release_platform.ui import jira_team_filter as jtf
from release_platform.ui import ticket_source as ts
from release_platform.ui.helpers import (
    continue_with_drift_gate,
    esc,
    filter_snapshot_issues,
    get_snapshot,
    navigate_to_app,
    populate_from_shared,
    render_project_release_picker,
    render_ticket_table,
)
from release_platform.ui.workflow import is_service_ticket_standalone, render_action_hint

_PREFIX = "stk_"


def _go(step: int) -> None:
    from release_platform.ui.service_ticket.nav import go_step

    go_step(step)


def _render_snapshot_banner() -> None:
    snap = get_snapshot()
    if not snap:
        return
    count = len(snap.get("ticket_keys", []))
    qa_excluded = snap.get("qa_excluded_keys") or []
    if qa_excluded:
        count = max(0, count - len(qa_excluded))
    locked_at = snap.get("locked_at", "?")
    team_line = jtf.format_snapshot_team_filters(snap)
    team_html = (
        f"<br><strong>Jira Team filter:</strong> {esc(team_line)}"
        if team_line
        else ""
    )
    st.markdown(
        f'<div style="padding:10px 16px;border-radius:10px;'
        f"background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);"
        f'margin-bottom:12px;font-size:.85rem">'
        f"<strong>Locked ticket list</strong> from Ticket Review "
        f"&mdash; {count} tickets, locked at {esc(locked_at)}"
        f"{team_html}"
        f"</div>",
        unsafe_allow_html=True,
    )
    issues = filter_snapshot_issues(snap)
    if issues:
        with st.expander(f"View all {count} tickets (Owner / Status / Link)", expanded=False):
            render_ticket_table(issues)


def _clear_stk_issue_cache() -> None:
    jtf.clear_issue_caches_for_prefix(_PREFIX)
    st.session_state.pop("stk_issues", None)
    st.session_state.pop("stk_extracted", None)


def _clear_stk_fetch_cache() -> None:
    _clear_stk_issue_cache()
    ts.clear_locked_ticket_source(_PREFIX)


def _team_ids_for_project(project_key: str) -> list[str] | None:
    ids = jtf.get_selected_team_ids(_PREFIX, project_key)
    return ids if ids else None


def _fetch_and_extract() -> None:
    """Fetch tickets and extract info from snapshot, fix version, or status filter."""
    ts.apply_locked_ticket_source(_PREFIX)
    snap = get_snapshot()
    standalone = is_service_ticket_standalone()
    mode = ts.get_effective_selection_mode(_PREFIX)

    use_snapshot = (
        not standalone
        and snap
        and snap.get("issues")
    )
    if use_snapshot:
        all_issues = filter_snapshot_issues(snap)
    else:
        all_issues = ts.fetch_combined_issues(
            _PREFIX,
            issues_cache_prefix="_stk_issues_",
            team_ids_for_project=_team_ids_for_project,
        )

    st.session_state["stk_issues"] = all_issues

    extracted = []
    for iss in all_issues:
        key = iss["key"]
        summary = iss.get("fields", {}).get("summary", "")
        info = jira_client.extract_ticket_info(summary, key)
        info["ticket"] = key
        info["summary"] = summary
        extracted.append(info)
    st.session_state["stk_extracted"] = extracted


def render() -> None:
    standalone = is_service_ticket_standalone()
    snap = get_snapshot()
    has_lock = bool(snap and snap.get("ticket_keys"))

    jtf.apply_snapshot_team_filters(_PREFIX, snap)
    ts.apply_snapshot_selection_context(_PREFIX, snap)

    st.markdown("## Select Tickets")

    if standalone:
        st.markdown(
            f"**Quick start** — load tickets by **fix version** or **Jira status** "
            f"({config.project_label()}). Optional **Team filter** below. "
            "Ticket Review and Release Notes are not required."
        )
    elif has_lock:
        st.markdown(
            "Using the **locked list** from Ticket Review. "
            "Choose **Fix version** below if the SHIPIT summary should include a release version; "
            "otherwise stay on **By status** (summary omits version; set schedule manually on Details)."
        )
        _render_snapshot_banner()
    else:
        st.error(
            "**Ticket Review lock-in is required** for the full workflow — or use quick start."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Open Ticket Review \u2192", type="primary", key="stk_s1_goto_tr"):
                navigate_to_app("ticket_review")
        with c2:
            from release_platform.ui.workflow import enable_service_ticket_standalone

            if st.button("Quick start instead \u2192", key="stk_s1_quick_start"):
                enable_service_ticket_standalone()
                st.rerun()
        return

    ts.render_selection_mode_radio(_PREFIX)
    mode = ts.get_selection_mode(_PREFIX)

    jtf.render_team_filter_panel(_PREFIX, on_change_clear=_clear_stk_fetch_cache)
    st.markdown("")

    if mode == ts.MODE_FIX_VERSION:
        st.markdown(
            f"Pick a release from **one or both projects** ({config.project_label()})."
        )
        pre_filled = populate_from_shared(_PREFIX)
        if pre_filled:
            st.info("Releases pre-selected from a previous app. Change below if needed.")
        render_project_release_picker(
            _PREFIX,
            button_key_prefix="stk_sel",
            on_change_keys=("stk_extracted", "stk_issues"),
        )
    else:
        st.markdown(
            f"Choose Jira statuses per project. **PIC** defaults to Review; "
            f"**AN** defaults to Passed QA."
        )
        ts.render_status_picker(_PREFIX)

    if not ts.has_step1_selection(prefix=_PREFIX):
        if has_lock:
            st.markdown("---")
            st.markdown("**Using locked ticket list** from Ticket Review.")
            if standalone:
                if st.button("Continue \u2192", type="primary", key="stk_s1_next_lock"):
                    jtf.ensure_team_filter_locked(_PREFIX, on_change_clear=_clear_stk_fetch_cache)
                    ts.lock_ticket_source(_PREFIX)
                    with st.spinner("Loading locked tickets\u2026"):
                        try:
                            _fetch_and_extract()
                        except Exception as exc:
                            st.error(f"Failed to load tickets: {exc}")
                            return
                    _go(2)
            else:
                clicked = st.button("Continue \u2192", type="primary", key="stk_s1_next_lock")
                if continue_with_drift_gate("stk", clicked=clicked):
                    jtf.ensure_team_filter_locked(_PREFIX, on_change_clear=_clear_stk_fetch_cache)
                    ts.lock_ticket_source(_PREFIX)
                    with st.spinner("Preparing tickets\u2026"):
                        try:
                            _fetch_and_extract()
                        except Exception as exc:
                            st.error(f"Failed to fetch tickets: {exc}")
                            return
                    _go(2)
            render_action_hint("Next: schedule, summary, and SharePoint link on Details.")
            return
        if mode == ts.MODE_FIX_VERSION:
            st.info("Select at least one fix version to continue.")
        else:
            st.info("Select at least one status on PIC or AN to continue.")
        return

    st.markdown("---")
    st.markdown(f"**Selected:** {ts.selection_summary(prefix=_PREFIX)}")
    st.markdown(f"**Team filter:** {jtf.team_filter_summary(_PREFIX)}")

    continue_label = ts.step1_continue_label(_PREFIX)
    if standalone:
        if st.button(continue_label, type="primary", key="stk_s1_next"):
            jtf.ensure_team_filter_locked(_PREFIX, on_change_clear=_clear_stk_fetch_cache)
            ts.lock_ticket_source(_PREFIX)
            _clear_stk_issue_cache()
            with st.spinner("Loading tickets from Jira\u2026"):
                try:
                    _fetch_and_extract()
                except Exception as exc:
                    st.error(f"Failed to fetch tickets: {exc}")
                    return
            _go(2)
        render_action_hint(
            "Next: enter schedule, summary, and your SharePoint link on the Details step."
        )
    else:
        clicked = st.button(continue_label, type="primary", key="stk_s1_next")
        if continue_with_drift_gate("stk", clicked=clicked):
            jtf.ensure_team_filter_locked(_PREFIX, on_change_clear=_clear_stk_fetch_cache)
            ts.lock_ticket_source(_PREFIX)
            _clear_stk_issue_cache()
            with st.spinner("Preparing tickets\u2026"):
                try:
                    _fetch_and_extract()
                except Exception as exc:
                    st.error(f"Failed to fetch tickets: {exc}")
                    return
            _go(2)
        render_action_hint(
            "Next: confirm schedule, summary, and SharePoint link on the Details step."
        )
