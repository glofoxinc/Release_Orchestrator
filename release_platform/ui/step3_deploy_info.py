"""Step 4 — Deployment Info (paste zone + per-client fields)."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

import jira_client
from release_platform.ui.deployer_flow import back_from_deploy_info, deployer_go, is_quick_start
from release_platform.ui.helpers import (
    collect_deploy_filled,
    collect_deployer_prefill,
    get_project_cfg,
    go,
    init_dep_field_defaults,
    save_deploy_filled_snapshot,
)


def _release_version() -> str:
    release = st.session_state.get("wiz_release", {})
    return str(release.get("name", "")) if isinstance(release, dict) else ""


def _apply_deploy_prefill(grouped: dict) -> int:
    """Fill empty fields from Release Notes session, SharePoint, or history.

    Only populates blank fields so manual edits and pasted values win.
    Returns the number of clients newly filled.
    """
    prefill = collect_deployer_prefill(grouped, _release_version())
    applied = 0
    for client, info in prefill.items():
        id_key = f"dep_id_{client}"
        if st.session_state.get(id_key, "").strip():
            continue
        dep_id = info.get("deployment_id", "").strip()
        if not dep_id:
            continue
        st.session_state[id_key] = dep_id
        if info.get("deployment_date"):
            st.session_state[f"dep_date_{client}"] = info["deployment_date"]
        if info.get("deployment_time"):
            st.session_state[f"dep_time_{client}"] = info["deployment_time"]
        applied += 1
    return applied


def _prefill_source_label() -> str:
    return (
        st.session_state.get("_deployer_prefill_source")
        or "Release Notes / SharePoint / history"
    )


def _parse_and_fill_multi(raw: str, grouped: dict, client_names: list[str]) -> None:
    """Parse pasted deployment text and populate per-client fields."""
    parsed = jira_client.parse_deployment_input(raw)
    matched = jira_client.match_deployments_to_tickets(parsed, grouped)
    for m in matched:
        if m.matched_jira_client:
            st.session_state[f"dep_id_{m.matched_jira_client}"] = m.deployment_id
            if m.deployment_date:
                st.session_state[f"dep_date_{m.matched_jira_client}"] = m.deployment_date
            if m.deployment_time:
                st.session_state[f"dep_time_{m.matched_jira_client}"] = m.deployment_time
    filled_count = sum(1 for m in matched if m.matched_jira_client)
    msgs: list[tuple[str, str]] = []
    if filled_count:
        msgs.append(("success", f"Auto-filled **{filled_count}/{len(client_names)}** client(s) from paste."))
    else:
        msgs.append(("warning", "No client fields detected in the pasted text. "
                                 "Check the deployment IDs and client names, then try again."))
    for m in matched:
        if m.error:
            msgs.append(("warning", f"Could not match: **{m.client}** \u2014 {m.error}"))
    st.session_state["_dep_info_msgs"] = msgs


def _render_info_msgs() -> None:
    for level, text in st.session_state.pop("_dep_info_msgs", []):
        if level == "success":
            st.success(text)
        else:
            st.warning(text)


def render() -> None:
    proj_key = st.session_state.get("wiz_project", "")
    proj_cfg = get_project_cfg(proj_key)
    if not proj_cfg:
        go(1)
        return
    multi_client = proj_cfg["multi_client"]
    today_str = datetime.now().strftime("%B %d %Y")

    st.markdown("## Paste Deployment Info")
    if multi_client:
        st.caption(
            "Deploy **one client at a time** if needed — fill deployment ID and time for "
            "the client(s) you are shipping now. Other clients can be deployed in a later run."
        )
        _render_multi_client(today_str, proj_key)
    else:
        _render_single(today_str, proj_key)

    st.markdown("")
    col_l, _, _ = st.columns([1, 4, 1])
    with col_l:
        if st.button("\u2190 Back", use_container_width=True):
            deployer_go(back_from_deploy_info())


def _render_multi_client(today_str: str, proj_key: str) -> None:
    grouped = st.session_state.get("wiz_grouped", {})
    client_names = list(grouped.keys())
    init_dep_field_defaults(client_names, today_str)

    if not st.session_state.get("dep_prefill_tried"):
        st.session_state["dep_prefill_tried"] = True
        applied = _apply_deploy_prefill(grouped)
        if applied:
            st.session_state["_dep_info_msgs"] = [(
                "success",
                f"Loaded deployment IDs for **{applied}** client(s) from "
                f"**{_prefill_source_label()}**. "
                "Review below or paste to override.",
            )]
            st.rerun()

    _render_info_msgs()

    st.markdown(
        '<div class="paste-hint">'
        '\U0001f4cb Paste all deployment info below \u2014 '
        'client names, IDs, dates and times are auto-detected'
        '</div>',
        unsafe_allow_html=True,
    )
    raw = st.text_area(
        "Paste here",
        key="paste_step3",
        height=180,
        placeholder=(
            "Jetts Deployment ID: a4438257-1820-44e0-8639-efb05911871f\n"
            "14/04/26, 10:39\n"
            "\n"
            "XPO Deployment ID: 78bded53-fbc6-4c4f-936c-11cf3933c740\n"
            "14/04/26, 10:45"
        ),
        label_visibility="collapsed",
        help="Paste deployment output from your CI/CD tool. Client names, UUIDs, dates, and times are auto-detected.",
    )

    act_detect, act_fill, _ = st.columns([1, 1, 2])
    with act_detect:
        if st.button("Detect from paste", use_container_width=True, key="dep_detect_paste"):
            if raw.strip():
                st.session_state["_prev_paste_multi"] = raw.strip()
                _parse_and_fill_multi(raw, grouped, client_names)
            else:
                st.session_state["_dep_info_msgs"] = [("warning", "Paste deployment output first.")]
            st.rerun()
    with act_fill:
        if st.button(
            "Fill from Release Notes / SharePoint / History",
            use_container_width=True,
            key="dep_fill_history",
        ):
            applied = _apply_deploy_prefill(grouped)
            st.session_state["_dep_info_msgs"] = [(
                "success" if applied else "warning",
                f"Loaded deployment IDs for **{applied}** client(s) from "
                f"**{_prefill_source_label()}**."
                if applied
                else (
                    "No deployment IDs found in Release Notes, SharePoint, or history. "
                    + st.session_state.get("_deployer_prefill_sharepoint_error", "")
                ).strip(),
            )]
            st.rerun()

    prev_paste = st.session_state.get("_prev_paste_multi", "")
    if raw.strip() and raw.strip() != prev_paste:
        st.session_state["_prev_paste_multi"] = raw.strip()
        _parse_and_fill_multi(raw, grouped, client_names)
        st.rerun()

    st.divider()

    has_any_filled = any(
        st.session_state.get(f"dep_id_{c}", "").strip() for c in client_names
    )
    with st.expander(
        "Per-Client Deployment Details" if has_any_filled else "Per-Client Deployment Details (auto-filled from paste)",
        expanded=True,
    ):
        with st.form("deploy_info_multi", clear_on_submit=False):
            hc1, hc2, hc3 = st.columns([4, 3, 3])
            hc1.caption("DEPLOYMENT ID")
            hc2.caption("DATE")
            hc3.caption("TIME")

            for client in client_names:
                ticket_count = len(grouped[client])
                st.markdown(
                    f'**{client}** · {ticket_count} ticket(s)',
                )
                c1, c2, c3 = st.columns([4, 3, 3])
                with c1:
                    st.text_input(
                        "id",
                        key=f"dep_id_{client}",
                        placeholder="Deployment ID (UUID)",
                        label_visibility="collapsed",
                    )
                with c2:
                    st.text_input(
                        "date",
                        key=f"dep_date_{client}",
                        placeholder="April 14 2026",
                        label_visibility="collapsed",
                    )
                with c3:
                    st.text_input(
                        "time",
                        key=f"dep_time_{client}",
                        placeholder="10:39 AM IST",
                        label_visibility="collapsed",
                    )

            submitted = st.form_submit_button("Next \u2192", type="primary", use_container_width=True)

    filled, skipped = collect_deploy_filled(proj_key, multi_client=True)
    missing_time = [
        client for client, info in filled.items()
        if not info.get("deployment_time", "").strip()
    ]

    if missing_time:
        st.error(f"Missing deployment time for: **{', '.join(missing_time)}**")
    elif not filled:
        st.info("Paste or fill deployment info for **at least one client** to continue.")
    else:
        ready = ", ".join(f"**{c}**" for c in filled)
        waiting = ", ".join(skipped) if skipped else "none"
        st.success(f"Ready to deploy: {ready}")
        if skipped:
            st.caption(f"Not in this run (no deployment ID yet): {waiting}")

    if submitted:
        if save_deploy_filled_snapshot(proj_key, multi_client=True):
            deployer_go(4 if is_quick_start() else 5)
        elif missing_time:
            st.error(f"Add deployment time for: **{', '.join(missing_time)}**")
        else:
            st.error("Enter a deployment ID and time for at least one client.")


def _parse_and_fill_single(raw: str) -> None:
    parsed = jira_client.parse_deployment_input(raw)
    if not parsed:
        st.session_state["_dep_info_msgs"] = [(
            "warning",
            "No deployment ID detected in the pasted text. Check the UUID and try again.",
        )]
        return
    p = parsed[0]
    if p.deployment_id:
        st.session_state["dep_id_single"] = p.deployment_id
    if p.deployment_date:
        st.session_state["dep_date_single"] = p.deployment_date
    if p.deployment_time:
        st.session_state["dep_time_single"] = p.deployment_time
    st.session_state["_dep_info_msgs"] = [("success", "Auto-filled from paste.")]


def _apply_deploy_prefill_single() -> int:
    """Populate one deployment field from Release Notes, SharePoint, or history."""
    if st.session_state.get("dep_id_single", "").strip():
        return 0
    prefill = collect_deployer_prefill(
        st.session_state.get("wiz_grouped", {}), _release_version()
    )
    info = next((v for v in prefill.values() if v.get("deployment_id", "").strip()), None)
    if not info:
        return 0
    st.session_state["dep_id_single"] = info["deployment_id"].strip()
    if info.get("deployment_date"):
        st.session_state["dep_date_single"] = info["deployment_date"]
    if info.get("deployment_time"):
        st.session_state["dep_time_single"] = info["deployment_time"]
    return 1


def _render_single(today_str: str, proj_key: str) -> None:
    init_dep_field_defaults([], today_str)

    if not st.session_state.get("dep_prefill_tried"):
        st.session_state["dep_prefill_tried"] = True
        if _apply_deploy_prefill_single():
            st.session_state["_dep_info_msgs"] = [(
                "success",
                f"Loaded the deployment ID from **{_prefill_source_label()}**. "
                "Paste to override.",
            )]
            st.rerun()

    _render_info_msgs()

    st.markdown(
        '<div class="paste-hint">'
        '\U0001f4cb Paste deployment info below \u2014 '
        'ID, date and time are auto-detected'
        '</div>',
        unsafe_allow_html=True,
    )
    raw = st.text_area(
        "Paste here",
        key="paste_step3_single",
        height=100,
        placeholder="Deployment ID: a4438257-1820-44e0-8639-efb05911871f\n14/04/26, 10:39",
        label_visibility="collapsed",
        help="Paste deployment output — ID, date, and time are auto-extracted.",
    )

    act_detect, act_fill, _ = st.columns([1, 1, 2])
    with act_detect:
        if st.button("Detect from paste", use_container_width=True, key="dep_detect_paste_single"):
            if raw.strip():
                st.session_state["_prev_paste_single"] = raw.strip()
                _parse_and_fill_single(raw)
            else:
                st.session_state["_dep_info_msgs"] = [("warning", "Paste deployment output first.")]
            st.rerun()
    with act_fill:
        if st.button(
            "Fill from Release Notes / SharePoint / History",
            use_container_width=True,
            key="dep_fill_history_single",
        ):
            applied = _apply_deploy_prefill_single()
            st.session_state["_dep_info_msgs"] = [(
                "success" if applied else "warning",
                f"Loaded the deployment ID from **{_prefill_source_label()}**."
                if applied
                else (
                    "No deployment ID found in Release Notes, SharePoint, or history. "
                    + st.session_state.get("_deployer_prefill_sharepoint_error", "")
                ).strip(),
            )]
            st.rerun()

    prev_paste = st.session_state.get("_prev_paste_single", "")
    if raw.strip() and raw.strip() != prev_paste:
        st.session_state["_prev_paste_single"] = raw.strip()
        _parse_and_fill_single(raw)
        st.rerun()

    st.divider()
    with st.form("deploy_info_single", clear_on_submit=False):
        c1, c2, c3 = st.columns([4, 3, 3])
        with c1:
            st.text_input(
                "id",
                key="dep_id_single",
                placeholder="Deployment ID (UUID)",
                label_visibility="collapsed",
            )
        with c2:
            st.text_input(
                "date",
                key="dep_date_single",
                placeholder="April 14 2026",
                label_visibility="collapsed",
            )
        with c3:
            st.text_input(
                "time",
                key="dep_time_single",
                placeholder="10:39 AM IST",
                label_visibility="collapsed",
            )
        submitted = st.form_submit_button("Next \u2192", type="primary", use_container_width=True)

    filled, _ = collect_deploy_filled(proj_key, multi_client=False)
    has_id = bool(st.session_state.get("dep_id_single", "").strip())
    has_time = bool(st.session_state.get("dep_time_single", "").strip())

    if has_id and not has_time:
        st.error("Deployment time is required.")
    elif not has_id:
        st.info("Paste or enter a deployment ID to continue.")

    if submitted:
        if save_deploy_filled_snapshot(proj_key, multi_client=False):
            deployer_go(4 if is_quick_start() else 5)
        elif has_id and not has_time:
            st.error("Deployment time is required.")
        else:
            st.error("Enter a deployment ID and time to continue.")
