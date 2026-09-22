"""Release Deployer wizard routing — full workflow (6 steps) vs quick start (5 steps)."""

from __future__ import annotations

import streamlit as st

from release_platform.ui.helpers import go
from release_platform.ui.workflow import is_deployer_standalone

FULL_STEP_LABELS = [
    "Select Release",
    "Tickets",
    "Exclude Tickets",
    "Deployment Info",
    "Review",
    "Deploy",
]

QUICK_STEP_LABELS = [
    "Release",
    "Select Tickets",
    "Deployment Info",
    "Review",
    "Deploy",
]


def is_quick_start() -> bool:
    return is_deployer_standalone()


def step_labels() -> list[str]:
    return QUICK_STEP_LABELS if is_quick_start() else FULL_STEP_LABELS


def step_count() -> int:
    return len(step_labels())


def deployer_go(step: int) -> None:
    """Navigate to wizard step and rerun."""
    from session_persist import persist_deploy_draft, persist_session

    persist_deploy_draft(dict(st.session_state))
    persist_session(dict(st.session_state))
    go(step)


def back_from_deploy_info() -> int:
    return 2 if is_quick_start() else 3


def back_from_review() -> int:
    return 3 if is_quick_start() else 4


def back_from_execute() -> int:
    return 4 if is_quick_start() else 5


def deploy_checkbox_key(ticket_key: str) -> str:
    return f"wiz_dep_chk_{ticket_key}"


def init_deploy_ticket_selection(
    candidates: list[dict],
    *,
    default_all: bool = True,
    allowed_keys: set[str] | None = None,
) -> None:
    """Initialize per-ticket deploy checkboxes."""
    if "wiz_deploy_selected_keys" in st.session_state:
        return

    selected: set[str] = set()
    for iss in candidates:
        key = iss["key"]
        if allowed_keys is not None:
            include = key in allowed_keys
        else:
            include = default_all
        if include:
            selected.add(key)
        st.session_state.setdefault(deploy_checkbox_key(key), include)
    st.session_state["wiz_deploy_selected_keys"] = selected


def read_deploy_ticket_selection(candidates: list[dict]) -> set[str]:
    selected: set[str] = set()
    default = st.session_state.get("wiz_deploy_selected_keys", set())
    for iss in candidates:
        key = iss["key"]
        if st.session_state.get(deploy_checkbox_key(key), key in default):
            selected.add(key)
    return selected


def set_deploy_ticket_selection(candidates: list[dict], selected_keys: set[str]) -> None:
    st.session_state["wiz_deploy_selected_keys"] = selected_keys
    for iss in candidates:
        key = iss["key"]
        st.session_state[deploy_checkbox_key(key)] = key in selected_keys


from release_platform.ui.ticket_selection_page import render_empty_selection_hint, render_stay_on_page_hint


def render_deploy_ticket_picker(
    candidates: list[dict],
    *,
    grouped: dict[str, list[dict]] | None = None,
    filled_clients: list[str] | None = None,
    title: str = "Tickets to update in Jira",
    caption: str | None = None,
) -> set[str]:
    """Checkbox list with select all / none. Returns selected ticket keys."""
    if caption is None:
        caption = (
            "Checked tickets receive a deployment comment and transition to **Done**. "
            "**Uncheck tickets that failed in production** — they stay unchanged."
        )

    st.markdown(f"### {title}")
    st.caption(caption)
    render_stay_on_page_hint(action_label="Next →")

    btn_all, btn_none, stats = st.columns([1, 1, 3])
    with btn_all:
        if st.button("Select all", key="wiz_dep_select_all"):
            set_deploy_ticket_selection(candidates, {iss["key"] for iss in candidates})
            st.rerun()
    with btn_none:
        if st.button("Deselect all", key="wiz_dep_deselect_all"):
            set_deploy_ticket_selection(candidates, set())
            st.rerun()

    st.markdown("")

    if grouped and filled_clients:
        for client in filled_clients:
            client_issues = grouped.get(client, [])
            if not client_issues:
                continue
            st.markdown(f"**{client}**")
            for iss in client_issues:
                _render_one_deploy_checkbox(iss)
    else:
        for iss in candidates:
            _render_one_deploy_checkbox(iss)

    selected_keys = read_deploy_ticket_selection(candidates)
    st.session_state["wiz_deploy_selected_keys"] = selected_keys

    with stats:
        st.caption(f"**{len(selected_keys)}** of **{len(candidates)}** selected")

    if not selected_keys:
        render_empty_selection_hint(mode_label="deploy tickets")
        st.error("Select at least one ticket to continue.")

    return selected_keys


def _render_one_deploy_checkbox(iss: dict) -> None:
    key = iss["key"]
    summary = iss.get("fields", {}).get("summary", "")
    chk_key = deploy_checkbox_key(key)
    if chk_key not in st.session_state:
        default = st.session_state.get("wiz_deploy_selected_keys", set())
        st.session_state[chk_key] = key in default
    st.checkbox(f"**{key}** — {summary}", key=chk_key)
