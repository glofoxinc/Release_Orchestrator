"""Step 3 — Remove fix version from tickets excluded from the release.

Lists every ticket still on the fix version (raw cache), pre-selects Ticket
Review exclusions, and lets the user exclude selected tickets then continue
to Deployment Info.
"""

from __future__ import annotations

import streamlit as st

import jira_client
from release_platform.ui.helpers import (
    apply_deploy_issue_filter,
    esc,
    get_default_exclusion_keys,
    get_project_cfg,
    get_snapshot_included_keys_for_project,
    go,
    rebuild_wiz_grouped,
    reset_exclude_selection_for_issues,
    ticket_issues_cache_key,
)
from release_platform.ui.ticket_selection_page import render_empty_selection_hint, render_stay_on_page_hint


def _checkbox_key(ticket_key: str) -> str:
    return f"wiz_exc_chk_{ticket_key}"


def _raw_cache_key(proj_key: str, release_id) -> str:
    return ticket_issues_cache_key(proj_key, str(release_id), prefix="wiz_issues_")


def _load_raw_issues(proj_key: str, release: dict) -> list[dict]:
    """Return all tickets on the fix version, fetching from Jira if uncached."""
    cache_key = _raw_cache_key(proj_key, release.get("id"))
    if cache_key not in st.session_state:
        st.session_state[cache_key] = jira_client.get_issues_for_version(
            proj_key, release["id"],
        )
    return list(st.session_state[cache_key] or [])


def _sync_filtered_deploy_issues(
    raw_issues: list[dict],
    proj_key: str,
    release: dict,
) -> list[dict]:
    """Keep wiz_issues as the snapshot-filtered deploy candidate list."""
    issues, filter_meta = apply_deploy_issue_filter(raw_issues, proj_key, release)
    st.session_state["wiz_deploy_filter_meta"] = filter_meta
    st.session_state["wiz_issues"] = issues
    grouped = rebuild_wiz_grouped(issues, proj_key)
    if grouped is not None:
        st.session_state["wiz_grouped"] = grouped
    else:
        st.session_state.pop("wiz_grouped", None)
    return issues


def _init_selection(issues: list[dict], proj_key: str, release_id: str) -> None:
    if "wiz_exc_initialized" in st.session_state:
        return

    default_keys = get_default_exclusion_keys(issues, proj_key, release_id)
    st.session_state["wiz_exc_selected_keys"] = default_keys
    for iss in issues:
        key = iss["key"]
        st.session_state[_checkbox_key(key)] = key in default_keys
    st.session_state["wiz_exc_initialized"] = True


def _read_selection(issues: list[dict]) -> set[str]:
    selected: set[str] = set()
    default_selected = st.session_state.get("wiz_exc_selected_keys", set())
    for iss in issues:
        key = iss["key"]
        if st.session_state.get(_checkbox_key(key), key in default_selected):
            selected.add(key)
    return selected


def _set_selection(issues: list[dict], selected_keys: set[str]) -> None:
    st.session_state["wiz_exc_selected_keys"] = selected_keys
    for iss in issues:
        key = iss["key"]
        st.session_state[_checkbox_key(key)] = key in selected_keys


def _refresh_release_issues(proj_key: str, release: dict) -> tuple[list[dict], list[dict]]:
    """Re-fetch fix-version tickets; return (raw_issues, filtered_deploy_issues)."""
    cache_key = _raw_cache_key(proj_key, release.get("id"))
    st.session_state.pop(cache_key, None)
    st.session_state.pop("wiz_grouped", None)
    raw_issues = jira_client.get_issues_for_version(proj_key, release["id"])
    st.session_state[cache_key] = raw_issues
    filtered = _sync_filtered_deploy_issues(raw_issues, proj_key, release)
    return raw_issues, filtered


def _apply_exclusion_and_continue(
    *,
    selected_keys: set[str],
    raw_issues: list[dict],
    proj_key: str,
    release: dict,
    version_id: str,
    version_name: str,
) -> None:
    """Remove fix version from selected tickets, refresh caches, then go to step 4."""
    issues_by_key = {iss["key"]: iss for iss in raw_issues}
    try:
        with st.spinner("Updating tickets in Jira…"):
            result = jira_client.remove_fix_version_from_issues(
                sorted(selected_keys),
                version_id,
                issues_by_key=issues_by_key,
            )
    except Exception as exc:
        st.error(f"Failed to update tickets: {exc}")
        return

    if result["success"]:
        prev = set(st.session_state.get("wiz_removed_from_release", []))
        st.session_state["wiz_removed_from_release"] = sorted(
            prev | set(result["success"])
        )
        raw_after, _filtered = _refresh_release_issues(proj_key, release)
        reset_exclude_selection_for_issues(
            raw_after, proj_key, str(release.get("id", "")),
        )
        remaining = {iss["key"] for iss in raw_after}
        _set_selection(raw_after, selected_keys & remaining)
        st.success(
            f"Removed **{version_name}** from "
            + ", ".join(f"**{k}**" for k in result["success"])
        )
    if result["skipped"]:
        st.warning(
            "Already removed or not on this version: "
            + ", ".join(result["skipped"])
        )
    for key, msg in result["errors"]:
        st.error(f"{key}: {msg}")

    if result["errors"] and not result["success"]:
        return

    st.session_state.pop("wiz_exc_confirm", None)
    go(4)


def render() -> None:
    proj_key = st.session_state.get("wiz_project", "")
    release = st.session_state.get("wiz_release", {})
    proj_cfg = get_project_cfg(proj_key)
    if not proj_cfg or not release.get("id"):
        go(1)
        return

    version_id = str(release["id"])
    version_name = release.get("name", "?")

    try:
        raw_issues = _load_raw_issues(proj_key, release)
    except Exception as exc:
        st.error(f"Failed to load tickets: {exc}")
        col_l, _ = st.columns([1, 5])
        with col_l:
            if st.button("\u2190 Back", use_container_width=True):
                go(2)
        return

    # Keep deploy candidates filtered for later steps, but select against raw list.
    _sync_filtered_deploy_issues(raw_issues, proj_key, release)
    reset_exclude_selection_for_issues(raw_issues, proj_key, version_id)

    if not raw_issues:
        st.warning("No tickets on this fix version.")
        col_l, _, col_r = st.columns([1, 4, 1])
        with col_l:
            if st.button("\u2190 Back", use_container_width=True):
                go(2)
        with col_r:
            if st.button("Next \u2192", type="primary", use_container_width=True):
                go(4)
        return

    _init_selection(raw_issues, proj_key, version_id)
    snapshot_keys = get_snapshot_included_keys_for_project(proj_key)
    review_exclusions = get_default_exclusion_keys(raw_issues, proj_key, version_id)

    st.markdown(f"## Exclude Tickets — {version_name}")
    st.caption(
        "Select tickets that should **not ship** with this release, then exclude "
        "and continue. This removes their fix version in Jira immediately. "
        "To skip post-deploy comments only (ticket stays on the version), leave "
        "them unchecked here and **uncheck them on Review**."
    )
    render_stay_on_page_hint(action_label="Exclude & Continue →")

    if snapshot_keys is not None:
        if review_exclusions:
            st.info(
                f"Pre-selected **{len(review_exclusions)}** ticket(s) that were "
                "deselected in Ticket Review. Confirm below, then exclude & continue."
            )
        else:
            st.success(
                "All tickets on this fix version match your Ticket Review selection. "
                "You can still select tickets to exclude, or continue without excluding."
            )
    else:
        st.info("No Ticket Review snapshot — select tickets manually below.")

    removed_keys = st.session_state.get("wiz_removed_from_release", [])
    if removed_keys:
        st.success(
            "Already removed fix version from: "
            + ", ".join(f"**{k}**" for k in sorted(removed_keys))
        )

    selected_keys = _read_selection(raw_issues)
    st.markdown(
        f"**{len(selected_keys)}/{len(raw_issues)}** ticket(s) selected to exclude"
    )
    if not selected_keys:
        render_empty_selection_hint(mode_label="tickets to exclude")

    btn1, btn2, btn3, _ = st.columns([1, 1, 1, 3])
    with btn1:
        if st.button("Select all", key="wiz_exc_select_all"):
            _set_selection(raw_issues, {iss["key"] for iss in raw_issues})
            st.rerun()
    with btn2:
        if st.button("Deselect all", key="wiz_exc_deselect_all"):
            _set_selection(raw_issues, set())
            st.rerun()
    with btn3:
        if st.button("Reset to review exclusions", key="wiz_exc_reset_defaults"):
            _set_selection(
                raw_issues,
                get_default_exclusion_keys(raw_issues, proj_key, version_id),
            )
            st.rerun()

    st.markdown("")
    for iss in raw_issues:
        key = iss["key"]
        fields = iss.get("fields", {})
        summary = esc(fields.get("summary", ""))
        status_name = esc(fields.get("status", {}).get("name", "?"))
        if snapshot_keys is not None:
            tag = "in release" if key in snapshot_keys else "excluded in review"
        else:
            tag = "on fix version"
        label = f"**{key}** — {summary}  ·  _{status_name}_  ·  _{tag}_"
        chk_key = _checkbox_key(key)
        if chk_key not in st.session_state:
            st.session_state[chk_key] = key in selected_keys
        st.checkbox(label, key=chk_key)

    selected_keys = _read_selection(raw_issues)
    st.session_state["wiz_exc_selected_keys"] = selected_keys

    st.markdown("")
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if st.button("\u2190 Back", use_container_width=True):
            st.session_state.pop("wiz_exc_confirm", None)
            go(2)

    with col_r:
        if selected_keys:
            confirming = st.session_state.get("wiz_exc_confirm", False)
            if not confirming:
                if st.button(
                    f"Exclude selected & continue ({len(selected_keys)})",
                    type="primary",
                    use_container_width=True,
                    key="wiz_exc_apply_continue",
                ):
                    st.session_state["wiz_exc_confirm"] = True
                    st.rerun()
            else:
                st.warning(
                    f"**Confirm:** remove fix version **{version_name}** from "
                    f"**{len(selected_keys)}** ticket(s), then continue to "
                    "Deployment Info?"
                )
                c_yes, c_no = st.columns(2)
                with c_yes:
                    if st.button(
                        "Yes, exclude & continue",
                        type="primary",
                        use_container_width=True,
                        key="wiz_exc_confirm_yes",
                    ):
                        _apply_exclusion_and_continue(
                            selected_keys=selected_keys,
                            raw_issues=raw_issues,
                            proj_key=proj_key,
                            release=release,
                            version_id=version_id,
                            version_name=version_name,
                        )
                with c_no:
                    if st.button(
                        "Cancel",
                        use_container_width=True,
                        key="wiz_exc_confirm_no",
                    ):
                        st.session_state.pop("wiz_exc_confirm", None)
                        st.rerun()
        else:
            remaining_review = review_exclusions
            if remaining_review:
                st.warning(
                    f"**{len(remaining_review)}** Ticket Review exclusion(s) still "
                    "have this fix version: "
                    + ", ".join(f"**{k}**" for k in sorted(remaining_review))
                    + ". Select them above to exclude, or continue without removing "
                    "the fix version."
                )
            if st.button(
                "Continue without excluding",
                type="primary",
                use_container_width=True,
                key="wiz_exc_continue_none",
            ):
                go(4)
