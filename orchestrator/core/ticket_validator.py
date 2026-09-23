"""Cross-field validation for TCKT ticket drafts.

After the description/plans have been built, this module looks for drift:

- Every dashboard mentioned in the Description must also appear in the Test
  Plan and Business Impact.
- Every ticket key referenced in any section must appear in the source
  extracted ticket list.

All warnings are non-blocking; each one optionally carries an auto-fix
payload that the UI can apply with one click.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from consolidation import dashboard_label
from diff_engine import _adf_to_text  # re-use the ADF flattener

logger = logging.getLogger(__name__)


@dataclass
class ValidationWarning:
    """One actionable warning from :func:`validate_coverage`."""

    code: str
    severity: str  # "warning" | "info"
    message: str
    missing: list[str] = field(default_factory=list)
    section: str = ""
    auto_fix: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "missing": list(self.missing),
            "section": self.section,
            "auto_fix": self.auto_fix,
        }


_TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return _adf_to_text(value)


def _find_ticket_refs(text: str) -> set[str]:
    return set(_TICKET_RE.findall(text or ""))


def _expected_dashboards(ticket_data: dict[str, Any]) -> list[str]:
    entries = ticket_data.get("extracted") or []
    seen: list[str] = []
    lookup: set[str] = set()
    for e in entries:
        label = dashboard_label(e)
        if label and label not in lookup:
            seen.append(label)
            lookup.add(label)
    return seen


def _label_in_text(label: str, text: str) -> bool:
    """Case-insensitive substring match anchored to a non-word boundary."""
    if not label or not text:
        return False
    return label.lower() in text.lower()


def validate_coverage(ticket_draft: dict[str, Any]) -> list[ValidationWarning]:
    """Run the full coverage pass on a ticket-data dict.

    The ``ticket_draft`` is expected to carry ``extracted`` (the source ticket
    list), and any of ``description``, ``test_plan``, ``business_impact``,
    ``implementation_plan``, ``backout_plan`` as either plain strings or ADF
    dicts. Missing sections are treated as empty strings.
    """
    warnings: list[ValidationWarning] = []

    dashboards = _expected_dashboards(ticket_draft)
    extracted = ticket_draft.get("extracted") or []
    known_ticket_keys = {
        e.get("ticket") for e in extracted if e.get("ticket")
    }

    description = _as_text(ticket_draft.get("description") or ticket_draft.get("description_adf"))
    test_plan = _as_text(ticket_draft.get("test_plan") or ticket_draft.get("test_plan_adf"))
    biz_impact = _as_text(
        ticket_draft.get("business_impact") or ticket_draft.get("business_impact_adf")
    )
    impl_plan = _as_text(
        ticket_draft.get("implementation_plan") or ticket_draft.get("impl_plan")
        or ticket_draft.get("implementation_plan_adf")
    )
    backout = _as_text(
        ticket_draft.get("backout_plan") or ticket_draft.get("backout_plan_adf")
    )

    # ── Every description dashboard must appear in the test plan ─
    if dashboards and test_plan:
        missing_test = [d for d in dashboards if not _label_in_text(d, test_plan)]
        if missing_test:
            warnings.append(
                ValidationWarning(
                    code="test_plan_missing_dashboards",
                    severity="warning",
                    message=(
                        f"{len(missing_test)} dashboard(s) from the Description are "
                        "not referenced in the Test Plan."
                    ),
                    missing=missing_test,
                    section="test_plan",
                    auto_fix={
                        "action": "append_test_plan_items",
                        "items": [f"Validate {d} changes." for d in missing_test],
                    },
                )
            )

    # ── Every description dashboard must appear in business impact ─
    if dashboards and biz_impact:
        missing_impact = [d for d in dashboards if not _label_in_text(d, biz_impact)]
        if missing_impact:
            warnings.append(
                ValidationWarning(
                    code="business_impact_missing_dashboards",
                    severity="warning",
                    message=(
                        f"{len(missing_impact)} dashboard(s) from the Description are "
                        "not referenced in Business Impact."
                    ),
                    missing=missing_impact,
                    section="business_impact",
                    auto_fix={
                        "action": "append_business_impact_lines",
                        "items": [f"{d}: updated in this release." for d in missing_impact],
                    },
                )
            )

    # ── Every ticket ref in any section must exist in extracted ─
    all_text = "\n".join([description, test_plan, biz_impact, impl_plan, backout])
    referenced = _find_ticket_refs(all_text)
    unknown = sorted(k for k in referenced if k and k not in known_ticket_keys)
    # Guard against false positives: if ``extracted`` is empty we can't tell.
    if unknown and known_ticket_keys:
        warnings.append(
            ValidationWarning(
                code="unknown_ticket_references",
                severity="warning",
                message=(
                    f"{len(unknown)} ticket reference(s) are not in the selected "
                    "release tickets."
                ),
                missing=unknown,
                section="description",
                auto_fix=None,
            )
        )

    # ── Empty-but-expected sections ──────────────────────────────
    for section_name, text in [
        ("test_plan", test_plan),
        ("business_impact", biz_impact),
        ("implementation_plan", impl_plan),
        ("backout_plan", backout),
    ]:
        if dashboards and not text.strip():
            warnings.append(
                ValidationWarning(
                    code=f"{section_name}_empty",
                    severity="warning",
                    message=(
                        f"{section_name.replace('_', ' ').title()} is empty but the "
                        f"Description lists {len(dashboards)} dashboard(s)."
                    ),
                    section=section_name,
                    auto_fix=None,
                )
            )

    logger.debug("validate_coverage produced %d warning(s)", len(warnings))
    return warnings


def apply_auto_fix(
    ticket_draft: dict[str, Any], warning: ValidationWarning
) -> dict[str, Any]:
    """Apply a warning's auto-fix to a ticket-data dict (non-destructive copy)."""
    if not warning.auto_fix:
        return dict(ticket_draft)
    new_draft = dict(ticket_draft)
    action = warning.auto_fix.get("action")
    items = warning.auto_fix.get("items") or []

    if action == "append_test_plan_items":
        existing = _as_text(new_draft.get("test_plan") or "")
        addition = "\n".join(items)
        new_draft["test_plan"] = (existing + ("\n" if existing else "") + addition).strip()
    elif action == "append_business_impact_lines":
        existing = _as_text(new_draft.get("business_impact") or "")
        addition = "\n".join(items)
        new_draft["business_impact"] = (existing + ("\n" if existing else "") + addition).strip()
    else:
        logger.warning("Unknown auto-fix action: %s", action)
    return new_draft
