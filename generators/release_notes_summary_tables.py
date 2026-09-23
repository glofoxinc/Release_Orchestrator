"""Tabular Key Highlights summary: category counts and report inventory by scope."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from generators.release_notes_quality import canonical_client_name, improve_extracted
from generators.release_notes_report_tables import (
    ReportTableRow,
    build_analyze_report_rows,
    build_custom_client_report_tables,
    classify_release_category,
    parse_analyze_report_rows,
    parse_custom_client_report_tables,
)
from generators.release_notes_template_defaults import (
    CATEGORY_SUMMARY_HEADERS,
    RELEASE_CATEGORIES,
)

CLIENT_SUMMARY_HEADERS = ("Client", "Tickets", "Dashboards", "Paginated reports")


@dataclass
class ScopeStats:
    tickets: int = 0
    dashboards: int = 0
    paginated: int = 0
    reports: list[ReportTableRow] = field(default_factory=list)


@dataclass
class HighlightSummary:
    total_tickets: int = 0
    analyze: ScopeStats = field(default_factory=ScopeStats)
    custom: ScopeStats = field(default_factory=ScopeStats)
    custom_by_client: dict[str, ScopeStats] = field(default_factory=dict)
    all_reports: list[tuple[str, ReportTableRow]] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class SummaryTable:
    title: str
    headers: tuple[str, ...]
    rows: list[list[str]]


def _asset_counts(rows: list[ReportTableRow]) -> tuple[int, int]:
    dashboards = sum(1 for row in rows if row.asset_type == "Dashboard")
    paginated = sum(1 for row in rows if row.asset_type == "Paginated report")
    return dashboards, paginated


def _ticket_count(entries: list[dict[str, Any]]) -> int:
    keys = {str(entry.get("ticket") or "").strip().upper() for entry in entries}
    keys.discard("")
    return len(keys)


def _entry_text(entry: dict[str, Any]) -> str:
    return " ".join(
        str(entry.get(key) or "")
        for key in ("report", "description", "summary")
        if entry.get(key)
    )


def build_category_counts(extracted: list[dict[str, Any]]) -> dict[str, int]:
    """Count distinct tickets per release category."""
    counts = {category: 0 for category in RELEASE_CATEGORIES}
    seen: set[str] = set()
    for entry in improve_extracted(extracted):
        ticket = str(entry.get("ticket") or "").strip().upper()
        if not ticket or ticket in seen:
            continue
        seen.add(ticket)
        category = classify_release_category(_entry_text(entry))
        counts[category] = counts.get(category, 0) + 1
    return counts


def _client_ticket_count(custom_entries: list[dict[str, Any]], client: str) -> int:
    needle = client.strip().lower()
    keys = {
        str(entry.get("ticket") or "").strip().upper()
        for entry in custom_entries
        if canonical_client_name(entry.get("client") or "").lower() == needle
        or str(entry.get("client") or "").strip().lower() == needle
    }
    keys.discard("")
    return len(keys)


def build_highlight_summary(extracted: list[dict[str, Any]]) -> HighlightSummary:
    cleaned = improve_extracted(extracted)
    analyze_entries = [entry for entry in cleaned if entry.get("type") == "Analyze"]
    custom_entries = [entry for entry in cleaned if entry.get("type") == "Custom"]

    analyze_rows = build_analyze_report_rows(cleaned)
    custom_tables = build_custom_client_report_tables(cleaned)

    analyze_stats = ScopeStats(
        tickets=_ticket_count(analyze_entries),
        reports=analyze_rows,
    )
    analyze_stats.dashboards, analyze_stats.paginated = _asset_counts(analyze_rows)

    all_custom_rows = [row for rows in custom_tables.values() for row in rows]
    custom_stats = ScopeStats(
        tickets=_ticket_count(custom_entries),
        reports=all_custom_rows,
    )
    custom_stats.dashboards, custom_stats.paginated = _asset_counts(all_custom_rows)

    custom_by_client: dict[str, ScopeStats] = {}
    for client, rows in custom_tables.items():
        stats = ScopeStats(
            tickets=_client_ticket_count(custom_entries, client),
            reports=rows,
        )
        stats.dashboards, stats.paginated = _asset_counts(rows)
        custom_by_client[client] = stats

    all_reports: list[tuple[str, ReportTableRow]] = []
    for row in analyze_rows:
        all_reports.append(("Analyze (Standard)", row))
    for client, rows in custom_tables.items():
        for row in rows:
            all_reports.append((client, row))

    return HighlightSummary(
        total_tickets=_ticket_count(cleaned),
        analyze=analyze_stats,
        custom=custom_stats,
        custom_by_client=custom_by_client,
        all_reports=all_reports,
        category_counts=build_category_counts(cleaned),
    )


def build_highlight_summary_from_report_data(
    *,
    analyze_rows: list[list[str]],
    custom_tables: dict[str, list[list[str]]],
    ticket_keys: list[str] | None = None,
) -> HighlightSummary:
    """Build summary when only pipe-delimited report rows are available."""
    analyze = [ReportTableRow.from_row(row, default_client="Analyze") for row in analyze_rows]
    custom: dict[str, list[ReportTableRow]] = {
        client: [ReportTableRow.from_row(row, default_client=client) for row in rows]
        for client, rows in custom_tables.items()
    }
    all_custom_rows = [row for rows in custom.values() for row in rows]

    keys = {k.strip().upper() for k in (ticket_keys or []) if k and str(k).strip()}
    total = len(keys) if keys else 0

    analyze_stats = ScopeStats(tickets=0, reports=analyze)
    analyze_stats.dashboards, analyze_stats.paginated = _asset_counts(analyze)
    custom_stats = ScopeStats(tickets=0, reports=all_custom_rows)
    custom_stats.dashboards, custom_stats.paginated = _asset_counts(all_custom_rows)

    custom_by_client: dict[str, ScopeStats] = {}
    for client, rows in custom.items():
        stats = ScopeStats(tickets=0, reports=rows)
        stats.dashboards, stats.paginated = _asset_counts(rows)
        custom_by_client[client] = stats

    if not total:
        total = analyze_stats.dashboards + analyze_stats.paginated
        for rows in custom.values():
            total += len(rows)

    if keys:
        analyze_keys = {
            part.strip().upper()
            for row in analyze
            for part in (row.tickets or "").split(",")
            if part.strip()
        }
        analyze_stats.tickets = len(analyze_keys & keys) or sum(
            1 for key in keys if key.startswith("AN-")
        )
        custom_stats.tickets = total - analyze_stats.tickets if total else 0

    all_reports: list[tuple[str, ReportTableRow]] = []
    for row in analyze:
        all_reports.append(("Analyze (Standard)", row))
    for client, rows in custom.items():
        for row in rows:
            all_reports.append((client, row))

    category_counts = {category: 0 for category in RELEASE_CATEGORIES}
    for row in analyze + all_custom_rows:
        category = classify_release_category(f"{row.name} {row.change_type}")
        category_counts[category] = category_counts.get(category, 0) + 1

    return HighlightSummary(
        total_tickets=total,
        analyze=analyze_stats,
        custom=custom_stats,
        custom_by_client=custom_by_client,
        all_reports=all_reports,
        category_counts=category_counts,
    )


def highlight_summary_tables(summary: HighlightSummary) -> list[SummaryTable]:
    """Convert summary stats into ordered DOCX/UI tables."""
    if summary.total_tickets <= 0 and not summary.all_reports:
        return []

    counts = summary.category_counts or {category: 0 for category in RELEASE_CATEGORIES}
    rows = [[category, str(counts.get(category, 0))] for category in RELEASE_CATEGORIES]
    total = sum(counts.get(category, 0) for category in RELEASE_CATEGORIES)
    rows.append(["Total", str(total)])
    if total <= 0 and not summary.all_reports:
        return []

    return [
        SummaryTable(
            title="",
            headers=CATEGORY_SUMMARY_HEADERS,
            rows=rows,
        )
    ]


def build_highlight_summary_tables(extracted: list[dict[str, Any]]) -> list[SummaryTable]:
    if not extracted:
        return []
    return highlight_summary_tables(build_highlight_summary(extracted))


def resolve_highlight_summary_tables(data: dict[str, Any]) -> list[SummaryTable]:
    extracted = data.get("extracted") or []
    if extracted:
        return build_highlight_summary_tables(extracted)

    analyze_rows = parse_analyze_report_rows(data.get("analyze_report_rows", ""))
    custom_tables = parse_custom_client_report_tables(data.get("custom_report_tables", ""))
    if not analyze_rows and not custom_tables:
        return []

    ticket_keys: list[str] = []
    for line in (data.get("change_rows") or "").splitlines():
        if "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if parts and parts[0]:
            ticket_keys.append(parts[0])
        elif len(parts) > 1 and parts[1]:
            ticket_keys.append(parts[1])

    summary = build_highlight_summary_from_report_data(
        analyze_rows=analyze_rows,
        custom_tables=custom_tables,
        ticket_keys=ticket_keys,
    )
    return highlight_summary_tables(summary)
