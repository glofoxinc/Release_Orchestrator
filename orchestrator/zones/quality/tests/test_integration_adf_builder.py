"""Integration tests for the ADF (Atlassian Document Format) builder.

Validates that composed documents match Jira's expected ADF schema.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adf_builder import bullet_item, doc, hard_break, link, paragraph, spacer, text


class TestADFSchema:
    """Every doc() output must satisfy Jira's top-level ADF contract."""

    def test_doc_type_is_doc(self):
        result = doc(paragraph(text("hi")))
        assert result["type"] == "doc"

    def test_doc_version_is_one(self):
        result = doc(paragraph(text("hi")))
        assert result["version"] == 1

    def test_doc_has_content_list(self):
        result = doc(paragraph(text("hi")))
        assert isinstance(result["content"], list)

    def test_doc_keys_only(self):
        result = doc(paragraph(text("hi")))
        assert set(result.keys()) == {"type", "version", "content"}


class TestBoldText:
    def test_bold_has_strong_mark(self):
        node = text("important", bold=True)
        assert node["marks"] == [{"type": "strong"}]

    def test_plain_has_no_marks(self):
        node = text("normal")
        assert "marks" not in node


class TestLinks:
    def test_link_mark_structure(self):
        node = link("Click", "https://example.com")
        assert node["type"] == "text"
        marks = node["marks"]
        assert len(marks) == 1
        assert marks[0]["type"] == "link"
        assert marks[0]["attrs"]["href"] == "https://example.com"

    def test_link_text_preserved(self):
        node = link("Jira Ticket", "https://jira.example.com/PROJ-1")
        assert node["text"] == "Jira Ticket"

    def test_link_with_special_url_chars(self):
        url = "https://example.com/search?q=hello+world&page=1"
        node = link("Search", url)
        assert node["marks"][0]["attrs"]["href"] == url


class TestBullets:
    def test_bullet_item_type(self):
        node = bullet_item(text("item"))
        assert node["type"] == "bulletList"

    def test_bullet_has_list_item(self):
        node = bullet_item(text("item"))
        assert node["content"][0]["type"] == "listItem"

    def test_bullet_content_wrapped_in_paragraph(self):
        node = bullet_item(text("item"))
        inner = node["content"][0]["content"][0]
        assert inner["type"] == "paragraph"
        assert inner["content"][0]["text"] == "item"


class TestComplexDocument:
    """Build a realistic multi-section ADF document and validate structure."""

    def _build_release_doc(self) -> dict:
        return doc(
            paragraph(text("Release Notes — v2.5.0", bold=True)),
            spacer(),
            paragraph(
                text("This release includes "),
                text("critical fixes", bold=True),
                text(" and new features."),
            ),
            bullet_item(text("PROJ-101: Fix login timeout")),
            bullet_item(
                link("PROJ-102", "https://jira.example.com/browse/PROJ-102"),
                text(": Dashboard performance"),
            ),
            paragraph(
                text("See full details at "),
                link("release page", "https://wiki.example.com/releases/2.5.0"),
            ),
        )

    def test_complex_doc_schema(self):
        result = self._build_release_doc()
        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) == 6

    def test_first_node_is_bold_paragraph(self):
        result = self._build_release_doc()
        first = result["content"][0]
        assert first["type"] == "paragraph"
        assert first["content"][0]["marks"] == [{"type": "strong"}]

    def test_spacer_is_second(self):
        result = self._build_release_doc()
        second = result["content"][1]
        assert second["type"] == "paragraph"
        assert second["content"][0]["text"] == " "

    def test_mixed_paragraph_has_bold_and_plain(self):
        result = self._build_release_doc()
        mixed = result["content"][2]
        assert len(mixed["content"]) == 3
        assert "marks" not in mixed["content"][0]
        assert mixed["content"][1]["marks"] == [{"type": "strong"}]
        assert "marks" not in mixed["content"][2]

    def test_bullet_items_are_bulletlists(self):
        result = self._build_release_doc()
        assert result["content"][3]["type"] == "bulletList"
        assert result["content"][4]["type"] == "bulletList"

    def test_bullet_with_link(self):
        result = self._build_release_doc()
        bullet_node = result["content"][4]
        para = bullet_node["content"][0]["content"][0]
        link_node = para["content"][0]
        assert link_node["marks"][0]["type"] == "link"
        assert "PROJ-102" in link_node["marks"][0]["attrs"]["href"]

    def test_last_paragraph_contains_link(self):
        result = self._build_release_doc()
        last = result["content"][5]
        assert last["type"] == "paragraph"
        link_node = last["content"][1]
        assert link_node["marks"][0]["type"] == "link"


class TestEdgeCases:
    def test_empty_doc(self):
        result = doc()
        assert result == {"type": "doc", "version": 1, "content": []}

    def test_empty_paragraph(self):
        result = paragraph()
        assert result == {"type": "paragraph", "content": []}

    def test_empty_text(self):
        result = text("")
        assert result == {"type": "text", "text": ""}

    def test_nested_bold_link_not_supported_but_doesnt_crash(self):
        node = link("bold link", "https://x.com")
        node["marks"].append({"type": "strong"})
        result = doc(paragraph(node))
        assert result["type"] == "doc"

    def test_hard_break_in_paragraph(self):
        result = paragraph(text("line1"), hard_break(), text("line2"))
        assert len(result["content"]) == 3
        assert result["content"][1]["type"] == "hardBreak"

    def test_unicode_text(self):
        node = text("Ünïcödé ☺ テスト")
        assert node["text"] == "Ünïcödé ☺ テスト"

    def test_very_long_text(self):
        long_str = "x" * 10_000
        node = text(long_str)
        assert len(node["text"]) == 10_000
