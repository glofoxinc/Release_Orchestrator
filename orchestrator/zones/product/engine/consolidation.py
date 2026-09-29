"""Dashboard-level ticket consolidation helpers.

These functions enforce the project rule from ``.cursor/rules/jira-release-ticket-creation.mdc``:

    Never list the same dashboard/report multiple times — always consolidate.

A single extracted-ticket dict is shaped as::

    {
        "type": "Analyze" | "Custom",
        "client": str,              # "Standard" for Analyze tickets
        "report": str,              # dashboard/report name (may be empty)
        "description": str,         # short verb-phrase ("add join type filter")
        "ticket": str,              # e.g. "AN-5192"
    }

The :func:`dashboard_label` helper produces the canonical grouping key; two
tickets that share the same label are considered the same dashboard for the
purposes of Description bullets, Business Impact lines, and Test Plan items.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


def dashboard_label(entry: dict[str, Any]) -> str:
    """Return the canonical dashboard label for an extracted ticket.

    - Custom tickets include the client prefix: ``"Jetts - Revenue Analysis"``.
    - Analyze tickets use the report name directly, falling back to the short
      description if no report was parsed.
    """
    if entry.get("type") == "Custom":
        client = (entry.get("client") or "").strip()
        report = (entry.get("report") or "").strip()
        if client and report:
            return f"{client} - {report}"
        return client or report or (entry.get("description") or "").strip()
    report = (entry.get("report") or "").strip()
    return report or (entry.get("description") or "").strip()


def _description_for_merge(entry: dict[str, Any], label: str) -> str:
    """Return a lowercase description suitable for merging, or empty string."""
    desc = (entry.get("description") or "").strip()
    if not desc:
        return ""
    if desc.lower() == label.lower():
        return ""
    return desc.lower()


def consolidate_dashboards(extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group extracted tickets by dashboard label.

    Returns a list of dicts with keys ``label``, ``summary`` (comma-separated
    merged descriptions), ``refs`` (comma-separated ticket keys), and the
    underlying ``tickets`` list for downstream consumers.
    """
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for entry in extracted or []:
        label = dashboard_label(entry)
        if not label:
            continue
        bucket = groups.setdefault(
            label,
            {"label": label, "descs": [], "tickets": [], "entries": []},
        )
        merged_desc = _description_for_merge(entry, label)
        if merged_desc:
            bucket["descs"].append(merged_desc)
        ticket_key = entry.get("ticket")
        if ticket_key:
            bucket["tickets"].append(ticket_key)
        bucket["entries"].append(entry)

    result: list[dict[str, Any]] = []
    for bucket in groups.values():
        unique_descs = list(dict.fromkeys(bucket["descs"]))
        unique_refs = list(dict.fromkeys(bucket["tickets"]))
        result.append({
            "label": bucket["label"],
            "summary": ", ".join(unique_descs),
            "refs": ", ".join(unique_refs),
            "tickets": unique_refs,
            "entries": bucket["entries"],
        })
    return result


def deduplicate_by_dashboard(
    items: list[dict[str, Any]],
    *,
    label_key: str = "label",
    text_key: str = "summary",
    refs_key: str = "refs",
) -> list[dict[str, Any]]:
    """Merge items that share the same dashboard label.

    This is a safety-net called by Description bullets, Business Impact lines
    and Test Plan items *after* the initial consolidation pass to guarantee
    that no dashboard label appears more than once.

    ``items`` is expected to already carry ``label_key`` (string) and may also
    carry ``text_key`` and ``refs_key`` (strings that will be merged
    deduplicated, comma-separated).
    """
    merged: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        label = (item.get(label_key) or "").strip()
        if not label:
            continue
        bucket = merged.get(label)
        if bucket is None:
            # Clone to avoid mutating the caller's dict
            bucket = dict(item)
            bucket[label_key] = label
            bucket[text_key] = (bucket.get(text_key) or "").strip()
            bucket[refs_key] = (bucket.get(refs_key) or "").strip()
            merged[label] = bucket
            continue
        # Merge summaries (case-insensitive dedupe)
        existing_texts = [t.strip() for t in (bucket.get(text_key) or "").split(",") if t.strip()]
        new_texts = [t.strip() for t in (item.get(text_key) or "").split(",") if t.strip()]
        seen_lower = {t.lower() for t in existing_texts}
        for t in new_texts:
            if t.lower() not in seen_lower:
                existing_texts.append(t)
                seen_lower.add(t.lower())
        bucket[text_key] = ", ".join(existing_texts)
        # Merge refs (exact dedupe)
        existing_refs = [r.strip() for r in (bucket.get(refs_key) or "").split(",") if r.strip()]
        new_refs = [r.strip() for r in (item.get(refs_key) or "").split(",") if r.strip()]
        for r in new_refs:
            if r not in existing_refs:
                existing_refs.append(r)
        bucket[refs_key] = ", ".join(existing_refs)
    return list(merged.values())
