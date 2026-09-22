"""Step 5 — Review & Confirm."""

from __future__ import annotations

import streamlit as st

import config
from release_platform.ui.deployer_flow import (
    back_from_review,
    deployer_go,
    init_deploy_ticket_selection,
    is_quick_start,
    render_deploy_ticket_picker,
)
from release_platform.ui.helpers import (
    clear_deploy_results_cache,
    deploy_filled_is_valid,
    esc,
    first_filled_entry,
    get_deploy_filled_snapshot,
    get_project_cfg,
    get_snapshot_keys_for_release,
    go,
    issues_for_filled_client,
    render_deploy_filter_warnings,
    reset_deploy_selection_for_issues,
)


def _truncate_id(deployment_id: str, max_len: int = 28) -> str:
    if len(deployment_id) > max_len:
        return deployment_id[:max_len] + "\u2026"
    return deployment_id


def render() -> None:
    proj_key = st.session_state.get("wiz_project", "")
    release = st.session_state.get("wiz_release", {})
    proj_cfg = get_project_cfg(proj_key)
    if not proj_cfg:
        go(1)
        return

    multi_client = proj_cfg["multi_client"]
    issues = st.session_state.get("wiz_issues", [])
    if not is_quick_start():
        reset_deploy_selection_for_issues(issues)
    filled, skipped = get_deploy_filled_snapshot(proj_key, multi_client)
    filter_meta = st.session_state.get("wiz_deploy_filter_meta", {})

    if not deploy_filled_is_valid(filled):
        st.markdown(f"## Review  \u2014  {release.get('name', '?')}")
        st.warning(
            "No deployment info saved yet. Go back to **Deployment Info**, enter a "
            "deployment ID and time for **at least one client**, then click **Next** inside the form.",
            icon=":material/warning:",
        )
        if multi_client:
            st.info(
                "You can deploy one client now (e.g. Jetts only) and leave the others for a later run."
            )
        col_l, _, col_r = st.columns([1, 4, 1])
        with col_l:
            if st.button("\u2190 Back to Deployment Info", use_container_width=True):
                deployer_go(back_from_review())
        with col_r:
            if st.button("Start over", use_container_width=True):
                go(1)
        return

    st.session_state["wiz_filled"] = filled
    st.session_state["wiz_skipped"] = skipped

    st.markdown(f"## Review  \u2014  {release.get('name', '?')}")
    if not is_quick_start():
        render_deploy_filter_warnings(filter_meta, release.get("name", "?"))

    grouped = st.session_state.get("wiz_grouped", {}) if multi_client else {}
    snapshot_keys = get_snapshot_keys_for_release(proj_key, str(release.get("id", "")))
    filled_clients = list(filled.keys())

    deploy_candidates: list[dict] = []
    if multi_client:
        for client in filled_clients:
            deploy_candidates.extend(issues_for_filled_client(client, grouped))
    else:
        deploy_candidates = list(issues)

    if is_quick_start():
        selected_keys = set(st.session_state.get("wiz_deploy_selected_keys", set()))
        if not selected_keys:
            st.error("No tickets selected. Go back and choose at least one ticket.")
            if st.button("\u2190 Change ticket selection", key="quick_rev_back_sel"):
                deployer_go(2)
            return
        _render_quick_review_summary(
            proj_key, multi_client, filled, skipped, grouped, selected_keys,
        )
    else:
        init_deploy_ticket_selection(
            deploy_candidates,
            default_all=snapshot_keys is None,
            allowed_keys=snapshot_keys,
        )
        selected_keys = render_deploy_ticket_picker(
            deploy_candidates,
            grouped=grouped if multi_client else None,
            filled_clients=filled_clients if multi_client else None,
        )
        _render_full_review_details(
            proj_key, multi_client, filled, skipped, grouped, selected_keys,
        )

    total_tickets = _count_selected(multi_client, filled_clients, grouped, selected_keys)

    st.markdown("### What will happen")
    st.markdown(
        f"**{total_tickets} ticket(s)** will be processed. For each selected ticket:\n"
        f"1. Check for existing deployment comment (skip if found)\n"
        f"2. Post the deployment comment\n"
        f"3. Transition to **Done**\n"
        f"\nTickets you left unchecked are skipped — no comment, no status change."
    )

    st.divider()
    st.markdown("### Comment preview")

    sample_info = first_filled_entry(filled)
    if not sample_info:
        st.warning("Deployment info is missing — go back to **Deployment Info**.")
        if st.button("\u2190 Back to Deployment Info", key="review_missing_filled"):
            deployer_go(back_from_review())
        return
    with st.container(border=True):
        deploy_env = config.DEPLOY_ENVIRONMENT
        st.markdown(
            f"The change has been deployed to {deploy_env} on {sample_info['deployment_date']} "
            f"at {sample_info['deployment_time']}.\n\n"
            f"and changes are reflecting the {deploy_env} and verified\n\n"
            f"**Deployment ID:** {sample_info['deployment_id']}"
        )

    st.checkbox(
        "Force post comments (ignore old/partial comments on tickets)",
        key="wiz_force_deploy",
        help=(
            "Use if a ticket was skipped as 'already deployed' but only has an on-hold or "
            "partial note — not a full verified deployment comment."
        ),
    )

    st.markdown("")
    col_l, col_mid, col_r = st.columns([1, 2, 1])
    with col_l:
        if st.button("\u2190 Back", use_container_width=True):
            deployer_go(back_from_review())
    with col_mid:
        if is_quick_start() and st.button("Change ticket selection", use_container_width=True):
            deployer_go(2)
    with col_r:
        deploy_disabled = not selected_keys
        if st.button(
            "\U0001f680 Deploy Now",
            type="primary",
            use_container_width=True,
            disabled=deploy_disabled,
        ):
            clear_deploy_results_cache(release.get("id"))
            deployer_go(5 if is_quick_start() else 6)


def _count_selected(
    multi_client: bool,
    filled_clients: list[str],
    grouped: dict[str, list[dict]],
    selected_keys: set[str],
) -> int:
    if multi_client:
        return sum(
            1
            for client in filled_clients
            for iss in issues_for_filled_client(client, grouped)
            if iss["key"] in selected_keys
        )
    return len(selected_keys)


def _deployment_card_html(title: str, tickets_html: str, info: dict) -> str:
    """One review card: heading, ticket list, and the deployment ID/date/time row."""
    dep_id = esc(_truncate_id(info.get("deployment_id", "")))
    dep_date = esc(info.get("deployment_date", ""))
    dep_time = esc(info.get("deployment_time", ""))
    return (
        f'<div class="review-card">'
        f'<strong style="font-size:1.05rem">{esc(title)}</strong>'
        f' <span style="opacity:.5">{tickets_html}</span>'
        f'<div style="display:flex;gap:24px;margin-top:10px;font-size:.88rem">'
        f'<div><span style="opacity:.5">ID</span><br><code>{dep_id}</code></div>'
        f'<div><span style="opacity:.5">Date</span><br>{dep_date}</div>'
        f'<div><span style="opacity:.5">Time</span><br>{dep_time}</div>'
        f"</div></div>"
    )


def _render_deployment_cards(
    proj_key: str,
    multi_client: bool,
    filled: dict[str, dict],
    skipped: list[str],
    grouped: dict[str, list[dict]],
    selected_keys: set[str],
) -> None:
    """Render one deployment card per client (multi-client) or a single project card."""
    if multi_client:
        for client, info in filled.items():
            ticket_keys = [
                iss["key"]
                for iss in issues_for_filled_client(client, grouped)
                if iss["key"] in selected_keys
            ]
            if not ticket_keys:
                continue
            codes = "  ".join(f"<code>{esc(k)}</code>" for k in ticket_keys)
            st.markdown(
                _deployment_card_html(
                    client,
                    f"\u00b7 {len(ticket_keys)} ticket(s): {codes}",
                    info,
                ),
                unsafe_allow_html=True,
            )
        if skipped:
            st.info(f"Not deploying this run (no deployment ID): **{', '.join(skipped)}**")
    else:
        info = first_filled_entry(filled) or {}
        keys = ", ".join(f"`{k}`" for k in sorted(selected_keys))
        st.markdown(
            _deployment_card_html(
                proj_key,
                f"\u00b7 {len(selected_keys)} ticket(s): {keys}",
                info,
            ),
            unsafe_allow_html=True,
        )


def _render_quick_review_summary(
    proj_key: str,
    multi_client: bool,
    filled: dict[str, dict],
    skipped: list[str],
    grouped: dict[str, list[dict]],
    selected_keys: set[str],
) -> None:
    st.markdown("### Selected tickets")
    st.caption(
        f"**{len(selected_keys)}** ticket(s) will be updated. "
        "Use **Change ticket selection** below to adjust."
    )
    _render_deployment_cards(proj_key, multi_client, filled, skipped, grouped, selected_keys)


def _render_full_review_details(
    proj_key: str,
    multi_client: bool,
    filled: dict[str, dict],
    skipped: list[str],
    grouped: dict[str, list[dict]],
    selected_keys: set[str],
) -> None:
    st.divider()
    _render_deployment_cards(proj_key, multi_client, filled, skipped, grouped, selected_keys)
