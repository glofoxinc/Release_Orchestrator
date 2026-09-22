"""Step 5 -- Execute deployment & results (including undo with confirmation).

Deployment never runs on first render: the operator must click an explicit
confirm button. Draft state is persisted for single-user desktop recovery.

Jira write loops live in ``deploy_ops`` (shared with MCP/headless); this module
only owns Streamlit progress UI and session wiring.
"""

from __future__ import annotations

import streamlit as st

import config
import deploy_draft
import deploy_ops
import jira_client
import team_scope
from common.logger import set_log_context
from release_platform.ui.deployer_flow import back_from_execute, deployer_go
from release_platform.ui.helpers import (
    clear_deploy_results_cache,
    compute_deploy_run_fingerprint,
    deploy_filled_is_valid,
    first_filled_entry,
    get_deploy_filled_snapshot,
    get_project_cfg,
    go,
    reset_wizard,
)


def render() -> None:
    proj_key = st.session_state.get("wiz_project", "")
    release = st.session_state.get("wiz_release", {})
    proj_cfg = get_project_cfg(proj_key)
    if not proj_cfg:
        go(1)
        return
    multi_client = proj_cfg["multi_client"]
    issues = st.session_state.get("wiz_issues", [])
    filled, _ = get_deploy_filled_snapshot(proj_key, multi_client)

    st.markdown(f"## Deploying  \u2014  {release.get('name', '?')}")

    if not deploy_filled_is_valid(filled):
        st.warning("No deployment info found. Please go back and fill in deployment details.")
        if st.button("\u2190 Back to Review", use_container_width=True):
            deployer_go(back_from_execute())
        return

    st.session_state["wiz_filled"] = filled
    from session_persist import persist_deploy_draft, persist_session

    persist_deploy_draft(dict(st.session_state))
    persist_session(dict(st.session_state))

    selected_keys = st.session_state.get("wiz_deploy_selected_keys", set())
    set_log_context(
        release_id=str(release.get("id") or release.get("name") or ""),
        project=proj_key,
    )

    grouped = st.session_state.get("wiz_grouped", {}) if multi_client else None
    tickets_to_process = deploy_ops.build_tickets_to_process(
        filled=filled,
        selected_keys=selected_keys,
        project_key=proj_key,
        issues=issues,
        grouped=grouped,
        multi_client=multi_client,
    )

    results_key = f"wiz_results_{release.get('id')}"
    fp_key = f"wiz_results_fp_{release.get('id')}"
    confirm_key = f"wiz_deploy_execute_confirmed_{release.get('id')}"
    run_fp = compute_deploy_run_fingerprint(
        release.get("id"),
        selected_keys,
        filled,
        force_deploy=bool(st.session_state.get("wiz_force_deploy")),
    )
    cached_fp = st.session_state.get(fp_key)

    # Fingerprint drift invalidates prior confirmation and cached results.
    if cached_fp is not None and cached_fp != run_fp:
        st.session_state.pop(confirm_key, None)
        st.session_state.pop(results_key, None)
        st.session_state.pop(fp_key, None)
        cached_fp = None

    needs_execute = results_key not in st.session_state or cached_fp != run_fp
    if needs_execute:
        if not st.session_state.get(confirm_key):
            _render_confirm_gate(
                tickets_to_process=tickets_to_process,
                release=release,
                confirm_key=confirm_key,
                filled=filled,
            )
            return
        _execute_deploy(
            tickets_to_process,
            results_key,
            release,
            filled,
            multi_client,
            proj_key,
            issues,
            grouped,
            selected_keys,
        )
        st.session_state[fp_key] = run_fp
        # One-shot confirmation — re-run with a new fingerprint requires a new click.
        st.session_state.pop(confirm_key, None)

    results = st.session_state[results_key]

    _render_results(results)

    _render_mark_released(results, release, proj_key)

    _render_undo(release)

    st.markdown("")
    col_l, _, col_r = st.columns([1, 3, 2])
    with col_l:
        if results.get("errors"):
            if st.button("\u2190 Back to Review (retry)", use_container_width=True):
                clear_deploy_results_cache(release.get("id"))
                st.session_state.pop(confirm_key, None)
                deployer_go(back_from_execute())
    with col_r:
        if st.button("\U0001f504 Deploy Another Release", type="primary", use_container_width=True):
            deploy_draft.clear_deploy_draft()
            reset_wizard()


def _render_confirm_gate(
    *,
    tickets_to_process: list,
    release: dict,
    confirm_key: str,
    filled: dict,
) -> None:
    """Require an explicit click before any Jira write."""
    st.info(
        "Review the deployment below, then confirm. "
        "Nothing is written to Jira until you click **Confirm & Deploy**."
    )
    st.markdown(f"**Release:** {release.get('name', '?')}")
    st.markdown(f"**Tickets to update:** {len(tickets_to_process)}")
    if st.session_state.get("wiz_force_deploy"):
        st.warning("Force post comments is enabled — existing deployment comments will be ignored.")

    sample = first_filled_entry(filled) or {}
    if sample:
        with st.container(border=True):
            st.markdown(
                f"Sample comment: deployed to **{config.DEPLOY_ENVIRONMENT}** on "
                f"{sample.get('deployment_date', '?')} at {sample.get('deployment_time', '?')} "
                f"(ID `{sample.get('deployment_id', '?')}`)."
            )

    col_l, col_r = st.columns([1, 1])
    with col_l:
        if st.button("\u2190 Back to Review", use_container_width=True):
            st.session_state.pop(confirm_key, None)
            deployer_go(back_from_execute())
    with col_r:
        disabled = len(tickets_to_process) == 0
        if st.button(
            "Confirm & Deploy",
            type="primary",
            use_container_width=True,
            disabled=disabled,
            key="wiz_confirm_deploy_btn",
        ):
            st.session_state[confirm_key] = True
            st.rerun()
    if disabled:
        selected_keys = st.session_state.get("wiz_deploy_selected_keys", set())
        if selected_keys:
            st.error(
                "No tickets matched the deployment client(s) you filled in. "
                "Go back to Review and verify client names and ticket selection."
            )
        else:
            st.warning("No tickets selected for deployment.")


def _release_audit_fields() -> dict:
    """Pull SharePoint / TCKT / Slack outcomes from the shared session."""
    sp = (
        st.session_state.get("shared_sharepoint_url")
        or st.session_state.get("stk_sharepoint")
        or st.session_state.get("stk_slack_sharepoint")
        or ""
    )
    tckt = st.session_state.get("stk_created_key") or ""
    tckt_url = st.session_state.get("stk_created_url") or ""
    if tckt and not tckt_url:
        tckt_url = f"{config.JIRA_BASE_URL}/browse/{tckt}"
    return {
        "sharepoint_url": str(sp).strip(),
        "tckt_key": str(tckt).strip(),
        "tckt_url": str(tckt_url).strip(),
        "slack_results": st.session_state.get("stk_slack_results") or [],
    }


def _execute_deploy(
    tickets_to_process: list,
    results_key: str,
    release: dict,
    filled: dict,
    multi_client: bool,
    proj_key: str,
    issues: list,
    grouped: dict | None,
    selected_keys: set,
) -> None:
    total = len(tickets_to_process)
    if total == 0:
        if selected_keys:
            st.error(
                "No tickets matched the deployment client(s) you filled in. "
                "This often happens when client names differ slightly "
                "(e.g. **BD Gyms** vs **BDGyms**). Go back to **Review** or "
                "**Deployment Info** and verify client names and ticket selection."
            )
        else:
            st.warning("No tickets selected for deployment.")
        st.session_state[results_key] = {"success": 0, "skipped": 0, "errors": 0, "log": []}
        return

    progress = st.progress(0, text="Starting...")

    def _on_progress(completed: int, total_n: int, message: str) -> None:
        frac = completed / total_n if total_n else 1.0
        if message == "Complete!":
            progress.progress(1.0, text="Complete!")
        else:
            progress.progress(frac, text=f"{message} ({completed}/{total_n})")

    audit = _release_audit_fields()
    result = deploy_ops.execute_deploy(
        tickets_to_process,
        filled=filled,
        release=release,
        project_key=proj_key,
        selected_keys=selected_keys,
        issues=issues,
        grouped=grouped,
        multi_client=multi_client,
        force_deploy=bool(st.session_state.get("wiz_force_deploy")),
        save_to_history=True,
        sharepoint_url=audit["sharepoint_url"] or None,
        tckt_key=audit["tckt_key"] or None,
        tckt_url=audit["tckt_url"] or None,
        slack_results=audit["slack_results"],
        on_progress=_on_progress,
    )

    st.session_state[results_key] = {
        "success": result["success"],
        "skipped": result["skipped"],
        "errors": result["errors"],
        "log": result["log"],
    }
    if result.get("undo_data"):
        st.session_state["wiz_undo_data"] = result["undo_data"]
    if result.get("history_timestamp"):
        st.session_state["wiz_last_history_timestamp"] = result["history_timestamp"]
        try:
            deploy_draft.clear_deploy_draft()
        except Exception:  # noqa: BLE001
            pass


def _render_results(results: dict) -> None:
    if results["success"] and not results["errors"]:
        st.balloons()
        st.markdown(
            '<div class="success-banner">'
            '<h3>\u2705 Deployment Complete</h3>'
            '<p>All tickets updated and transitioned successfully.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
    elif results["errors"] and results["success"]:
        st.markdown(
            '<div class="error-banner error-banner--warn">'
            '<h3>\u26a0\ufe0f Partially Complete</h3>'
            f'<p><strong>{results["success"]}</strong> succeeded, '
            f'<strong>{results["errors"]}</strong> failed. '
            f'Failed tickets were not modified.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
    elif results["errors"] and not results["success"]:
        st.markdown(
            '<div class="error-banner">'
            '<h3>\u274c All Tickets Failed</h3>'
            '<p>Check the execution log below for details.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        if results["skipped"] and not results["success"]:
            st.warning(
                "No tickets were updated. Skipped tickets may only have **partial or on-hold** "
                "comments — not a verified deployment. Go back to **Review**, enable "
                "**Force post comments**, and deploy again."
            )
        else:
            st.info("No tickets were updated (all already have verified deployment comments).")

    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("Updated", results["success"])
    rc2.metric("Skipped", results["skipped"])
    rc3.metric("Errors", results["errors"])

    with st.expander("Execution log", expanded=True):
        for entry in results["log"]:
            st.markdown(entry)


def _render_mark_released(results: dict, release: dict, project_key: str) -> None:
    """Offer to mark the Jira version as Released after a clean deployment."""
    if results["errors"] or not results["success"]:
        return

    release_flag_key = f"wiz_version_released_{release.get('id')}"
    if st.session_state.get(release_flag_key):
        st.success(f"Version **{release.get('name', '?')}** marked as Released in Jira.")
        return

    st.divider()
    st.markdown("### Mark version as Released")
    try:
        scope = team_scope.scope_from_project(project_key)
    except team_scope.TeamScopeError:
        scope = team_scope.parse_scope({})
    if not scope.owns_version:
        st.info(
            "Mark-released is disabled for this team scope because it affects the entire "
            "Jira fix version, not only your board. Enable **Team owns whole Jira version** "
            "in Settings → Projects when your team truly owns the version."
        )
        return

    st.caption(
        f"All tickets deployed successfully. Mark **{release.get('name', '?')}** "
        f"as released in Jira so it no longer appears in unreleased versions."
    )
    if st.button("\U0001f3f7\ufe0f  Mark as Released", use_container_width=False):
        try:
            mr = deploy_ops.mark_release(
                str(release.get("id") or ""),
                project_key=project_key,
                history_timestamp=st.session_state.get("wiz_last_history_timestamp"),
                version_name=str(release.get("name") or ""),
            )
            if mr.get("status") == "released":
                st.session_state[release_flag_key] = True
                jira_client.clear_version_cache()
                st.rerun()
            elif mr.get("status") == "blocked":
                st.error(mr.get("error") or "Mark-released is blocked for this team scope.")
            else:
                st.error(
                    mr.get("error")
                    or "Jira returned an unexpected response. The version may not have been updated."
                )
        except Exception as e:
            st.error(f"Failed to mark as released: {e}")


def _render_undo(release: dict) -> None:
    undo_data = st.session_state.get("wiz_undo_data", [])
    undo_results_key = f"wiz_undo_results_{release.get('id')}"

    if undo_data and undo_results_key not in st.session_state:
        st.divider()
        st.markdown("### Undo this deployment")
        st.caption("Deletes the posted comments and reverts ticket statuses back to their pre-deploy state.")

        confirming = st.session_state.get("undo_confirm", False)

        if not confirming:
            if st.button("\u21a9\ufe0f  Undo Deployment", type="secondary", use_container_width=False):
                st.session_state["undo_confirm"] = True
                st.rerun()
        else:
            ticket_count = len(undo_data)
            transitioned_count = sum(1 for u in undo_data if u.get("transitioned"))
            st.warning(
                f"**Are you sure?** This will delete **{ticket_count}** deployment comment(s) "
                f"and revert **{transitioned_count}** ticket status(es)."
            )
            c_yes, c_no, _ = st.columns([1, 1, 4])
            with c_yes:
                if st.button("\u2705 Yes, Undo", type="primary", use_container_width=True):
                    st.session_state.pop("undo_confirm", None)
                    _execute_undo(undo_data, undo_results_key)
                    st.rerun()
            with c_no:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.pop("undo_confirm", None)
                    st.rerun()

    if undo_results_key in st.session_state:
        st.divider()
        ur = st.session_state[undo_results_key]
        if ur["fail"] == 0:
            st.success(f"Undo complete — {ur['ok']} ticket(s) reverted.")
        else:
            st.warning(f"Undo partial — {ur['ok']} reverted, {ur['fail']} failed.")
        with st.expander("Undo log", expanded=True):
            for entry in ur["log"]:
                st.markdown(entry)


def _execute_undo(undo_data: list[dict], undo_results_key: str) -> None:
    progress = st.progress(0, text="Starting undo...")

    def _on_progress(completed: int, total_n: int, message: str) -> None:
        frac = completed / total_n if total_n else 1.0
        if message == "Complete!":
            progress.progress(1.0, text="Complete!")
        else:
            progress.progress(frac, text=f"{message} ({completed}/{total_n})")

    result = deploy_ops.undo_deploy(
        undo_data,
        history_timestamp=st.session_state.get("wiz_last_history_timestamp"),
        on_progress=_on_progress,
    )
    st.session_state[undo_results_key] = {
        "ok": result["ok"],
        "fail": result["fail"],
        "log": result["log"],
    }
    st.session_state.pop("wiz_undo_data", None)
