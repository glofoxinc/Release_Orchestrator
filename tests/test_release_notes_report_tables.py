"""Tests for dashboard / paginated report inventory tables."""

from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


def _ticket(
    ticket_type: str,
    client: str,
    report: str,
    description: str,
    ticket: str,
    assignee: str = "",
) -> dict:
    return {
        "type": ticket_type,
        "client": client,
        "report": report,
        "description": description,
        "ticket": ticket,
        "assignee": assignee,
    }


class TestReportTableBuilders:
    def test_analyze_table_classifies_paginated_and_new(self):
        from generators.release_notes_report_tables import build_analyze_report_rows

        extracted = [
            _ticket("Analyze", "Standard", "New Dashboard", "New dashboard for promo", "AN-1", "Alice"),
            _ticket(
                "Analyze",
                "Standard",
                "Payouts",
                "Existing payout dashboard enhancement",
                "AN-2",
                "Bob",
            ),
        ]
        rows = build_analyze_report_rows(extracted)
        assert len(rows) == 2
        by_name = {row.name: row for row in rows}
        assert by_name["New Dashboard"].client == "Analyze"
        assert by_name["New Dashboard"].asset_type == "Dashboard"
        assert by_name["New Dashboard"].change_type == "New"
        assert by_name["New Dashboard"].tickets == "AN-1"
        assert by_name["New Dashboard"].owner == "Alice"
        assert by_name["Payouts"].change_type == "Existing"

    def test_custom_tables_group_by_client(self):
        from generators.release_notes_report_tables import build_custom_client_report_tables

        extracted = [
            _ticket(
                "Custom",
                "Jazzercise",
                "Bookings by Location",
                "Existing dashboard update",
                "PIC-1",
                "Carol",
            ),
            _ticket(
                "Custom",
                "Lift",
                "ABC Customize",
                "New paginated report migrated from Looker",
                "PIC-2",
                "Dave",
            ),
        ]
        tables = build_custom_client_report_tables(extracted)
        assert sorted(tables) == ["Jazzercise", "Lift"]
        assert tables["Lift"][0].asset_type == "Paginated report"
        assert tables["Lift"][0].change_type == "Looker-exit"
        assert tables["Lift"][0].client == "Lift"
        assert tables["Lift"][0].tickets == "PIC-2"
        assert tables["Lift"][0].owner == "Dave"


class TestGeneratorLayout:
    def test_docx_uses_report_tables_not_legacy_summaries(self):
        from docx import Document

        from generators.release_notes_generator import generate_release_notes_docx
        from generators.release_notes_template_defaults import (
            CLIENT_DETAIL_REPORT_HEADERS,
            REPORT_TABLE_HEADERS,
        )

        data = {
            "version": "v2026.3.08.12",
            "include_analyze_section": True,
            "analyze_report_rows": (
                "Analyze|Promo look up|PIC-10|Owner A|Dashboard|Existing\n"
                "Analyze|New Dashboard|PIC-11|Owner B|Dashboard|New"
            ),
            "custom_report_tables": (
                "[Jazzercise]\nJazzercise|Bookings by Location|PIC-1|Owner C|Dashboard|Existing\n"
                "[Lift]\nLift|ABC Customize|PIC-2|Owner D|Paginated report|Looker-exit"
            ),
            "custom_clients": "Jazzercise, Lift",
        }
        doc = Document(io.BytesIO(generate_release_notes_docx(data)))
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Standard & Custom Summary" not in text
        assert "All Analyze-based (Standard) clients" not in text
        assert "Dashboards / Reports:" not in text
        assert "Reports / Dashboards Delivered" in text
        assert "Analyze Clients" not in text
        assert "Custom Clients" not in text

        from generators.release_notes_template_defaults import DELIVERED_REPORTS_HEADERS

        delivered_tables = [
            table
            for table in doc.tables
            if [cell.text.strip() for cell in table.rows[0].cells] == list(DELIVERED_REPORTS_HEADERS)
        ]
        assert len(delivered_tables) >= 1
        delivered_body = [cell.text.strip() for cell in delivered_tables[0].rows[1].cells]
        assert delivered_body[0] in {"Glofox Analyze", "Analyze"}
