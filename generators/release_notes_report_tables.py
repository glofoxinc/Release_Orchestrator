"""Dashboard / paginated report inventory tables for Release Notes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from consolidation import consolidate_dashboards
from generators.release_notes_quality import (
    build_custom_clients_list,
    clean_release_text,
    improve_extracted,
)

REPORT_TABLE_HEADERS = (
    "Client",
    "Dashboard / Report",
    "Ticket#",
    "Owner",
    "Type",
    "Label",
)
REPORT_TABLE_COLUMN_COUNT = len(REPORT_TABLE_HEADERS)

_LOOKER_CHANGE = re.compile(
    r"\blooker\b|looker[\s-]?exit|migrat\w*\s+from\s+looker|looker\s+transformation",
    re.IGNORECASE,
)
_NEW_CHANGE = re.compile(
    r"\bnew\b|\bcreated\b|\bcreation\b|\bintroduc\w+\b|\badd(?:ed|ing)?\s+(?:a\s+)?new\b",
    re.IGNORECASE,
)
_PAGINATED = re.compile(r"\bpaginated\b", re.IGNORECASE)
_DASHBOARD = re.compile(r"\bdashboard\b", re.IGNORECASE)

from generators.release_notes_template_defaults import GLOFOX_ANALYZE_CLIENT

_OPTIMIZATION = re.compile(
    r"\boptimiz\w*\b|\bperformance\b|\bblank page\b|\befficien\w*\b|\bspeed\b|\bload time\b",
    re.IGNORECASE,
)
_CUSTOMIZATION = re.compile(
    r"\bcustomiz\w*\b|\benhancement\b|\bfix\b|\bupdate\b|\bcorrect\b|\bbug\b",
    re.IGNORECASE,
)
_CHANGE_RANK = {"Looker-exit": 3, "New": 2, "Existing": 1}


@dataclass(frozen=True)
class ReportTableRow:
    client: str
    name: str
    tickets: str
    owner: str
    asset_type: str
    change_type: str

    def to_row(self) -> list[str]:
        return [
            self.client,
            self.name,
            self.tickets,
            self.owner,
            self.asset_type,
            self.change_type,
        ]

    def to_detail_row(self) -> list[str]:
        return [self.name, self.tickets, self.owner, self.asset_type, self.change_type]

    @classmethod
    def from_row(cls, cells: list[str], *, default_client: str = "") -> ReportTableRow:
        normalized = normalize_report_row_cells(cells, default_client=default_client)
        return cls(
            client=clean_release_text(normalized[0]) or default_client,
            name=clean_release_text(normalized[1]),
            tickets=clean_release_text(normalized[2]),
            owner=clean_release_text(normalized[3]),
            asset_type=clean_release_text(normalized[4]) or "Dashboard",
            change_type=clean_release_text(normalized[5]) or "Existing",
        )


def normalize_report_row_cells(
    cells: list[str],
    *,
    default_client: str = "",
) -> list[str]:
    """Normalize legacy 3-column and new 6-column pipe rows."""
    values = [str(cell or "").strip() for cell in cells]
    if len(values) == 3 and values[0] and values[1] in {
        "Dashboard",
        "Paginated report",
    }:
        # Legacy: Report|Asset type|Change
        return [default_client, values[0], "", "", values[1], values[2]]
    if len(values) == 3 and values[0] and values[2] in {"New", "Existing", "Looker-exit"}:
        return [default_client, values[0], "", "", values[1], values[2]]
    while len(values) < REPORT_TABLE_COLUMN_COUNT:
        values.append("")
    if not values[0]:
        values[0] = default_client
    return values[:REPORT_TABLE_COLUMN_COUNT]


def _entry_text(entry: dict[str, Any]) -> str:
    return " ".join(
        str(entry.get(key) or "")
        for key in ("report", "description", "summary")
        if entry.get(key)
    )


def classify_asset_type(text: str) -> str:
    lowered = (text or "").lower()
    if _PAGINATED.search(lowered):
        return "Paginated report"
    if _DASHBOARD.search(lowered):
        return "Dashboard"
    return "Dashboard"


def classify_change_type(text: str) -> str:
    lowered = (text or "").lower()
    if _LOOKER_CHANGE.search(lowered):
        return "Looker-exit"
    if _NEW_CHANGE.search(lowered):
        return "New"
    return "Existing"


def classify_release_category(text: str) -> str:
    """Map ticket text to release-summary category counts."""
    change = classify_change_type(text)
    if change == "Looker-exit":
        return "Looker Exits"
    if change == "New":
        return "New Reports"
    if _OPTIMIZATION.search(text or ""):
        return "Optimizations"
    if change == "Existing" and _CUSTOMIZATION.search(text or ""):
        return "Customizations"
    if change == "Existing":
        return "Customizations"
    return "Customizations"


def _merge_change_types(values: list[str]) -> str:
    if not values:
        return "Existing"
    return max(values, key=lambda value: _CHANGE_RANK.get(value, 0))


def _owners_from_entries(entries: list[dict[str, Any]]) -> str:
    owners: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        owner = clean_release_text(entry.get("assignee") or "")
        if not owner:
            continue
        key = owner.lower()
        if key in seen:
            continue
        seen.add(key)
        owners.append(owner)
    return ", ".join(owners)


def _report_name_for_group(item: dict[str, Any], *, client: str | None = None) -> str:
    entries = item.get("entries") or []
    sample = entries[0] if entries else {}
    report = clean_release_text(sample.get("report") or "")
    label = clean_release_text(item.get("label") or "")
    if client:
        prefix = f"{client} - "
        if label.startswith(prefix):
            report = clean_release_text(label[len(prefix) :]) or report
    if not report and label:
        if client and label.lower().startswith(client.lower()):
            rest = label[len(client) :].lstrip(" -–—")
            report = clean_release_text(rest) or label
        else:
            report = label
    summary = clean_release_text(item.get("summary") or "")
    if not report and summary:
        report = clean_release_text(summary.split(",")[0])
    return report or label or "Report"


def _rows_from_consolidated(
    items: list[dict[str, Any]],
    *,
    client: str,
) -> list[ReportTableRow]:
    rows: list[ReportTableRow] = []
    seen: set[str] = set()
    for item in items:
        entries = item.get("entries") or []
        combined = " ".join(_entry_text(entry) for entry in entries)
        combined += " " + clean_release_text(item.get("summary") or "")
        name = _report_name_for_group(item, client=client if client != "Analyze" else None)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        tickets = ", ".join(item.get("tickets") or [])
        rows.append(
            ReportTableRow(
                client=client,
                name=name,
                tickets=tickets,
                owner=_owners_from_entries(entries),
                asset_type=classify_asset_type(combined),
                change_type=_merge_change_types(
                    [classify_change_type(_entry_text(entry)) for entry in entries]
                    or [classify_change_type(combined)]
                ),
            )
        )
    return rows


def _change_summary_for_group(item: dict[str, Any]) -> str:
    summary = clean_release_text(item.get("summary") or "")
    if summary:
        return summary
    entries = item.get("entries") or []
    parts: list[str] = []
    for entry in entries:
        report = clean_release_text(entry.get("report") or "")
        description = clean_release_text(entry.get("description") or "")
        if description and description != report:
            parts.append(description)
        elif report:
            parts.append(report)
    return ", ".join(dict.fromkeys(parts))


def build_delivered_reports_rows(extracted: list[dict[str, Any]]) -> list[list[str]]:
    """Single combined Client | Report | Change table for all scopes."""
    cleaned = improve_extracted(extracted)
    rows: list[list[str]] = []

    analyze_entries = [entry for entry in cleaned if entry.get("type") == "Analyze"]
    if analyze_entries:
        for item in consolidate_dashboards(analyze_entries):
            name = _report_name_for_group(item)
            if not name:
                continue
            rows.append([
                GLOFOX_ANALYZE_CLIENT,
                name,
                _change_summary_for_group(item),
            ])

    custom_entries = [entry for entry in cleaned if entry.get("type") == "Custom"]
    for client in build_custom_clients_list(custom_entries):
        client_entries = [
            entry
            for entry in custom_entries
            if clean_release_text(entry.get("client") or "").lower() == client.lower()
        ]
        for item in consolidate_dashboards(client_entries):
            name = _report_name_for_group(item, client=client)
            if not name:
                continue
            rows.append([
                client,
                name,
                _change_summary_for_group(item),
            ])
    return rows


def build_analyze_report_rows(extracted: list[dict[str, Any]]) -> list[ReportTableRow]:
    cleaned = improve_extracted(extracted)
    analyze_entries = [entry for entry in cleaned if entry.get("type") == "Analyze"]
    if not analyze_entries:
        return []
    consolidated = consolidate_dashboards(analyze_entries)
    return _rows_from_consolidated(consolidated, client="Analyze")


def build_custom_client_report_tables(
    extracted: list[dict[str, Any]],
) -> dict[str, list[ReportTableRow]]:
    cleaned = improve_extracted(extracted)
    custom_entries = [entry for entry in cleaned if entry.get("type") == "Custom"]
    clients = build_custom_clients_list(custom_entries)
    tables: dict[str, list[ReportTableRow]] = {}
    for client in clients:
        client_entries = [
            entry
            for entry in custom_entries
            if clean_release_text(entry.get("client") or "").lower() == client.lower()
        ]
        if not client_entries:
            continue
        consolidated = consolidate_dashboards(client_entries)
        rows = _rows_from_consolidated(consolidated, client=client)
        if rows:
            tables[client] = rows
    return tables


def format_analyze_report_rows(rows: list[ReportTableRow] | list[list[str]]) -> str:
    lines: list[str] = []
    for row in rows:
        if isinstance(row, ReportTableRow):
            cells = row.to_row()
        else:
            cells = normalize_report_row_cells(row, default_client="Analyze")
        if not any(cells[1:]):
            continue
        lines.append("|".join(cells))
    return "\n".join(lines)


def parse_analyze_report_rows(raw: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "|" in stripped:
            cells = [part.strip() for part in stripped.split("|", REPORT_TABLE_COLUMN_COUNT - 1)]
        else:
            cells = [stripped, "Dashboard", "Existing"]
        rows.append(normalize_report_row_cells(cells, default_client="Analyze"))
    return rows


def format_custom_client_report_tables(tables: dict[str, list[ReportTableRow]]) -> str:
    lines: list[str] = []
    for client in sorted(tables, key=str.lower):
        lines.append(f"[{client}]")
        for row in tables[client]:
            lines.append("|".join(row.to_row()))
        lines.append("")
    return "\n".join(lines).strip()


def parse_custom_client_report_tables(raw: str) -> dict[str, list[list[str]]]:
    tables: dict[str, list[list[str]]] = {}
    current: str | None = None
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip()
            tables.setdefault(current, [])
            continue
        if current is None:
            continue
        if "|" in stripped:
            cells = [part.strip() for part in stripped.split("|", REPORT_TABLE_COLUMN_COUNT - 1)]
        else:
            cells = [stripped, "Dashboard", "Existing"]
        tables[current].append(
            normalize_report_row_cells(cells, default_client=current),
        )
    return tables


def build_analyze_report_rows_from_legacy_dashboard_lines(lines: list[str]) -> list[ReportTableRow]:
    rows: list[ReportTableRow] = []
    for line in lines:
        cleaned = clean_release_text(line)
        if not cleaned:
            continue
        if cleaned.lower().startswith("analyze - "):
            name = clean_release_text(cleaned[9:])
        elif " - " in cleaned:
            _, name = cleaned.split(" - ", 1)
            name = clean_release_text(name)
        else:
            name = cleaned
        if not name:
            continue
        rows.append(
            ReportTableRow(
                client="Analyze",
                name=name,
                tickets="",
                owner="",
                asset_type=classify_asset_type(cleaned),
                change_type=classify_change_type(cleaned),
            )
        )
    return rows


def build_custom_tables_from_legacy_dashboard_lines(lines: list[str]) -> dict[str, list[ReportTableRow]]:
    tables: dict[str, list[ReportTableRow]] = {}
    for line in lines:
        cleaned = clean_release_text(line)
        if not cleaned or cleaned.lower().startswith("analyze - "):
            continue
        if " - " not in cleaned:
            continue
        client, name = cleaned.split(" - ", 1)
        client = clean_release_text(client)
        name = clean_release_text(name)
        if not client or not name:
            continue
        tables.setdefault(client, []).append(
            ReportTableRow(
                client=client,
                name=name,
                tickets="",
                owner="",
                asset_type=classify_asset_type(cleaned),
                change_type=classify_change_type(cleaned),
            )
        )
    return tables
