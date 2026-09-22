"""Ticket preview tab — render the TCKT draft exactly as it will appear in Jira.

Used by ``ui.service_ticket`` as a dedicated preview step before the user
hits "Create Ticket". Also exposes "Copy as JSON" / "Copy as Markdown"
helpers and a side-by-side diff against a previous TCKT.
"""

from __future__ import annotations

import html as _html
import json
import logging
from typing import Any

import streamlit as st

import config
import jira_client
from diff_engine import FieldDiff, diff_tickets, extract_ticket_fields
from release_platform.ui.helpers import esc

logger = logging.getLogger(__name__)


# ── ADF → HTML renderer ──────────────────────────────────────────


def _render_text_node(node: dict[str, Any]) -> str:
    text = _html.escape(node.get("text", ""), quote=True)
    for mark in node.get("marks", []) or []:
        m_type = mark.get("type")
        if m_type == "strong":
            text = f"<strong>{text}</strong>"
        elif m_type == "em":
            text = f"<em>{text}</em>"
        elif m_type == "code":
            text = f"<code>{text}</code>"
        elif m_type == "link":
            href = _html.escape(mark.get("attrs", {}).get("href", ""), quote=True)
            text = f'<a href="{href}" target="_blank">{text}</a>'
    return text


def _render_inline(nodes: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for node in nodes or []:
        t = node.get("type")
        if t == "text":
            out.append(_render_text_node(node))
        elif t == "hardBreak":
            out.append("<br/>")
        elif t == "mention":
            out.append(f"@{_html.escape(node.get('attrs', {}).get('text', ''))}")
    return "".join(out)


def adf_to_html(adf: Any) -> str:
    """Render an ADF doc (or any fragment) to safe HTML."""
    if adf is None:
        return ""
    if isinstance(adf, str):
        return _html.escape(adf, quote=True).replace("\n", "<br/>")
    if not isinstance(adf, dict):
        return _html.escape(str(adf), quote=True)

    t = adf.get("type")
    content = adf.get("content") or []

    if t == "doc":
        return "".join(adf_to_html(c) for c in content)
    if t == "paragraph":
        inner = _render_inline(content)
        return f"<p>{inner or '&nbsp;'}</p>"
    if t == "bulletList":
        items = "".join(adf_to_html(c) for c in content)
        return f"<ul>{items}</ul>"
    if t == "orderedList":
        items = "".join(adf_to_html(c) for c in content)
        return f"<ol>{items}</ol>"
    if t == "listItem":
        return f"<li>{''.join(adf_to_html(c) for c in content)}</li>"
    if t == "heading":
        level = adf.get("attrs", {}).get("level", 2)
        level = max(1, min(6, int(level)))
        return f"<h{level}>{_render_inline(content)}</h{level}>"
    if t == "codeBlock":
        return f"<pre><code>{_html.escape(_render_inline(content))}</code></pre>"
    if t == "rule":
        return "<hr/>"
    if t == "text":
        return _render_text_node(adf)
    if t == "hardBreak":
        return "<br/>"

    if content:
        return "".join(adf_to_html(c) for c in content)
    return _html.escape(str(adf.get("text", "")), quote=True)


# ── Markdown export ──────────────────────────────────────────────


def _adf_to_markdown_inline(nodes: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for node in nodes or []:
        t = node.get("type")
        if t == "text":
            text = node.get("text", "")
            for mark in node.get("marks", []) or []:
                if mark.get("type") == "strong":
                    text = f"**{text}**"
                elif mark.get("type") == "em":
                    text = f"*{text}*"
                elif mark.get("type") == "code":
                    text = f"`{text}`"
                elif mark.get("type") == "link":
                    href = mark.get("attrs", {}).get("href", "")
                    text = f"[{text}]({href})"
            out.append(text)
        elif t == "hardBreak":
            out.append("  \n")
    return "".join(out)


def adf_to_markdown(adf: Any) -> str:
    """Render an ADF doc (or fragment) to GitHub-flavoured markdown."""
    if adf is None:
        return ""
    if isinstance(adf, str):
        return adf
    if not isinstance(adf, dict):
        return str(adf)

    t = adf.get("type")
    content = adf.get("content") or []

    if t == "doc":
        parts = [adf_to_markdown(c) for c in content]
        return "\n\n".join(p for p in parts if p).strip()
    if t == "paragraph":
        return _adf_to_markdown_inline(content)
    if t == "bulletList":
        lines = []
        for item in content:
            inner = adf_to_markdown(item).strip() or " "
            lines.append(f"- {inner}")
        return "\n".join(lines)
    if t == "orderedList":
        lines = []
        for idx, item in enumerate(content, 1):
            inner = adf_to_markdown(item).strip() or " "
            lines.append(f"{idx}. {inner}")
        return "\n".join(lines)
    if t == "listItem":
        return "\n".join(adf_to_markdown(c) for c in content).strip()
    if t == "heading":
        level = adf.get("attrs", {}).get("level", 2)
        return "#" * int(level) + " " + _adf_to_markdown_inline(content)
    if t == "codeBlock":
        return "```\n" + _adf_to_markdown_inline(content) + "\n```"
    if t == "rule":
        return "---"
    if t == "text":
        return _adf_to_markdown_inline([adf])
    if t == "hardBreak":
        return "  \n"
    return ""


def _plain_to_markdown(value: Any) -> str:
    if isinstance(value, dict):
        return adf_to_markdown(value)
    return str(value or "").strip()


# ── Assembly ─────────────────────────────────────────────────────


def build_ticket_payload(ss: dict | Any) -> dict[str, Any]:
    """Collect the current ticket draft from Streamlit session state."""

    def g(key: str, default: Any = "") -> Any:
        try:
            return ss.get(key, default)
        except Exception:
            return default

    return {
        "summary": g("stk_summary", ""),
        "description_adf": g("stk_description_adf"),
        "implementation_plan": g("stk_impl_plan", ""),
        "test_plan": g("stk_test_plan", ""),
        "backout_plan": g("stk_backout_plan", ""),
        "business_impact": g("stk_business_impact", ""),
        "sharepoint_url": g("stk_sharepoint", ""),
        "priority": config.TCKT_DEFAULTS.get("priority"),
        "change_type": g("stk_change_type", "Normal"),
        "change_risk": g("stk_change_risk", "Medium"),
        "impact": g("stk_impact", "Moderate / Limited"),
        "urgency": g("stk_urgency", "Medium"),
        "planned_start_date": g("stk_planned_start_date"),
        "planned_start_time": g("stk_planned_start_time"),
        "planned_end_date": g("stk_planned_end_date"),
        "planned_end_time": g("stk_planned_end_time"),
        "approvers": ss.get("stk_approvers") or config.TCKT_DEFAULTS.get("approvers", []),
        "approver_groups": ss.get("stk_approver_groups") or config.TCKT_DEFAULTS.get("approver_groups", []),
        "team": config.TCKT_DEFAULTS.get("team", ""),
        "affected_services": config.TCKT_DEFAULTS.get("affected_services", []),
        "extracted": g("stk_extracted", []),
    }


def _render_value(value: Any) -> str:
    if isinstance(value, dict):
        return adf_to_html(value)
    if isinstance(value, list):
        return "<ul>" + "".join(f"<li>{esc(str(v))}</li>" for v in value) + "</ul>"
    return esc(str(value or ""))


def render_preview(ticket_data: dict[str, Any]) -> None:
    """Render the ticket preview UI in-place.

    Pure Streamlit side effects; returns ``None``. Also stashes the current
    payload in ``st.session_state["stk_preview_payload"]`` for other modules.
    """
    st.markdown("## Ticket Preview")
    st.caption(
        "This is exactly how the TCKT ticket will appear in Jira once created. "
        "Review every section before clicking Create."
    )

    st.session_state["stk_preview_payload"] = ticket_data

    # ── Summary card ─────────────────────────────────────────────
    st.markdown("### Summary")
    st.markdown(
        f'<div class="review-card"><strong>{esc(ticket_data.get("summary", ""))}</strong></div>',
        unsafe_allow_html=True,
    )

    # ── Schedule & classification side-by-side ───────────────────
    col_sched, col_class = st.columns(2)
    with col_sched:
        st.markdown("### Schedule")
        sd = ticket_data.get("planned_start_date")
        st_ = ticket_data.get("planned_start_time")
        ed = ticket_data.get("planned_end_date")
        et_ = ticket_data.get("planned_end_time")
        st.markdown(f"**Start:** {sd} {st_}")
        st.markdown(f"**End:** {ed} {et_}")
    with col_class:
        st.markdown("### Classification")
        st.markdown(f"**Change Type:** {esc(ticket_data.get('change_type', ''))}")
        st.markdown(f"**Risk:** {esc(ticket_data.get('change_risk', ''))}")
        st.markdown(f"**Impact:** {esc(ticket_data.get('impact', ''))}")
        st.markdown(f"**Urgency:** {esc(ticket_data.get('urgency', ''))}")

    # ── Description ──────────────────────────────────────────────
    st.markdown("### Description")
    html_desc = adf_to_html(ticket_data.get("description_adf") or {})
    st.markdown(
        f'<div class="review-card">{html_desc or "<em>No description</em>"}</div>',
        unsafe_allow_html=True,
    )

    # ── Plans (four collapsible expanders) ───────────────────────
    st.markdown("### Plans")
    for label, key in [
        ("Implementation Plan", "implementation_plan"),
        ("Test Plan", "test_plan"),
        ("Backout Plan", "backout_plan"),
        ("Business Impact", "business_impact"),
    ]:
        with st.expander(label, expanded=False):
            value = ticket_data.get(key, "")
            if isinstance(value, dict):
                st.markdown(adf_to_html(value), unsafe_allow_html=True)
            else:
                st.text(value or "")

    # ── Approvers / Groups / Team ────────────────────────────────
    st.markdown("### Approvers")
    approvers = ticket_data.get("approvers") or []
    groups = ticket_data.get("approver_groups") or []
    if approvers:
        st.markdown(
            "<ul>"
            + "".join(
                f"<li>{esc(a.get('name') or a.get('accountId') or str(a))}</li>"
                for a in approvers
            )
            + "</ul>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("No approvers set.")
    if groups:
        st.markdown("**Approver Groups**")
        st.markdown(
            "<ul>"
            + "".join(
                f"<li>{esc(g.get('name') if isinstance(g, dict) else str(g))}</li>"
                for g in groups
            )
            + "</ul>",
            unsafe_allow_html=True,
        )
    team_id = ticket_data.get("team") or ""
    if team_id:
        st.caption(f"Team: {team_id}")

    # ── Copy as JSON / Markdown ──────────────────────────────────
    st.markdown("### Export")
    c1, c2 = st.columns(2)
    json_payload = json.dumps(_json_safe(ticket_data), indent=2, default=str)
    md_payload = to_markdown(ticket_data)
    with c1:
        with st.expander("Copy as JSON", expanded=False):
            st.code(json_payload, language="json")
            st.download_button(
                "Download JSON",
                json_payload.encode("utf-8"),
                file_name="tckt_preview.json",
                mime="application/json",
                key="preview_json_dl",
            )
    with c2:
        with st.expander("Copy as Markdown", expanded=False):
            st.code(md_payload, language="markdown")
            st.download_button(
                "Download Markdown",
                md_payload.encode("utf-8"),
                file_name="tckt_preview.md",
                mime="text/markdown",
                key="preview_md_dl",
            )

    # ── Compare to previous TCKT ─────────────────────────────────
    st.markdown("### Compare to Previous TCKT")
    st.caption(
        "Paste an existing TCKT key to diff against this draft. "
        "Useful for catching accidentally-missing approvers or dashboards."
    )
    prev_key = st.text_input(
        "Previous ticket key",
        value=st.session_state.get("stk_preview_prev_key", ""),
        placeholder="TCKT-102259",
        key="stk_preview_prev_key_input",
        help="Jira will be queried for this ticket and compared field-by-field.",
    )
    if prev_key:
        st.session_state["stk_preview_prev_key"] = prev_key
        _render_diff_against(prev_key, ticket_data)


def _json_safe(data: Any) -> Any:
    """Convert dates/times to strings so json.dumps succeeds."""
    if isinstance(data, dict):
        return {k: _json_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_json_safe(v) for v in data]
    try:
        json.dumps(data)
        return data
    except TypeError:
        return str(data)


def to_markdown(ticket_data: dict[str, Any]) -> str:
    """Flatten the ticket draft to a markdown document for email / Slack."""
    parts: list[str] = []
    parts.append(f"# {ticket_data.get('summary', '')}")
    parts.append("")
    parts.append(
        f"**Schedule:** {ticket_data.get('planned_start_date')} "
        f"{ticket_data.get('planned_start_time')} → "
        f"{ticket_data.get('planned_end_date')} "
        f"{ticket_data.get('planned_end_time')}"
    )
    parts.append(
        f"**Change:** {ticket_data.get('change_type')} · "
        f"Risk {ticket_data.get('change_risk')} · "
        f"Impact {ticket_data.get('impact')} · "
        f"Urgency {ticket_data.get('urgency')}"
    )
    parts.append("")
    parts.append("## Description")
    parts.append(_plain_to_markdown(ticket_data.get("description_adf") or ""))
    for label, key in [
        ("Implementation Plan", "implementation_plan"),
        ("Test Plan", "test_plan"),
        ("Backout Plan", "backout_plan"),
        ("Business Impact", "business_impact"),
    ]:
        parts.append("")
        parts.append(f"## {label}")
        parts.append(_plain_to_markdown(ticket_data.get(key, "")))
    approvers = ticket_data.get("approvers") or []
    if approvers:
        parts.append("")
        parts.append("## Approvers")
        for a in approvers:
            parts.append(f"- {a.get('name') or a.get('accountId') or str(a)}")
    groups = ticket_data.get("approver_groups") or []
    if groups:
        parts.append("")
        parts.append("## Approver Groups")
        for g in groups:
            name = g.get("name") if isinstance(g, dict) else str(g)
            parts.append(f"- {name}")
    return "\n".join(parts).strip() + "\n"


# ── Diff rendering ───────────────────────────────────────────────


def _render_diff_against(prev_key: str, current: dict[str, Any]) -> None:
    try:
        with st.spinner(f"Fetching {prev_key}..."):
            issue = jira_client.get_issue(prev_key)
    except Exception as exc:
        st.error(f"Could not fetch {prev_key}: {exc}")
        return

    previous = extract_ticket_fields(issue)
    current_for_diff = _build_diff_view(current)
    diff = diff_tickets(current_for_diff, previous)

    if not diff.has_changes():
        st.success("No differences between this draft and the previous ticket.")
        return

    for fd in diff.changes():
        _render_field_diff(fd)


def _build_diff_view(data: dict[str, Any]) -> dict[str, Any]:
    """Map the preview-payload schema to the diff_engine logical schema."""
    return {
        "summary": data.get("summary", ""),
        "priority": data.get("priority"),
        "change_type": data.get("change_type"),
        "change_risk": data.get("change_risk"),
        "impact": data.get("impact"),
        "urgency": data.get("urgency"),
        "description": data.get("description_adf"),
        "implementation_plan": data.get("implementation_plan"),
        "test_plan": data.get("test_plan"),
        "backout_plan": data.get("backout_plan"),
        "business_impact": data.get("business_impact"),
        "approvers": data.get("approvers"),
        "approver_groups": data.get("approver_groups"),
        "team": data.get("team"),
        "affected_services": data.get("affected_services"),
    }


def _render_field_diff(fd: FieldDiff) -> None:
    label = fd.field.replace("_", " ").title()
    palette = {
        "added": ("review-card--added", "jt-diff-added", "Added"),
        "removed": ("review-card--removed", "jt-diff-removed", "Removed"),
        "changed": ("review-card--changed", "jt-diff-changed", "Changed"),
        "same": ("review-card--same", "jt-diff-same", "Same"),
    }
    card_cls, text_cls, tag = palette.get(fd.status, ("review-card--same", "jt-diff-same", fd.status))
    st.markdown(
        f'<div class="review-card {card_cls}">'
        f'<strong>{esc(label)}</strong> '
        f'<span class="{text_cls}" style="font-size:.75rem;text-transform:uppercase;font-weight:700">'
        f'{tag}</span></div>',
        unsafe_allow_html=True,
    )
    if fd.added or fd.removed:
        if fd.added:
            st.markdown(
                f"<span class='jt-diff-added'>+ {esc(', '.join(str(a) for a in fd.added))}</span>",
                unsafe_allow_html=True,
            )
        if fd.removed:
            st.markdown(
                f"<span class='jt-diff-removed'>- {esc(', '.join(str(r) for r in fd.removed))}</span>",
                unsafe_allow_html=True,
            )
    else:
        prev = fd.previous if isinstance(fd.previous, str) else _render_value(fd.previous)
        curr = fd.current if isinstance(fd.current, str) else _render_value(fd.current)
        cols = st.columns(2)
        with cols[0]:
            st.caption("Previous")
            st.markdown(prev or "<em>(empty)</em>", unsafe_allow_html=True)
        with cols[1]:
            st.caption("Current")
            st.markdown(curr or "<em>(empty)</em>", unsafe_allow_html=True)
