"""Step 2 — Fetch tickets from all selected projects, let user select/deselect."""

from __future__ import annotations

import streamlit as st

import config
import jira_client
import release_gates
from release_platform.ui import jira_team_filter as jtf
from release_platform.ui import ticket_source as ts
from release_platform.ui.gate_panel import render_post_qa_panel
from release_platform.ui.helpers import (
    esc,
    filter_snapshot_issues,
    get_snapshot,
    render_ticket_table,
    sync_rn_ticket_draft,
)
from release_platform.ui.ticket_selection_page import (
    clear_step2_loaded,
    issues_fingerprint,
    mark_step2_loaded,
    render_empty_selection_hint,
    render_stay_on_page_hint,
)
from release_platform.ui.workflow import is_release_notes_standalone, render_action_hint

try:
    from release_mcp import release_ops as _release_ops
except ImportError:  # pragma: no cover - streamlit without package layout
    _release_ops = None

_PREFIX = "rn_"


def _go(step: int) -> None:
    from session_persist import persist_session

    persist_session(dict(st.session_state))
    st.session_state["rn_step"] = step
    st.rerun()


def _checkbox_key(ticket_key: str) -> str:
    return f"rn_chk_{ticket_key}"


def _set_ticket_selection(all_extracted: list[dict], selected_keys: set[str]) -> None:
    st.session_state["rn_selected_keys"] = selected_keys
    for info in all_extracted:
        st.session_state[_checkbox_key(info["ticket"])] = info["ticket"] in selected_keys


def _read_ticket_selection(all_extracted: list[dict]) -> set[str]:
    selected: set[str] = set()
    for info in all_extracted:
        key = info["ticket"]
        if st.session_state.get(_checkbox_key(key), False):
            selected.add(key)
    return selected


def _clear_issue_cache(*, clear_selection: bool = False) -> None:
    jtf.clear_issue_caches_for_prefix(_PREFIX)
    st.session_state.pop("rn_all_extracted", None)
    st.session_state.pop("rn_source_fp", None)
    st.session_state.pop("rn_issues_fp", None)
    if clear_selection:
        st.session_state.pop("rn_selected_keys", None)
        for key in list(st.session_state.keys()):
            if key.startswith("rn_chk_"):
                st.session_state.pop(key, None)


def _initial_selection(all_extracted: list[dict]) -> set[str]:
    snap = get_snapshot()
    snap_keys = set(snap.get("ticket_keys", [])) if snap else set()
    all_ticket_keys = {e["ticket"] for e in all_extracted}
    if snap_keys:
        return snap_keys & all_ticket_keys
    if ts.get_effective_selection_mode(_PREFIX) == ts.MODE_STATUS:
        return all_ticket_keys
    if is_release_notes_standalone():
        return all_ticket_keys
    return set()


def _ensure_checkbox_defaults(all_extracted: list[dict]) -> None:
    """Seed checkbox keys once — never overwrite after widgets exist."""
    if "rn_selected_keys" not in st.session_state:
        _set_ticket_selection(all_extracted, _initial_selection(all_extracted))
        return
    selected = set(st.session_state.get("rn_selected_keys") or [])
    for info in all_extracted:
        chk = _checkbox_key(info["ticket"])
        if chk not in st.session_state:
            st.session_state[chk] = info["ticket"] in selected


def _team_ids_for_project(project_key: str) -> list[str] | None:
    ids = jtf.get_selected_team_ids(_PREFIX, project_key)
    return ids if ids else None


def _issues_from_extracted(all_extracted: list[dict]) -> list[dict]:
    """Minimal Jira-shaped issues from cached extracted rows (session recovery)."""
    return [
        {
            "key": row["ticket"],
            "fields": {
                "summary": row.get("summary", ""),
                "assignee": {"displayName": row.get("assignee", "")},
                "parent": {"key": row.get("parent", row["ticket"])},
            },
        }
        for row in all_extracted
    ]


def _fetch_combined_issues(*, force: bool = False) -> list[dict]:
    ts.apply_locked_ticket_source(_PREFIX)
    standalone = is_release_notes_standalone()
    snap = get_snapshot()
    mode = ts.get_effective_selection_mode(_PREFIX)

    use_snapshot = (
        not standalone
        and snap
        and snap.get("issues")
    )
    if use_snapshot:
        return filter_snapshot_issues(snap)

    return ts.fetch_combined_issues(
        _PREFIX,
        issues_cache_prefix="_rn_issues_",
        team_ids_for_project=_team_ids_for_project,
        force=force,
    )


def _extract_all(issues: list[dict]) -> list[dict]:
    """Extract ticket info; preserve manual checkbox selection across reruns."""
    if "rn_all_extracted" in st.session_state:
        return st.session_state["rn_all_extracted"]

    from generators.release_notes_quality import improve_extracted

    extracted: list[dict] = []
    for idx, iss in enumerate(issues):
        key = iss["key"]
        fields = iss.get("fields", {})
        summary = fields.get("summary", "")
        info = jira_client.extract_ticket_info(summary, key)
        info["ticket"] = key
        info["summary"] = summary
        assignee = fields.get("assignee") or {}
        info["assignee"] = assignee.get("displayName", "")
        parent = fields.get("parent") or {}
        info["parent"] = parent.get("key", key)
        info["parent_epic"] = parent.get("key", key)
        info["sno"] = str(idx + 1)
        info["link"] = f"{config.JIRA_BASE_URL}/browse/{key}"
        extracted.append(info)

    extracted = improve_extracted(extracted)
    for idx, info in enumerate(extracted):
        info["sno"] = str(idx + 1)

    st.session_state["rn_all_extracted"] = extracted
    st.session_state["rn_source_fp"] = ts.selection_fingerprint(_PREFIX)
    st.session_state["rn_issues_fp"] = issues_fingerprint(issues)
    return extracted


@st.fragment
def _ticket_selection_fragment(all_extracted: list[dict]) -> None:
    """Checkbox list — reruns only this block so deselect never navigates away."""
    _ensure_checkbox_defaults(all_extracted)

    selected_keys = _read_ticket_selection(all_extracted)
    st.session_state["rn_selected_keys"] = selected_keys

    st.markdown(
        f"**{len(selected_keys)}/{len(all_extracted)} tickets selected** "
        f"(Analyze + Custom)"
    )

    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        if st.button("Select All", key="rn_sel_all", use_container_width=True):
            _set_ticket_selection(all_extracted, {e["ticket"] for e in all_extracted})
    with c2:
        if st.button("Deselect All", key="rn_desel_all", use_container_width=True):
            _set_ticket_selection(all_extracted, set())

    st.markdown("")

    analyze_tickets = [e for e in all_extracted if e["type"] == "Analyze"]
    custom_tickets = [e for e in all_extracted if e["type"] == "Custom"]

    if analyze_tickets:
        st.markdown(f"#### Analyze Tickets ({len(analyze_tickets)})")
        for info in analyze_tickets:
            st.checkbox(
                f"**{info['ticket']}** — {info['report']} • {info['description']}",
                key=_checkbox_key(info["ticket"]),
            )

    if custom_tickets:
        st.markdown(f"#### Custom Tickets ({len(custom_tickets)})")
        for info in custom_tickets:
            st.checkbox(
                f"**{info['ticket']}** — {info['client']} • {info['report']} • {info['description']}",
                key=_checkbox_key(info["ticket"]),
            )

    selected_keys = _read_ticket_selection(all_extracted)
    st.session_state["rn_selected_keys"] = selected_keys

    if not selected_keys:
        render_empty_selection_hint()


def _apply_release_ready_filter(*, include_override: str = "") -> None:
    """Re-fetch with release-ready statuses (MCP Step 3 parity) and refresh ticket list."""
    if _release_ops is None:
        st.error("Release-ready filter requires the jira-release-tool package (mcp).")
        return
    snap = get_snapshot() or {}
    locked = [str(k).strip().upper() for k in (snap.get("ticket_keys") or []) if str(k).strip()]
    if not locked:
        locked = [
            str(k).strip().upper()
            for k in (st.session_state.get("rn_selected_keys") or [])
            if str(k).strip()
        ]
    projects = [p["key"] for p in config.PROJECTS]
    team_map: dict[str, list[str]] = {}
    for pk in projects:
        ids = _team_ids_for_project(pk)
        if ids:
            team_map[pk] = ids
    override_keys = [
        part.strip().upper()
        for part in include_override.replace(",", " ").split()
        if part.strip() and "-" in part
    ]
    stored = list(st.session_state.get("rn_include_override_keys") or [])
    include_keys = list(dict.fromkeys(stored + override_keys))

    with st.spinner("Fetching release-ready tickets (Ready for Release / QA(migrated))…"):
        result = _release_ops.fetch_release_notes_extracted(
            selection_mode=ts.MODE_STATUS,
            projects=projects,
            locked_ticket_keys=locked,
            include_ticket_keys=include_keys,
            jira_team_ids_by_project=team_map or None,
        )

    st.session_state["rn_release_ready_fetch"] = {
        "not_release_ready_keys": result.get("not_release_ready_keys") or [],
        "explicit_override_keys": result.get("explicit_override_keys") or [],
        "release_ready_ticket_keys": result.get("release_ready_ticket_keys") or [],
    }
    if result.get("status") != "ok":
        st.warning(result.get("message") or "No release-ready tickets matched.")
        return

    extracted = list(result.get("extracted") or [])
    if not extracted:
        st.warning(result.get("message") or "No release-ready tickets matched.")
        return

    st.session_state["rn_include_override_keys"] = include_keys
    st.session_state["rn_all_extracted"] = extracted
    st.session_state.pop("rn_source_fp", None)
    st.session_state.pop("rn_issues_fp", None)
    selected = {row["ticket"] for row in extracted}
    _set_ticket_selection(extracted, selected)
    st.session_state["rn_selected_keys"] = selected
    st.success(
        "Applied release-ready filter: "
        + ", ".join(result.get("release_ready_ticket_keys") or [])
    )
    st.rerun()


def _advance_to_edit_content(all_extracted: list[dict], selected_keys: set[str]) -> None:
    sync_rn_ticket_draft(selected_keys)
    filtered = [e for e in all_extracted if e["ticket"] in selected_keys]
    for i, entry in enumerate(filtered):
        entry["sno"] = str(i + 1)
    st.session_state["rn_extracted"] = filtered
    st.session_state["rn_source_fp"] = ts.selection_fingerprint(_PREFIX)
    _go(3)


def render() -> None:
    ts.apply_locked_ticket_source(_PREFIX)
    mode = ts.get_effective_selection_mode(_PREFIX)

    st.markdown("## Tickets Overview")
    st.caption(
        "**Step 2 of 4** — Check the tickets to include. "
        "**Step 3** edits summaries; **Step 4** previews and downloads the Word file."
    )
    render_stay_on_page_hint(action_label="Next → Edit Content (Step 3)")

    source_label = (
        f"**By status:** {esc(ts.effective_selection_summary(prefix=_PREFIX))}"
        if mode == ts.MODE_STATUS
        else f"**Fix version:** {esc(ts.effective_selection_summary(prefix=_PREFIX))}"
    )
    if ts.effective_selection_summary(prefix=_PREFIX):
        st.info(source_label, icon=":material/filter_list:")

    if mode == ts.MODE_STATUS and _release_ops is not None:
        st.caption(
            "**Platform ↔ MCP parity:** Step 1 uses review statuses; release notes should use "
            "**Ready for Release** (PIC) and **QA(migrated)** (AN). Use the filter below before Step 3."
        )
        rr_meta = st.session_state.get("rn_release_ready_fetch") or {}
        if rr_meta.get("not_release_ready_keys"):
            st.warning(
                "Not release-ready: "
                + ", ".join(rr_meta["not_release_ready_keys"])
            )
        if rr_meta.get("explicit_override_keys"):
            st.info(
                "Explicit overrides: "
                + ", ".join(rr_meta["explicit_override_keys"])
            )
        with st.expander("Release-ready filter (MCP Step 3 parity)", expanded=False):
            override_raw = st.text_input(
                "Include ticket by key (override)",
                placeholder="PIC-5966 or PIC-5966, AN-1234",
                key="rn_include_override_input",
            )
            if st.button(
                "Apply release-ready filter",
                key="rn_apply_release_ready",
                use_container_width=True,
            ):
                _apply_release_ready_filter(include_override=override_raw.strip())

    # Never bounce to Step 1 while the user is actively on Step 2.
    if st.session_state.get("rn_step") == 2:
        mark_step2_loaded(_PREFIX)

    snap = get_snapshot()
    if (
        not is_release_notes_standalone()
        and snap
        and snap.get("ticket_keys")
        and mode == ts.MODE_STATUS
        and _release_ops is not None
        and not st.session_state.get("rn_release_ready_auto_applied")
    ):
        st.session_state["rn_release_ready_auto_applied"] = True
        _apply_release_ready_filter(
            include_override=str(st.session_state.get("rn_include_override_input") or "").strip()
        )
        return

    has_anchor = (
        st.session_state.get("rn_step") == 2
        or st.session_state.get(f"{_PREFIX}step2_loaded")
        or st.session_state.get("rn_all_extracted")
    )
    if not has_anchor and not ts.has_step1_selection(prefix=_PREFIX) and not (
        snap and snap.get("issues")
    ):
        _go(1)
        return

    title_col, refresh_col = st.columns([6, 1])
    with title_col:
        team_summary = jtf.team_filter_summary(_PREFIX)
        if team_summary != "All teams (no Team filter)":
            st.markdown(f"**Team filter:** {esc(team_summary)}")
    with refresh_col:
        if st.button("🔄 Refresh", key="rn_s2_refresh", use_container_width=True):
            _clear_issue_cache(clear_selection=True)
            st.rerun()

    try:
        label = (
            "Fetching tickets for selected statuses…"
            if mode == ts.MODE_STATUS
            else "Fetching tickets from all selected releases…"
        )
        with st.spinner(label):
            issues = _fetch_combined_issues()
            if not issues and st.session_state.get("rn_all_extracted"):
                issues = _fetch_combined_issues(force=True)
            if not issues and st.session_state.get("rn_all_extracted"):
                cached_fp = st.session_state.get("rn_source_fp")
                if cached_fp and cached_fp == ts.selection_fingerprint(_PREFIX):
                    issues = _issues_from_extracted(st.session_state["rn_all_extracted"])
    except Exception as exc:
        st.error(f"Failed to fetch tickets: {exc}")
        if st.button("← Change filters (Step 1)", key="rn_s2_err_back"):
            clear_step2_loaded(_PREFIX)
            _go(1)
        return

    if not issues:
        summary = ts.effective_selection_summary(prefix=_PREFIX)
        if mode == ts.MODE_STATUS:
            st.warning(
                f"No tickets found for the selected statuses"
                + (f": {esc(summary)}" if summary else ".")
            )
            st.caption(
                "Status mode is separate from fix version. Try **Refresh**, adjust the "
                "**Team filter**, or go back to change statuses."
            )
        else:
            st.warning(
                "No tickets found in the selected releases"
                + (f": {esc(summary)}" if summary else ".")
            )
            st.caption(
                "Pick at least one fix version on Step 1, or switch to **By status** "
                "if you are not using release versions."
            )
        if st.button("← Change filters (Step 1)", key="rn_s2_empty_back"):
            clear_step2_loaded(_PREFIX)
            ts.clear_locked_ticket_source(_PREFIX)
            _go(1)
        return

    mark_step2_loaded(_PREFIX)

    parts: list[str] = []
    summary = ts.effective_selection_summary(prefix=_PREFIX)
    if summary:
        parts.append(summary)

    all_extracted = _extract_all(issues)

    if parts:
        st.markdown(f"**{' + '.join(parts)}**")

    with st.expander("Full Ticket Table (Owner / Status / Link)", expanded=False):
        render_ticket_table(issues)

    _ticket_selection_fragment(all_extracted)

    selected_keys = set(st.session_state.get("rn_selected_keys") or _read_ticket_selection(all_extracted))

    def _apply_qa_exclusions(blocked, payload) -> None:
        blocked_keys = {t.key for t in blocked}
        st.session_state["rn_selected_keys"] = selected_keys - blocked_keys
        for info in all_extracted:
            key = info["ticket"]
            st.session_state[_checkbox_key(key)] = key in st.session_state["rn_selected_keys"]
        existing = st.session_state.get("rn_excluded_tickets", "")
        st.session_state["rn_excluded_tickets"] = release_gates.merge_excluded_text(
            existing, blocked,
        )
        snap_inner = get_snapshot()
        if snap_inner is not None:
            qa_keys = sorted(set(snap_inner.get("qa_excluded_keys") or []) | blocked_keys)
            snap_inner["qa_excluded_keys"] = qa_keys
            excluded = sorted(set(snap_inner.get("excluded_keys") or []) | blocked_keys)
            snap_inner["excluded_keys"] = excluded
            locked = [k for k in snap_inner.get("ticket_keys", []) if k not in blocked_keys]
            snap_inner["ticket_keys"] = locked
            st.session_state["shared_snapshot"] = snap_inner
            from session_persist import persist_session

            persist_session(dict(st.session_state))
        st.rerun()

    render_post_qa_panel(
        issues,
        extracted=all_extracted,
        selected_keys=selected_keys,
        on_apply=_apply_qa_exclusions,
        session_prefix="rn_",
    )
    selected_keys = set(st.session_state.get("rn_selected_keys") or selected_keys)

    st.markdown("---")
    st.markdown("### Continue to next step")
    st.caption(
        "When your ticket list looks right, go to **Step 3 — Edit Content** "
        "to review summaries, metadata, and the change table before generating the .docx."
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Change filters (Step 1)", key="rn_s2_back", use_container_width=True):
            for info in all_extracted:
                st.session_state.pop(_checkbox_key(info["ticket"]), None)
            _clear_issue_cache(clear_selection=True)
            clear_step2_loaded(_PREFIX)
            ts.clear_locked_ticket_source(_PREFIX)
            _go(1)
    with c2:
        next_label = f"Next → Edit Content (Step 3 of 4) — {len(selected_keys)} ticket(s)"
        if not selected_keys:
            st.button(next_label, type="primary", key="rn_s2_next", disabled=True)
            st.caption("Select at least one ticket above to continue.")
        elif st.button(next_label, type="primary", key="rn_s2_next", use_container_width=True):
            _advance_to_edit_content(all_extracted, selected_keys)
        else:
            render_action_hint(
                "Opens Step 3 where you edit release notes text before preview and download."
            )
