"""History list (step -1) and history detail (step -2)."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

import streamlit as st

import config
from release_platform.ui.helpers import esc, load_history

logger = logging.getLogger(__name__)


def render_list(*, embedded: bool = False) -> None:
    all_history = load_history()

    if not embedded:
        if st.button("\u2190 Back to Deployer"):
            st.session_state["wiz_step"] = 1
            st.rerun()

    st.markdown("## Deployment History")
    st.caption("Browse, search, and filter past deployments. Use the export button to download as CSV.")

    # ── Search / Filter ──────────────────────────────────────────
    proj_keys = ["All"] + [p["key"] for p in config.PROJECTS]
    filter_cols = st.columns([3, 1, 1] + [1] * (len(proj_keys) - 2))

    with filter_cols[0]:
        search_text = st.text_input(
            "Search",
            placeholder="Version, client, or ticket key...",
            label_visibility="collapsed",
            key="hist_search",
            help="Filter by version name, client name, or ticket key.",
        )

    for i, pk in enumerate(proj_keys):
        with filter_cols[1 + i]:
            selected_proj = st.session_state.get("hist_proj_filter", "All")
            btn_type = "primary" if selected_proj == pk else "secondary"
            if st.button(pk, key=f"hf_{pk}", type=btn_type, use_container_width=True):
                st.session_state["hist_proj_filter"] = pk
                st.rerun()

    # ── Date range filter ────────────────────────────────────────
    dc1, dc2 = st.columns(2)
    with dc1:
        date_from = st.date_input(
            "From date",
            value=None,
            key="hist_date_from",
            help="Show only deployments on or after this date.",
        )
    with dc2:
        date_to = st.date_input(
            "To date",
            value=None,
            key="hist_date_to",
            help="Show only deployments on or before this date.",
        )

    selected_proj = st.session_state.get("hist_proj_filter", "All")
    query = search_text.strip().lower() if search_text else ""

    filtered: list[tuple[int, dict]] = []
    for idx, h in enumerate(all_history):
        if selected_proj != "All" and h.get("project", "") != selected_proj:
            continue
        if query:
            searchable = " ".join([
                h.get("version", ""),
                h.get("project", ""),
                h.get("tckt_key", ""),
                h.get("sharepoint_url", ""),
                " ".join(h.get("clients", {}).keys()),
                " ".join(
                    tk
                    for c in h.get("clients", {}).values()
                    for tk in c.get("tickets", [])
                ),
            ]).lower()
            if query not in searchable:
                continue
        if date_from or date_to:
            try:
                ts_date = datetime.fromisoformat(h.get("timestamp", "")).date()
            except (ValueError, TypeError):
                # An undated entry cannot satisfy a date filter — exclude it rather
                # than letting it through and showing rows outside the range.
                logger.warning("Skipping history entry with unparseable timestamp: %r", h.get("timestamp"))
                continue
            if date_from and ts_date < date_from:
                continue
            if date_to and ts_date > date_to:
                continue
        filtered.append((idx, h))

    st.caption(f"{len(filtered)} of {len(all_history)} deployment(s)")

    # ── Export CSV ────────────────────────────────────────────────
    if filtered:
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow([
            "Timestamp", "Project", "Version", "Clients", "Tickets",
            "Updated", "Skipped", "Errors", "TCKT", "SharePoint", "Slack OK",
        ])
        for _, h in filtered:
            clients = h.get("clients", {})
            total_tickets = sum(len(c.get("tickets", [])) for c in clients.values())
            slack = h.get("slack_results") or []
            slack_ok = sum(1 for s in slack if isinstance(s, dict) and s.get("ok"))
            writer.writerow([
                h.get("timestamp", ""),
                h.get("project", ""),
                h.get("version", ""),
                ", ".join(clients.keys()),
                total_tickets,
                h.get("success", 0),
                h.get("skipped", 0),
                h.get("errors", 0),
                h.get("tckt_key", ""),
                h.get("sharepoint_url", ""),
                f"{slack_ok}/{len(slack)}" if slack else "",
            ])
        st.download_button(
            "Export CSV",
            data=csv_buf.getvalue().encode("utf-8"),
            file_name="deployment_history.csv",
            mime="text/csv",
            key="hist_export_csv",
        )

    st.markdown("")

    if not filtered:
        st.info("No deployments match your search.")
        if not embedded:
            st.stop()
        return

    for global_idx, h in filtered:
        _render_history_item(h, global_idx)

    if not embedded:
        st.stop()


def _render_history_item(h: dict, global_idx: int) -> None:
    ts_raw = h.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_raw).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        logger.debug("Failed to parse timestamp '%s'", ts_raw, exc_info=True)
        ts = ts_raw[:16]
    proj = esc(h.get("project", "?"))
    ver = esc(h.get("version", "?"))
    ok = h.get("success", 0)
    err = h.get("errors", 0)
    skip_ct = h.get("skipped", 0)
    clients = h.get("clients", {})
    total_tickets = sum(len(c.get("tickets", [])) for c in clients.values())
    client_names = esc(", ".join(clients.keys())) if clients else ""
    status_icon = "\u2705" if err == 0 else "\u26a0\ufe0f"

    st.markdown(
        f'<div class="hist-item">'
        f'<div style="display:flex;justify-content:space-between;align-items:center">'
        f'<div>'
        f'<p class="hi-title">{status_icon} {proj} / {ver}</p>'
        f'<p class="hi-meta">{ts}</p>'
        f'</div>'
        f'<div style="text-align:right">'
        f'<span style="font-size:.85rem;font-weight:600">{total_tickets} tickets</span><br>'
        f'<span style="font-size:.72rem;opacity:.5">{ok} updated \u00b7 {skip_ct} skipped \u00b7 {err} errors</span>'
        f'</div></div>'
        + (f'<p style="font-size:.78rem;opacity:.45;margin:4px 0 0">{client_names}</p>' if client_names else "")
        + '</div>',
        unsafe_allow_html=True,
    )
    if st.button("View details \u2192", key=f"hist_{global_idx}", use_container_width=True):
        st.session_state["view_history_idx"] = global_idx
        st.session_state["wiz_step"] = -2
        st.rerun()


def render_detail() -> None:
    hist_idx = st.session_state.get("view_history_idx", 0)
    all_history = load_history()
    if hist_idx >= len(all_history):
        st.warning("History entry not found.")
        if st.button("\u2190 Back to History"):
            st.session_state["wiz_step"] = -1
            st.rerun()
        st.stop()

    h = all_history[hist_idx]
    ts_raw = h.get("timestamp", "")
    try:
        ts_display = datetime.fromisoformat(ts_raw).strftime("%B %d, %Y at %I:%M %p")
    except Exception:
        logger.debug("Failed to parse timestamp '%s'", ts_raw, exc_info=True)
        ts_display = ts_raw[:19]
    proj = esc(h.get("project", "?"))
    ver = esc(h.get("version", "?"))
    ok = h.get("success", 0)
    err = h.get("errors", 0)
    skip_ct = h.get("skipped", 0)
    clients = h.get("clients", {})
    status_icon = "\u2705" if err == 0 else "\u26a0\ufe0f"
    total_tickets = sum(len(c.get("tickets", [])) for c in clients.values())

    if st.button("\u2190 Back to History"):
        st.session_state["wiz_step"] = -1
        st.session_state.pop("view_history_idx", None)
        st.rerun()

    st.markdown("")

    st.markdown(
        f'<div class="hist-detail-header">'
        f'<h2 style="margin:0 0 4px !important;font-size:1.6rem !important">{status_icon} {proj} / {ver}</h2>'
        f'<p style="opacity:.5;margin:0;font-size:.9rem">{esc(ts_display)}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total Tickets", total_tickets)
    mc2.metric("Updated", ok)
    mc3.metric("Skipped", skip_ct)
    mc4.metric("Errors", err)

    st.markdown("")
    # Optional release-audit fields (backward compatible when absent).
    if h.get("tckt_key") or h.get("sharepoint_url") or h.get("slack_results") or h.get("mark_released"):
        st.markdown("### Release audit")
        if h.get("tckt_key"):
            tckt_url = h.get("tckt_url") or f"{config.JIRA_BASE_URL}/browse/{h['tckt_key']}"
            st.markdown(f"**TCKT:** [{esc(h['tckt_key'])}]({tckt_url})")
        if h.get("sharepoint_url"):
            st.markdown(f"**SharePoint:** {esc(h['sharepoint_url'])}")
        slack_results = h.get("slack_results") or []
        if slack_results:
            for sr in slack_results:
                ch = esc(sr.get("channel_name") or "?")
                if sr.get("ok"):
                    link = sr.get("permalink") or ""
                    st.success(f"#{ch}: sent" + (f" — {link}" if link else ""))
                else:
                    st.error(f"#{ch}: {esc(sr.get('error') or 'failed')}")
        mark = h.get("mark_released")
        if isinstance(mark, dict) and mark.get("status"):
            st.info(
                f"Mark-released: **{esc(mark.get('status'))}** "
                f"({esc(mark.get('version_name') or mark.get('version_id') or '')})"
            )
        if h.get("reverted"):
            st.warning(f"Undone at {esc(h.get('reverted_at') or '?')}")

    st.markdown("### Deployment Details")

    if clients:
        browse = f"{config.JIRA_BASE_URL}/browse"
        for cname, cinfo in clients.items():
            tickets = cinfo.get("tickets", [])
            dep_id = cinfo.get("deployment_id", "")
            dep_time = cinfo.get("deployment_time", "")
            dep_date = cinfo.get("deployment_date", "")
            ticket_links = "  ".join(
                f'<a href="{browse}/{t}" target="_blank" class="jt-link">'
                f'<code>{t}</code></a>'
                for t in tickets
            )
            st.markdown(
                f'<div class="hist-client-card">'
                f'<strong style="font-size:1.05rem">{esc(cname)}</strong>'
                f' <span style="opacity:.5">\u00b7 {len(tickets)} ticket(s)</span>'
                f'<div style="margin:10px 0 12px">{ticket_links}</div>'
                f'<div style="display:flex;gap:24px;font-size:.88rem">'
                f'<div><span style="opacity:.5">Deployment ID</span><br>'
                f'<code style="font-size:.82rem">{dep_id}</code></div>'
                f'<div><span style="opacity:.5">Date</span><br>{dep_date}</div>'
                f'<div><span style="opacity:.5">Time</span><br>{dep_time}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No client details recorded for this deployment.")

    st.stop()
