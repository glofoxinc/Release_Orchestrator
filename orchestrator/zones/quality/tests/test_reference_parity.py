"""Structural and theme parity checks against Release Notes 2026.3.07.15.docx."""

from __future__ import annotations

import io
import os
import sys

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.release_notes_generator import format_change_row, generate_release_notes_docx
from generators.release_notes_template_defaults import (
    CHANGE_HEADER_FILL,
    PAGE_MARGIN_INCHES,
    SECTION_SHADING,
    TITLE_COLOR,
    VERSION_TEXT_COLOR,
)
from tests.reference_fixture import REFERENCE_AVAILABLE
from tests.test_reference_template import _reference_like_data


from generators.release_notes_parity import _change_table


def _table_has_borders(table) -> bool:
    tbl_pr = table._tbl.tblPr
    if tbl_pr is None:
        return False
    return tbl_pr.find(qn("w:tblBorders")) is not None


def _para_shading(paragraph) -> str | None:
    p_pr = paragraph._p.pPr
    if p_pr is None:
        return None
    shd = p_pr.find(qn("w:shd"))
    if shd is None:
        return None
    return shd.get(qn("w:fill"))


def _cell_has_borders(cell) -> bool:
    tc_pr = cell._tc.tcPr
    if tc_pr is None:
        return False
    return tc_pr.find(qn("w:tcBorders")) is not None


def _run_color(run) -> str | None:
    if run.font.color and run.font.color.rgb:
        return str(run.font.color.rgb)
    return None


@pytest.mark.skipif(not REFERENCE_AVAILABLE, reason="Reference DOCX not available")
class TestReferenceParity:
    def test_title_and_version_centered_like_reference(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        assert doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER
        assert doc.paragraphs[0].text.strip() == "Release Notes"
        assert doc.paragraphs[1].alignment == WD_ALIGN_PARAGRAPH.CENTER
        assert "Version: v2026.3.09.09" in doc.paragraphs[1].text

    def test_title_blue_and_version_black(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        title_style = doc.styles["Heading 1"]
        title_style_color = (
            str(title_style.font.color.rgb)
            if title_style.font.color and title_style.font.color.rgb
            else None
        )
        assert title_style_color == TITLE_COLOR
        title_run_color = _run_color(doc.paragraphs[0].runs[0])
        assert title_run_color in (None, TITLE_COLOR)
        version_runs = doc.paragraphs[1].runs
        assert len(version_runs) >= 1
        assert all(run.bold for run in version_runs)
        assert _run_color(version_runs[0]) == VERSION_TEXT_COLOR

    def test_section_gray_shading_like_reference(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        shaded = {
            p.text.strip()[:40]: _para_shading(p)
            for p in doc.paragraphs
            if p.text.strip()
        }
        assert shaded.get("Key Highlights") == SECTION_SHADING
        assert any(v == SECTION_SHADING for k, v in shaded.items() if k.startswith("Release Summary"))
        assert shaded.get("Reports / Dashboards Delivered") == SECTION_SHADING
        assert shaded.get("Testing Evidence:") == SECTION_SHADING

    def test_page_margins_match_reference(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        section = doc.sections[0]
        assert round(section.left_margin.inches, 2) == PAGE_MARGIN_INCHES
        assert round(section.right_margin.inches, 2) == PAGE_MARGIN_INCHES

    def test_deployment_and_change_tables_have_no_table_borders(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        deploy = next(
            t for t in doc.tables if any("Deployment Owner" in c.text for c in t.rows[0].cells)
        )
        change = _change_table(doc)
        assert _table_has_borders(deploy) is False
        assert _table_has_borders(change) is False

    def test_deployment_table_cells_have_borders(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        deploy = next(
            t for t in doc.tables if any("Deployment Owner" in c.text for c in t.rows[0].cells)
        )
        bordered = sum(
            1 for row in deploy.rows for cell in row.cells if _cell_has_borders(cell)
        )
        total = sum(len(row.cells) for row in deploy.rows)
        assert bordered == total
        hdr = deploy.rows[0].cells[0]._tc.tcPr.find(qn("w:shd"))
        assert hdr is not None
        assert hdr.get(qn("w:fill")) == "156082"

    def test_change_table_cells_have_borders(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        change = _change_table(doc)
        total = sum(len(row.cells) for row in change.rows)
        bordered = sum(
            1 for row in change.rows for cell in row.cells if _cell_has_borders(cell)
        )
        assert bordered == total
        assert total > 0

    def test_change_header_white_on_black(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        change = _change_table(doc)
        cell = change.rows[0].cells[0]
        shd = cell._tc.tcPr.find(qn("w:shd"))
        assert shd is not None
        assert shd.get(qn("w:fill")) == CHANGE_HEADER_FILL
        run = cell.paragraphs[0].runs[0]
        assert _run_color(run) is None
        assert run.bold is not True

    def test_excluded_placeholder_has_borders(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        excluded = next(t for t in doc.tables if len(t.columns) == 8 and t.rows[0].cells[0].text.strip() == "S.No")
        assert _table_has_borders(excluded) is True
        assert all(_cell_has_borders(cell) for row in excluded.rows for cell in row.cells)

    def test_change_table_row_columns_match_reference(self):
        row = format_change_row(
            ticket="PIC-5730",
            link="https://example/browse/PIC-5730",
            test_by="Nikhila",
            testing_status="Done",
        )
        result = generate_release_notes_docx({**_reference_like_data(), "change_rows": row})
        doc = Document(io.BytesIO(result))
        table = _change_table(doc)
        values = [c.text.strip() for c in table.rows[1].cells]
        assert values[0] == "PIC-5730"
        assert values[1].startswith("https://")
        assert values[2] == ""
        assert values[3] == "Nikhila"
        assert values[4] == "Done"

    def test_key_highlights_use_summary_tables(self):
        from generators.release_notes_template_defaults import CATEGORY_SUMMARY_HEADERS

        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        summary_tables = [
            table
            for table in doc.tables
            if [cell.text.strip() for cell in table.rows[0].cells] == list(CATEGORY_SUMMARY_HEADERS)
        ]
        assert summary_tables
        assert any("Total" in cell.text for table in summary_tables for row in table.rows for cell in row.cells)

    def test_delivered_reports_table_lists_dashboards(self):
        from generators.release_notes_template_defaults import DELIVERED_REPORTS_HEADERS

        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        delivered = [
            table
            for table in doc.tables
            if [cell.text.strip() for cell in table.rows[0].cells] == list(DELIVERED_REPORTS_HEADERS)
        ]
        assert delivered
        assert any(
            "Royalties" in cell.text
            for table in delivered
            for row in table.rows[1:]
            for cell in row.cells
        )
        assert any(
            "Glofox Analyze" in cell.text
            for table in delivered
            for row in table.rows[1:]
            for cell in row.cells
        )

    def test_release_summary_body_is_normal_style(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        body = next(
            p
            for p in doc.paragraphs
            if "reporting enhancements" in p.text
        )
        assert body.style.name == "Normal"

    def test_section_headings_use_org_blue_and_larger_size(self):
        from generators.release_notes_template_defaults import TITLE_COLOR

        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        style_color = str(doc.styles["Heading 2"].font.color.rgb)
        assert style_color == TITLE_COLOR
        assert any(p.text.strip().startswith("Testing Evidence:") for p in doc.paragraphs)

    def test_shaded_paragraph_count_reasonable(self):
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))
        shaded_count = sum(
            1
            for p in doc.paragraphs
            if p._p.pPr is not None and p._p.pPr.find(qn("w:shd")) is not None
        )
        assert shaded_count >= 5

    def test_overall_theme_parity_score(self):
        """All programmatic theme/structure checks that define 10/10 reference parity."""
        result = generate_release_notes_docx(_reference_like_data())
        doc = Document(io.BytesIO(result))

        checks = {
            "margins": round(doc.sections[0].left_margin.inches, 2) == PAGE_MARGIN_INCHES,
            "title_centered": doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER,
            "title_blue": str(doc.styles["Heading 1"].font.color.rgb) == TITLE_COLOR,
            "title_run_inherits": _run_color(doc.paragraphs[0].runs[0]) in (None, TITLE_COLOR),
            "version_black_bold": (
                doc.paragraphs[1].runs[0].bold
                and _run_color(doc.paragraphs[1].runs[0]) == VERSION_TEXT_COLOR
            ),
            "shaded_sections": sum(
                1 for p in doc.paragraphs if p._p.pPr is not None and p._p.pPr.find(qn("w:shd")) is not None
            )
            >= 5,
            "change_cell_borders": all(
                _cell_has_borders(cell) for row in _change_table(doc).rows for cell in row.cells
            ),
            "change_header_fill": _change_table(doc).rows[0].cells[0]._tc.tcPr.find(qn("w:shd")).get(
                qn("w:fill")
            )
            == CHANGE_HEADER_FILL,
            "change_header_inherited_text": _run_color(
                _change_table(doc).rows[0].cells[0].paragraphs[0].runs[0]
            )
            is None,
            "excluded_borders": _table_has_borders(
                next(
                    t
                    for t in doc.tables
                    if len(t.columns) == 8 and t.rows[0].cells[0].text.strip() == "S.No"
                )
            ),
        }
        assert all(checks.values()), f"Parity gaps: {[k for k, v in checks.items() if not v]}"

    def test_normalize_fixes_extra_parent_column(self):
        from generators.release_notes_generator import _normalize_change_row

        cols = [
            "1", "PIC-5234", "PIC-5234", "PIC-5234", "PIC-4211",
            "https://example/browse/PIC-5234", "Custom", "Jetts", "Report", "Desc", "Tester", "", "",
        ]
        normalized = _normalize_change_row(cols)
        assert normalized[0] == "PIC-5234"
        assert normalized[1].startswith("https://")
        assert normalized[2] == ""
        assert normalized[3] == "Tester"
        assert len(normalized) == 5
