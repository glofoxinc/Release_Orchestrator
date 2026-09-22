"""ADF (Atlassian Document Format) builder helpers."""

from __future__ import annotations

import re


def text(t: str, bold: bool = False) -> dict:
    node: dict = {"type": "text", "text": t}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return node


def link(t: str, href: str) -> dict:
    return {
        "type": "text",
        "text": t,
        "marks": [{"type": "link", "attrs": {"href": href}}],
    }


def mention(display_name: str, account_id: str) -> dict:
    """Jira @-mention node (requires assignee accountId)."""
    label = (display_name or "user").strip()
    if not label.startswith("@"):
        label = f"@{label}"
    return {
        "type": "mention",
        "attrs": {
            "id": str(account_id or "").strip(),
            "text": label,
            "accessLevel": "",
        },
    }


def hard_break() -> dict:
    return {"type": "hardBreak"}


def paragraph(*content) -> dict:
    return {"type": "paragraph", "content": list(content)}


def spacer() -> dict:
    return paragraph(text(" "))


def bullet_item(*content) -> dict:
    """A single spaced bullet (its own bulletList node)."""
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [paragraph(*content)],
            }
        ],
    }


def doc(*content) -> dict:
    return {"type": "doc", "version": 1, "content": list(content)}


def adf_links(adf_node: dict) -> list[tuple[str, str]]:
    """Return (link text, href) pairs from an ADF document."""
    links: list[tuple[str, str]] = []

    def _walk(node: dict) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "text":
            for mark in node.get("marks") or []:
                if mark.get("type") == "link":
                    href = (mark.get("attrs") or {}).get("href", "")
                    links.append((node.get("text", ""), href))
        for child in node.get("content") or []:
            _walk(child)

    _walk(adf_node)
    return links


def adf_to_plain_text(adf_node: dict) -> str:
    """Extract editable plain text from an ADF document."""
    if not isinstance(adf_node, dict):
        return str(adf_node or "")

    parts: list[str] = []

    def _inline(nodes: list[dict]) -> str:
        chunks: list[str] = []
        for node in nodes or []:
            if node.get("type") == "text":
                chunks.append(node.get("text", ""))
            elif node.get("type") == "hardBreak":
                chunks.append("\n")
        return "".join(chunks)

    def _walk(node: dict) -> None:
        t = node.get("type")
        if t == "doc":
            for child in node.get("content", []):
                _walk(child)
        elif t == "paragraph":
            line = _inline(node.get("content", []))
            if line.strip():
                parts.append(line)
            else:
                parts.append("")
        elif t == "bulletList":
            for item in node.get("content", []):
                for block in item.get("content", []):
                    if block.get("type") == "paragraph":
                        parts.append(f"- {_inline(block.get('content', []))}")
        else:
            for child in node.get("content", []) or []:
                _walk(child)

    _walk(adf_node)
    return "\n".join(parts).strip()


# SHIPIT plan fields — phase / section headings rendered bold in Jira (SHIPIT-17036).
_SHIPIT_BOLD_HEADINGS = frozenset(
    {
        "Pre-deployment",
        "During deployment",
        "After success",
        "After rollback",
        "Pre-deployment backups",
        "Overall",
        "Shared controls",
        "Layout and export",
    }
)

_SHIPIT_BOLD_PREFIXES = (
    "Before:",
    "After:",
    "Audience and boundary:",
    "Ticket:",
    "Measured impact:",
    "CAB exceptions on this request:",
)

_RISK_SUBHEADING = re.compile(r"^.+\([A-Z]+-\d+\)$")


def _inline_with_bold_prefix(line: str) -> list[dict]:
    for prefix in _SHIPIT_BOLD_PREFIXES:
        if line.startswith(prefix):
            rest = line[len(prefix) :]
            return [text(prefix, bold=True), text(rest)]
    return [text(line)]


def _shipit_heading_line(line: str) -> bool:
    stripped = line.strip()
    if stripped in _SHIPIT_BOLD_HEADINGS:
        return True
    return bool(_RISK_SUBHEADING.match(stripped))


def shipit_plan_to_doc(plain: str) -> dict:
    """Convert SHIPIT plan plain text to ADF with bold phase headings (17036 parity)."""
    blocks = [b for b in plain.strip().split("\n\n") if b.strip()]
    paras: list[dict] = []
    for block in blocks:
        lines = block.splitlines()
        first = lines[0].strip() if lines else ""
        if first in _SHIPIT_BOLD_HEADINGS and len(lines) > 1:
            paras.append(paragraph(text(first, bold=True)))
            content: list[dict] = []
            for i, line in enumerate(lines[1:]):
                if i > 0:
                    content.append(hard_break())
                content.extend(_inline_with_bold_prefix(line))
            if content:
                paras.append(paragraph(*content))
            continue
        if len(lines) == 1 and _shipit_heading_line(first):
            paras.append(paragraph(text(first, bold=True)))
            continue
        content = []
        for i, line in enumerate(lines):
            if i > 0:
                content.append(hard_break())
            stripped = line.strip()
            if _shipit_heading_line(stripped):
                content.append(text(stripped, bold=True))
            else:
                content.extend(_inline_with_bold_prefix(line))
        if content:
            paras.append(paragraph(*content))
    return doc(*paras) if paras else doc(paragraph(text(" ")))


def plain_text_to_doc(plain: str) -> dict:
    """Convert plain text (paragraphs + ``- `` bullets) to ADF."""
    blocks: list[dict] = []
    for block in plain.strip().split("\n\n"):
        lines = block.splitlines()
        if not lines:
            continue
        if all(line.lstrip().startswith("- ") for line in lines if line.strip()):
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("- "):
                    blocks.append(bullet_item(text(stripped[2:])))
            continue
        content: list[dict] = []
        for i, line in enumerate(lines):
            if i > 0:
                content.append(hard_break())
            stripped = line.strip()
            if stripped.startswith("http://") or stripped.startswith("https://"):
                blocks.append(paragraph(link(stripped, stripped)))
                content = []
                break
            content.append(text(line))
        if content:
            blocks.append(paragraph(*content))
    return doc(*blocks) if blocks else doc(paragraph(text(" ")))
