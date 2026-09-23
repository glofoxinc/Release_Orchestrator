"""JQL Search Panel — ad-hoc ticket search from Platform UI."""

from __future__ import annotations

import streamlit as st

import config
import jira_client
from release_platform.ui.helpers import esc


def _go_back() -> None:
    st.session_state.pop("active_app", None)
    st.rerun()


def render() -> None:
    """Render the JQL search panel."""
    st.markdown("## JQL Search")
    st.caption(
        "Execute ad-hoc JQL queries against Jira. "
        "Use this to find tickets, explore releases, or investigate issues."
    )

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("← Back", key="jql_back"):
            _go_back()

    default_jql = st.session_state.get("jql_query", "")
    example_queries = [
        "project = PIC AND fixVersion = 'v2026.08.01'",
        "project = AN AND status = 'In Progress'",
        "reporter = currentUser() AND created >= -30d",
        f"project = {config.TCKT_PROJECT_KEY} AND status = Open" if config.TCKT_PROJECT_KEY else "",
    ]
    example_queries = [q for q in example_queries if q]

    with st.expander("Example queries", expanded=False):
        for q in example_queries:
            if st.button(q, key=f"jql_example_{hash(q)}", use_container_width=True):
                st.session_state["jql_query"] = q
                st.rerun()

    jql = st.text_area(
        "JQL Query",
        value=default_jql,
        height=100,
        key="_jql_query_input",
        placeholder="project = PIC AND fixVersion = 'v2026.08.01'",
    )
    st.session_state["jql_query"] = jql

    c1, c2, c3 = st.columns([1, 1, 4])
    with c1:
        max_results = st.number_input(
            "Max results",
            min_value=1,
            max_value=500,
            value=st.session_state.get("jql_max_results", 50),
            key="_jql_max_results",
        )
        st.session_state["jql_max_results"] = max_results
    with c2:
        if st.button("Search", type="primary", key="jql_search"):
            if jql.strip():
                _execute_search(jql, int(max_results))
            else:
                st.warning("Please enter a JQL query.")

    _render_results()


def _execute_search(jql: str, max_results: int) -> None:
    """Execute JQL search and store results in session state."""
    try:
        with st.spinner("Searching Jira…"):
            issues = jira_client.search_jql(jql, max_results=max_results)
        st.session_state["jql_results"] = issues
        st.session_state["jql_error"] = None
    except Exception as exc:
        st.session_state["jql_results"] = []
        st.session_state["jql_error"] = str(exc)
    st.rerun()


def _render_results() -> None:
    """Render search results."""
    error = st.session_state.get("jql_error")
    if error:
        st.error(f"Search failed: {esc(error)}")
        return

    results = st.session_state.get("jql_results", [])
    if not results:
        return

    st.markdown(f"### Results ({len(results)} tickets)")

    browse = f"{config.JIRA_BASE_URL}/browse"

    for issue in results:
        key = issue.get("key", "")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        status = fields.get("status", {})
        status_name = status.get("name", "")
        status_cat = status.get("statusCategory", {}).get("key", "new")
        assignee = fields.get("assignee") or {}
        assignee_name = assignee.get("displayName", "Unassigned")
        priority = fields.get("priority", {})
        priority_name = priority.get("name", "") if priority else ""

        status_color = {
            "done": "#28a745",
            "indeterminate": "#ffc107",
            "new": "#6c757d",
        }.get(status_cat, "#6c757d")

        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid #eee">'
            f'<a href="{browse}/{key}" target="_blank" style="font-weight:600;text-decoration:none">{esc(key)}</a>'
            f'<span style="flex:1">{esc(summary)}</span>'
            f'<span style="background:{status_color};color:white;padding:2px 8px;border-radius:4px;font-size:.8rem">'
            f'{esc(status_name)}</span>'
            f'<span style="font-size:.85rem;color:#666">{esc(assignee_name)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if results:
        import csv
        import io

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["Key", "Summary", "Status", "Assignee", "Priority", "Link"])
        for issue in results:
            fields = issue.get("fields", {})
            assignee = fields.get("assignee") or {}
            priority = fields.get("priority") or {}
            writer.writerow([
                issue.get("key", ""),
                fields.get("summary", ""),
                fields.get("status", {}).get("name", ""),
                assignee.get("displayName", "Unassigned"),
                priority.get("name", "") if priority else "",
                f"{browse}/{issue.get('key', '')}",
            ])
        st.download_button(
            "Export to CSV",
            data=csv_buf.getvalue().encode("utf-8"),
            file_name="jql_search_results.csv",
            mime="text/csv",
            key="jql_export_csv",
        )
