"""Quick start Step 2 — load tickets and choose which get post-deploy updates."""

from __future__ import annotations

import streamlit as st

import config
import jira_client
from release_platform.ui.css import status_badge
from release_platform.ui.deployer_flow import deployer_go, init_deploy_ticket_selection, render_deploy_ticket_picker
from release_platform.ui.helpers import (
    apply_deploy_issue_filter,
    esc,
    get_project_cfg,
    go,
    reset_deploy_selection_for_issues,
    reset_deployer_downstream_state,
    ticket_issues_cache_key,
)
from release_platform.ui.ticket_selection_page import render_stay_on_page_hint


def render() -> None:
    proj_key = st.session_state.get("wiz_project", "")
    release = st.session_state.get("wiz_release", {})
    proj_cfg = get_project_cfg(proj_key)
    if not proj_cfg:
        go(1)
        return

    multi_client = proj_cfg["multi_client"]
    version_name = release.get("name", "?")

    title_col, refresh_col = st.columns([6, 1])
    with title_col:
        st.markdown(f"## Select Tickets — {version_name}")
    with refresh_col:
        st.markdown("")
        if st.button("\U0001f504 Refresh", use_container_width=True, key="quick_t2_refresh"):
            issues_key = ticket_issues_cache_key(
                proj_key, release.get("id"), prefix="wiz_issues_",
            )
            st.session_state.pop(issues_key, None)
            reset_deployer_downstream_state()
            st.rerun()

    st.markdown(
        "All tickets on this fix version are listed below. "
        "Uncheck any that **failed in production** or should not be updated."
    )
    render_stay_on_page_hint(action_label="Next →")

    issues_key = ticket_issues_cache_key(proj_key, release.get("id"), prefix="wiz_issues_")
    if issues_key not in st.session_state:
        try:
            with st.spinner("Loading tickets from Jira…"):
                st.session_state[issues_key] = jira_client.get_issues_for_version(
                    proj_key, release["id"],
                )
        except Exception as exc:
            st.error(f"Failed to load tickets: {exc}")
            if st.button("\u2190 Back to Release", key="quick_t2_back_err"):
                go(1)
            st.stop()

    raw_issues = st.session_state[issues_key]
    if not raw_issues:
        st.warning("No tickets on this fix version.")
        if st.button("\u2190 Back to Release", key="quick_t2_back_empty"):
            go(1)
        st.stop()

    issues, filter_meta = apply_deploy_issue_filter(raw_issues, proj_key, release)
    st.session_state["wiz_deploy_filter_meta"] = filter_meta
    st.session_state["wiz_issues"] = issues
    reset_deploy_selection_for_issues(issues)

    if multi_client:
        grouped = jira_client.group_issues_by_client(issues, project_key=proj_key)
        st.session_state["wiz_grouped"] = grouped
    else:
        grouped = {}

    done_count = sum(
        1 for iss in issues
        if iss["fields"]["status"].get("statusCategory", {}).get("key") == "done"
    )
    pending_count = len(issues) - done_count

    m1, m2, m3 = st.columns(3)
    m1.metric("Total", len(issues))
    m2.metric("Pending", pending_count)
    m3.metric("Already Done", done_count)

    if done_count:
        st.info(
            f"{done_count} ticket(s) are already **Done** — deployment comments may already exist. "
            "Uncheck them if you do not want to post again."
        )

    deploy_candidates: list[dict] = list(issues)
    init_deploy_ticket_selection(deploy_candidates, default_all=True)

    selected_keys = render_deploy_ticket_picker(
        deploy_candidates,
        grouped=grouped if multi_client else None,
        filled_clients=list(grouped.keys()) if multi_client else None,
        title="Which tickets should be updated?",
    )

    with st.expander(f"Preview all {len(issues)} tickets", expanded=False):
        browse = f"{config.JIRA_BASE_URL}/browse"
        for iss in issues:
            status = iss["fields"]["status"]
            badge = status_badge(
                status["name"],
                status.get("statusCategory", {}).get("key", "new"),
            )
            included = iss["key"] in selected_keys
            mark = "\u2713" if included else "\u2717"
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;padding:4px 0">'
                f'<span style="opacity:.6">{mark}</span>'
                f'<code style="font-weight:600"><a href="{browse}/{iss["key"]}" '
                f'target="_blank" style="text-decoration:none;color:inherit">'
                f'{esc(iss["key"])}</a></code>'
                f'<span style="flex:1">{esc(iss.get("fields", {}).get("summary", ""))}</span>'
                f"{badge}</div>",
                unsafe_allow_html=True,
            )

    st.markdown("")
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if st.button("\u2190 Back", use_container_width=True, key="quick_t2_back"):
            go(1)
    with col_r:
        if st.button(
            "Next \u2192",
            type="primary",
            use_container_width=True,
            disabled=not selected_keys,
            key="quick_t2_next",
        ):
            deployer_go(3)
