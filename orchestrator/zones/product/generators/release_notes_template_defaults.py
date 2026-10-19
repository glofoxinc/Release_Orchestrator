"""Defaults extracted from Release Notes 2026.3.07.15.docx (org reference template)."""

from __future__ import annotations

# Page layout (must be defined before any derived width constants).
PAGE_MARGIN_INCHES = 1.0
PAGE_CONTENT_WIDTH_TWIPS = int((8.5 - (2 * PAGE_MARGIN_INCHES)) * 1440)

# Metadata defaults — update workspace.yaml release_notes section to match your team.
REFERENCE_META = {
    "dev_team": "Customize BI Team",
    "release_owner": "Lakshmi Narasimha",
    "senior_mgr": "Sushma Bhamidipati",
    "director": "Trent Vanest",
    "svp": "Rahul Das",
    "environment": "Production",
}

# User-facing metadata label (session/config key remains ``svp`` for compatibility).
METADATA_GM_LABEL = "GM"

# Tab/colon suffix after each metadata label (matches reference DOCX run layout).
META_LABEL_SUFFIXES: dict[str, str] = {
    "Release Date": "\t\t              : \t",
    "Development Team": "\t\t: \t",
    "Release Owner": "\t\t: \t",
    "Senior Manager": "\t\t: \t",
    "Director": "\t\t\t: \t",
    "GM": "\t\t\t\t: \t",
    "SVP": "\t\t\t\t: \t",
    "Environment": "\t\t\t: \t",
}

GLOFOX_ANALYZE_CLIENT = "Glofox Analyze"

CHANGE_HEADERS = [
    "Ticket",
    "Ticket Link",
    "Assignee",
    "Test",
    "Status",
]

CHANGE_COLUMN_COUNT = len(CHANGE_HEADERS)

# Canonical pipe column order for ticket-detail rows (5 fields).
CHANGE_ROW_FIELDS = (
    "ticket",
    "link",
    "assignee",
    "test_by",
    "testing_status",
)

# Legacy 10-column change table (import normalization only).
LEGACY_CHANGE_ROW_FIELDS = (
    "sno",
    "ticket",
    "parent_ticket",
    "parent_epic",
    "link",
    "report",
    "description",
    "test_by",
    "comments",
    "testing_status",
)

CATEGORY_SUMMARY_HEADERS = ("Category", "Count")
RELEASE_CATEGORIES = (
    "New Reports",
    "Customizations",
    "Looker Exits",
    "Optimizations",
)

DELIVERED_REPORTS_HEADERS = (
    "Client",
    "Dashboard / Report",
    "Change",
)

DELIVERED_REPORTS_COLUMN_WIDTHS = (2400, 3360, 3840)
DELIVERED_REPORTS_TABLE_WIDTH = sum(DELIVERED_REPORTS_COLUMN_WIDTHS)

DEPLOYMENT_HEADERS = [
    "Client",
    "Deployment Owner",
    "Status",
    "Deployment ID & Time",
]

# Column widths in twips (dxa) for the 5-column Ticket Details table.
CHANGE_COLUMN_WIDTHS = (1700, 3360, 1800, 2400, 2320)
DEPLOYMENT_COLUMN_WIDTHS = (1900, 2240, 1500, 2620)
EXCLUDED_COLUMN_WIDTHS = (640, 944, 880, 1325, 772, 920, 1122, 2727)
CHANGE_TABLE_WIDTH = sum(CHANGE_COLUMN_WIDTHS)
DEPLOYMENT_TABLE_WIDTH = sum(DEPLOYMENT_COLUMN_WIDTHS)
EXCLUDED_TABLE_WIDTH = sum(EXCLUDED_COLUMN_WIDTHS)

REPORT_TABLE_HEADERS = [
    "Client",
    "Dashboard / Report",
    "Ticket#",
    "Owner",
    "Type",
    "Label",
]

CLIENT_DETAIL_REPORT_HEADERS = [
    "Dashboard / Report",
    "Ticket#",
    "Owner",
    "Type",
    "Label",
]

REPORT_TABLE_COLUMN_WIDTHS = (1200, 2400, 1200, 1560, 1500, 1500)
CLIENT_DETAIL_REPORT_COLUMN_WIDTHS = (2760, 1200, 1560, 1500, 1500)
REPORT_TABLE_WIDTH = sum(REPORT_TABLE_COLUMN_WIDTHS)
CLIENT_DETAIL_REPORT_TABLE_WIDTH = sum(CLIENT_DETAIL_REPORT_COLUMN_WIDTHS)

SUMMARY_TABLE_4COL_WIDTHS = (2340, 2340, 2340, 2310)
SUMMARY_TABLE_4COL_WIDTH = sum(SUMMARY_TABLE_4COL_WIDTHS)

EXCLUDED_HEADERS = [
    "S.No",
    "Ticket#",
    "Parent",
    "Link",
    "Type",
    "Client",
    "Report",
    "Reason",
]

EXCLUDED_ROW_FIELDS = (
    "sno",
    "ticket",
    "parent",
    "link",
    "type",
    "client",
    "report",
    "reason",
)

DEFAULT_DEPLOYMENT_STATUS = "Deployed"

# Deployment table visual tokens (Grid Table 4 Accent 1 / reference theme accent1).
DEPLOYMENT_HEADER_FILL = "156082"
DEPLOYMENT_HEADER_TEXT = "FFFFFF"
DEPLOYMENT_CELL_BORDER_COLOR = "45B0E1"
DEPLOYMENT_HEADER_BORDER_COLOR = "156082"
DEPLOYMENT_CELL_BORDER_SZ = "4"
DEPLOYMENT_TBL_LOOK_VAL = "06A0"
# 0 = same left edge as body text and other tables (avoids staggered indents).
DEPLOYMENT_TBL_IND_TWIPS = 0

# Change table extends past margins (reference tblInd=-922, tblW=11580).
CHANGE_TBL_IND_TWIPS = -922
CHANGE_TBL_LOOK_VAL = DEPLOYMENT_TBL_LOOK_VAL
# Merged cell widths from Release Notes 2026.3.07.15.docx (gridSpan sums).
CHANGE_PARENT_HEADER_MERGE_WIDTH = CHANGE_COLUMN_WIDTHS[2] + CHANGE_COLUMN_WIDTHS[3]
CHANGE_TICKET_PARENT_MERGE_WIDTH = CHANGE_COLUMN_WIDTHS[1] + CHANGE_COLUMN_WIDTHS[2]


def fit_column_widths(widths: tuple[int, ...], target_total: int) -> tuple[int, ...]:
    """Scale column widths proportionally to fit printable page width."""
    total = sum(widths)
    if total <= 0 or total == target_total:
        return widths
    scaled = [max(int(width * target_total / total), 300) for width in widths]
    delta = target_total - sum(scaled)
    scaled[-1] = max(scaled[-1] + delta, 300)
    return tuple(scaled)


# Optional fitted widths (reference uses exact CHANGE_COLUMN_WIDTHS / 11580 twips).
CHANGE_COLUMN_WIDTHS_FITTED = fit_column_widths(CHANGE_COLUMN_WIDTHS, PAGE_CONTENT_WIDTH_TWIPS)
CHANGE_TABLE_WIDTH_FITTED = sum(CHANGE_COLUMN_WIDTHS_FITTED)

DEFAULT_SANITY_CHECKLIST = (
    "Report loads successfully – Yes\n"
    "Paginated report works correctly after applying parameters – Yes\n"
    "Applied changes are reflected as expected – Yes\n"
    "Existing functionalities/changes are not impacted – Yes"
)

TESTING_EVIDENCE_HEADING = "Testing Evidence:"
TESTING_EVIDENCE_SUBHEADING = "Deployment & configuration screenshots"
TESTING_EVIDENCE_CLIENTS_HEADING = "Clients"
TESTING_EVIDENCE_TICKETS_LIST_HEADING = "Tickets list"
TESTING_EVIDENCE_CLIENT_PLACEHOLDER = (
    "Add deployment screenshot(s) and configuration screenshot(s) for this client."
)
TESTING_EVIDENCE_TICKET_PLACEHOLDER = "Add testing screenshot(s) for this ticket."
# Legacy alias — import sites may still reference the old name.
SCREENSHOTS_DEPLOYMENT_HEADING = TESTING_EVIDENCE_SUBHEADING


def _sorted_ticket_keys(extracted: list[dict]) -> list[str]:
    return sorted(
        {
            str(entry.get("ticket") or "").strip().upper()
            for entry in extracted
            if str(entry.get("ticket") or "").strip()
        }
    )


def build_testing_evidence_client_names(
    extracted: list[dict],
    deployment_rows: str | list[list[str]] = "",
) -> list[str]:
    """Distinct client names for Testing Evidence.

    Rules:
    - Only include clients backed by selected tickets.
    - Include ``Analyze (Standard)`` only when AN/Analyze tickets exist.
    """
    from generators.release_notes_quality import build_custom_clients_list

    cleaned_extracted = extracted or []
    custom_clients = set(build_custom_clients_list(cleaned_extracted))
    has_analyze_tickets = any(
        str(entry.get("project") or "").strip().upper() == "AN"
        or str(entry.get("type") or "").strip().lower() == "analyze"
        for entry in cleaned_extracted
    )

    clients: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        label = (name or "").strip()
        if not label:
            return
        key = label.lower()
        if key in seen:
            return
        seen.add(key)
        clients.append(label)

    analyze_aliases = {"analyze", "glofox analyze", "standard", "analyze (standard)"}

    def add_if_allowed(name: str) -> None:
        label = (name or "").strip()
        if not label:
            return
        lowered = label.lower()
        if lowered in analyze_aliases:
            if has_analyze_tickets:
                add("Analyze (Standard)")
            return
        if custom_clients:
            if label in custom_clients:
                add(label)
            return
        add(label)

    if isinstance(deployment_rows, str):
        for line in deployment_rows.splitlines():
            stripped = line.strip()
            if not stripped or "|" not in stripped:
                continue
            add_if_allowed(stripped.split("|", 1)[0].strip())
    else:
        for row in deployment_rows:
            if row:
                add_if_allowed(str(row[0] or ""))

    if has_analyze_tickets:
        add("Analyze (Standard)")
    for client in sorted(custom_clients, key=str.lower):
        add(client)

    normalized: list[str] = []
    for client in clients:
        if client.strip().lower() in analyze_aliases:
            normalized.append("Analyze (Standard)")
        else:
            normalized.append(client)
    deduped: list[str] = []
    seen = set()
    for client in normalized:
        key = client.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(client)
    return deduped


def build_testing_evidence_ticket_lines(extracted: list[dict]) -> str:
    """One ticket key per line for the Testing Evidence ticket list."""
    return "\n".join(_sorted_ticket_keys(extracted))


def build_testing_evidence_editor_text(
    extracted: list[dict],
    *,
    deployment_rows: str = "",
) -> str:
    """Default Testing Evidence editor text: clients with placeholders, then ticket list."""
    lines: list[str] = []
    for client in build_testing_evidence_client_names(extracted, deployment_rows):
        lines.append(client)
        lines.append(f"  {TESTING_EVIDENCE_CLIENT_PLACEHOLDER}")
        lines.append("")
    lines.append(TESTING_EVIDENCE_TICKETS_LIST_HEADING)
    for ticket in _sorted_ticket_keys(extracted):
        lines.append(ticket)
        lines.append(f"  {TESTING_EVIDENCE_TICKET_PLACEHOLDER}")
    return "\n".join(lines).strip()


def build_screenshot_ticket_lines(extracted: list[dict]) -> str:
    """Backward-compatible alias for :func:`build_testing_evidence_ticket_lines`."""
    return build_testing_evidence_ticket_lines(extracted)

EXCLUDED_TICKETS_PLACEHOLDER_COLS = 8
EXCLUDED_TICKETS_PLACEHOLDER_ROWS = 2

# Word built-in table styles from Release Notes 2026.3.07.15.docx.
GRID_TABLE_ACCENT_STYLE = "Grid Table 4 Accent 1"
EXCLUDED_TABLE_STYLE = "Table Grid"

LIST_STYLE = "List Paragraph"
CHANGE_HEADER_FILL = "000000"
CHANGE_HEADER_TEXT = "FFFFFF"
TITLE_COLOR = "0F4761"
VERSION_TEXT_COLOR = "000000"
SECTION_SHADING = "F7F7F7"

# Reference Heading 2/3 run sizes (w:sz half-points / 2).
HEADING2_SIZE_PT = 16
HEADING3_SIZE_PT = 14
CUSTOM_CLIENTS_HEADING = "Custom Clients"
CELL_BORDER_COLOR = "0D0D0D"
CELL_BORDER_SZ = "8"
EXCLUDED_HEADER_FILL = "000000"
EXCLUDED_HEADER_TEXT = "FFFFFF"
EXCLUDED_BODY_FILL = "C0C0C0"

# Reference theme accent1 — drives Grid Table 4 Accent 1 header/border tint in Word.
THEME_ACCENT1_COLOR = "156082"

# Paragraph spacing profiles (twips) from Release Notes 2026.3.07.15.docx.
SPACING_SHADED_SECTION = {"before": "240", "after": "0", "line": "360", "lineRule": "auto"}
SPACING_SHADED_HEADING3 = {"before": "240", "after": "0", "line": "269", "lineRule": "auto"}
SPACING_LIST_COMPACT = {"after": "0", "line": "278", "lineRule": "auto"}
SPACING_LIST_LINE_ONLY = {"line": "278", "lineRule": "auto"}
SPACING_DASHBOARD_LINE = {"after": "0", "line": "240", "lineRule": "auto"}
SPACING_DASHBOARD_EMPTY_GAP = {"after": "0", "line": "240", "lineRule": "auto"}
SPACING_PRE_DEPLOYMENT_GAP = {"line": "278", "lineRule": "auto"}
SPACING_CHANGE_DETAILS_HEADING = {"before": "240", "after": "120", "line": "278", "lineRule": "auto"}
SPACING_POST_DEPLOYMENT_TABLE_GAP = {"line": "278", "lineRule": "auto"}
SPACING_PRE_CHANGE_TABLE_GAP = {"line": "278", "lineRule": "auto"}
SPACING_POST_CHANGE_TABLE_GAP = {"line": "278", "lineRule": "auto"}
SPACING_TESTING_SUBHEADING = {"before": "180", "after": "60", "line": "278", "lineRule": "auto"}
SPACING_TESTING_CLIENT_BLOCK = {"before": "60", "after": "160", "line": "240", "lineRule": "auto"}
SPACING_TESTING_TICKET_BLOCK = {"before": "80", "after": "120", "line": "240", "lineRule": "auto"}
SPACING_POST_TESTING_GAP = {"before": "240", "after": "0", "line": "240", "lineRule": "auto"}
SPACING_EXCLUDED_HEADING = {"before": "120", "after": "80", "line": "278", "lineRule": "auto"}

# Reference change-table data row height (twips) from Release Notes 2026.3.07.15.docx.
CHANGE_DATA_ROW_HEIGHT_TWIPS = 286

SPACING_PROFILES = {
    "shaded_section": SPACING_SHADED_SECTION,
    "shaded_heading3": SPACING_SHADED_HEADING3,
    "list_compact": SPACING_LIST_COMPACT,
    "list_line_only": SPACING_LIST_LINE_ONLY,
    "dashboard_line": SPACING_DASHBOARD_LINE,
    "dashboard_empty_gap": SPACING_DASHBOARD_EMPTY_GAP,
    "pre_deployment_gap": SPACING_PRE_DEPLOYMENT_GAP,
    "change_details_heading": SPACING_CHANGE_DETAILS_HEADING,
    "post_deployment_table_gap": SPACING_POST_DEPLOYMENT_TABLE_GAP,
    "pre_change_table_gap": SPACING_PRE_CHANGE_TABLE_GAP,
    "post_change_table_gap": SPACING_POST_CHANGE_TABLE_GAP,
    "testing_subheading": SPACING_TESTING_SUBHEADING,
    "testing_client_block": SPACING_TESTING_CLIENT_BLOCK,
    "testing_ticket_block": SPACING_TESTING_TICKET_BLOCK,
    "post_testing_gap": SPACING_POST_TESTING_GAP,
    "excluded_heading": SPACING_EXCLUDED_HEADING,
}
