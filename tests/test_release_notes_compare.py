"""Tests for release_notes_compare module."""

from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.release_notes_generator import generate_release_notes_docx
from generators.release_notes_sample import sample_release_notes_data
from release_notes_compare import compare_generated_bytes, extract_section_headings
from tests.reference_fixture import REFERENCE_AVAILABLE, REFERENCE_PATH


class TestReleaseNotesCompare:
    def test_extract_section_headings_from_sample(self):
        from docx import Document

        doc = Document(io.BytesIO(generate_release_notes_docx(sample_release_notes_data())))
        headings = extract_section_headings(doc)
        assert "Key Highlights" in headings
        assert "Reports / Dashboards Delivered" in headings

    def test_compare_generated_bytes_matches_reference(self):
        if not REFERENCE_AVAILABLE:
            import pytest

            pytest.skip("Reference DOCX not available")
        data = sample_release_notes_data()
        result = compare_generated_bytes(REFERENCE_PATH, generate_release_notes_docx(data))
        assert result["status"] == "ok"
        assert not result["missing_v4_sections"]
