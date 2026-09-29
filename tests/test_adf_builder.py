"""Tests for the ADF (Atlassian Document Format) builder helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adf_builder import bullet_item, doc, hard_break, link, paragraph, shipit_plan_to_doc, spacer, text


class TestText:
    def test_plain_text(self):
        result = text("hello")
        assert result == {"type": "text", "text": "hello"}

    def test_bold_text(self):
        result = text("bold", bold=True)
        assert result["type"] == "text"
        assert result["text"] == "bold"
        assert result["marks"] == [{"type": "strong"}]

    def test_plain_text_has_no_marks(self):
        result = text("no marks")
        assert "marks" not in result


class TestLink:
    def test_link_structure(self):
        result = link("Click here", "https://example.com")
        assert result["type"] == "text"
        assert result["text"] == "Click here"
        assert result["marks"] == [{"type": "link", "attrs": {"href": "https://example.com"}}]

    def test_link_preserves_url(self):
        url = "https://jira.example.com/browse/PROJ-123"
        result = link("PROJ-123", url)
        assert result["marks"][0]["attrs"]["href"] == url


class TestStructuralNodes:
    def test_hard_break(self):
        assert hard_break() == {"type": "hardBreak"}

    def test_paragraph_single_child(self):
        child = text("hello")
        result = paragraph(child)
        assert result == {"type": "paragraph", "content": [child]}

    def test_paragraph_multiple_children(self):
        children = [text("a"), hard_break(), text("b")]
        result = paragraph(*children)
        assert result["type"] == "paragraph"
        assert len(result["content"]) == 3

    def test_spacer_is_paragraph_with_space(self):
        result = spacer()
        assert result["type"] == "paragraph"
        assert result["content"][0]["text"] == " "


class TestBulletItem:
    def test_bullet_item_structure(self):
        result = bullet_item(text("item"))
        assert result["type"] == "bulletList"
        assert len(result["content"]) == 1
        list_item = result["content"][0]
        assert list_item["type"] == "listItem"
        assert list_item["content"][0]["type"] == "paragraph"


class TestShipitPlanToDoc:
    def test_bolds_phase_heading_and_label_prefix(self):
        plain = (
            "Pre-deployment\nNotify the squad.\n\n"
            "Before: Operators use the current report.\n\n"
            "Ticket: AN-5516."
        )
        result = shipit_plan_to_doc(plain)
        paras = result["content"]
        assert paras[0]["content"][0]["marks"] == [{"type": "strong"}]
        assert paras[0]["content"][0]["text"] == "Pre-deployment"
        before_para = paras[2]["content"]
        assert before_para[0]["text"] == "Before:"
        assert before_para[0]["marks"] == [{"type": "strong"}]


class TestDoc:
    def test_doc_wraps_content(self):
        p = paragraph(text("hello"))
        result = doc(p)
        assert result["type"] == "doc"
        assert result["version"] == 1
        assert result["content"] == [p]

    def test_empty_doc(self):
        result = doc()
        assert result == {"type": "doc", "version": 1, "content": []}
