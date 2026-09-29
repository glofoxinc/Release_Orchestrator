"""Confluence release-notes companion page generation and publishing.

Generates a *storage-format* XHTML body from a finished SHIPIT service ticket and
optionally publishes it to a Confluence space. Intended to be called from
the Streamlit preview step *after* the ticket has been created.

Configuration (env vars)
------------------------
``CONFLUENCE_URL``
    Atlassian base URL, e.g. ``https://yourorg.atlassian.net``. Falls back
    to ``JIRA_BASE_URL`` if unset.
``CONFLUENCE_TOKEN``
    API token. Falls back to ``JIRA_API_TOKEN``.
``CONFLUENCE_SPACE``
    Default space key to publish into (optional).
``CONFLUENCE_PARENT_ID``
    Default parent page ID (optional).
"""

from __future__ import annotations

import html
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import jira_client
from consolidation import consolidate_dashboards
from diff_engine import _adf_to_text
from generators.release_notes_insights import build_release_summary_paragraph
from generators.release_notes_report_tables import build_delivered_reports_rows
from generators.release_notes_summary_tables import build_highlight_summary_tables

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    ok: bool
    page_id: str = ""
    url: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "page_id": self.page_id,
            "url": self.url,
            "error": self.error,
        }


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _section(title: str, body_xml: str) -> str:
    """Wrap content in a Confluence expand macro (collapsible)."""
    return (
        '<ac:structured-macro ac:name="expand">'
        f'<ac:parameter ac:name="title">{_esc(title)}</ac:parameter>'
        f"<ac:rich-text-body>{body_xml}</ac:rich-text-body>"
        "</ac:structured-macro>"
    )


def _as_paragraphs(text: str) -> str:
    """Convert plain text with blank-line paragraph breaks to XHTML."""
    text = (text or "").strip()
    if not text:
        return ""
    out: list[str] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = [_esc(ln) for ln in block.splitlines()]
        out.append("<p>" + "<br/>".join(lines) + "</p>")
    return "\n".join(out)


def generate_page_body(ticket: dict[str, Any]) -> str:
    """Build the Confluence storage-format XHTML body for a ticket.

    ``ticket`` uses the canonical schema: ``ticket_key``, ``summary``,
    ``sharepoint_url``, ``extracted``, ``affected_clients``, and any of the
    plan strings (``implementation_plan``, ``test_plan``, ``backout_plan``,
    ``business_impact`` — accepts plain strings or ADF dicts).
    """
    ticket_key = ticket.get("ticket_key") or ticket.get("key") or ""
    summary = ticket.get("summary", "")
    sharepoint_url = ticket.get("sharepoint_url") or ticket.get("sharepoint") or ""
    extracted = ticket.get("extracted") or []
    jira_base = getattr(__import__("config"), "JIRA_BASE_URL", "")

    parts: list[str] = []

    # Header
    parts.append("<h1>" + _esc(f"{ticket_key}: {summary}" if ticket_key else summary) + "</h1>")

    if ticket_key:
        url = f"{jira_base.rstrip('/')}/browse/{ticket_key}"
        parts.append(f'<p><strong>Jira:</strong> <a href="{_esc(url)}">{_esc(ticket_key)}</a></p>')

    if sharepoint_url:
        parts.append(
            f'<p><strong>SharePoint Release Notes:</strong> '
            f'<a href="{_esc(sharepoint_url)}">{_esc(sharepoint_url)}</a></p>'
        )

    if extracted:
        parts.append("<h2>Release Summary</h2>")
        parts.append(f"<p>{_esc(build_release_summary_paragraph(extracted))}</p>")

        highlight_blocks = build_highlight_summary_tables(extracted)
        if highlight_blocks:
            parts.append("<h2>Key Highlights</h2>")
            for block in highlight_blocks:
                parts.append(f"<h3>{_esc(block.title)}</h3>")
                parts.append(
                    "<ul>"
                    + "".join(
                        f"<li>{_esc(' | '.join(row))}</li>" for row in block.rows
                    )
                    + "</ul>"
                )

        delivered_rows = build_delivered_reports_rows(extracted)
        if delivered_rows:
            parts.append("<h2>Reports / Dashboards Delivered</h2>")
            parts.append(
                "<table><tbody>"
                "<tr><th>Client</th><th>Dashboard / Report</th><th>Change</th></tr>"
                + "".join(
                    f"<tr><td>{_esc(r[0])}</td><td>{_esc(r[1])}</td><td>{_esc(r[2])}</td></tr>"
                    for r in delivered_rows
                )
                + "</tbody></table>"
            )

    # Legacy fallback when extracted is empty but affected_clients provided
    affected = ticket.get("affected_clients") or sorted({
        e.get("client") for e in extracted
        if e.get("client") and e.get("client") not in ("Standard", "Unknown")
    })
    if affected and not extracted:
        parts.append("<h2>Affected Clients</h2>")
        parts.append(
            "<ul>" + "".join(f"<li>{_esc(str(c))}</li>" for c in affected) + "</ul>"
        )

    # Legacy dashboards list when no delivered rows builder input
    if extracted and not build_delivered_reports_rows(extracted):
        consolidated = consolidate_dashboards(extracted)
        parts.append("<h2>Dashboards / Reports</h2>")
        items = []
        for entry in consolidated:
            label = _esc(entry.get("label", ""))
            summary_text = _esc(entry.get("summary", ""))
            refs = _esc(entry.get("refs", ""))
            body = f"<strong>{label}</strong>"
            if summary_text:
                body += f" — {summary_text}"
            if refs:
                body += f" <em>({refs})</em>"
            items.append(f"<li>{body}</li>")
        parts.append("<ul>" + "".join(items) + "</ul>")

    # Collapsible plan sections
    for label, key in [
        ("Implementation Plan", "implementation_plan"),
        ("Test Plan", "test_plan"),
        ("Backout Plan", "backout_plan"),
        ("Business Impact", "business_impact"),
    ]:
        value = ticket.get(key) or ticket.get(f"{key}_adf")
        if not value:
            continue
        body_text = value if isinstance(value, str) else _adf_to_text(value)
        xhtml = _as_paragraphs(body_text)
        if xhtml:
            parts.append(_section(label, xhtml))

    # Tickets table
    if extracted:
        parts.append("<h2>Source Tickets</h2>")
        rows = []
        for e in extracted:
            key = _esc(e.get("ticket", ""))
            desc = _esc(e.get("description", ""))
            client = _esc(e.get("client", ""))
            rows.append(
                f"<tr><td>{key}</td><td>{client}</td><td>{desc}</td></tr>"
            )
        parts.append(
            "<table><tbody>"
            "<tr><th>Key</th><th>Client</th><th>Description</th></tr>"
            + "".join(rows)
            + "</tbody></table>"
        )

    parts.append(
        f"<p><em>Generated by jira-release-tool at {_esc(time.strftime('%Y-%m-%d %H:%M:%S'))}.</em></p>"
    )
    return "\n".join(parts)


def publish_page(
    space: str,
    parent: str | None,
    body: str,
    *,
    title: str,
    publisher: Callable[[str, str, str, str | None], dict] | None = None,
    upsert: bool = True,
) -> PublishResult:
    """Publish ``body`` to Confluence under ``space`` / ``parent``.

    When ``upsert`` is True (default), updates an existing page with the same title.

    ``publisher`` is injected for testing; defaults to upsert/create via jira_client.
    """
    if not space:
        return PublishResult(ok=False, error="No Confluence space key provided.")

    try:
        if publisher:
            page = publisher(space, title, body, parent)
        elif upsert:
            page = _upsert_publisher(space, title, body, parent)
        else:
            page = _default_publisher(space, title, body, parent)
    except Exception as exc:
        logger.debug("Confluence publish failed", exc_info=True)
        return PublishResult(ok=False, error=str(exc))

    page_id = str(page.get("id", ""))
    base = os.environ.get("CONFLUENCE_URL") or getattr(__import__("config"), "JIRA_BASE_URL", "")
    web_ui = page.get("_links", {}).get("webui", "") if isinstance(page, dict) else ""
    url = ""
    if web_ui:
        url = f"{base.rstrip('/')}/wiki{web_ui}" if base else web_ui
    return PublishResult(ok=True, page_id=page_id, url=url)


def _default_publisher(space: str, title: str, body: str, parent: str | None) -> dict:
    return jira_client.confluence_create_page(space, title, body, parent_id=parent)


def _upsert_publisher(space: str, title: str, body: str, parent: str | None) -> dict:
    existing = jira_client.confluence_find_page_by_title(space, title)
    if existing:
        version = (existing.get("version") or {}).get("number", 1)
        return jira_client.confluence_update_page(
            str(existing["id"]),
            title=title,
            body_storage=body,
            version_number=int(version) + 1,
        )
    return jira_client.confluence_create_page(space, title, body, parent_id=parent)


def default_title(ticket: dict[str, Any]) -> str:
    """Reasonable default page title: '<ticket_key> Release Notes'."""
    key = ticket.get("ticket_key") or ticket.get("key") or ""
    summary = ticket.get("summary", "")
    if key:
        return f"{key} — Release Notes"
    if summary:
        return f"{summary} — Release Notes"
    return "Release Notes"
