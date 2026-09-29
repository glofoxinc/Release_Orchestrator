"""Step 1 — Select tickets by fix version or board status."""

from __future__ import annotations

import streamlit as st

import config
from release_platform.ui.helpers import get_snapshot, populate_from_shared, render_project_release_picker
from release_platform.ui.ticket_review.jira_team_filter import (
    apply_snapshot_team_filters,
    clear_ticket_review_issue_caches,
    ensure_team_filter_locked,
    render_team_filter_panel,
    team_filter_summary,
)
from release_platform.ui.ticket_review.selection import (
    MODE_FIX_VERSION,
    MODE_SESSION_KEY,
    MODE_STATUS,
    apply_default_status_selections,
    apply_snapshot_selection_context,
    get_selected_statuses,
    get_selection_mode,
    has_step1_selection,
    load_project_status_options,
    on_mode_change,
    selection_summary,
    status_session_key,
)
from release_platform.ui.workflow import render_action_hint

_PREFIX = "tr_"


def _go(step: int) -> None:
    st.session_state["tr_step"] = step
    st.rerun()


def _render_status_picker() -> None:
    apply_default_status_selections(force=False)
    for proj in config.PROJECTS:
        pk = proj["key"]
        st.markdown(f"### {pk} board")
        options = load_project_status_options(pk)
        if not options:
            st.info(
                f"Could not load statuses for {pk}. Check Jira credentials and project access."
            )
            continue

        st.multiselect(
            f"{pk} statuses",
            options=options,
            key=status_session_key(pk),
            help="Tickets on this board matching any selected status will appear in the review list.",
        )
        selected = get_selected_statuses(pk)
        if selected:
            st.caption(f"Selected: {', '.join(selected)}")


def render() -> None:
    st.markdown("## Select Tickets")

    snap = get_snapshot()
    apply_snapshot_team_filters(snap)
    apply_snapshot_selection_context(snap)

    if MODE_SESSION_KEY not in st.session_state:
        st.session_state[MODE_SESSION_KEY] = MODE_FIX_VERSION

    prev_mode = st.session_state.get(MODE_SESSION_KEY, MODE_FIX_VERSION)
    st.radio(
        "Selection mode",
        options=[MODE_FIX_VERSION, MODE_STATUS],
        format_func=lambda m: "Fix version" if m == MODE_FIX_VERSION else "By status (board)",
        horizontal=True,
        key=MODE_SESSION_KEY,
        help=(
            "**Fix version** — pick unreleased Jira versions (standard release workflow). "
            "**By status** — pick workflow statuses per project (e.g. In Progress, In Review)."
        ),
    )
    if st.session_state[MODE_SESSION_KEY] != prev_mode:
        on_mode_change()
        st.rerun()

    mode = get_selection_mode()

    render_team_filter_panel()
    st.markdown("")

    if mode == MODE_FIX_VERSION:
        st.markdown(
            f"Pick a release from **one or both projects** ({config.project_label()}). "
            "Use the dropdown to select, switch, or choose **— None —** to deselect."
        )
        pre_filled = populate_from_shared(_PREFIX)
        if pre_filled:
            st.info("Releases pre-selected from a previous app. Change below if needed.")
        render_project_release_picker(
            _PREFIX,
            button_key_prefix="tr_sel",
            on_change_keys=("tr_grouped", "tr_selected_keys"),
        )
    else:
        st.markdown(
            f"For each project ({config.project_label()}), choose one or more Jira statuses. "
            "Tickets matching those statuses on your configured board scope will be loaded "
            "with assignee and summary in the next step."
        )
        _render_status_picker()

    if has_step1_selection(prefix=_PREFIX):
        summary = selection_summary(prefix=_PREFIX)
        team_summary = team_filter_summary()
        st.markdown("---")
        st.markdown(f"**Selected:** {summary}")
        st.markdown(f"**Team filter:** {team_summary}")

        continue_label = (
            "Confirm fix version(s) \u2192"
            if mode == MODE_FIX_VERSION
            else "Confirm statuses \u2192"
        )
        if st.button(continue_label, type="primary", key="tr_s1_next"):
            clear_ticket_review_issue_caches()
            st.session_state.pop("tr_grouped", None)
            from release_platform.ui.ticket_review.selection import lock_ticket_source
            from release_platform.ui import ticket_source as ts

            ensure_team_filter_locked()
            lock_ticket_source()
            st.session_state["tr_source_fp"] = ts.selection_fingerprint("tr_")
            st.session_state["tr_step"] = 2
            from session_persist import persist_session

            persist_session(dict(st.session_state))
            _go(2)
        hint = (
            "Loads tickets in the selected fix version(s) for review."
            if mode == MODE_FIX_VERSION
            else "Loads tickets matching the selected board statuses for review."
        )
        render_action_hint(hint)
    else:
        if mode == MODE_FIX_VERSION:
            st.info("Select at least one fix version to continue.")
        else:
            st.info("Select at least one status on PIC or AN to continue.")
