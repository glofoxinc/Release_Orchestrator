"""Detect opportunities to consolidate tickets by dashboard or client.

Given a list of Jira issues (from PIC / AN) the detector groups them by the
dashboard/report name extracted from the ticket summary and suggests a
consolidated bullet whenever a group contains two or more tickets.

Integrates with :mod:`consolidation` for the actual merging logic and with
:mod:`jira_client` for the per-project ticket parsing.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import jira_client
from consolidation import dashboard_label

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationSuggestion:
    """One consolidation opportunity — a dashboard with 2+ tickets."""

    label: str
    tickets: list[str]
    descriptions: list[str]
    merged_summary: str
    merged_bullet: str
    kind: str = "dashboard"  # "dashboard" | "client" | "report"
    entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "tickets": list(self.tickets),
            "descriptions": list(self.descriptions),
            "merged_summary": self.merged_summary,
            "merged_bullet": self.merged_bullet,
            "kind": self.kind,
        }


def _extract_from_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Turn a raw Jira issue into the extracted-ticket shape used elsewhere."""
    fields = issue.get("fields", {}) or {}
    summary = fields.get("summary") or ""
    key = issue.get("key") or ""
    info = jira_client.extract_ticket_info(summary, key)
    return {
        "ticket": key,
        "summary": summary,
        "type": info["type"],
        "client": info["client"],
        "report": info["report"],
        "description": info["description"],
    }


def _merged_summary(descriptions: list[str]) -> str:
    """Return a deduplicated, lowercase comma-separated summary."""
    seen: dict[str, None] = {}
    for d in descriptions:
        d = (d or "").strip().lower()
        if not d:
            continue
        seen.setdefault(d, None)
    return ", ".join(seen.keys())


def _build_bullet(label: str, summary: str, refs: list[str]) -> str:
    """Build the 'BoldLabel – merged summary (AN-XXXX)' rule-format bullet."""
    refs_str = ", ".join(refs)
    if summary:
        return f"**{label}** – {summary} ({refs_str})"
    return f"**{label}** ({refs_str})"


_SIMILARITY_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_SIMILARITY_TOKEN_RE.findall((text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def detect_consolidation_opportunities(
    tickets: list[dict[str, Any]],
    *,
    min_group_size: int = 2,
    similarity_threshold: float = 0.6,
) -> list[ConsolidationSuggestion]:
    """Return suggestions for tickets that should be merged into one bullet.

    Accepts either raw Jira issue dicts (with ``fields``) or pre-extracted
    entries already containing ``ticket``, ``type``, ``client``, ``report``
    and ``description`` keys. A single suggestion is returned per unique
    dashboard label that has ``>= min_group_size`` tickets.

    Additional client- and report-level suggestions are produced when multiple
    tickets share the same client or the same report even across different
    dashboard labels, and a "semantic" grouping is emitted when descriptions
    cross the ``similarity_threshold`` Jaccard similarity.
    """
    extracted: list[dict[str, Any]] = []
    for item in tickets or []:
        if not isinstance(item, dict):
            continue
        if "fields" in item and "key" in item:
            extracted.append(_extract_from_issue(item))
        else:
            extracted.append({
                "ticket": item.get("ticket") or item.get("key") or "",
                "type": item.get("type") or "Analyze",
                "client": item.get("client") or "Standard",
                "report": item.get("report") or "",
                "description": item.get("description") or "",
            })

    suggestions: list[ConsolidationSuggestion] = []

    # ── Dashboard grouping (the primary rule) ────────────────────
    dashboard_groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for e in extracted:
        label = dashboard_label(e)
        if not label:
            continue
        dashboard_groups.setdefault(label, []).append(e)

    for label, group in dashboard_groups.items():
        if len(group) < min_group_size:
            continue
        refs = [e["ticket"] for e in group if e.get("ticket")]
        descs = [e.get("description", "") for e in group]
        summary = _merged_summary(descs)
        suggestions.append(
            ConsolidationSuggestion(
                label=label,
                tickets=refs,
                descriptions=[d for d in descs if d],
                merged_summary=summary,
                merged_bullet=_build_bullet(label, summary, refs),
                kind="dashboard",
                entries=list(group),
            )
        )

    # ── Client grouping (Custom tickets only) ────────────────────
    client_groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for e in extracted:
        if e.get("type") != "Custom":
            continue
        client = (e.get("client") or "").strip()
        if not client or client.lower() in ("standard", "unknown"):
            continue
        client_groups.setdefault(client, []).append(e)

    for client, group in client_groups.items():
        if len(group) < min_group_size:
            continue
        # Skip client-level suggestion if all tickets already share one
        # dashboard label (we already emitted that suggestion).
        labels = {dashboard_label(e) for e in group}
        if len(labels) <= 1:
            continue
        refs = [e["ticket"] for e in group if e.get("ticket")]
        descs = [e.get("description", "") for e in group]
        summary = _merged_summary(descs)
        suggestions.append(
            ConsolidationSuggestion(
                label=client,
                tickets=refs,
                descriptions=[d for d in descs if d],
                merged_summary=summary,
                merged_bullet=_build_bullet(client, summary, refs),
                kind="client",
                entries=list(group),
            )
        )

    # ── Same-report cross-type grouping ──────────────────────────
    report_groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for e in extracted:
        report = (e.get("report") or "").strip()
        if not report:
            continue
        report_groups.setdefault(report.lower(), []).append(e)

    for report, group in report_groups.items():
        if len(group) < min_group_size:
            continue
        labels = {dashboard_label(e) for e in group}
        if len(labels) <= 1:
            continue
        refs = [e["ticket"] for e in group if e.get("ticket")]
        descs = [e.get("description", "") for e in group]
        summary = _merged_summary(descs)
        pretty_report = group[0].get("report") or report
        suggestions.append(
            ConsolidationSuggestion(
                label=pretty_report,
                tickets=refs,
                descriptions=[d for d in descs if d],
                merged_summary=summary,
                merged_bullet=_build_bullet(pretty_report, summary, refs),
                kind="report",
                entries=list(group),
            )
        )

    # ── Semantic (description-similarity) grouping ───────────────
    seen_pairs: set[frozenset] = set()
    for i, a in enumerate(extracted):
        ta = _tokenize(a.get("description", ""))
        if not ta:
            continue
        cluster = [a]
        for b in extracted[i + 1:]:
            tb = _tokenize(b.get("description", ""))
            if not tb:
                continue
            if _jaccard(ta, tb) >= similarity_threshold:
                cluster.append(b)
        if len(cluster) < min_group_size:
            continue
        fp = frozenset(e.get("ticket", "") for e in cluster)
        if fp in seen_pairs:
            continue
        # Avoid producing a duplicate of an existing dashboard suggestion
        if any(set(s.tickets) == set(fp) for s in suggestions):
            continue
        seen_pairs.add(fp)
        refs = [e["ticket"] for e in cluster if e.get("ticket")]
        descs = [e.get("description", "") for e in cluster]
        summary = _merged_summary(descs)
        suggestions.append(
            ConsolidationSuggestion(
                label="Similar descriptions",
                tickets=refs,
                descriptions=[d for d in descs if d],
                merged_summary=summary,
                merged_bullet=_build_bullet("Similar", summary, refs),
                kind="semantic",
                entries=list(cluster),
            )
        )

    logger.debug(
        "consolidation_detector: %d suggestion(s) from %d ticket(s)",
        len(suggestions),
        len(extracted),
    )
    return suggestions


def apply_suggestion(
    extracted: list[dict[str, Any]],
    suggestion: ConsolidationSuggestion,
) -> list[dict[str, Any]]:
    """Collapse the tickets named by ``suggestion`` into a single entry.

    The first ticket in the suggestion is used as the canonical entry; its
    description is replaced with the merged summary and its ``ticket`` field
    becomes a comma-separated list of refs so downstream renderers show the
    combined bullet. Tickets not in the suggestion are preserved in order.
    """
    keys_to_merge = set(suggestion.tickets)
    if not keys_to_merge:
        return list(extracted)

    result: list[dict[str, Any]] = []
    merged_inserted = False
    for e in extracted:
        if e.get("ticket") in keys_to_merge:
            if not merged_inserted:
                canonical = dict(e)
                canonical["description"] = suggestion.merged_summary
                canonical["ticket"] = ", ".join(suggestion.tickets)
                canonical["_consolidated_refs"] = list(suggestion.tickets)
                result.append(canonical)
                merged_inserted = True
            continue
        result.append(e)
    return result
