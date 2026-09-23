"""Field-by-field diff between two TCKT ticket payloads.

Used by the preview step to warn about inconsistencies against a previous
TCKT (e.g. "last release had 5 approvers, this one has 4"). The comparison
is purely structural — both sides are normalised to primitive dicts/lists of
strings before being compared, so ADF rich-text fields, approver lists, and
team IDs all go through the same code path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


_RICH_FIELDS = (
    "description",
    "implementation_plan",
    "test_plan",
    "backout_plan",
    "business_impact",
    "communication_plan",
    "risks_management",
    "qa_test_plan",
)


@dataclass
class FieldDiff:
    """Diff for a single field."""

    field: str
    status: str  # "same" | "added" | "removed" | "changed"
    previous: Any = None
    current: Any = None
    added: list[Any] = field(default_factory=list)
    removed: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "status": self.status,
            "previous": self.previous,
            "current": self.current,
            "added": list(self.added),
            "removed": list(self.removed),
        }


@dataclass
class DiffResult:
    """Result of comparing a current draft against a previous ticket."""

    fields: list[FieldDiff] = field(default_factory=list)

    def by_field(self, name: str) -> FieldDiff | None:
        for f in self.fields:
            if f.field == name:
                return f
        return None

    def changes(self) -> list[FieldDiff]:
        return [f for f in self.fields if f.status != "same"]

    def has_changes(self) -> bool:
        return any(f.status != "same" for f in self.fields)

    def to_dict(self) -> dict[str, Any]:
        return {"fields": [f.to_dict() for f in self.fields]}


# ── ADF / text helpers ────────────────────────────────────────────────


def _adf_to_text(node: Any) -> str:
    """Flatten an ADF node (or any nested dict/list) to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(_adf_to_text(x) for x in node).strip()
    if isinstance(node, dict):
        if node.get("type") == "text":
            return str(node.get("text", ""))
        if node.get("type") == "hardBreak":
            return "\n"
        content = node.get("content")
        if isinstance(content, list):
            joined = "".join(_adf_to_text(x) for x in content)
            if node.get("type") in ("paragraph", "heading", "listItem"):
                return joined + "\n"
            return joined
    return str(node)


def _normalize_rich(value: Any) -> str:
    """Normalise a rich-text field for comparison."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return _adf_to_text(value).strip()


def _normalize_list(value: Any, *, key: str | None = None) -> list[str]:
    """Return a sorted list of string identifiers for a list-valued field."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        return sorted([p for p in parts if p])
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return [str(value)]
    out: list[str] = []
    for item in value:
        if isinstance(item, dict):
            if key and item.get(key):
                out.append(str(item[key]))
            elif "accountId" in item:
                out.append(str(item["accountId"]))
            elif "name" in item:
                out.append(str(item["name"]))
            elif "id" in item:
                out.append(str(item["id"]))
            else:
                out.append(str(sorted(item.items())))
        else:
            out.append(str(item))
    return sorted([s for s in out if s])


def _normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or sorted(value.items()))
    return str(value).strip()


def _diff_list(name: str, prev: Iterable[str], curr: Iterable[str]) -> FieldDiff:
    prev_list = list(prev)
    curr_list = list(curr)
    prev_set = set(prev_list)
    curr_set = set(curr_list)
    added = sorted(curr_set - prev_set)
    removed = sorted(prev_set - curr_set)
    if not added and not removed:
        status = "same"
    elif added and not removed:
        status = "added"
    elif removed and not added:
        status = "removed"
    else:
        status = "changed"
    return FieldDiff(
        field=name,
        status=status,
        previous=prev_list,
        current=curr_list,
        added=added,
        removed=removed,
    )


def _diff_scalar(name: str, prev: str, curr: str) -> FieldDiff:
    if prev == curr:
        return FieldDiff(field=name, status="same", previous=prev, current=curr)
    if not prev and curr:
        return FieldDiff(field=name, status="added", previous=prev, current=curr)
    if prev and not curr:
        return FieldDiff(field=name, status="removed", previous=prev, current=curr)
    return FieldDiff(field=name, status="changed", previous=prev, current=curr)


# ── Extraction from Jira get_issue response ───────────────────────────


def extract_ticket_fields(
    issue: dict[str, Any],
    *,
    field_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Extract a canonical ticket-data dict from a raw Jira get-issue response.

    ``field_map`` maps logical field names (e.g. ``"approvers"``) to Jira
    custom-field IDs (``"customfield_11752"``). Defaults to
    :data:`config.TCKT_FIELDS` when available.
    """
    if field_map is None:
        try:
            import config  # local import keeps the module importable without config
            field_map = dict(config.TCKT_FIELDS)
        except Exception:
            field_map = {}

    fields = issue.get("fields", {}) or {}
    out: dict[str, Any] = {
        "summary": fields.get("summary", ""),
        "priority": fields.get("priority"),
        "description": fields.get("description"),
    }
    for logical in (
        "change_type",
        "change_risk",
        "impact",
        "urgency",
        "planned_start",
        "planned_end",
        "implementation_plan",
        "test_plan",
        "backout_plan",
        "business_impact",
        "communication_plan",
        "reason_for_change",
        "risks_management",
        "qa_test_plan",
        "approvers",
        "approver_groups",
        "affected_services",
        "team",
    ):
        cf = field_map.get(logical)
        if cf and cf in fields:
            out[logical] = fields[cf]
    return out


# ── Public API ────────────────────────────────────────────────────────

_LIST_FIELDS = {
    "approvers": "accountId",
    "approver_groups": "name",
    "affected_services": "id",
}


def diff_tickets(current: dict[str, Any], previous: dict[str, Any]) -> DiffResult:
    """Compare a current draft against a previous ticket payload.

    Both ``current`` and ``previous`` use the logical-name schema (see
    :func:`extract_ticket_fields`). Missing keys are treated as empty.
    """
    result = DiffResult()
    all_keys: list[str] = []
    seen: set[str] = set()
    preferred_order = [
        "summary",
        "priority",
        "change_type",
        "change_risk",
        "impact",
        "urgency",
        "planned_start",
        "planned_end",
        "description",
        "implementation_plan",
        "test_plan",
        "backout_plan",
        "business_impact",
        "communication_plan",
        "reason_for_change",
        "risks_management",
        "qa_test_plan",
        "approvers",
        "approver_groups",
        "team",
        "affected_services",
    ]
    for k in preferred_order:
        if k in current or k in previous:
            all_keys.append(k)
            seen.add(k)
    for src in (current, previous):
        for k in src.keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    for name in all_keys:
        prev_val = previous.get(name)
        curr_val = current.get(name)
        if name in _RICH_FIELDS:
            result.fields.append(
                _diff_scalar(name, _normalize_rich(prev_val), _normalize_rich(curr_val))
            )
        elif name in _LIST_FIELDS:
            result.fields.append(
                _diff_list(
                    name,
                    _normalize_list(prev_val, key=_LIST_FIELDS[name]),
                    _normalize_list(curr_val, key=_LIST_FIELDS[name]),
                )
            )
        else:
            result.fields.append(
                _diff_scalar(name, _normalize_scalar(prev_val), _normalize_scalar(curr_val))
            )
    return result


def extract_dashboards(ticket_data: dict[str, Any]) -> list[str]:
    """Return the ordered list of dashboard labels referenced by a ticket."""
    entries = ticket_data.get("extracted") or []
    from consolidation import dashboard_label
    labels = []
    seen: set[str] = set()
    for e in entries:
        label = dashboard_label(e)
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


def diff_dashboards(
    current: dict[str, Any], previous: dict[str, Any]
) -> FieldDiff:
    """Specifically diff the dashboards list between two tickets."""
    return _diff_list(
        "dashboards",
        sorted(extract_dashboards(previous)),
        sorted(extract_dashboards(current)),
    )
