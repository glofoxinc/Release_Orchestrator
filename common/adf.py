"""Shared Atlassian Document Format (ADF) builders.

These helpers produce the JSON shape that Jira and Confluence (Cloud) accept
for rich-text fields. They deliberately mirror the existing top-level
``adf_builder`` module so both projects can consume a single canonical set of
primitives.

Example
-------
>>> from common import adf
>>> body = adf.doc(
...     adf.paragraph(adf.text("Release "), adf.text("2026.04.14", bold=True)),
...     adf.spacer(),
...     adf.bullet_item(adf.text("New Members filter")),
... )
>>> body["type"]
'doc'
"""

from __future__ import annotations

from typing import Any

_Node = dict[str, Any]


def text(t: str, *, bold: bool = False, italic: bool = False, code: bool = False) -> _Node:
    """Text leaf node, with optional bold/italic/code marks."""
    node: _Node = {"type": "text", "text": t}
    marks: list[dict[str, Any]] = []
    if bold:
        marks.append({"type": "strong"})
    if italic:
        marks.append({"type": "em"})
    if code:
        marks.append({"type": "code"})
    if marks:
        node["marks"] = marks
    return node


def link(t: str, href: str) -> _Node:
    """Hyperlink text node."""
    return {
        "type": "text",
        "text": t,
        "marks": [{"type": "link", "attrs": {"href": href}}],
    }


def hard_break() -> _Node:
    """Force a line-break inside a paragraph."""
    return {"type": "hardBreak"}


def paragraph(*content: _Node) -> _Node:
    """Paragraph node with the given inline children."""
    return {"type": "paragraph", "content": list(content)}


def spacer() -> _Node:
    """Visible empty paragraph — used to separate sections."""
    return paragraph(text(" "))


def heading(level: int, *content: _Node) -> _Node:
    """Heading of level 1..6 (clamped to range)."""
    lvl = max(1, min(6, int(level)))
    return {"type": "heading", "attrs": {"level": lvl}, "content": list(content)}


def bullet_item(*content: _Node) -> _Node:
    """A single spaced bullet (own bulletList per ABC BI convention)."""
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [paragraph(*content)]},
        ],
    }


def bullet_list(items: list[list[_Node]]) -> _Node:
    """Standard (non-spaced) bullet list."""
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [paragraph(*it)]} for it in items
        ],
    }


def ordered_list(items: list[list[_Node]]) -> _Node:
    """Ordered list."""
    return {
        "type": "orderedList",
        "content": [
            {"type": "listItem", "content": [paragraph(*it)]} for it in items
        ],
    }


def code_block(content: str, language: str | None = None) -> _Node:
    """Code block with optional language attribute."""
    attrs: dict[str, Any] = {}
    if language:
        attrs["language"] = language
    node: _Node = {
        "type": "codeBlock",
        "content": [{"type": "text", "text": content}],
    }
    if attrs:
        node["attrs"] = attrs
    return node


def doc(*content: _Node) -> _Node:
    """Top-level ADF document wrapper."""
    return {"type": "doc", "version": 1, "content": list(content)}


def to_plain_text(node: Any) -> str:
    """Flatten any ADF node (or list / string) to its text content.

    Round-trippable in the limited sense that text leaves are preserved; marks
    and formatting are dropped.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(to_plain_text(n) for n in node)
    if not isinstance(node, dict):
        return str(node)
    t = node.get("type")
    if t == "text":
        return str(node.get("text", ""))
    if t == "hardBreak":
        return "\n"
    parts = [to_plain_text(c) for c in node.get("content", []) or []]
    joined = "".join(parts)
    if t in {"paragraph", "heading", "listItem"}:
        return joined + "\n"
    return joined


__all__ = [
    "text",
    "link",
    "hard_break",
    "paragraph",
    "spacer",
    "heading",
    "bullet_item",
    "bullet_list",
    "ordered_list",
    "code_block",
    "doc",
    "to_plain_text",
]
