"""Release timeline — the TCKTs the current user has reported.

Rendered inside the Service Ticket app as a secondary tab. Pulls from
``reporter = currentUser() AND project = TCKT`` and shows a filterable
timeline with CSV export and a read-only detail drawer.

The companion module :mod:`ui.history` still handles *deployment* history;
the two modules intentionally do not share state.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any

import streamlit as st

import config
import jira_client
from release_platform.ui.helpers import esc

logger = logging.getLogger(__name__)

_CACHE_KEY = "_tckt_history_cache"


def _load_tickets(force: bool = False, *, team_deployments: bool = False) -> list[dict[str, Any]]:
    cache_key = "_tckt_team_cache" if team_deployments else _CACHE_KEY
    cache = st.session_state.get(cache_key)
    if cache and not force:
        return cache
    if not config.TCKT_PROJECT_KEY:
        st.session_state[cache_key] = []
        return []
    try:
        with st.spinner("Loading SHIPIT history..."):
            if team_deployments:
                import tckt_reference
                tickets = tckt_reference.search_deployment_tickets(max_results=50)
            else:
                tickets = jira_client.search_my_service_desk_tickets(
                    config.TCKT_PROJECT_KEY
                )
    except Exception as exc:
        logger.debug("Failed to fetch TCKT history", exc_info=True)
        st.error(f"Failed to fetch SHIPIT history: {exc}")
        tickets = []
    st.session_state[cache_key] = tickets
    return tickets


def _matches_filters(
    ticket: dict[str, Any],
    *,
    query: str,
    status_filter: str,
    date_from,
    date_to,
    approver_filter: str,
) -> bool:
    fields = ticket.get("fields", {}) or {}
    summary = (fields.get("summary") or "").lower()
    key = (ticket.get("key") or "").lower()
    status = (fields.get("status", {}) or {}).get("name", "")

    if query and query.lower() not in summary and query.lower() not in key:
        return False
    if status_filter != "All" and status != status_filter:
        return False

    created_str = fields.get("created", "")
    created_dt = None
    if created_str:
        try:
            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        except ValueError:
            created_dt = None
    if (date_from or date_to) and created_dt is None:
        return False
    if date_from and created_dt and created_dt.date() < date_from:
        return False
    if date_to and created_dt and created_dt.date() > date_to:
        return False

    if approver_filter and approver_filter != "All":
        approvers = _format_approvers(fields)
        if approver_filter not in approvers:
            return False
    return True


def _format_approvers(fields: dict[str, Any]) -> list[str]:
    cf = (config.TCKT_FIELDS or {}).get("approvers", "")
    if not cf or cf not in fields:
        return []
    raw = fields.get(cf) or []
    if isinstance(raw, dict):
        raw = [raw]
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("displayName") or item.get("name") or item.get("accountId")
            if name:
                names.append(str(name))
    return names


def render_list(*, embedded: bool = False) -> None:
    """Render the filterable TCKT history table."""
    if not embedded and st.button("Back to Service Ticket"):
        st.session_state["stk_step"] = 1
        st.rerun()

    st.markdown("## Change Ticket History")
    st.caption(
        "Browse SHIPIT and legacy TCKT deployment change tickets. Use **Team deployments** "
        "to see all Customize BI production tickets (including SHIPIT-8346) and load one as a template."
    )

    view = st.radio(
        "Show",
        ["My tickets", "Team deployments"],
        horizontal=True,
        key="tckt_hist_view",
    )
    team_mode = view == "Team deployments"

    col_refresh, col_count = st.columns([1, 3])
    with col_refresh:
        if st.button("Refresh", key="tckt_history_refresh"):
            _load_tickets(force=True, team_deployments=team_mode)
            st.rerun()

    tickets = _load_tickets(team_deployments=team_mode)
    with col_count:
        st.caption(f"{len(tickets)} ticket(s) in history")

    if not tickets:
        st.info("No SHIPIT history yet.")
        return

    # ── Filters ──────────────────────────────────────────────────
    statuses = ["All"] + sorted({
        (t.get("fields", {}) or {}).get("status", {}).get("name", "")
        for t in tickets
    } - {""})
    approver_options = ["All"] + sorted({
        a for t in tickets for a in _format_approvers(t.get("fields", {}) or {})
    })

    f1, f2, f3 = st.columns([3, 1, 1])
    with f1:
        query = st.text_input(
            "Search by key or summary",
            value=st.session_state.get("tckt_hist_q", ""),
            key="tckt_hist_q",
            placeholder="TCKT-102259 or 'Glofox'",
            help="Filter by ticket key or summary text.",
        )
    with f2:
        status_filter = st.selectbox(
            "Status", statuses, key="tckt_hist_status",
            help="Filter by current ticket status.",
        )
    with f3:
        approver_filter = st.selectbox(
            "Approver", approver_options, key="tckt_hist_approver",
            help="Filter by approver display name.",
        )

    d1, d2 = st.columns(2)
    with d1:
        date_from = st.date_input(
            "From", value=None, key="tckt_hist_from",
            help="Only tickets created on/after this date.",
        )
    with d2:
        date_to = st.date_input(
            "To", value=None, key="tckt_hist_to",
            help="Only tickets created on/before this date.",
        )

    filtered = [
        t for t in tickets
        if _matches_filters(
            t,
            query=query or "",
            status_filter=status_filter,
            date_from=date_from,
            date_to=date_to,
            approver_filter=approver_filter,
        )
    ]
    st.caption(f"{len(filtered)} of {len(tickets)} after filters")

    # ── Export ───────────────────────────────────────────────────
    if filtered:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Key", "Created", "Status", "Summary", "Approvers"])
        for t in filtered:
            f = t.get("fields", {}) or {}
            writer.writerow([
                t.get("key", ""),
                f.get("created", ""),
                (f.get("status", {}) or {}).get("name", ""),
                f.get("summary", ""),
                "; ".join(_format_approvers(f)),
            ])
        st.download_button(
            "Export CSV",
            buf.getvalue().encode("utf-8"),
            file_name="tckt_history.csv",
            mime="text/csv",
            key="tckt_hist_export",
        )

    # ── Timeline table ───────────────────────────────────────────
    for t in filtered:
        _render_row(t)


def _render_row(ticket: dict[str, Any]) -> None:
    key = ticket.get("key", "")
    fields = ticket.get("fields", {}) or {}
    summary = fields.get("summary", "")
    status = (fields.get("status", {}) or {}).get("name", "")
    created_raw = fields.get("created", "")
    try:
        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        created_display = created.strftime("%d %b %Y")
    except Exception:
        created_display = (created_raw or "")[:10]
    approvers = ", ".join(_format_approvers(fields))

    st.markdown(
        f'<div class="hist-item">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<div><p class="hi-title">{esc(key)} — {esc(summary)}</p>'
        f'<p class="hi-meta">{esc(created_display)} · {esc(status)}</p></div>'
        f'<div style="opacity:.6;font-size:.75rem">{esc(approvers)}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([1, 1])
    with c1:
        jira_url = f"{config.JIRA_BASE_URL}/browse/{key}"
        st.markdown(f"[Open in Jira]({jira_url})", unsafe_allow_html=False)
    with c2:
        if st.button("View details", key=f"tckt_hist_view_{key}"):
            st.session_state["tckt_hist_detail_key"] = key
            st.rerun()
        if st.button("Use as template", key=f"tckt_hist_tpl_{key}"):
            try:
                import tckt_reference
                ref = tckt_reference.fetch_reference(key)
                tckt_reference.apply_reference_to_session(ref, st.session_state)
                st.session_state["stk_step"] = 2
                st.success(f"Loaded {key} into Service Ticket draft — go to Step 2 to review.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load template: {exc}")

    if st.session_state.get("tckt_hist_detail_key") == key:
        _render_detail(ticket)


def _render_detail(ticket: dict[str, Any]) -> None:
    fields = ticket.get("fields", {}) or {}
    with st.expander("Ticket detail", expanded=True):
        st.markdown(f"**Key:** {esc(ticket.get('key', ''))}")
        st.markdown(f"**Summary:** {esc(fields.get('summary', ''))}")
        st.markdown(f"**Status:** {esc((fields.get('status', {}) or {}).get('name', ''))}")
        st.markdown(f"**Created:** {esc(fields.get('created', ''))}")
        st.markdown(f"**Updated:** {esc(fields.get('updated', ''))}")
        approvers = _format_approvers(fields)
        if approvers:
            st.markdown("**Approvers:**")
            st.markdown("- " + "\n- ".join(esc(a) for a in approvers))
        if st.button("Close detail", key=f"tckt_hist_close_{ticket.get('key')}"):
            st.session_state.pop("tckt_hist_detail_key", None)
            st.rerun()
