"""Regression tests for Release Notes Key Highlights and Ticket Details hyperlinks."""

from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docx import Document
from docx.oxml.ns import qn

from generators.release_notes_generator import (
    build_key_highlight_lines,
    count_change_table_hyperlinks,
    format_change_row,
    generate_release_notes_docx,
    resolve_change_row_link_url,
)


class TestBuildKeyHighlightLines:
    def test_custom_client_dedupes_repeated_report_and_description(self):
        extracted = [
            {
                "type": "Custom",
                "client": "Jetts",
                "report": "Custom model dataset replacing with Jetts Dataset",
                "description": "Custom model dataset replacing with Jetts Dataset",
            }
        ]
        lines = build_key_highlight_lines(extracted)
        assert lines == ["Jetts: Custom model dataset replacing with Jetts Dataset"]

    def test_analyze_dedupes_repeated_report_and_description(self):
        extracted = [
            {
                "type": "Analyze",
                "client": "Standard",
                "report": "Trainer Class Report",
                "description": "Trainer Class Report",
            }
        ]
        lines = build_key_highlight_lines(extracted)
        assert lines == ["Standard (Analyze): Updates to Trainer Class Report"]

    def test_custom_client_keeps_distinct_report_and_description(self):
        extracted = [
            {
                "type": "Custom",
                "client": "Jazzercise",
                "report": "Elevate Sales",
                "description": "customize paginated report",
            }
        ]
        lines = build_key_highlight_lines(extracted)
        assert lines == ["Jazzercise: Elevate Sales: customize paginated report"]

    def test_analyze_keeps_distinct_report_and_description(self):
        extracted = [
            {
                "type": "Analyze",
                "client": "Standard",
                "report": "Payout Transaction Details(paginated report)",
                "description": "Missing failed payments and Duplicate In-transit records",
            }
        ]
        lines = build_key_highlight_lines(extracted)
        assert lines == [
            "Standard (Analyze): Updates to Payout Transaction Details (paginated report): "
            "Missing failed payments and Duplicate In-transit records"
        ]


def _hyperlink_targets(paragraph) -> dict[str, str]:
    """Map visible hyperlink text -> resolved URL for every hyperlink in a paragraph."""
    part = paragraph.part
    targets: dict[str, str] = {}
    for hyperlink_el in paragraph._p.findall(qn("w:hyperlink")):
        r_id = hyperlink_el.get(qn("r:id"))
        text = "".join(t.text or "" for t in hyperlink_el.findall(".//" + qn("w:t")))
        targets[text] = part.rels[r_id].target_ref if r_id else ""
    return targets


class TestChangeTableHyperlinks:
    def _generate(self):
        row = format_change_row(
            ticket="PIC-5196",
            link="https://abcfinancial.atlassian.net/browse/PIC-5196",
            test_by="Chanti",
            testing_status="Done",
        )
        result = generate_release_notes_docx({"version": "1.0.0", "change_rows": row})
        return Document(io.BytesIO(result))

    def _change_table(self, doc: Document):
        return next(t for t in doc.tables if any("Ticket" in c.text for c in t.rows[0].cells))

    def test_ticket_cell_is_hyperlinked_to_its_jira_url(self):
        doc = self._generate()
        table = self._change_table(doc)
        ticket_cell = table.rows[1].cells[0]
        assert ticket_cell.text.strip() == "PIC-5196"
        links = _hyperlink_targets(ticket_cell.paragraphs[0])
        assert links.get("PIC-5196") == "https://abcfinancial.atlassian.net/browse/PIC-5196"

    def test_link_cell_is_clickable(self):
        doc = self._generate()
        table = self._change_table(doc)
        link_cell = table.rows[1].cells[1]
        url = "https://abcfinancial.atlassian.net/browse/PIC-5196"
        assert link_cell.text.strip() == url
        links = _hyperlink_targets(link_cell.paragraphs[0])
        assert links.get(url) == url

    def test_ticket_cell_still_bordered_after_hyperlink(self):
        doc = self._generate()
        table = self._change_table(doc)
        ticket_cell = table.rows[1].cells[0]
        assert ticket_cell._tc.tcPr.find(qn("w:tcBorders")) is not None

    def test_empty_link_column_still_hyperlinks_ticket_from_jira_base(self, monkeypatch):
        import config

        monkeypatch.setattr(config, "JIRA_BASE_URL", "https://abcfinancial.atlassian.net")
        row = format_change_row(
            ticket="PIC-9999",
            link="",
            test_by="Chanti",
            testing_status="Done",
        )
        result = generate_release_notes_docx({"version": "1.0.0", "change_rows": row})
        doc = Document(io.BytesIO(result))
        table = self._change_table(doc)
        ticket_cell = table.rows[1].cells[0]
        assert ticket_cell.text.strip() == "PIC-9999"
        links = _hyperlink_targets(ticket_cell.paragraphs[0])
        assert links.get("PIC-9999") == "https://abcfinancial.atlassian.net/browse/PIC-9999"

    def test_resolves_link_from_ticket_when_link_column_empty(self):
        row = ["PIC-5196", "", "Chanti", "Done"]
        url = resolve_change_row_link_url(row)
        assert url.endswith("/browse/PIC-5196")

    def test_resolves_link_from_legacy_ten_column_row(self):
        row = [
            "1", "PIC-5196", "PIC-5196", "PIC-4000", "",
            "Custom", "Jetts", "Monthly", "Desc", "Chanti", "", "Done",
        ]
        url = resolve_change_row_link_url(row)
        assert url.endswith("/browse/PIC-5196")

    def test_hyperlink_count_matches_linked_rows(self):
        row = format_change_row(
            ticket="PIC-5196",
            link="https://abcfinancial.atlassian.net/browse/PIC-5196",
            test_by="Chanti",
            testing_status="Done",
        )
        result = generate_release_notes_docx({"version": "1.0.0", "change_rows": row})
        assert count_change_table_hyperlinks(result) >= 2
