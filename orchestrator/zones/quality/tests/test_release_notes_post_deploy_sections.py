"""Release notes post-deploy section defaults (sanity, screenshots, excluded table)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


def test_build_screenshot_ticket_lines_from_extracted():
    from generators.release_notes_template_defaults import build_screenshot_ticket_lines

    extracted = [
        {"ticket": "AN-100"},
        {"ticket": "PIC-200"},
        {"ticket": "PIC-200"},
    ]
    assert build_screenshot_ticket_lines(extracted).splitlines() == ["AN-100", "PIC-200"]


def test_screenshot_tickets_derived_from_change_rows_when_missing():
    import io

    from docx import Document

    from generators.release_notes_generator import generate_release_notes_docx

    data = {
        "version": "v2026.3.08.12",
        "change_rows": (
            "1|PIC-11|PIC-11|P-1|https://example/browse/PIC-11|Custom|Jetts|R|Desc|T||\n"
            "2|AN-22|AN-22|P-2|https://example/browse/AN-22|Analyze|Std|R|Desc|T||"
        ),
    }
    doc = Document(io.BytesIO(generate_release_notes_docx(data)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "PIC-11" in text
    assert "AN-22" in text
