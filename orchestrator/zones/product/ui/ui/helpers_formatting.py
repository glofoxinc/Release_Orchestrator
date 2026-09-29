"""Streamlit ticket table rendering and display helpers."""

from __future__ import annotations

import config
import streamlit as st

from ui.helpers import esc




def render_ticket_table(issues: list[dict], grouped_by_owner: bool = True) -> None:
    browse = f"{config.JIRA_BASE_URL}/browse"

    rows_by_owner: dict[str, list[dict]] = {}
    for iss in issues:
        fields = iss.get("fields", {})
        assignee = fields.get("assignee") or {}
        owner = assignee.get("displayName", "Unassigned")
        rows_by_owner.setdefault(owner, []).append(iss)

    header = (
        '<table class="jt-table"><thead><tr>'
        '<th>Owner</th><th>Ticket</th><th>Summary</th><th>Status</th><th>Link</th>'
        "</tr></thead><tbody>"
    )

    sorted_owners = sorted(rows_by_owner.keys())
    rows_html = ""
    for oidx, owner in enumerate(sorted_owners):
        owner_issues = rows_by_owner[owner]
        for i, iss in enumerate(owner_issues):
            fields = iss.get("fields", {})
            key = iss["key"]
            summary = esc(fields.get("summary", ""))
            status = esc(fields.get("status", {}).get("name", ""))
            link = f"{browse}/{key}"
            owner_cell = esc(owner) if i == 0 else ""
            row_class = "jt-table__group-start" if i == 0 and oidx > 0 else ""
            rows_html += (
                f'<tr class="{row_class}">'
                f'<td style="font-weight:600;vertical-align:top;white-space:nowrap">{owner_cell}</td>'
                f'<td style="white-space:nowrap"><code>{esc(key)}</code></td>'
                f'<td>{summary}</td>'
                f'<td style="white-space:nowrap">{status}</td>'
                f'<td><a href="{link}" target="_blank" class="jt-link">{esc(key)}</a></td>'
                f"</tr>"
            )

    st.markdown(header + rows_html + "</tbody></table>", unsafe_allow_html=True)


def user_initials() -> str:
    email = config.JIRA_EMAIL or ""
    name_part = email.split("@")[0] if "@" in email else email
    parts = name_part.replace(".", " ").replace("_", " ").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name_part[:2].upper() if name_part else "?"
