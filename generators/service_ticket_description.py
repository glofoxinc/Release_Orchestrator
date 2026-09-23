"""Service Ticket ADF description aligned with Release Notes DOCX layout."""

from __future__ import annotations

import adf_builder as adf
from generators.release_notes_insights import build_release_summary_paragraph
from generators.release_notes_report_tables import build_delivered_reports_rows
from generators.release_notes_summary_tables import build_highlight_summary_tables
from generators.release_notes_template_defaults import GLOFOX_ANALYZE_CLIENT


def build_service_ticket_description_adf(
    extracted: list[dict],
    sharepoint_url: str,
    *,
    version_label: str = "",
    window: dict[str, str] | None = None,
    link_label: str | None = None,
) -> dict:
    """ADF body matching the built-in Release Notes structure (2026 format)."""
    content: list[dict] = []

    content.append(adf.paragraph(adf.text("Release Summary ", bold=True)))
    content.append(adf.paragraph(adf.text(build_release_summary_paragraph(extracted))))
    content.append(adf.spacer())

    analyze = any(entry.get("type") == "Analyze" for entry in extracted)
    custom_clients = sorted({
        str(entry.get("client") or "").strip()
        for entry in extracted
        if entry.get("type") == "Custom" and str(entry.get("client") or "").strip()
    }, key=str.lower)
    affected = ([GLOFOX_ANALYZE_CLIENT] if analyze else []) + custom_clients
    if affected:
        content.append(adf.paragraph(adf.text("Affected Clients", bold=True)))
        for client in affected:
            content.append(adf.bullet_item(adf.text(client)))
        content.append(adf.spacer())

    if window and window.get("sentence"):
        content.append(adf.paragraph(adf.text("Deployment Window", bold=True)))
        content.append(adf.paragraph(adf.text(window["sentence"])))
        if window.get("note"):
            content.append(adf.paragraph(adf.text(window["note"])))
        content.append(adf.spacer())

    highlight_blocks = build_highlight_summary_tables(extracted)
    if highlight_blocks:
        content.append(adf.paragraph(adf.text("Key Highlights", bold=True)))
        for block in highlight_blocks:
            content.append(adf.paragraph(adf.text(block.title, bold=True)))
            for row in block.rows:
                content.append(adf.bullet_item(adf.text(" | ".join(row))))
        content.append(adf.spacer())

    delivered_rows = build_delivered_reports_rows(extracted)
    if delivered_rows:
        content.append(adf.paragraph(adf.text("Reports / Dashboards Delivered", bold=True)))
        for client, report, change in delivered_rows:
            content.append(
                adf.bullet_item(adf.text(f"{client} | {report} | {change}"))
            )
        content.append(adf.spacer())

    if extracted:
        content.append(adf.paragraph(adf.text("Ticket Details", bold=True)))
        for entry in extracted:
            key = str(entry.get("ticket") or "").strip()
            report = str(entry.get("report") or entry.get("summary") or "Report").strip()
            status = str(entry.get("status") or "Release approved").strip()
            owner = str(entry.get("assignee") or "").strip()
            details = [key, report, status]
            if owner:
                details.append(f"Owner: {owner}")
            link = str(entry.get("link") or "").strip()
            nodes = [adf.text(" | ".join(details))]
            if key and link.startswith(("https://", "http://")):
                nodes = [adf.link(key, link), adf.text(" | " + " | ".join(details[1:]))]
            content.append(adf.bullet_item(*nodes))
        content.append(adf.spacer())

    if sharepoint_url:
        label = link_label or f"Release Notes {version_label.lstrip('v')}.docx"
        content.append(adf.paragraph(adf.text("Release Notes Documentation", bold=True)))
        if sharepoint_url.startswith(("https://", "http://")):
            content.append(adf.paragraph(adf.link(label, sharepoint_url)))
        else:
            content.append(adf.paragraph(adf.text(label)))

    return adf.doc(*content) if content else adf.doc(adf.paragraph(adf.text(" ")))
