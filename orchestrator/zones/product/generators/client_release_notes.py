"""Client-facing Release Notes — PIC / custom clients only.

Short client copy (Sushma / customize-bi-glofox-product): one opening line,
no “issues delivered”, no repeated what-changed / impact / validation essay,
no assignee table. Fonts and navy/teal match internal Insights notes.
Analyze (AN) tickets are excluded.
"""

from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml.parser import OxmlElement
from docx.shared import Pt

from generators.release_notes_docx_styles import patch_docx_grid_table4_accent1_style
from generators.release_notes_generator import (
    BODY_SIZE,
    FONT_NAME,
    GRID_TABLE_ACCENT_STYLE,
    _add_deployment_cell_borders,
    _add_hyperlink_run,
    _apply_reference_margins,
    _apply_reference_table_style,
    _apply_table_column_widths,
    _configure_reference_document_theme,
    _format_section_paragraph,
    _prevent_table_row_splits,
    _reset_cell_paragraph,
    _set_cell_shading,
    _set_deployment_header_row_cnf,
    _set_paragraph_keep_with_next,
    _set_reference_tbl_look,
    _set_table_indent,
    _style_run,
    _write_deployment_header_cell,
)
from generators.release_notes_quality import (
    build_custom_clients_list,
    improve_extracted,
)
from generators.release_notes_template_defaults import (
    DEPLOYMENT_HEADER_FILL,
    DEPLOYMENT_HEADER_TEXT,
    LIST_STYLE,
    PAGE_CONTENT_WIDTH_TWIPS,
    TITLE_COLOR,
    fit_column_widths,
)

GENERATOR_BUILD_ID = "2026.10.18-client-notes-pic-v5"
TITLE_SIZE_PT = 28
CLIENT_BANNER_SIZE_PT = 20
GOLD = "C9A227"
CLIENT_OVERVIEW_HEADERS = ("Client", "Reports", "Tickets", "What you get")
TABLE_INDENT_TWIPS = 0
DEFAULT_JIRA_BASE = "https://abcfinancial.atlassian.net"

_MONTH = {
    "01": "January",
    "02": "February",
    "03": "March",
    "04": "April",
    "05": "May",
    "06": "June",
    "07": "July",
    "08": "August",
    "09": "September",
    "10": "October",
    "11": "November",
    "12": "December",
}
_REPORT_HINT = re.compile(
    r"\b(analysis|report|dashboard|paginated|partnership|utilization|members?)\b",
    re.IGNORECASE,
)
_DASH_SPLIT = re.compile(r"\s+[—–-]\s+")
_SKIP_DETAIL = re.compile(r"^(tasks?\s*-?|notes?\s*-?)$", re.IGNORECASE)
_REGION_ONLY = re.compile(
    r"^(australia|new zealand|united kingdom|\buk\b|usa|\bus\b|canada)\s*(update)?$",
    re.IGNORECASE,
)
_ADD_FILTER = re.compile(r"^add\s+(?P<body>.+?)\s+filters?$", re.IGNORECASE)
_ADD_REST = re.compile(r"^add\s+(?P<rest>.+)$", re.IGNORECASE)
_SMART_QUOTES = str.maketrans({
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
})


def _repair_pic_report_fields(entry: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(entry)
    report = str(repaired.get("report") or "").strip()
    desc = str(repaired.get("description") or "").strip()
    if report and desc and len(report.split()) <= 2 and _REPORT_HINT.search(desc):
        parts = _DASH_SPLIT.split(desc, maxsplit=1)
        title = parts[0].strip()
        tail = parts[1].strip() if len(parts) > 1 else ""
        if title and title.lower() != report.lower():
            repaired["report"] = title
            extra = " ".join(part for part in (report, tail) if part)
            repaired["description"] = extra or desc
    return repaired


def is_pic_custom_entry(entry: dict[str, Any]) -> bool:
    ticket = str(entry.get("ticket") or "").strip().upper()
    project = str(entry.get("project") or "").strip().upper()
    ticket_type = str(entry.get("type") or "").strip()
    if ticket.startswith("AN-") or project == "AN" or ticket_type == "Analyze":
        return False
    return ticket.startswith("PIC-") or project == "PIC" or ticket_type == "Custom"


def filter_pic_custom_extracted(extracted: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for entry in improve_extracted(extracted or []):
        if not is_pic_custom_entry(entry):
            continue
        copy = dict(entry)
        if not str(copy.get("type") or "").strip():
            copy["type"] = "Custom"
        kept.append(_repair_pic_report_fields(copy))
    return kept


def _version_display(data: dict[str, Any]) -> str:
    version = str(data.get("version") or "").strip()
    if version and not version.lower().startswith("v"):
        return f"v{version}"
    return version


def _version_plain(data: dict[str, Any]) -> str:
    return str(data.get("version") or "").lstrip("vV")


def _pretty_date(data: dict[str, Any]) -> str:
    raw = str(data.get("release_date") or "").strip()
    if re.match(r"^\d{1,2}-[A-Za-z]+-\d{4}$", raw):
        day, month, year = raw.split("-")
        return f"{int(day)} {month} {year}"
    match = re.search(r"(\d{4})\.(\d)\.(\d{2})\.(\d{2})", str(data.get("version") or ""))
    if match:
        year, _q, mm, dd = match.groups()
        return f"{int(dd)} {_MONTH.get(mm, mm)} {year}"
    return raw


def _client_name(entry: dict[str, Any]) -> str:
    return str(entry.get("client") or "").strip() or "Custom"


def _report_name(entry: dict[str, Any]) -> str:
    return str(entry.get("report") or "").strip() or "the report"


def _region(entry: dict[str, Any]) -> str:
    desc = str(entry.get("description") or "").strip()
    match = _REGION_ONLY.match(desc)
    if match:
        token = match.group(1)
        lowered = token.lower()
        if lowered in {"uk", "united kingdom"}:
            return "UK"
        if lowered in {"us", "usa"}:
            return "US"
        return token.title()
    return ""


def _strip_quotes(text: str) -> str:
    cleaned = text.translate(_SMART_QUOTES)
    return cleaned.replace("'", "").replace('"', "").strip()


def _polish_control(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().rstrip(".")
    cleaned = re.sub(r"\bdate date\b", "date", cleaned, flags=re.IGNORECASE)
    return cleaned


def _as_user_control(raw: str) -> str:
    """Turn a Jira task line into something a client would say."""
    text = _polish_control(raw.translate(_SMART_QUOTES))
    added_filter = _ADD_FILTER.match(text)
    if added_filter:
        name = _strip_quotes(added_filter.group("body"))
        name = re.sub(r"\s+date$", "", name, flags=re.IGNORECASE).strip()
        if re.search(r"commenced", name, re.IGNORECASE):
            return "Choose a commenced date range"
        if re.search(r"\bdate\b", name, re.IGNORECASE):
            return f"Choose a {name} range"
        return f"Filter by {name}"
    added = _ADD_REST.match(text)
    if added:
        rest = _strip_quotes(added.group("rest")).rstrip(".")
        if re.search(r"from date|to date|commenced", rest, re.IGNORECASE):
            return "Set a membership commenced date range"
        if "%" in rest or re.search(r"concentration", rest, re.IGNORECASE):
            percents = re.findall(r"\d+%", rest)
            if percents:
                joined = ", ".join(percents[:-1] + [f"or {percents[-1]}"]) if len(percents) > 1 else percents[0]
                if len(percents) == 2:
                    joined = f"{percents[0]} or {percents[1]}"
                return f"Choose visit concentration ({joined})"
            return rest[0].upper() + rest[1:] if rest else rest
        return f"Use {rest[0].lower() + rest[1:]}" if rest else text
    return _polish_control(_strip_quotes(text) or text)


def _details_text(entry: dict[str, Any]) -> str:
    for key in ("details_plain", "jira_description", "acceptance", "comments"):
        value = str(entry.get(key) or "").strip()
        if value:
            return value
    return ""


def _scope_bullets(entry: dict[str, Any]) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for raw in _details_text(entry).splitlines():
        cleaned = raw.strip().lstrip("*-•").strip()
        if not cleaned or _SKIP_DETAIL.match(cleaned):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        bullets.append(_as_user_control(cleaned))
    if bullets:
        return bullets
    report = _report_name(entry)
    desc = str(entry.get("description") or "").strip()
    if desc and not _region(entry) and desc.lower() != report.lower():
        bullets.append(_as_user_control(desc))
    else:
        bullets.append(f"Use the updated {report}")
    return bullets


def _group_by_client(extracted: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in extracted:
        grouped[_client_name(entry)].append(entry)
    ordered: dict[str, list[dict[str, Any]]] = {}
    for client in build_custom_clients_list(extracted):
        if client in grouped:
            ordered[client] = grouped[client]
    for client, rows in grouped.items():
        if client not in ordered:
            ordered[client] = rows
    return ordered


def _control_list(entry: dict[str, Any]) -> str:
    controls = _scope_bullets(entry)
    if not controls:
        return _report_name(entry)
    if len(controls) == 1:
        return controls[0][0].lower() + controls[0][1:]
    return ", ".join(c[0].lower() + c[1:] for c in controls[:-1]) + f", and {controls[-1][0].lower() + controls[-1][1:]}"


def _join_names(names: list[str]) -> str:
    unique = [n for n in dict.fromkeys(names) if n]
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    if len(unique) == 2:
        return f"{unique[0]} and {unique[1]}"
    return f"{', '.join(unique[:-1])}, and {unique[-1]}"


def _intro(extracted: list[dict[str, Any]], clients: list[str]) -> str:
    if not extracted:
        return "This production deployment has no custom-client report updates."
    who = _join_names(clients) or "custom clients"
    if len(extracted) == 1 and clients:
        return f"This release includes one update for {who}."
    n = len(extracted)
    noun = "update" if n == 1 else "updates"
    return f"This release includes {n} {noun} for {who}."


def _jira_base(extracted: list[dict[str, Any]]) -> str:
    for entry in extracted:
        link = str(entry.get("link") or "").strip()
        if "/browse/" in link:
            return link.rsplit("/browse/", 1)[0].rstrip("/")
    try:
        import config

        base = str(getattr(config, "JIRA_BASE_URL", "") or "").rstrip("/")
        if base:
            return base
    except Exception:
        pass
    return DEFAULT_JIRA_BASE


def _ticket_url(entry: dict[str, Any], base: str) -> str:
    link = str(entry.get("link") or "").strip()
    if link.startswith("http"):
        return link
    key = str(entry.get("ticket") or "").strip()
    return f"{base}/browse/{key}" if key else ""


def _fix_version_url(base: str, version_plain: str) -> str:
    if not base or not version_plain:
        return ""
    quoted = version_plain.replace(" ", "%20")
    return f"{base}/issues/?jql=fixVersion%20%3D%20%22{quoted}%22"


def _write_left_cell(cell, text: str, *, url: str = "") -> None:
    _reset_cell_paragraph(cell)
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    value = (text or "").strip()
    if url and value:
        _add_hyperlink_run(paragraph, value, url)
    else:
        run = paragraph.add_run(value)
        _style_run(run, size=BODY_SIZE)
    _add_deployment_cell_borders(cell, header=False)


def _add_flush_table(
    doc: Document,
    headers: tuple[str, ...] | list[str],
    rows: list[list[str]],
    *,
    widths: tuple[int, ...] | None = None,
    row_urls: list[str] | None = None,
    url_column: int = 0,
) -> None:
    """One left edge, one content width — used for every client-notes table."""
    header_list = list(headers)
    cols = len(header_list)
    if widths is None:
        base = tuple(max(PAGE_CONTENT_WIDTH_TWIPS // cols, 900) for _ in header_list)
        widths = fit_column_widths(base, PAGE_CONTENT_WIDTH_TWIPS)
    else:
        widths = fit_column_widths(widths, PAGE_CONTENT_WIDTH_TWIPS)
    table = doc.add_table(rows=1 + max(len(rows), 1), cols=cols)
    _apply_reference_table_style(table, GRID_TABLE_ACCENT_STYLE)
    _set_reference_tbl_look(table)
    _set_table_indent(table, TABLE_INDENT_TWIPS)
    header_row = table.rows[0]
    _set_deployment_header_row_cnf(header_row)
    for idx, header in enumerate(header_list):
        _write_deployment_header_cell(header_row.cells[idx], header)
    body = rows or [[""] * cols]
    for row_idx, row_data in enumerate(body):
        row = table.rows[row_idx + 1]
        url = (row_urls or [""] * len(body))[row_idx] if row_idx < len(row_urls or []) else ""
        for col_idx in range(cols):
            value = row_data[col_idx] if col_idx < len(row_data) else ""
            _write_left_cell(
                row.cells[col_idx],
                value,
                url=url if col_idx == url_column else "",
            )
    _apply_table_column_widths(
        table,
        widths,
        total_width=PAGE_CONTENT_WIDTH_TWIPS,
        fixed_layout=True,
    )
    _prevent_table_row_splits(table)


def _add_kv_table(doc: Document, pairs: list[tuple[str, str]]) -> None:
    """Label | value rows — labels use the teal header fill (revised-sample look)."""
    table = doc.add_table(rows=len(pairs), cols=2)
    _apply_reference_table_style(table, GRID_TABLE_ACCENT_STYLE)
    _set_reference_tbl_look(table)
    _set_table_indent(table, TABLE_INDENT_TWIPS)
    for idx, (label, value) in enumerate(pairs):
        row = table.rows[idx]
        _write_deployment_header_cell(row.cells[0], label)
        _write_left_cell(row.cells[1], value)
    _apply_table_column_widths(
        table,
        fit_column_widths((2800, PAGE_CONTENT_WIDTH_TWIPS - 2800), PAGE_CONTENT_WIDTH_TWIPS),
        total_width=PAGE_CONTENT_WIDTH_TWIPS,
        fixed_layout=True,
    )
    _prevent_table_row_splits(table)


def table_left_edges(doc: Document) -> list[int]:
    edges: list[int] = []
    for table in doc.tables:
        tbl_pr = table._tbl.tblPr
        ind = tbl_pr.find(qn("w:tblInd")) if tbl_pr is not None else None
        edges.append(int(ind.get(qn("w:w"))) if ind is not None else 0)
    return edges


def _gold_underline(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    existing = p_pr.find(qn("w:pBdr"))
    if existing is not None:
        p_pr.remove(existing)
    border = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "18")
    bottom.set(qn("w:space"), "6")
    bottom.set(qn("w:color"), GOLD)
    border.append(bottom)
    p_pr.append(border)


def _title_block(doc: Document, version: str) -> None:
    title = doc.add_paragraph(style="Heading 1")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run("Release Notes")
    _style_run(title_run, bold=True, size=Pt(TITLE_SIZE_PT), color_hex=TITLE_COLOR)
    _gold_underline(title)
    if version:
        version_para = doc.add_paragraph()
        version_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        version_run = version_para.add_run(version if version.lower().startswith("v") else f"v{version}")
        _style_run(version_run, bold=True, size=Pt(14), color_hex=TITLE_COLOR)


def _client_banner(doc: Document, client: str, subtitle: str) -> None:
    table = doc.add_table(rows=1, cols=1)
    _apply_reference_table_style(table, GRID_TABLE_ACCENT_STYLE)
    _set_table_indent(table, TABLE_INDENT_TWIPS)
    cell = table.rows[0].cells[0]
    _reset_cell_paragraph(cell)
    _set_cell_shading(cell, DEPLOYMENT_HEADER_FILL)
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    name = paragraph.add_run(client)
    _style_run(name, bold=True, size=Pt(CLIENT_BANNER_SIZE_PT), color_hex=DEPLOYMENT_HEADER_TEXT)
    if subtitle:
        extra = cell.add_paragraph()
        extra.alignment = WD_ALIGN_PARAGRAPH.LEFT
        sub = extra.add_run(subtitle)
        _style_run(sub, size=BODY_SIZE, color_hex=DEPLOYMENT_HEADER_TEXT)
    _add_deployment_cell_borders(cell, header=True)
    _apply_table_column_widths(
        table,
        (PAGE_CONTENT_WIDTH_TWIPS,),
        total_width=PAGE_CONTENT_WIDTH_TWIPS,
        fixed_layout=True,
    )
    _prevent_table_row_splits(table)


def _overview_rows(grouped: dict[str, list[dict[str, Any]]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for client, entries in grouped.items():
        reports = ", ".join(dict.fromkeys(_report_name(e) for e in entries))
        tickets = ", ".join(str(e.get("ticket") or "").strip() for e in entries if e.get("ticket"))
        what = "; ".join(_control_list(e) for e in entries)
        rows.append([client, reports, tickets, what[:160]])
    return rows


def _label_heading(doc: Document, text: str) -> None:
    para = doc.add_paragraph()
    run = para.add_run(text)
    _style_run(run, bold=True, color_hex=TITLE_COLOR)
    _format_section_paragraph(para, shaded=True, spacing="shaded_section")
    _set_paragraph_keep_with_next(para)


def _body(doc: Document, text: str, *, bold_prefix: str = "") -> None:
    para = doc.add_paragraph()
    _format_section_paragraph(para, spacing="list_compact")
    if bold_prefix:
        lead = para.add_run(bold_prefix)
        _style_run(lead, bold=True)
        tail = para.add_run(text)
        _style_run(tail)
    else:
        run = para.add_run(text)
        _style_run(run)


def _bullet(doc: Document, text: str, *, bold_prefix: str = "") -> None:
    para = doc.add_paragraph(style=LIST_STYLE)
    para.clear()
    if bold_prefix:
        lead = para.add_run(bold_prefix)
        _style_run(lead, bold=True)
        run = para.add_run(text)
        _style_run(run)
    else:
        run = para.add_run(text)
        _style_run(run)
    _format_section_paragraph(para, spacing="list_compact")


def _unique_controls(entries: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for entry in entries:
        for bullet in _scope_bullets(entry):
            key = bullet.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(bullet)
    return items


def _write_client_section(
    doc: Document,
    client: str,
    entries: list[dict[str, Any]],
) -> None:
    reports = _join_names([_report_name(e) for e in entries])
    n = len(entries)
    subtitle = f"{n} update{'s' if n != 1 else ''}  ·  {reports}"
    _client_banner(doc, client, subtitle)
    for bullet in _unique_controls(entries):
        _bullet(doc, bullet)


def _write_references(
    doc: Document,
    extracted: list[dict[str, Any]],
    version_plain: str,
    jira_base: str,
) -> None:
    _label_heading(doc, "References")
    para = doc.add_paragraph()
    _format_section_paragraph(para, shaded=True, spacing="shaded_section")
    lead = para.add_run("Jira: ")
    _style_run(lead, bold=True, color_hex=TITLE_COLOR)
    keys = [e for e in extracted if str(e.get("ticket") or "").strip()]
    for idx, entry in enumerate(keys):
        key = str(entry.get("ticket") or "").strip()
        url = _ticket_url(entry, jira_base)
        if url:
            _add_hyperlink_run(para, key, url)
        else:
            run = para.add_run(key)
            _style_run(run, bold=True)
        if idx < len(keys) - 1:
            sep = para.add_run("  ·  ")
            _style_run(sep)
    if version_plain:
        mid = para.add_run("      ")
        _style_run(mid)
        fv_label = para.add_run("Fix version: ")
        _style_run(fv_label, bold=True, color_hex=TITLE_COLOR)
        fv_url = _fix_version_url(jira_base, version_plain)
        if fv_url:
            _add_hyperlink_run(para, version_plain, fv_url)
        else:
            fv = para.add_run(version_plain)
            _style_run(fv, bold=True)


def generate_client_release_notes_docx(data: dict[str, Any]) -> bytes:
    extracted = filter_pic_custom_extracted(data.get("extracted") or [])
    clients = build_custom_clients_list(extracted)
    version = _version_display(data)
    version_plain = _version_plain(data)
    pretty = _pretty_date(data)

    doc = Document()
    _apply_reference_margins(doc)
    _configure_reference_document_theme(doc)
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = BODY_SIZE
    style.paragraph_format.space_after = Pt(0)

    _title_block(doc, version)
    _body(doc, _intro(extracted, clients))

    _add_kv_table(
        doc,
        [
            ("Version", version_plain or "(set)"),
            ("Release date", pretty or "(set)"),
        ],
    )

    grouped = _group_by_client(extracted)
    if len(grouped) > 1:
        _label_heading(doc, "Clients in this release")
        _add_flush_table(
            doc,
            CLIENT_OVERVIEW_HEADERS,
            _overview_rows(grouped),
            widths=(1800, 2600, 1800, 3160),
        )

    jira_base = _jira_base(extracted)
    for client, entries in grouped.items():
        _write_client_section(doc, client, entries)

    if extracted:
        _write_references(doc, extracted, version_plain, jira_base)

    buf = io.BytesIO()
    doc.core_properties.keywords = GENERATOR_BUILD_ID
    doc.save(buf)
    return patch_docx_grid_table4_accent1_style(buf.getvalue())


def client_notes_filename(version_name: str) -> str:
    safe = re.sub(r"[^\w.\-]+", "_", str(version_name or "").lstrip("vV"))
    return f"Client Release Notes {safe}.docx"


def default_client_notes_path(version_name: str) -> Path:
    return Path.home() / "Downloads" / client_notes_filename(version_name)


def write_client_release_notes_beside(
    data: dict[str, Any],
    internal_docx_path: str,
) -> dict[str, Any]:
    payload_data = dict(data)
    payload_data["extracted"] = filter_pic_custom_extracted(data.get("extracted") or [])
    payload = generate_client_release_notes_docx(payload_data)
    sibling = Path(internal_docx_path)
    out = sibling.with_name(client_notes_filename(str(data.get("version") or sibling.stem)))
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.write_bytes(payload)
    except PermissionError:
        out = out.with_name(f"{out.stem} ({int(datetime.now().timestamp())}){out.suffix}")
        out.write_bytes(payload)
    return {
        "ok": True,
        "client_docx_path": str(out.resolve()),
        "client_docx_filename": out.name,
        "client_docx_bytes": len(payload),
        "client_ticket_count": len(payload_data["extracted"]),
        "client_clients": build_custom_clients_list(payload_data["extracted"]),
    }


def write_client_release_notes_file(
    data: dict[str, Any],
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    payload_data = dict(data)
    payload_data["extracted"] = filter_pic_custom_extracted(data.get("extracted") or [])
    payload = generate_client_release_notes_docx(payload_data)
    out = Path(output_path) if output_path else default_client_notes_path(str(data.get("version") or ""))
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.write_bytes(payload)
    except PermissionError:
        out = out.with_name(f"{out.stem} ({int(datetime.now().timestamp())}){out.suffix}")
        out.write_bytes(payload)
    return {
        "ok": True,
        "status": "ok",
        "client_docx_path": str(out.resolve()),
        "client_docx_filename": out.name,
        "client_docx_bytes": len(payload),
        "client_ticket_count": len(payload_data["extracted"]),
        "client_clients": build_custom_clients_list(payload_data["extracted"]),
    }
