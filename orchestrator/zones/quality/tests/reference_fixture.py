"""Resolve the reference Release Notes DOCX for parity tests."""

from __future__ import annotations

import os
from pathlib import Path

_FIXTURE_NAME = "Release Notes 2026.3.09.09.docx"
_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / _FIXTURE_NAME
_LEGACY_FIXTURE_NAME = "Release Notes 2026.3.07.15.docx"
_LEGACY_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / _LEGACY_FIXTURE_NAME


def reference_docx_path() -> str:
    """Prefer bundled fixture; fall back to legacy fixture or ~/Downloads for local dev."""
    if _FIXTURE_PATH.is_file():
        return str(_FIXTURE_PATH)
    if _LEGACY_FIXTURE_PATH.is_file():
        return str(_LEGACY_FIXTURE_PATH)
    downloads = Path.home() / "Downloads" / _FIXTURE_NAME
    if downloads.is_file():
        return str(downloads)
    legacy_downloads = Path.home() / "Downloads" / _LEGACY_FIXTURE_NAME
    if legacy_downloads.is_file():
        return str(legacy_downloads)
    return str(_FIXTURE_PATH)


REFERENCE_PATH = reference_docx_path()
REFERENCE_AVAILABLE = os.path.isfile(REFERENCE_PATH)


def parity_reference_docx_path() -> str:
    """DOCX used for generator fingerprint parity (sample data aligns with legacy template)."""
    if _LEGACY_FIXTURE_PATH.is_file():
        return str(_LEGACY_FIXTURE_PATH)
    return REFERENCE_PATH


PARITY_REFERENCE_PATH = parity_reference_docx_path()
PARITY_REFERENCE_AVAILABLE = os.path.isfile(PARITY_REFERENCE_PATH)
