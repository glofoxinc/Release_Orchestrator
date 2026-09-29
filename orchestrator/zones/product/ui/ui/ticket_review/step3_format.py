"""Step 3 — Formatted review list, CSV export, then Release Notes."""

from __future__ import annotations

import csv
import io
import logging

import streamlit as st

import config
import jira_client
from template_engine import render_template
from release_platform.ui.helpers import esc, get_snapshot, navigate_to_app, render_ticket_table
from release_platform.ui.ticket_review.selection import MODE_STATUS, get_selection_mode, selection_summary
from release_platform.ui.workflow import check_app_prerequisites, render_action_hint

logger = logging.getLogger(__name__)


def _go(step: int) -> None:
    st.session_state["tr_step"] = step
    st.rerun()


def _build_review_text(grouped: dict[str, list[dict]], base_url: str) -> str:
    """Build the formatted review text using template."""
    try:
        return render_template("review_format.j2", grouped=grouped, base_url=base_url)
    except Exception:
        logger.debug("Template rendering failed, using fallback format", exc_info=True)
        sections: list[str] = []
        heading = "Tickets for review\n"
        sections.append(heading)
        for owner, issues in grouped.items():
            block = f"{owner}\n"
            for iss in issues:
                key = iss["key"]
                summary = iss.get("fields", {}).get("summary", "")
                block += f"{key}\n\nLink:\n{base_url}/browse/{key}\n\nSummary: {summary}\n\n"
            sections.append(block)
        return "________________________________________\n\n".join(sections)


def _flatten_grouped(grouped: dict[str, list[dict]]) -> list[dict]:
    return [iss for owner_list in grouped.values() for iss in owner_list]


def _build_ticket_csv(grouped: dict[str, list[dict]], base_url: str) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Owner", "Key", "Summary", "Status", "Link"])
    for owner, issues in grouped.items():
        for iss in issues:
            fields = iss.get("fields", {}) or {}
            writer.writerow([
                owner,
                iss.get("key", ""),
                fields.get("summary", ""),
                (fields.get("status") or {}).get("name", ""),
                f"{base_url}/browse/{iss.get('key', '')}",
            ])
    return buf.getvalue().encode("utf-8-sig")


def _resolve_grouped() -> dict[str, list[dict]] | None:
    grouped = st.session_state.get("tr_grouped")
    if grouped:
        return grouped
    snap = get_snapshot()
    if snap and snap.get("issues"):
        grouped = jira_client.group_issues_by_assignee(snap["issues"])
        st.session_state["tr_grouped"] = grouped
        return grouped
    return None


def _context_label() -> str:
    snap = get_snapshot() or {}
    if snap.get("selection_mode") == MODE_STATUS or get_selection_mode() == MODE_STATUS:
        filters = snap.get("status_filters") or {}
        if filters:
            parts = [
                f"{pk}: {', '.join(statuses)}"
                for pk, statuses in filters.items()
                if statuses
            ]
            if parts:
                return " + ".join(parts)
        return selection_summary(prefix="tr")
    return selection_summary(prefix="tr")


def render() -> None:
    st.markdown("## Formatted Review List")

    grouped = _resolve_grouped()
    if not grouped:
        st.warning(
            "No review list found. Go back to **Review Tickets**, select tickets, "
            "and click **Generate Review List →**."
        )
        if st.button("\u2190 Back to Review Tickets", key="tr_s3_missing_back"):
            _go(2)
        return

    context_label = _context_label()
    total = sum(len(v) for v in grouped.values())
    snap = get_snapshot()
    locked_at = (snap or {}).get("locked_at", "")

    locked_line = f" • locked {esc(locked_at)}" if locked_at else ""
    context_html = (
        f'<br><span style="font-size:.85rem">{esc(context_label)}</span>'
        if context_label
        else ""
    )

    st.markdown(
        f'<div class="success-banner">'
        f"<h3>Review list ready</h3>"
        f"<p>{total} tickets \u2022 {len(grouped)} owners{locked_line}"
        f"{context_html}"
        f"</p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "**Next in the release workflow:** download the list below (optional), then open "
        "**Release Notes** to build the Word document from this same locked ticket list."
    )

    all_issues = _flatten_grouped(grouped)
    with st.expander(f"Ticket Table ({total} selected)", expanded=False):
        render_ticket_table(all_issues)

    review_text = _build_review_text(grouped, config.JIRA_BASE_URL)
    csv_bytes = _build_ticket_csv(grouped, config.JIRA_BASE_URL)

    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button(
            "Download .txt",
            data=review_text,
            file_name="ticket-review-list.txt",
            mime="text/plain",
            key="tr_s3_download_txt",
            use_container_width=True,
        )
    with dl2:
        st.download_button(
            "Download CSV",
            data=csv_bytes,
            file_name="ticket-review-list.csv",
            mime="text/csv",
            key="tr_s3_download_csv",
            use_container_width=True,
        )
    with dl3:
        st.download_button(
            "Download Excel (.csv)",
            data=csv_bytes,
            file_name="ticket-review-list.xlsx.csv",
            mime="text/csv",
            key="tr_s3_download_excel",
            use_container_width=True,
            help="UTF-8 CSV — opens directly in Excel.",
        )

    with st.expander("Preview formatted text", expanded=False):
        st.code(review_text, language=None)

    st.markdown("")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("\u2190 Back", key="tr_s3_back"):
            _go(2)
    with c2:
        if st.button("\U0001f3e0 Home", key="tr_s3_home"):
            st.session_state.pop("active_app", None)
            st.rerun()
    with c3:
        rn_ready = check_app_prerequisites("release_notes").ok
        if st.button(
            "Release Notes \u2192",
            type="primary",
            key="tr_s3_next_app",
            disabled=not rn_ready,
        ):
            navigate_to_app("release_notes")
        if rn_ready:
            render_action_hint(
                "Opens Release Notes with the same locked ticket list to build the Word document."
            )
        else:
            render_action_hint("Lock tickets on Step 2 first (Generate Review List).")
