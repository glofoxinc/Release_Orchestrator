"""Tests for ui.preview rendering helpers (no Streamlit runtime required)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from release_platform.ui.preview import _json_safe, adf_to_html, adf_to_markdown, to_markdown

DOC = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "paragraph", "content": [
            {"type": "text", "text": "Hello ", "marks": []},
            {"type": "text", "text": "world", "marks": [{"type": "strong"}]},
        ]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "item"}]}
            ]}
        ]},
    ],
}


class TestAdfToHtml:
    def test_doc_wraps_paragraph(self):
        assert "<p>" in adf_to_html(DOC)

    def test_strong_mark(self):
        assert "<strong>world</strong>" in adf_to_html(DOC)

    def test_bullet_list(self):
        out = adf_to_html(DOC)
        assert "<ul>" in out and "<li>" in out

    def test_em_mark(self):
        adf = {"type": "paragraph", "content": [
            {"type": "text", "text": "x", "marks": [{"type": "em"}]}
        ]}
        assert "<em>x</em>" in adf_to_html(adf)

    def test_link_mark(self):
        adf = {"type": "paragraph", "content": [
            {"type": "text", "text": "go", "marks": [{"type": "link", "attrs": {"href": "https://x"}}]}
        ]}
        out = adf_to_html(adf)
        assert 'href="https://x"' in out
        assert ">go</a>" in out

    def test_escape_html(self):
        adf = {"type": "paragraph", "content": [
            {"type": "text", "text": "<script>"}
        ]}
        out = adf_to_html(adf)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_hard_break(self):
        out = adf_to_html({"type": "paragraph", "content": [{"type": "hardBreak"}]})
        assert "<br/>" in out

    def test_string_input(self):
        assert "foo" in adf_to_html("foo")

    def test_none_input(self):
        assert adf_to_html(None) == ""


class TestAdfToMarkdown:
    def test_strong(self):
        md = adf_to_markdown(DOC)
        assert "**world**" in md

    def test_bullet_item(self):
        md = adf_to_markdown(DOC)
        assert "- item" in md

    def test_link_mark(self):
        adf = {"type": "paragraph", "content": [
            {"type": "text", "text": "go", "marks": [{"type": "link", "attrs": {"href": "https://x"}}]}
        ]}
        assert "[go](https://x)" in adf_to_markdown(adf)

    def test_string_passthrough(self):
        assert adf_to_markdown("raw") == "raw"


class TestToMarkdown:
    def test_contains_summary_heading(self):
        ticket = {"summary": "My Ticket", "description_adf": {"type": "doc", "content": []}}
        md = to_markdown(ticket)
        assert md.startswith("# My Ticket")

    def test_contains_all_plans(self):
        ticket = {
            "summary": "T",
            "implementation_plan": "IP",
            "test_plan": "TP",
            "backout_plan": "BP",
            "business_impact": "BI",
        }
        md = to_markdown(ticket)
        for section in ("Implementation Plan", "Test Plan", "Backout Plan", "Business Impact"):
            assert section in md

    def test_approvers_list(self):
        ticket = {"summary": "T", "approvers": [{"name": "Alice"}, {"accountId": "a"}]}
        md = to_markdown(ticket)
        assert "Alice" in md
        assert "- a" in md


class TestJsonSafe:
    def test_datetime_becomes_string(self):
        from datetime import date
        safe = _json_safe({"d": date(2026, 4, 14)})
        assert json.dumps(safe) == '{"d": "2026-04-14"}'

    def test_nested_structures(self):
        safe = _json_safe({"a": [1, 2, {"b": 3}]})
        assert safe == {"a": [1, 2, {"b": 3}]}
