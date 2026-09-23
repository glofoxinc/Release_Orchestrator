"""Inject Word table styles missing from the python-docx blank template."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

GRID_TABLE4_ACCENT1_STYLE_ID = "GridTable4-Accent1"
_GRID_TABLE4_STYLE_PATH = (
    Path(__file__).resolve().parent / "assets" / "grid_table4_accent1_style.xml"
)


def patch_docx_grid_table4_accent1_style(docx_bytes: bytes) -> bytes:
    """Ensure saved DOCX includes Grid Table 4 Accent 1 (deployment/change tables)."""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zin:
        styles_text = zin.read("word/styles.xml").decode("utf-8")
        if GRID_TABLE4_ACCENT1_STYLE_ID in styles_text and "Grid Table 4 Accent 1" in styles_text:
            return docx_bytes
        style_xml = _GRID_TABLE4_STYLE_PATH.read_text(encoding="utf-8")

    in_buf = io.BytesIO(docx_bytes)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(
        out_buf, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                text = data.decode("utf-8")
                if "Grid Table 4 Accent 1" not in text:
                    text = text.replace("</w:styles>", f"{style_xml}</w:styles>", 1)
                    data = text.encode("utf-8")
            zout.writestr(item, data)
    return out_buf.getvalue()
