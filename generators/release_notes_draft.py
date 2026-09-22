"""Shared Release Notes draft builder — UI and MCP parity."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import config
from generators.release_notes_deployment import build_deployment_rows
from generators.release_notes_generator import format_change_row
from generators.release_notes_insights import build_release_summary_paragraph
from generators.release_notes_quality import (
    build_custom_clients_list,
    canonical_client_name,
    improve_extracted,
    prepare_change_table_entries,
)
from generators.release_notes_report_tables import (
    build_analyze_report_rows,
    build_custom_client_report_tables,
    build_delivered_reports_rows,
    format_analyze_report_rows,
    format_custom_client_report_tables,
)
from generators.release_notes_template_defaults import (
    build_testing_evidence_editor_text,
)
from generators.release_notes_test_by import (
    assign_change_table_testers,
    assign_change_table_testing_statuses,
)

_FIX_VERSION_RE = re.compile(r"(\d{4})\.(\d)\.(\d{2})\.(\d{2})")
_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def parse_fix_version_name(name: str) -> tuple[str, str] | None:
    match = _FIX_VERSION_RE.search((name or "").strip())
    if not match:
        return None
    year, quarter, month_str, day_str = match.groups()
    month = int(month_str)
    day = int(day_str)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"v{year}.{quarter}.{month_str}.{day_str}", f"{day:02d}-{_MONTH_NAMES[month]}-{year}"


def version_label_from_deploy_date(deploy_on: date | None = None) -> tuple[str, str]:
    """Build vYYYY.Q.MM.DD + date label from a deploy date (defaults to today)."""
    d = deploy_on or date.today()
    quarter = (d.month - 1) // 3 + 1
    version = f"v{d.year}.{quarter}.{d.month:02d}.{d.day:02d}"
    date_label = f"{d.day:02d}-{_MONTH_NAMES[d.month]}-{d.year}"
    return version, date_label


def resolve_release_version_metadata(
    *,
    explicit: str = "",
    fix_version_names: list[str] | None = None,
    deploy_on: date | None = None,
) -> tuple[str, str]:
    """Resolve release version + date label for RN, SHIPIT, and Slack."""
    raw = (explicit or "").strip()
    if raw:
        parsed = parse_fix_version_name(raw.lstrip("vV"))
        if parsed:
            return parsed
        label = raw if raw.lower().startswith("v") else f"v{raw.lstrip('vV')}"
        return label, ""

    for name in fix_version_names or []:
        parsed = parse_fix_version_name(str(name or ""))
        if parsed:
            return parsed
        if name:
            label = str(name) if str(name).lower().startswith("v") else f"v{name}"
            return label, ""

    return version_label_from_deploy_date(deploy_on)


def build_change_rows_text(extracted: list[dict], *, release_seed: str = "") -> str:
    test_by = assign_change_table_testers(extracted, release_seed=release_seed)
    statuses = assign_change_table_testing_statuses(extracted)
    rows = prepare_change_table_entries(
        extracted,
        test_by_names=test_by,
        testing_statuses=statuses,
    )
    return "\n".join(
        format_change_row(
            sno=entry["sno"],
            ticket=entry["ticket"],
            parent_epic=entry["parent_epic"],
            link=entry["link"],
            type_=entry["type"],
            client=entry["client"],
            report=entry["report"],
            description=entry["description"],
            assignee=entry.get("assignee") or "",
            test_by=entry["test_by"],
            testing_status=entry.get("testing_status") or "",
        )
        for entry in rows
    )


def client_owners_from_extracted(extracted: list[dict]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for entry in improve_extracted(extracted):
        if entry.get("type") == "Analyze":
            label = "Analyze"
        else:
            label = canonical_client_name(entry.get("client") or "") or entry.get("client") or "Custom"
        if label not in owners:
            owners[label] = str(entry.get("assignee") or "")
    return owners


def build_release_notes_draft_from_extracted(
    extracted: list[dict],
    version_name: str,
    *,
    release_seed: str = "",
    deployment_rows: str = "",
    client_owners: dict[str, str] | None = None,
    deploy_info: dict[str, Any] | None = None,
    include_fix_version_metadata: bool = True,
) -> dict[str, Any]:
    """Build the full generator payload matching Release Notes Step 3 defaults."""
    if include_fix_version_metadata and version_name:
        parsed = parse_fix_version_name(version_name)
        version_label, date_label = parsed if parsed else (f"v{version_name}", "")
    else:
        version_label, date_label = "", ""
    seed = release_seed or version_label or "release"
    has_analyze = any(entry.get("type") == "Analyze" for entry in extracted)
    custom_clients = build_custom_clients_list(extracted)
    owners = client_owners if client_owners is not None else client_owners_from_extracted(extracted)

    if not deployment_rows and owners:
        deployment_rows = build_deployment_rows(owners, deploy_info or {})

    return {
        "version": version_label,
        "release_date": date_label,
        "include_fix_version_metadata": include_fix_version_metadata,
        **config.RELEASE_META,
        "extracted": extracted,
        "summary_p1": build_release_summary_paragraph(extracted),
        "summary_p2": "",
        "custom_clients": ", ".join(custom_clients),
        "change_rows": build_change_rows_text(extracted, release_seed=seed),
        "deployment_rows": deployment_rows,
        "analyze_report_rows": format_analyze_report_rows(build_analyze_report_rows(extracted)),
        "custom_report_tables": format_custom_client_report_tables(
            build_custom_client_report_tables(extracted),
        ),
        "delivered_report_rows": "\n".join(
            "|".join(row) for row in build_delivered_reports_rows(extracted)
        ),
        "sanity_checklist": "",
        "screenshot_names": build_testing_evidence_editor_text(
            extracted,
            deployment_rows=deployment_rows,
        ),
        "testing_evidence_tickets": build_testing_evidence_editor_text(
            extracted,
            deployment_rows=deployment_rows,
        ),
        "excluded_tickets": "",
        "notes": "",
        "include_analyze_section": has_analyze,
    }


RELEASE_NOTES_DRAFT_FIELDS: dict[str, str] = {
    "version": "Release version label (e.g. v2026.3.08.12)",
    "release_date": "Release date (e.g. 12-August-2026)",
    "summary_p1": "Release Summary opening paragraph",
    "analyze_report_rows": "Pipe rows: Client|Report|Ticket#|Owner|Type|Label",
    "custom_report_tables": "[Client] sections with pipe rows",
    "change_rows": "Ticket Details pipe rows (5 columns: Ticket|Ticket Link|Assignee|Test|Status)",
    "delivered_report_rows": "Client|Dashboard / Report|Change pipe rows",
    "deployment_rows": "Client|Owner|Status|Deployment ID & Time",
    "screenshot_names": "Ticket keys for Testing Evidence section (legacy key name)",
    "testing_evidence_tickets": "Ticket keys for Testing Evidence section",
    "excluded_tickets": "Excluded tickets table (pipe rows)",
    "notes": "Optional Notes section",
}


def release_notes_draft_schema() -> dict[str, Any]:
    return {
        "fields": RELEASE_NOTES_DRAFT_FIELDS,
        "note": "Patch these keys via release_notes_draft in the MCP wizard.",
    }
