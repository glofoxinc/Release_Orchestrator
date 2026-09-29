"""Format ticket digest for meeting body and console output."""

from __future__ import annotations

from html import escape
from typing import Any


def format_text_report(
    rows: list[dict[str, str]],
    *,
    team_name: str,
    by_project: dict[str, Any],
) -> str:
    lines = [
        f"Daily ticket review — {team_name}",
        f"Total tickets: {len(rows)}",
        "",
    ]
    for pk, info in sorted(by_project.items()):
        if not isinstance(info, dict):
            continue
        statuses = info.get("statuses") or []
        count = info.get("count", 0)
        lines.append(f"{pk} ({count}) — statuses: {', '.join(statuses)}")
    lines.append("")
    for row in rows:
        lines.append(
            f"{row['key']} | {row['status']} | {row['assignee']} | {row['summary']}"
        )
    return "\n".join(lines)


def format_html_report(rows: list[dict[str, str]], *, team_name: str, meeting_date: str) -> str:
    parts = [
        f"<p><strong>Daily ticket review</strong> — {escape(team_name)}<br/>"
        f"Meeting date: {escape(meeting_date)}<br/>"
        f"Tickets: {len(rows)}</p>",
        "<table border='1' cellpadding='4' cellspacing='0'>",
        "<tr><th>Key</th><th>Status</th><th>Assignee</th><th>Summary</th></tr>",
    ]
    for row in rows:
        key_cell = escape(row["key"])
        if row.get("link"):
            key_cell = f"<a href='{escape(row['link'])}'>{key_cell}</a>"
        parts.append(
            "<tr>"
            f"<td>{key_cell}</td>"
            f"<td>{escape(row['status'])}</td>"
            f"<td>{escape(row['assignee'])}</td>"
            f"<td>{escape(row['summary'])}</td>"
            "</tr>"
        )
    parts.append("</table>")
    return "".join(parts)
