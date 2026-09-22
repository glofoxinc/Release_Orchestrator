"""Pre-flight verification of source PIC/AN tickets referenced in a release.

Every ticket that rolls up into a TCKT deployment should (at minimum):

* Be in an expected state (``Done`` / ``Ready for release`` by default).
* Have a non-empty summary.
* Have an acceptance-criteria or test-plan field filled in.

This module runs those checks by querying Jira, reports a list of findings,
and optionally updates the linked tickets with a release-tracking label.

The Jira backend is an **injected callable** — tests supply a fake; production
wires :func:`jira_client.get_issue` and :func:`jira_client._post`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# Callables injected for network access ------------------------------------

IssueFetcher = Callable[[str], dict[str, Any] | None]
LabelUpdater = Callable[[str, str], None]


DEFAULT_EXPECTED_STATES: tuple[str, ...] = (
    "done",
    "closed",
    "resolved",
    "ready for release",
    "ready for deployment",
)


@dataclass
class TicketFinding:
    ticket: str
    ok: bool
    state: str = ""
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket": self.ticket,
            "ok": self.ok,
            "state": self.state,
            "issues": list(self.issues),
        }


@dataclass
class VerificationReport:
    total: int = 0
    passed: int = 0
    findings: list[TicketFinding] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def all_ok(self) -> bool:
        return self.total > 0 and self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "all_ok": self.all_ok,
            "findings": [f.to_dict() for f in self.findings],
        }


def _as_text(value: Any) -> str:
    """Flatten an ADF dict or plain string to searchable text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: list[str] = []
        if value.get("type") == "text" and "text" in value:
            parts.append(str(value["text"]))
        for child in value.get("content", []) or []:
            parts.append(_as_text(child))
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(_as_text(v) for v in value)
    return ""


_AC_FIELD_HINTS = re.compile(r"acceptance\s*criteria", re.I)


def _has_acceptance_criteria(fields: dict[str, Any]) -> bool:
    """Return True when any known acceptance-criteria field is non-empty."""
    if not isinstance(fields, dict):
        return False
    for key, value in fields.items():
        if not isinstance(key, str):
            continue
        if _AC_FIELD_HINTS.search(key):
            if _as_text(value).strip():
                return True
    # Common custom field IDs we've seen in practice.
    for cf in ("customfield_12300", "customfield_12301"):
        if _as_text(fields.get(cf)).strip():
            return True
    return False


def _extract_state(fields: dict[str, Any]) -> str:
    status = fields.get("status") or {}
    if isinstance(status, dict):
        return str(status.get("name") or "")
    return str(status or "")


def verify_tickets(
    ticket_keys: list[str],
    *,
    fetch: IssueFetcher,
    expected_states: tuple[str, ...] = DEFAULT_EXPECTED_STATES,
    require_acceptance_criteria: bool = True,
) -> VerificationReport:
    """Run the full pre-flight pass against every ticket key."""
    report = VerificationReport()
    expected = {s.lower() for s in expected_states}
    seen: set[str] = set()
    for key in ticket_keys:
        key = (key or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        report.total += 1
        finding = TicketFinding(ticket=key, ok=True)
        try:
            issue = fetch(key)
        except Exception as exc:
            finding.ok = False
            finding.issues.append(f"fetch failed: {exc}")
            report.findings.append(finding)
            continue
        if issue is None:
            finding.ok = False
            finding.issues.append("ticket not found")
            report.findings.append(finding)
            continue

        fields = (issue.get("fields") or {}) if isinstance(issue, dict) else {}
        state = _extract_state(fields)
        finding.state = state
        if state.lower() not in expected:
            finding.ok = False
            finding.issues.append(f"state '{state}' not in expected {sorted(expected)}")

        summary = (fields.get("summary") or "").strip() if isinstance(fields, dict) else ""
        if not summary:
            finding.ok = False
            finding.issues.append("missing summary")

        if require_acceptance_criteria and not _has_acceptance_criteria(fields):
            finding.ok = False
            finding.issues.append("missing acceptance criteria")

        if finding.ok:
            report.passed += 1
        report.findings.append(finding)
    return report


def apply_release_label(
    report: VerificationReport,
    *,
    label: str,
    label_update: LabelUpdater,
    only_passing: bool = True,
) -> list[str]:
    """Add ``label`` to every (passing) ticket in ``report`` via ``label_update``.

    Returns the list of tickets that were successfully labelled.
    """
    label = (label or "").strip()
    if not label:
        raise ValueError("label is required")
    updated: list[str] = []
    for finding in report.findings:
        if only_passing and not finding.ok:
            continue
        try:
            label_update(finding.ticket, label)
            updated.append(finding.ticket)
        except Exception as exc:
            logger.warning("failed to label %s: %s", finding.ticket, exc)
    return updated


def human_summary(report: VerificationReport) -> str:
    """Single-line human-readable result suitable for a log/UI banner."""
    if report.total == 0:
        return "No tickets supplied for verification."
    if report.all_ok:
        return f"All {report.total} tickets pass pre-flight checks."
    return f"{report.failed}/{report.total} tickets have warnings that need review."


__all__ = [
    "IssueFetcher",
    "LabelUpdater",
    "TicketFinding",
    "VerificationReport",
    "DEFAULT_EXPECTED_STATES",
    "verify_tickets",
    "apply_release_label",
    "human_summary",
]
