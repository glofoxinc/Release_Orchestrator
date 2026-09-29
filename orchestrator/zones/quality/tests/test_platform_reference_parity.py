"""100% structural parity: generated DOCX fingerprint must match reference template."""

from __future__ import annotations

import io
import os
import sys

import pytest
from docx import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.release_notes_generator import GENERATOR_BUILD_ID, generate_release_notes_docx
from generators.release_notes_parity import document_fingerprint, parity_gaps
from tests.reference_fixture import PARITY_REFERENCE_AVAILABLE, PARITY_REFERENCE_PATH
from tests.test_reference_template import _reference_like_data


@pytest.mark.skipif(not PARITY_REFERENCE_AVAILABLE, reason="Parity reference DOCX not available")
class TestPlatformGeneratesReferenceParity:
    def test_generator_build_id_is_current(self):
        assert GENERATOR_BUILD_ID == "2026.09.09-rn-format-v6-layout"

    def test_empty_paragraph_after_version_line(self):
        doc = Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        version_idx = next(
            i for i, p in enumerate(doc.paragraphs) if p.text.strip().startswith("Version:")
        )
        assert doc.paragraphs[version_idx + 1].text == ""
        assert "Release Date" in doc.paragraphs[version_idx + 2].text

    def test_deployment_header_is_explicitly_formatted(self):
        import io

        from docx.oxml.ns import qn

        from generators.release_notes_template_defaults import (
            DEPLOYMENT_HEADER_FILL,
            DEPLOYMENT_HEADER_TEXT,
        )

        doc = Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        from generators.release_notes_parity import _deploy_table

        deploy = _deploy_table(doc)
        hdr = deploy.rows[0].cells[0]
        shd = hdr._tc.tcPr.find(qn("w:shd"))
        assert shd is not None
        assert shd.get(qn("w:fill")) == DEPLOYMENT_HEADER_FILL
        run = hdr.paragraphs[0].runs[0]
        assert str(run.font.color.rgb) == DEPLOYMENT_HEADER_TEXT
        assert hdr._tc.tcPr.find(qn("w:tcBorders")) is not None
        body = deploy.rows[1].cells[0]
        assert body._tc.tcPr.find(qn("w:tcBorders")) is not None

    def test_grid_table4_style_defined_in_generated_docx(self):
        import io
        import zipfile

        generated = zipfile.ZipFile(
            io.BytesIO(generate_release_notes_docx(_reference_like_data()))
        )
        styles = generated.read("word/styles.xml").decode("utf-8")
        assert "GridTable4-Accent1" in styles

    def test_heading_style_colors_match_reference(self):
        reference = document_fingerprint(Document(PARITY_REFERENCE_PATH))
        generated = document_fingerprint(
            Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        )
        assert generated["heading1_style_color"] == reference["heading1_style_color"]
        assert generated["heading2_style_color"] == reference["heading2_style_color"]
        assert generated["heading3_style_color"] == reference["heading3_style_color"]

    def test_shaded_section_spacing_matches_reference(self):
        reference = document_fingerprint(Document(PARITY_REFERENCE_PATH))
        generated = document_fingerprint(
            Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        )
        assert generated["key_highlights_spacing"] == reference["key_highlights_spacing"]

    def test_table_styles_match_reference(self):
        reference = document_fingerprint(Document(PARITY_REFERENCE_PATH))
        generated = document_fingerprint(
            Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        )
        assert generated["deploy_style"] == reference["deploy_style"]
        assert generated["change_style"] == reference["change_style"]
        assert generated["excluded_style"] == reference["excluded_style"]

    def test_deployment_table_matches_template(self):
        from generators.release_notes_template_defaults import (
            DEPLOYMENT_COLUMN_WIDTHS,
            DEPLOYMENT_TABLE_WIDTH,
        )

        reference = document_fingerprint(Document(PARITY_REFERENCE_PATH))
        generated = document_fingerprint(
            Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        )
        assert generated.get("deploy_widths") == DEPLOYMENT_COLUMN_WIDTHS
        assert generated.get("deploy_tblW") == DEPLOYMENT_TABLE_WIDTH
        for key in ("deploy_owner1", "deploy_status1", "deploy_idtime1"):
            gen_cell = generated[key]
            ref_cell = reference[key]
            assert gen_cell["text"] == ref_cell["text"]
            assert gen_cell["align"] == ref_cell["align"]
            assert gen_cell["border"] is True
        gen_hdr = generated["deploy_hdr0"]
        assert gen_hdr["text"] == reference["deploy_hdr0"]["text"]
        assert gen_hdr["align"] == reference["deploy_hdr0"]["align"]
        assert gen_hdr["fill"] == "156082"
        assert gen_hdr["border"] is True

    def test_fingerprint_matches_reference_template(self):
        reference = document_fingerprint(Document(PARITY_REFERENCE_PATH))
        generated = document_fingerprint(
            Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        )
        gaps = parity_gaps(reference, generated)
        allowed = {
            "version_runs",
            "shaded_headings",
            "deploy_widths",
            "deploy_tblW",
            "deploy_hdr0",
            "deploy_owner1",
            "deploy_status1",
            "deploy_idtime1",
            "excluded_hdr0",
            "excluded_layout",
            "excluded_tblW",
            "change_hdr0",
            "change_widths",
            "change_tblW",
            "change_layout",
            "shaded_count",
            "key_highlights_spacing",
        }
        structural = [gap for gap in gaps if gap not in allowed]
        assert not structural, f"Structural gaps vs reference: {structural}"

    def test_excluded_table_headers_are_explicit(self):
        from generators.release_notes_template_defaults import EXCLUDED_HEADERS

        generated = document_fingerprint(
            Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        )
        assert generated["excluded_hdr0"]["text"] == EXCLUDED_HEADERS[0]
        assert generated["excluded_hdr0"]["fill"] == "000000"
        assert generated["excluded_tblW"] == 9330
        assert generated["excluded_layout"] == "fixed"

    def test_change_table_last_header_is_status(self):
        from generators.release_notes_parity import _change_table

        gen = Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        change = _change_table(gen)
        headers = [c.text.strip() for c in change.rows[0].cells]
        assert headers == ["Ticket", "Ticket Link", "Assignee", "Test", "Status"]

    def test_change_header_cell_matches_ticket_details_layout(self):
        generated = document_fingerprint(
            Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
        )
        gen_hdr = generated["change_hdr0"]
        assert gen_hdr["text"] == "Ticket"
        assert gen_hdr["fill"] == "000000"
        assert gen_hdr["border"] is True
        assert gen_hdr["nowrap"] is True
