"""Step 2 -- Tickets Overview."""

from __future__ import annotations

import streamlit as st

import config
import jira_client
import linked_ticket_verifier as ltv
from release_platform.ui.css import status_badge
from release_platform.ui.helpers import (
    apply_deploy_issue_filter,
    check_snapshot_drift,
    deploy_filter_blocks_progress,
    drift_blocks_proceed,
    drift_has_changes,
    esc,
    get_project_cfg,
    go,
    render_deploy_filter_warnings,
    reset_deployer_downstream_state,
    reset_exclude_selection_for_issues,
    ticket_issues_cache_key,
)


def render() -> None:
    proj_key = st.session_state.get("wiz_project", "")
    release = st.session_state.get("wiz_release", {})
    proj_cfg = get_project_cfg(proj_key)
    if not proj_cfg:
        go(1)
        return
    multi_client = proj_cfg["multi_client"]

    title_col, refresh_col = st.columns([6, 1])
    with title_col:
        st.markdown(f"## {proj_key} \u2014 {release.get('name', '?')}")
    with refresh_col:
        st.markdown("")
        if st.button("\U0001f504 Refresh", use_container_width=True):
            issues_key_to_clear = ticket_issues_cache_key(
                proj_key, release.get("id"), prefix="wiz_issues_",
            )
            st.session_state.pop(issues_key_to_clear, None)
            reset_deployer_downstream_state()
            st.rerun()

    issues_key = ticket_issues_cache_key(proj_key, release.get("id"), prefix="wiz_issues_")
    if issues_key not in st.session_state:
        try:
            with st.spinner("Loading tickets..."):
                st.session_state[issues_key] = jira_client.get_issues_for_version(
                    proj_key, release["id"],
                )
        except Exception as e:
            st.error(f"Failed to load tickets: {e}")
            col_l, _ = st.columns([1, 5])
            with col_l:
                if st.button("\u2190 Back"):
                    go(1)
            st.stop()

    raw_issues = st.session_state[issues_key]
    if not raw_issues:
        st.warning("No tickets in this release.")
        col_l, _ = st.columns([1, 5])
        with col_l:
            if st.button("\u2190 Back"):
                go(1)
        st.stop()

    issues, filter_meta = apply_deploy_issue_filter(raw_issues, proj_key, release)
    st.session_state["wiz_deploy_filter_meta"] = filter_meta
    st.session_state["wiz_issues"] = issues
    # Fingerprint against raw fix-version tickets so Exclude Tickets can
    # pre-select Ticket Review exclusions that are not in the filtered list.
    reset_exclude_selection_for_issues(
        raw_issues, proj_key, str(release.get("id", "")),
    )

    render_deploy_filter_warnings(filter_meta, release.get("name", "?"))

    block_next = not issues or deploy_filter_blocks_progress(filter_meta)

    drift = check_snapshot_drift()
    if drift_blocks_proceed(drift):
        st.error(
            "Could not verify the Ticket Review lock-in against Jira. "
            f"{drift.get('message', '')} "
            "Deploy with caution or re-run Ticket Review after Jira is reachable."
        )
    elif drift_has_changes(drift):
        parts = []
        if drift.get("added"):
            parts.append(f"added: {', '.join(drift['added'])}")
        if drift.get("removed"):
            parts.append(f"removed: {', '.join(drift['removed'])}")
        st.warning(
            "Ticket Review snapshot is out of date — fix version changed since you locked tickets "
            f"({'; '.join(parts)}). Re-run **Ticket Review** or continue with the filtered list below."
        )

    done_count = sum(
        1 for iss in issues
        if iss["fields"]["status"].get("statusCategory", {}).get("key") == "done"
    )
    pending_count = len(issues) - done_count

    _show_validation_warnings(issues)

    # ── Linked ticket verification (optional) ─────────────────────
    _render_ticket_verification(issues)

    browse = f"{config.JIRA_BASE_URL}/browse"

    if not issues:
        st.warning("No tickets remain for deploy after applying your Ticket Review selection.")

    if multi_client:
        grouped = jira_client.group_issues_by_client(issues, project_key=proj_key)
        st.session_state["wiz_grouped"] = grouped
        client_names = list(grouped.keys())

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Tickets", len(issues))
        m2.metric("Clients", len(client_names))
        m3.metric("Pending", pending_count)
        m4.metric("Already Done", done_count)

        st.markdown("")
        for client, client_issues in grouped.items():
            with st.expander(
                f"**{client}** \u2014 {len(client_issues)} ticket(s)",
                expanded=len(client_issues) <= 2,
            ):
                for iss in client_issues:
                    _render_ticket_row(iss, browse)
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Tickets", len(issues))
        m2.metric("Pending", pending_count)
        m3.metric("Already Done", done_count)

        st.markdown("")
        with st.expander(f"View all {len(issues)} tickets", expanded=False):
            for iss in issues:
                _render_ticket_row(iss, browse)

    # Export ticket list as CSV
    import csv
    import io

    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["Key", "Summary", "Status", "Assignee", "Link"])
    for iss in issues:
        fields = iss.get("fields", {})
        assignee = fields.get("assignee") or {}
        writer.writerow([
            iss["key"],
            fields.get("summary", ""),
            fields.get("status", {}).get("name", ""),
            assignee.get("displayName", "Unassigned"),
            f"{browse}/{iss['key']}",
        ])
    st.download_button(
        "Export ticket list as CSV",
        data=csv_buf.getvalue().encode("utf-8"),
        file_name=f"{proj_key}_{release.get('name', 'release')}_tickets.csv",
        mime="text/csv",
        key="step2_export_csv",
    )

    st.caption(
        "Next: **Exclude Tickets** — select tickets that should not ship, "
        "remove their fix version, then continue to Deployment Info."
    )

    st.markdown("")
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if st.button("\u2190 Back", use_container_width=True):
            go(1)
    with col_r:
        if block_next:
            st.button("Next \u2192", type="primary", use_container_width=True, disabled=True)
            if not issues:
                st.caption("No deployable tickets — update Ticket Review or fix version in Jira.")
            elif deploy_filter_blocks_progress(filter_meta):
                st.caption("Resolve the fix-version mismatch above before continuing.")
        elif st.button("Next \u2192", type="primary", use_container_width=True):
            go(3)


def _render_ticket_verification(issues: list[dict]) -> None:
    """Render ticket verification panel using linked_ticket_verifier."""
    if not issues:
        return

    with st.expander("Ticket Pre-flight Verification", expanded=False):
        st.caption(
            "Run pre-flight checks to verify all tickets are in expected states, "
            "have summaries, and have acceptance criteria defined."
        )

        cached_report = st.session_state.get("wiz_verification_report")

        c1, c2 = st.columns([2, 1])
        with c1:
            if st.button("Run Verification", key="wiz_run_verification"):
                ticket_keys = [iss["key"] for iss in issues]
                with st.spinner("Verifying tickets…"):
                    report = ltv.verify_tickets(
                        ticket_keys,
                        fetch=jira_client.get_issue,
                    )
                st.session_state["wiz_verification_report"] = report.to_dict()
                st.rerun()
        with c2:
            if cached_report and st.button("Clear", key="wiz_clear_verification"):
                st.session_state.pop("wiz_verification_report", None)
                st.rerun()

        if cached_report:
            total = cached_report.get("total", 0)
            passed = cached_report.get("passed", 0)
            failed = cached_report.get("failed", 0)
            all_ok = cached_report.get("all_ok", False)

            if all_ok:
                st.success(f"All {total} tickets pass pre-flight checks.")
            else:
                st.warning(f"{failed}/{total} tickets have issues that need review.")

            findings = cached_report.get("findings", [])
            failed_findings = [f for f in findings if not f.get("ok")]
            if failed_findings:
                st.markdown("**Tickets with issues:**")
                for finding in failed_findings:
                    ticket = finding.get("ticket", "")
                    issues_list = finding.get("issues", [])
                    state = finding.get("state", "")
                    st.markdown(
                        f"- **{esc(ticket)}** (state: {esc(state)}): "
                        f"{', '.join(esc(i) for i in issues_list)}"
                    )


_EXPECTED_PRE_DEPLOY = {"done", "indeterminate"}


def _show_validation_warnings(issues: list[dict]) -> None:
    """Flag tickets in unexpected statuses before deployment."""
    unexpected = []
    already_done = []
    for iss in issues:
        status = iss["fields"]["status"]
        cat_key = status.get("statusCategory", {}).get("key", "new")
        sname = status["name"]
        if cat_key == "done":
            already_done.append((iss["key"], sname))
        elif cat_key not in _EXPECTED_PRE_DEPLOY:
            unexpected.append((iss["key"], sname))

    if unexpected:
        keys_list = ", ".join(f"**{k}** ({s})" for k, s in unexpected)
        st.warning(
            f"**Pre-deployment check:** {len(unexpected)} ticket(s) may not be ready "
            f"for deployment: {keys_list}. "
            "They are still in an early status. You can proceed, but verify these are intentional."
        )
    if already_done:
        keys_list = ", ".join(f"**{k}**" for k, _ in already_done)
        st.info(
            f"{len(already_done)} ticket(s) are already marked Done: {keys_list}. "
            "Deployment comments may already exist on these."
        )


def _render_ticket_row(iss: dict, browse: str) -> None:
    status = iss["fields"]["status"]
    sname = status["name"]
    scat = status.get("statusCategory", {}).get("key", "new")
    badge = status_badge(sname, scat)
    link = f"{browse}/{iss['key']}"
    summary = esc(iss["fields"].get("summary", ""))
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;padding:6px 0">'
        f'<code style="font-weight:600"><a href="{link}" target="_blank" '
        f'style="text-decoration:none;color:inherit">{esc(iss["key"])}</a></code>'
        f'<span style="flex:1">{summary}</span>'
        f'{badge}</div>',
        unsafe_allow_html=True,
    )
