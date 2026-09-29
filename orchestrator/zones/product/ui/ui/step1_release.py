"""Step 1 -- Select Release."""

from __future__ import annotations

import logging

import streamlit as st

import config
import jira_client
from release_platform.ui.deployer_flow import deployer_go, is_quick_start
from release_platform.ui.helpers import (
    INITIAL_RELEASE_NAMES,
    apply_shared_release_to_deployer,
    clear_deployer_session,
    esc,
    populate_from_shared,
    reset_deployer_downstream_state,
    ss_default,
)

logger = logging.getLogger(__name__)


def render() -> None:
    standalone = is_quick_start()
    st.markdown("## Select a Release")
    if standalone:
        st.caption(
            "Choose the fix version you deployed. You will pick which tickets to update on the next step."
        )

    if populate_from_shared("wiz_"):
        if standalone:
            st.info(
                "Using your last release selection — change below if needed.",
                icon=":material/info:",
            )
        else:
            st.info(
                "Pre-filled from your shared release selection. Confirm the project and version below.",
                icon=":material/info:",
            )
    apply_shared_release_to_deployer()

    proj_names = [p["name"] for p in config.PROJECTS]
    ss_default("wiz_project_idx", 0)

    cols = st.columns(len(proj_names))
    for i, pname in enumerate(proj_names):
        with cols[i]:
            is_active = st.session_state.get("wiz_project_idx") == i
            btn_type = "primary" if is_active else "secondary"
            if st.button(pname, key=f"proj_pill_{i}", type=btn_type, use_container_width=True):
                st.session_state["wiz_project_idx"] = i
                clear_deployer_session(full_reset=True)
                for k in list(st.session_state.keys()):
                    if k.startswith(("versions_", "counts_")):
                        del st.session_state[k]
                st.rerun()

    selected_idx = st.session_state.get("wiz_project_idx", 0)
    proj = config.PROJECTS[selected_idx]
    proj_key = proj["key"]

    st.markdown("")

    cache_key = f"versions_{proj_key}"
    if cache_key not in st.session_state:
        try:
            with st.spinner(f"Loading {proj_key} releases\u2026"):
                st.session_state[cache_key] = jira_client.get_project_versions(
                    proj_key, released=False,
                )
        except Exception as e:
            st.error(f"Cannot connect to Jira: {e}")
            st.stop()

    versions = [
        v for v in st.session_state[cache_key]
        if v.get("name", "").strip().lower() not in INITIAL_RELEASE_NAMES
    ]

    if not versions:
        st.info(f"No unreleased releases found in **{proj_key}**.")
        st.stop()

    counts_key = f"counts_{proj_key}"
    if counts_key not in st.session_state:
        with st.spinner("Loading ticket counts\u2026"):
            def _count_one(v: dict) -> tuple[str, int]:
                try:
                    return v["id"], jira_client.get_issue_count_for_version(proj_key, v["id"])
                except Exception:
                    logger.debug(
                        "Failed to fetch ticket count for version %s",
                        v.get("id"),
                        exc_info=True,
                    )
                    return v["id"], -1

            # Read-only preflight — optional bounded concurrency via env.
            counted = jira_client.readonly_map(_count_one, versions)
            st.session_state[counts_key] = {vid: n for vid, n in counted}
    version_counts = st.session_state[counts_key]

    version_by_name = {v["name"]: v for v in versions}
    version_names = list(version_by_name.keys())

    current_id = st.session_state.get("wiz_release_id")
    default_idx = 0
    if current_id:
        for i, v in enumerate(versions):
            if v["id"] == current_id:
                default_idx = i
                break

    picked_name = st.selectbox(
        "Fix version",
        options=version_names,
        index=default_idx,
        key="wiz_release_select",
        help="Unreleased fix versions in this project, newest first in Jira.",
    )
    picked = version_by_name[picked_name]
    count = version_counts.get(picked["id"], -1)
    count_label = f"{count} ticket{'s' if count != 1 else ''}" if count >= 0 else "ticket count unknown"

    if st.session_state.get("wiz_release_id") != picked["id"]:
        st.session_state["wiz_release_id"] = picked["id"]
        st.session_state["wiz_release"] = picked
        st.session_state["wiz_project"] = proj_key
        st.session_state[f"shared_release_{proj_key}"] = picked
        reset_deployer_downstream_state()

    desc = picked.get("description", "")
    st.markdown(
        f'<div class="review-card" style="margin-top:8px">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:12px">'
        f'<div><strong style="font-size:1.1rem">{esc(picked_name)}</strong>'
        f' <span style="font-size:.85rem;opacity:.55">\u00b7 {esc(count_label)}</span></div>'
        f'<span style="color:var(--jt-accent);font-weight:600;font-size:.85rem">\u2713 Selected</span>'
        f"</div>"
        + (f'<div style="font-size:.85rem;opacity:.55;margin-top:6px">{esc(desc)}</div>' if desc else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("")
    col_l, col_r = st.columns([5, 1])
    with col_r:
        next_label = "Continue \u2192" if is_quick_start() else "Next \u2192"
        if st.button(
            next_label,
            type="primary",
            use_container_width=True,
            disabled=st.session_state.get("wiz_release_id") is None,
        ):
            deployer_go(2)
