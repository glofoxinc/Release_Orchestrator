"""SharePoint upload receipt — idempotent handoff evidence for release notes."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import browser_automation
import sharepoint_url as sp_url


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def file_checksum(path: str | Path) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def build_receipt(
    *,
    local_path: str,
    version_name: str,
    sharepoint_url: str,
    upload_mode: str = "manual",
    folder_url: str = "",
) -> dict[str, Any]:
    """Build a receipt dict after upload or manual URL confirmation."""
    local = Path(local_path)
    remote_name = browser_automation.resolve_remote_name(version_name.lstrip("v"))
    folder = browser_automation.resolve_sharepoint_folder_url(version_name=version_name)
    return {
        "recorded_at": _utc_now(),
        "upload_mode": upload_mode,
        "local_path": str(local),
        "local_checksum_sha256": file_checksum(local) if local.is_file() else "",
        "remote_name": remote_name,
        "quarter_folder": browser_automation.resolve_sharepoint_quarter_label(version_name=version_name),
        "folder_url": folder_url or folder,
        "file_url": sharepoint_url,
        "url_valid": sp_url.validate_sharepoint_url(sharepoint_url),
    }


def validate_receipt(receipt: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Return (ok, issues) before SHIPIT create."""
    if not isinstance(receipt, dict):
        return False, ["SharePoint receipt missing — paste or upload release notes URL first."]
    issues: list[str] = []
    if not receipt.get("file_url"):
        issues.append("SharePoint file URL is required.")
    elif not sp_url.validate_sharepoint_url(str(receipt.get("file_url") or "")):
        issues.append("SharePoint file URL failed validation.")
    if not receipt.get("remote_name"):
        issues.append("Expected remote document name missing from receipt.")
    return not issues, issues


def persist_receipt(receipt: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return path


def receipt_matches_local(receipt: dict[str, Any] | None, local_path: str | Path) -> bool:
    """True when receipt checksum matches the local DOCX (idempotent upload skip)."""
    if not isinstance(receipt, dict):
        return False
    expected = str(receipt.get("local_checksum_sha256") or "").strip()
    if not expected:
        return False
    local = Path(local_path)
    if not local.is_file():
        return False
    try:
        return file_checksum(local) == expected
    except OSError:
        return False


def can_reuse_receipt(
    receipt: dict[str, Any] | None,
    *,
    local_path: str | Path,
    sharepoint_url: str = "",
) -> tuple[bool, str]:
    """Return (reuse_ok, reason) for resumable SharePoint handoff."""
    if not isinstance(receipt, dict):
        return False, "no_receipt"
    ok, issues = validate_receipt(receipt)
    if not ok:
        return False, "; ".join(issues) or "invalid_receipt"
    url = str(sharepoint_url or receipt.get("file_url") or "").strip()
    if url and str(receipt.get("file_url") or "").strip() != url:
        return False, "url_mismatch"
    if not receipt_matches_local(receipt, local_path):
        return False, "checksum_mismatch"
    return True, "already_uploaded"
