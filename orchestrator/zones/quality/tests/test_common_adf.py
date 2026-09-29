"""Tests for the shared ADF builder module."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import adf


class TestTextLeaves:
    def test_plain_text(self):
        node = adf.text("hello")
        assert node == {"type": "text", "text": "hello"}

    def test_bold_text(self):
        node = adf.text("x", bold=True)
        assert node["marks"] == [{"type": "strong"}]

    def test_italic_text(self):
        node = adf.text("x", italic=True)
        assert node["marks"] == [{"type": "em"}]

    def test_code_text(self):
        node = adf.text("x", code=True)
        assert node["marks"] == [{"type": "code"}]

    def test_multiple_marks_combined(self):
        node = adf.text("x", bold=True, italic=True)
        types = {m["type"] for m in node["marks"]}
        assert types == {"strong", "em"}

    def test_no_marks_key_when_plain(self):
        assert "marks" not in adf.text("x")


class TestLink:
    def test_link_contains_href(self):
        node = adf.link("click me", "https://example.com")
        assert node["marks"][0]["type"] == "link"
        assert node["marks"][0]["attrs"]["href"] == "https://example.com"

    def test_link_preserves_text(self):
        assert adf.link("click", "u")["text"] == "click"


class TestStructuralNodes:
    def test_hard_break(self):
        assert adf.hard_break() == {"type": "hardBreak"}

    def test_paragraph_collects_children(self):
        p = adf.paragraph(adf.text("a"), adf.text("b"))
        assert p["type"] == "paragraph"
        assert len(p["content"]) == 2

    def test_spacer_is_single_space(self):
        s = adf.spacer()
        assert s["content"][0]["text"] == " "

    def test_heading_level_clamped_low(self):
        assert adf.heading(0, adf.text("x"))["attrs"]["level"] == 1

    def test_heading_level_clamped_high(self):
        assert adf.heading(10, adf.text("x"))["attrs"]["level"] == 6

    def test_heading_normal_level(self):
        assert adf.heading(3, adf.text("x"))["attrs"]["level"] == 3


class TestLists:
    def test_bullet_item_wraps_in_own_bulletlist(self):
        node = adf.bullet_item(adf.text("one"))
        assert node["type"] == "bulletList"
        assert len(node["content"]) == 1
        assert node["content"][0]["type"] == "listItem"

    def test_bullet_list_multiple_items(self):
        node = adf.bullet_list([[adf.text("a")], [adf.text("b")], [adf.text("c")]])
        assert len(node["content"]) == 3
        assert all(i["type"] == "listItem" for i in node["content"])

    def test_ordered_list_multiple_items(self):
        node = adf.ordered_list([[adf.text("a")], [adf.text("b")]])
        assert node["type"] == "orderedList"
        assert len(node["content"]) == 2

    def test_empty_lists(self):
        assert adf.bullet_list([])["content"] == []
        assert adf.ordered_list([])["content"] == []


class TestCodeBlock:
    def test_code_block_no_language(self):
        node = adf.code_block("print(1)")
        assert node["type"] == "codeBlock"
        assert "attrs" not in node

    def test_code_block_language_attr(self):
        node = adf.code_block("print(1)", language="python")
        assert node["attrs"]["language"] == "python"

    def test_code_block_content_text(self):
        node = adf.code_block("abc")
        assert node["content"][0]["text"] == "abc"


class TestDoc:
    def test_doc_wraps_content(self):
        d = adf.doc(adf.paragraph(adf.text("hi")))
        assert d["type"] == "doc"
        assert d["version"] == 1
        assert len(d["content"]) == 1

    def test_empty_doc(self):
        assert adf.doc()["content"] == []


class TestPlainTextRoundtrip:
    def test_string_passthrough(self):
        assert adf.to_plain_text("raw") == "raw"

    def test_none_returns_empty(self):
        assert adf.to_plain_text(None) == ""

    def test_list_concatenates(self):
        assert adf.to_plain_text([adf.text("a"), adf.text("b")]) == "ab"

    def test_paragraph_adds_newline(self):
        out = adf.to_plain_text(adf.paragraph(adf.text("hi")))
        assert out == "hi\n"

    def test_hard_break_renders_newline(self):
        doc = adf.paragraph(adf.text("a"), adf.hard_break(), adf.text("b"))
        assert adf.to_plain_text(doc).startswith("a\nb")

    def test_nested_doc(self):
        d = adf.doc(
            adf.heading(1, adf.text("H")),
            adf.paragraph(adf.text("body")),
        )
        flat = adf.to_plain_text(d)
        assert "H" in flat and "body" in flat

    def test_non_string_non_dict_coerces(self):
        assert adf.to_plain_text(42) == "42"
