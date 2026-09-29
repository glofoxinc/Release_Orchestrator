"""SharePoint upload receipt — validation and idempotent reuse."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sharepoint_receipt as sp


def test_validate_receipt_requires_file_url():
    ok, issues = sp.validate_receipt({})
    assert ok is False
    assert any("URL" in issue for issue in issues)


def test_receipt_matches_local_checksum(tmp_path):
    docx = tmp_path / "notes.docx"
    docx.write_bytes(b"release-notes-v1")
    receipt = sp.build_receipt(
        local_path=str(docx),
        version_name="v2026.3.09.25",
        sharepoint_url="https://contoso.sharepoint.com/sites/bi/Shared%20Documents/notes.docx",
        upload_mode="manual",
    )
    assert sp.receipt_matches_local(receipt, docx) is True
    docx.write_bytes(b"changed")
    assert sp.receipt_matches_local(receipt, docx) is False


def test_can_reuse_receipt_when_checksum_and_url_match(tmp_path):
    docx = tmp_path / "notes.docx"
    docx.write_bytes(b"stable")
    url = "https://contoso.sharepoint.com/sites/bi/Shared%20Documents/notes.docx"
    receipt = sp.build_receipt(
        local_path=str(docx),
        version_name="v2026.3.09.25",
        sharepoint_url=url,
        upload_mode="manual",
    )
    ok, reason = sp.can_reuse_receipt(receipt, local_path=docx, sharepoint_url=url)
    assert ok is True
    assert reason == "already_uploaded"
