"""Step 1 — Select tickets by fix version, status, or locked Ticket Review list."""

from __future__ import annotations

import streamlit as st

import config
from release_platform.ui import jira_team_filter as jtf
from release_platform.ui import ticket_source as ts
from release_platform.ui.helpers import (
    RN_DRAFT_RESET_KEYS,
    continue_with_drift_gate,
    esc,
    get_snapshot,
    navigate_to_app,
    populate_from_shared,
    render_project_release_picker,
    render_ticket_table,
)
from release_platform.ui.ticket_selection_page import clear_step2_loaded
from release_platform.ui.workflow import is_release_notes_standalone, render_action_hint

_PREFIX = "rn_"


def _go(step: int) -> None:
    from session_persist import persist_session

    persist_session(dict(st.session_state))
    st.session_state["rn_step"] = step
    st.rerun()


def _clear_step2_ticket_state() -> None:
    """Drop ticket list caches when source selection changes."""
    clear_step2_loaded(_PREFIX)
    ts.clear_locked_ticket_source(_PREFIX)
    for key in RN_DRAFT_RESET_KEYS:
        st.session_state.pop(key, None)
    st.session_state.pop("rn_issues_fp", None)
    for key in list(st.session_state.keys()):
        if key.startswith("rn_chk_"):
            st.session_state.pop(key, None)
    jtf.clear_issue_caches_for_prefix(_PREFIX)


def _prepare_step2() -> bool:
    _clear_step2_ticket_state()
    jtf.ensure_team_filter_locked(_PREFIX, on_change_clear=_clear_step2_ticket_state)
    try:
        ts.lock_ticket_source(_PREFIX)
    except ValueError as exc:
        st.error(str(exc))
        return False
    st.session_state["rn_source_fp"] = ts.selection_fingerprint(_PREFIX)
    return True


def _render_snapshot_banner() -> None:
    snap = get_snapshot()
    if not snap:
        return
    count = len(snap.get("ticket_keys", []))
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
    issues = snap.get("issues", [])
    if issues:
        with st.expander(f"View all {count} tickets (Owner / Status / Link)", expanded=False):
            render_ticket_table(issues)


def render() -> None:
    standalone = is_release_notes_standalone()
    snap = get_snapshot()
    has_lock = bool(snap and snap.get("ticket_keys"))

    jtf.apply_snapshot_team_filters(_PREFIX, snap)
    ts.apply_snapshot_selection_context(_PREFIX, snap)

    st.markdown("## Select Tickets")

    if standalone:
        st.markdown(
            f"**Quick start** — load tickets by **fix version** or **Jira status** "
            f"({config.project_label()}). Optional **Team filter** below. "
            "Ticket Review lock is not required."
        )
    elif has_lock:
        st.markdown(
            "Using the **locked list** from Ticket Review. "
            "Choose **Fix version** below if the release notes need a version header; "
            "otherwise stay on **By status** (version and date are omitted from the document)."
        )
        _render_snapshot_banner()
    else:
        st.error(
            "**Ticket Review lock-in is required** for the full workflow — or use quick start."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Open Ticket Review \u2192", type="primary", key="rn_s1_goto_tr"):
                navigate_to_app("ticket_review")
        with c2:
            from release_platform.ui.workflow import enable_release_notes_standalone

            if st.button("Quick start instead \u2192", key="rn_s1_quick_start"):
                enable_release_notes_standalone()
                st.rerun()
        return

    ts.render_selection_mode_radio(_PREFIX)
    mode = ts.get_selection_mode(_PREFIX)

    jtf.render_team_filter_panel(_PREFIX, on_change_clear=_clear_step2_ticket_state)
    st.markdown("")

    if mode == ts.MODE_FIX_VERSION:
        st.markdown("### Fix version")
        st.markdown(
            f"Pick a release from **one or both projects** ({config.project_label()}). "
            "Use **— None —** to deselect a project."
        )
        pre_filled = populate_from_shared(_PREFIX)
        if pre_filled:
            st.info("Releases pre-selected from a previous app. Change below if needed.")
        render_project_release_picker(
            _PREFIX,
            button_key_prefix="rn_sel",
            on_change_keys=RN_DRAFT_RESET_KEYS,
        )
    else:
        st.markdown("### By status (board)")
        st.markdown(
            f"Choose Jira statuses per project — independent of fix version. "
            f"**PIC** defaults to Review; **AN** defaults to Passed QA."
        )
        ts.render_status_picker(_PREFIX)

    if not ts.has_step1_selection(prefix=_PREFIX):
        if has_lock:
            st.markdown("---")
            st.markdown("**Using locked ticket list** from Ticket Review.")
            if standalone:
                if st.button("Continue \u2192", type="primary", key="rn_s1_next_lock"):
                    if _prepare_step2():
                        _go(2)
            else:
                clicked = st.button("Continue \u2192", type="primary", key="rn_s1_next_lock")
                if continue_with_drift_gate("rn", clicked=clicked):
                    if _prepare_step2():
                        _go(2)
            render_action_hint("Loads locked tickets for the release notes document.")
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
        if st.button(continue_label, type="primary", key="rn_s1_next"):
            if _prepare_step2():
                _go(2)
        render_action_hint(
            "Step 2: review tickets. Step 3: edit content. Step 4: preview and download .docx."
        )
    else:
        clicked = st.button(continue_label, type="primary", key="rn_s1_next")
        if continue_with_drift_gate("rn", clicked=clicked):
            if _prepare_step2():
                _go(2)
        render_action_hint(
            "Step 2: review tickets. Step 3: edit content. Step 4: preview and download .docx."
        )
