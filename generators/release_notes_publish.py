"""Shared publish path for UI and MCP release notes DOCX generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from generators.parsing import parse_change_rows as _parse_change_rows
from generators.release_notes_generator import (
    count_change_table_hyperlinks,
    generate_release_notes_docx,
    resolve_change_row_link_url,
)
from generators.release_notes_insights import (
    ReadinessReport,
    assess_release_notes_readiness,
    readiness_to_dict,
)


@dataclass
class PublishResult:
    status: str  # ok | blocked | error
    docx_bytes: bytes | None = None
    readiness: ReadinessReport | None = None
    hyperlink_check: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"status": self.status}
        if self.readiness is not None:
            body["readiness"] = readiness_to_dict(self.readiness)
        if self.hyperlink_check:
            body["hyperlink_check"] = self.hyperlink_check
        if self.error:
            body["error"] = self.error
        if self.docx_bytes is not None:
            body["docx_bytes_len"] = len(self.docx_bytes)
        return body


def publish_release_notes_docx(
    data: dict[str, Any],
    *,
    enforce_readiness: bool = True,
) -> PublishResult:
    """Generate DOCX with readiness and hyperlink checks (UI + MCP parity)."""
    readiness = assess_release_notes_readiness(data)
    if enforce_readiness and not readiness.ready:
        return PublishResult(status="blocked", readiness=readiness)

    try:
        docx_bytes = generate_release_notes_docx(data)
    except Exception as exc:  # noqa: BLE001 — surface to caller
        return PublishResult(status="error", readiness=readiness, error=str(exc))

    change_rows = _parse_change_rows(data.get("change_rows", ""))
    rows_with_links = sum(
        1 for row in change_rows if resolve_change_row_link_url(row)
    )
    hyperlink_count = count_change_table_hyperlinks(docx_bytes)
    hyperlink_check = {
        "rows_with_links": rows_with_links,
        "hyperlink_count": hyperlink_count,
        "passed": not rows_with_links or hyperlink_count >= rows_with_links,
    }

    if rows_with_links and hyperlink_count < rows_with_links:
        return PublishResult(
            status="error",
            readiness=readiness,
            docx_bytes=docx_bytes,
            hyperlink_check=hyperlink_check,
            error=(
                f"Hyperlink check failed — expected links for {rows_with_links} change row(s), "
                f"found {hyperlink_count} in the DOCX."
            ),
        )

    return PublishResult(
        status="ok",
        docx_bytes=docx_bytes,
        readiness=readiness,
        hyperlink_check=hyperlink_check,
    )
