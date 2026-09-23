"""Step 2 — Fetch tickets, show table with select/deselect, then proceed."""

from __future__ import annotations

import hashlib

import streamlit as st

import config
import jira_client
import release_gates
from release_platform.ui.helpers import (
    clear_ticket_review_lock,
    create_snapshot,
    esc,
    get_snapshot,
    get_snapshot_ticket_keys,
    render_ticket_table,
    snapshot_selection_pending,
)
from release_platform.ui.gate_panel import render_pre_review_panel
from release_platform.ui.ticket_review.jira_team_filter import (
    clear_ticket_review_issue_caches,
    team_filter_summary,
    team_filters_for_snapshot,
    snapshot_team_filter_matches,
)
from release_platform.ui.ticket_review.selection import (
    MODE_STATUS,
    apply_locked_ticket_source,
    apply_snapshot_selection_context,
    clear_locked_ticket_source,
    effective_selection_summary,
    fetch_combined_issues,
    get_effective_selection_mode,
    get_selection_mode,
    get_selected_statuses,
    has_fix_version_selection,
    has_status_selection,
    has_step1_selection,
    initial_ticket_selection,
)
from release_platform.ui.ticket_selection_page import (
    mark_step2_loaded,
    render_empty_selection_hint,
    render_stay_on_page_hint,
)
from release_platform.ui.workflow import render_action_hint
from release_platform.ui.teams_panel import render_teams_schedule_panel
from teams_meeting_content import MeetingContext


def _go(step: int) -> None:
    st.session_state["tr_step"] = step
    st.rerun()


def _clear_issue_cache() -> None:
    clear_ticket_review_issue_caches()
    clear_locked_ticket_source()


def _fetch_combined_issues(*, force: bool = False) -> list[dict]:
    apply_locked_ticket_source()
    return fetch_combined_issues(force=force)


def _checkbox_key(ticket_key: str) -> str:
    return f"tr_chk_{ticket_key}"


def _set_ticket_selection(issues: list[dict], selected_keys: set[str]) -> None:
    st.session_state["tr_selected_keys"] = selected_keys
    for iss in issues:
        st.session_state[_checkbox_key(iss["key"])] = iss["key"] in selected_keys


def _read_ticket_selection(issues: list[dict]) -> set[str]:
    selected: set[str] = set()
    for iss in issues:
        key = iss["key"]
        if st.session_state.get(
            _checkbox_key(key),
            key in st.session_state.get("tr_selected_keys", set()),
        ):
            selected.add(key)
    return selected


def _get_owner(iss: dict) -> str:
    assignee = iss.get("fields", {}).get("assignee") or {}
    return assignee.get("displayName", "Unassigned")


def _issues_fingerprint(issues: list[dict]) -> str:
    keys = sorted(str(iss.get("key") or "") for iss in issues)
    keys = [k for k in keys if k]
    return hashlib.sha256("|".join(keys).encode("utf-8")).hexdigest()[:16]


def _reset_ticket_checkboxes(issues: list[dict]) -> None:
    for iss in issues:
        st.session_state.pop(_checkbox_key(iss["key"]), None)
    st.session_state.pop("tr_selected_keys", None)


def _ensure_step1_context() -> bool:
    """Restore status/version context from locked source or snapshot."""
    apply_locked_ticket_source()
    snap = get_snapshot()
    if snap:
        apply_snapshot_selection_context(snap)
        apply_locked_ticket_source()

    if has_step1_selection():
        return True

    mode = get_effective_selection_mode()
    if mode == MODE_STATUS:
        if snap and snap.get("status_filters"):
            apply_snapshot_selection_context(snap)
            apply_locked_ticket_source()
            return has_step1_selection() or has_status_selection()
        return False
    return has_fix_version_selection()


def _owner_action_key(owner: str, action: str) -> str:
    digest = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:10]
    return f"tr_owner_{action}_{digest}"


@st.fragment
def _ticket_selection_fragment(
    issues: list[dict],
    owners_sorted: dict[str, list[dict]],
    snap_keys: set[str] | None,
) -> None:
    """Checkbox list — reruns only this block so toggling tickets stays on Step 2."""
    selected_keys = _read_ticket_selection(issues)

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        if st.button("Select All", key="tr_sel_all", use_container_width=True):
            _set_ticket_selection(issues, {iss["key"] for iss in issues})
    with c2:
        if st.button("Deselect All", key="tr_desel_all", use_container_width=True):
            _set_ticket_selection(issues, set())
    with c3:
        if snap_keys is not None and st.button(
            "Clear lock",
            key="tr_clear_lock",
            use_container_width=True,
        ):
            clear_ticket_review_lock()
            st.rerun()
    with c4:
        if snap_keys is not None and snapshot_selection_pending(selected_keys):
            if st.button("Reset to locked list", key="tr_reset_locked", use_container_width=True):
                _set_ticket_selection(issues, snap_keys & {iss["key"] for iss in issues})

    st.markdown("")

    for owner in sorted(owners_sorted.keys()):
        owner_issues = owners_sorted[owner]
        owner_selected = [i for i in owner_issues if i["key"] in selected_keys]
        with st.expander(
            f"**{esc(owner)}** \u2014 {len(owner_selected)}/{len(owner_issues)} selected",
            expanded=True,
        ):
            sel_col, des_col, _ = st.columns([1, 1, 4])
            with sel_col:
                if st.button(
                    "Select all",
                    key=_owner_action_key(owner, "sel"),
                    use_container_width=True,
                ):
                    st.session_state["_tr_owner_selection_pending"] = (
                        owner,
                        "sel",
                        [i["key"] for i in owner_issues],
                    )
                    st.rerun()
            with des_col:
                if st.button(
                    "Deselect all",
                    key=_owner_action_key(owner, "des"),
                    use_container_width=True,
                ):
                    st.session_state["_tr_owner_selection_pending"] = (
                        owner,
                        "des",
                        [i["key"] for i in owner_issues],
                    )
                    st.rerun()
            for iss in owner_issues:
                key = iss["key"]
                fields = iss.get("fields", {})
                summary = fields.get("summary", "")
                status_name = fields.get("status", {}).get("name", "")
                label = f"**{key}** \u2014 {summary}  \u00b7  _{status_name}_"
                chk_key = _checkbox_key(key)
                if chk_key not in st.session_state:
                    st.session_state[chk_key] = key in selected_keys
                st.checkbox(label, key=chk_key)

    st.session_state["tr_selected_keys"] = _read_ticket_selection(issues)


def _apply_owner_selection(
    owner_issues: list[dict],
    *,
    select: bool,
    all_issues: list[dict],
) -> None:
    owner_keys = {iss["key"] for iss in owner_issues}
    current = _read_ticket_selection(all_issues)
    if select:
        current |= owner_keys
    else:
        current -= owner_keys
    _set_ticket_selection(all_issues, current)


def render() -> None:
    apply_locked_ticket_source()

    pending_owner = st.session_state.pop("_tr_owner_selection_pending", None)
    if pending_owner:
        owner, action, issue_keys = pending_owner
        all_issues = st.session_state.get("_tr_step2_issues") or []
        owner_issues = [i for i in all_issues if i["key"] in issue_keys]
        if owner_issues and all_issues:
            _apply_owner_selection(
                owner_issues,
                select=action == "sel",
                all_issues=all_issues,
            )
        st.rerun()

    st.markdown("## Review Tickets")

    snap_keys = get_snapshot_ticket_keys()
    mode = get_effective_selection_mode()
    if snap_keys is None:
        if mode == MODE_STATUS:
            st.markdown(
                '<div class="jt-banner jt-banner--info" style="margin-bottom:12px">'
                "<strong>Status mode:</strong> Tickets in <strong>Review</strong> (PIC) and "
                "<strong>Passed QA</strong> (AN) are pre-selected. Adjust checkboxes, then click "
                "<strong>Generate Review List →</strong> when ready."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="jt-banner jt-banner--info" style="margin-bottom:12px">'
                "<strong>Manual selection:</strong> Check the tickets you want in this release. "
                "Nothing is pre-selected — use <strong>Select All</strong> or pick individually, "
                "then click <strong>Generate Review List →</strong> when ready."
                "</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="jt-banner jt-banner--info" style="margin-bottom:12px">'
            f"<strong>Locked list active</strong> — {len(snap_keys)} tickets in the saved list. "
            "Adjust checkboxes here anytime; use <strong>Clear lock</strong> to unlock downstream "
            "steps without leaving this page, or <strong>Generate Review List →</strong> to save changes."
            "</div>",
            unsafe_allow_html=True,
        )

    if mode == MODE_STATUS:
        if not _ensure_step1_context():
            if st.session_state.get("tr_issues_fp"):
                st.warning(
                    "Board/status filter context was lost from session. "
                    "Tickets below are from your last load — adjust checkboxes freely, "
                    "or click **Change filters** to pick new statuses."
                )
            else:
                _go(1)
                return
    elif not _ensure_step1_context():
        if st.session_state.get("tr_issues_fp"):
            st.warning(
                "Release filter context was lost from session. "
                "Tickets below are from your last load — use **Change filters** to change release."
            )
        else:
            _go(1)
            return

    render_stay_on_page_hint(action_label="Generate Review List →")

    title_col, refresh_col = st.columns([6, 1])
    with title_col:
        pass
    with refresh_col:
        if st.button("\U0001f504 Refresh", key="tr_s2_refresh", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key.startswith("tr_chk_"):
                    st.session_state.pop(key, None)
            _clear_issue_cache()
            st.rerun()

    fetch_label = (
        "Fetching tickets for selected statuses\u2026"
        if mode == MODE_STATUS
        else "Fetching tickets from all selected releases\u2026"
    )
    try:
        with st.spinner(fetch_label):
            issues = _fetch_combined_issues()
    except Exception as exc:
        st.error(f"Failed to fetch tickets: {exc}")
        st.caption(
            f"Team filter: {team_filter_summary()}. "
            "Try **Unlock team filter**, clear teams, or click **Refresh** on Step 2."
        )
        if st.button("\u2190 Change filters", key="tr_s2_err_back"):
            _go(1)
        return

    if not issues:
        empty_msg = (
            "No tickets found for the selected statuses."
            if mode == MODE_STATUS
            else "No tickets found in the selected releases."
        )
        st.warning(empty_msg)
        if st.button("\u2190 Back"):
            _go(1)
        return

    issue_fp = _issues_fingerprint(issues)
    if st.session_state.get("tr_issues_fp") != issue_fp:
        st.session_state["tr_issues_fp"] = issue_fp
        if "tr_selected_keys" not in st.session_state:
            _reset_ticket_checkboxes(issues)
        st.session_state.pop("tr_grouped", None)

    mark_step2_loaded("tr_")

    if release_gates.skip_review_completed_comments_enabled():
        reviewable_issues: list[dict] = []
        held_review_comment: list[dict] = []
        for issue in issues:
            key = str(issue.get("key") or "")
            done, snippet = release_gates.ticket_has_review_completed_comment(key)
            if done:
                fields = issue.get("fields") or {}
                held_review_comment.append(
                    {
                        "key": key,
                        "summary": str(fields.get("summary") or ""),
                        "snippet": snippet,
                    }
                )
                continue
            reviewable_issues.append(issue)
        if held_review_comment:
            st.info(
                f"**{len(held_review_comment)}** ticket(s) hidden — Jira comments already mark review complete "
                f"(e.g. \"review completed\")."
            )
            with st.expander(f"Held back from review fetch ({len(held_review_comment)})", expanded=False):
                for row in held_review_comment:
                    st.markdown(f"- **{row['key']}** — {row['summary']}")
        issues = reviewable_issues
        if not issues:
            st.warning(
                "All fetched tickets already have review-complete comments. Move them to Ready for Release "
                "or use Release Notes when they are QA-ready."
            )
            if st.button("\u2190 Back"):
                _go(1)
            return

    if mode != MODE_STATUS and release_gates.ticket_review_pre_review_enabled():
        issues, _held_back = render_pre_review_panel(issues, session_prefix="tr_")
        if not issues:
            st.warning(
                "No tickets are in a review-ready Jira status. Move tickets to In Review "
                "(or configure ready_statuses in workspace.yaml), or notify assignees above."
            )
            if st.button("\u2190 Back"):
                _go(1)
            return
    else:
        st.session_state.pop("tr_pre_review_held", None)

    if "tr_grouped" not in st.session_state:
        st.session_state["tr_grouped"] = jira_client.group_issues_by_assignee(issues)

    st.session_state["_tr_step2_issues"] = issues

    if "tr_selected_keys" not in st.session_state:
        initial = initial_ticket_selection(issues, snap_keys, mode=mode)
        _set_ticket_selection(issues, initial)

    selected_keys = _read_ticket_selection(issues)
    st.session_state["tr_selected_keys"] = selected_keys

    st.markdown(
        f"**{effective_selection_summary()}** \u2014 "
        f"{len(selected_keys)}/{len(issues)} tickets selected  \u00b7  "
        f"**Team:** {team_filter_summary()}"
    )

    owners_sorted: dict[str, list[dict]] = {}
    for iss in issues:
        owner = _get_owner(iss)
        owners_sorted.setdefault(owner, []).append(iss)

    _ticket_selection_fragment(issues, owners_sorted, snap_keys)
    selected_keys = _read_ticket_selection(issues)
    st.session_state["tr_selected_keys"] = selected_keys

    if snapshot_selection_pending(selected_keys):
        st.info(
            "Your checkbox selection differs from the locked list. "
            "Click **Generate Review List →** to save the update, or **Reset to locked list** "
            "to undo changes — you stay on this page either way."
        )
    elif get_snapshot() and not snapshot_team_filter_matches(team_filters_for_snapshot()):
        st.warning(
            "Your **Jira Team filter** differs from the locked ticket list. "
            "Click **Generate Review List →** after confirming the correct team and tickets."
        )
    elif not selected_keys:
        render_empty_selection_hint(mode_label="tickets")

    with st.expander("Full Ticket Table (Owner / Status / Link)", expanded=False):
        selected_issues = [i for i in issues if i["key"] in selected_keys]
        if selected_issues:
            render_ticket_table(selected_issues)
        else:
            st.info("No tickets selected.")

    with st.expander("Schedule Teams review call (optional)", expanded=False):
        render_teams_schedule_panel(
            kind="review",
            version="",
            meeting_context=MeetingContext(kind="review"),
        )

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Change filters", key="tr_s2_back"):
            for iss in issues:
                st.session_state.pop(_checkbox_key(iss["key"]), None)
            st.session_state.pop("tr_selected_keys", None)
            st.session_state.pop("tr_grouped", None)
            _go(1)
    with c2:
        if not selected_keys:
            st.button(
                "Generate Review List \u2192",
                type="primary",
                key="tr_s2_next",
                disabled=True,
            )
            st.caption("Select at least one ticket to continue.")
        else:
            if st.button(
                "Generate Review List \u2192",
                type="primary",
                key="tr_s2_next",
            ):
                filtered_grouped: dict[str, list[dict]] = {}
                for owner, owner_issues in owners_sorted.items():
                    kept = [i for i in owner_issues if i["key"] in selected_keys]
                    if kept:
                        filtered_grouped[owner] = kept
                st.session_state["tr_grouped"] = filtered_grouped
                snap = create_snapshot(
                    [i for i in issues if i["key"] in selected_keys],
                    candidate_keys={i["key"] for i in issues},
                )
                snap["selection_mode"] = mode
                if mode == MODE_STATUS:
                    snap["status_filters"] = {
                        proj["key"]: get_selected_statuses(proj["key"])
                        for proj in config.PROJECTS
                        if get_selected_statuses(proj["key"])
                    }
                st.session_state["shared_snapshot"] = snap
                st.session_state["tr_step"] = 3
                from session_persist import persist_session

                persist_session(dict(st.session_state))
                held = st.session_state.get("tr_pre_review_held") or []
                if held:
                    snap = st.session_state.get("shared_snapshot") or {}
                    snap["pre_review_held_keys"] = sorted(held)
                    st.session_state["shared_snapshot"] = snap
                    persist_session(dict(st.session_state))
                _go(3)
            render_action_hint(
                "Saves the locked ticket list used by Release Notes, SHIPIT, and Deployer."
            )
