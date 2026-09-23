"""Structured Release Notes preview for MCP wizard (mirrors Streamlit Step 4)."""

from __future__ import annotations

from typing import Any

from generators.release_notes_report_tables import (
    build_delivered_reports_rows,
    parse_analyze_report_rows,
    parse_custom_client_report_tables,
)
from generators.release_notes_summary_tables import build_highlight_summary_tables


def _parse_change_rows(raw: str) -> list[list[str]]:
    from generators.parsing import parse_change_rows

    return parse_change_rows(raw)


def build_structured_preview(draft: dict[str, Any]) -> dict[str, Any]:
    """Section-by-section preview aligned with the platform Release Notes layout."""
    extracted = draft.get("extracted") or []
    analyze_rows = parse_analyze_report_rows(draft.get("analyze_report_rows", ""))
    custom_tables = parse_custom_client_report_tables(draft.get("custom_report_tables", ""))
    change_rows = _parse_change_rows(draft.get("change_rows", ""))
    highlight_blocks = build_highlight_summary_tables(extracted)
    delivered_rows = build_delivered_reports_rows(extracted)

    deploy_rows = [
        [part.strip() for part in line.split("|", 3)]
        for line in (draft.get("deployment_rows") or "").splitlines()
        if line.strip()
    ]

    custom_clients = [
        client.strip()
        for client in str(draft.get("custom_clients") or "").split(",")
        if client.strip()
    ]
    if not custom_clients:
        custom_clients = sorted(custom_tables.keys(), key=str.lower)

    evidence_raw = draft.get("testing_evidence_tickets") or draft.get("screenshot_names") or ""

    return {
        "metadata": {
            "version": draft.get("version", ""),
            "release_date": draft.get("release_date", ""),
            "dev_team": draft.get("dev_team", ""),
            "release_owner": draft.get("release_owner", ""),
            "environment": draft.get("environment", ""),
        },
        "release_summary": draft.get("summary_p1", ""),
        "key_highlights": [
            {"title": block.title, "rows": block.rows, "headers": list(block.headers)}
            for block in highlight_blocks
        ],
        "delivered_reports": delivered_rows,
        "affected_clients": {
            "analyze": analyze_rows,
            "custom": {
                client: (custom_tables.get(client) or [])
                for client in custom_clients
            },
        },
        "deployment_tracking": deploy_rows,
        "ticket_details": {
            "row_count": len(change_rows),
            "sample": change_rows[:5],
        },
        "testing_evidence": [
            line.strip()
            for line in str(evidence_raw).splitlines()
            if line.strip()
        ],
        "screenshots": [
            line.strip()
            for line in str(evidence_raw).splitlines()
            if line.strip()
        ],
        "excluded_tickets": draft.get("excluded_tickets", ""),
        "notes": draft.get("notes", ""),
    }
