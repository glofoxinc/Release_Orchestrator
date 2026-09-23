"""SHIPIT test / demo ticket helpers — no approvers, no team, safe disposal."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import config

_TEST_MARKERS = (
    "TEST SHIPIT",
    "DO NOT DEPLOY",
    "DEMO VALIDATION",
    "MIGRATION VALIDATION",
)

_VERSION_RE = re.compile(r"(\d{4})\.(\d)\.(\d{2})\.(\d{2})")


def is_test_shipit_summary(summary: str) -> bool:
    """True when summary marks a non-production SHIPIT (test / demo / migration)."""
    upper = (summary or "").strip().upper()
    return any(marker in upper for marker in _TEST_MARKERS)


def default_test_summary(version_label: str) -> str:
    """Canonical TEST summary (matches SHIPIT-16710 / operator runbook)."""
    label = version_label if version_label.lower().startswith("v") else f"v{version_label}"
    return (
        f"TEST SHIPIT Demo Validation - Insights Customize BI - DO NOT DEPLOY ({label})"
    )


def parse_release_version_date(version_name: str) -> date | None:
    """Parse ``2026.3.09.11`` → Sep 11, 2026 (PIC/AN fix-version shape)."""
    match = _VERSION_RE.search((version_name or "").strip())
    if not match:
        return None
    year, _, month_str, day_str = match.groups()
    try:
        return date(int(year), int(month_str), int(day_str))
    except ValueError:
        return None


def validate_fix_version_name(version_name: str) -> tuple[bool, str | None]:
    """Return (ok, error_message). Requires PIC/AN shape ``YYYY.Q.MM.DD``."""
    name = (version_name or "").strip()
    if not name:
        return False, "version_name is required."
    match = _VERSION_RE.search(name)
    if not match:
        return (
            False,
            f"Version '{name}' must match YYYY.Q.MM.DD (e.g. 2026.3.09.11). "
            "Do not use 2026.9.11.11-style strings — month and day are the 3rd and 4th segments.",
        )
    _year, quarter, month_str, day_str = match.groups()
    try:
        quarter_i = int(quarter)
        month_i = int(month_str)
    except ValueError:
        return False, f"Version '{name}' has non-numeric quarter/month segments."
    if not (1 <= quarter_i <= 4):
        return (
            False,
            f"Version '{name}' has invalid quarter segment '{quarter}' (expected 1–4). "
            "Use PIC/AN fix-version shape, e.g. 2026.3.09.11.",
        )
    if not (1 <= month_i <= 12):
        return False, f"Version '{name}' has invalid month segment '{month_str}'."
    if parse_release_version_date(name) is None:
        return False, f"Version '{name}' has an invalid calendar date."
    return True, None


def merge_prod_draft(draft: dict[str, Any] | None) -> dict[str, Any]:
    """Prod SHIPIT (Rekha / SHIPIT-16769): approver groups only, no team."""
    merged = dict(draft or {})
    if "approver_groups" not in merged:
        merged["approver_groups"] = list(config.TCKT_DEFAULTS.get("approver_groups") or [])
    if "affected_services" not in merged:
        merged["affected_services"] = list(
            config.TCKT_DEFAULTS.get("affected_services") or []
        )
    merged["team"] = None
    merged.setdefault("approvers", [])
    merged.setdefault("assignment_group", None)
    return merged


def merge_test_draft(draft: dict[str, Any] | None) -> dict[str, Any]:
    """Force empty approver/team assignments for demo tickets."""
    merged = dict(draft or {})
    merged["approver_groups"] = []
    merged["approvers"] = []
    merged["team"] = None
    merged["assignment_group"] = None
    merged["affected_services"] = []
    return merged


def demo_extracted_row(*, version_name: str = "2026.3.09.11") -> list[dict[str, Any]]:
    """Minimal Analyze ticket row for SHIPIT migration / demo dry-runs."""
    return [{
        "ticket": "AN-TEST",
        "summary": "New Members - DEMO test only",
        "status": "Done",
        "type": "Analyze",
        "client": "Standard",
        "report": "New Members",
        "description": "DEMO test · Dashboard · DO NOT DEPLOY",
        "assignee": "Test",
        "parent": "AN-TEST",
        "project": "AN",
        "fix_version": version_name,
        "link": "https://abcfinancial.atlassian.net/browse/AN-TEST",
    }]
