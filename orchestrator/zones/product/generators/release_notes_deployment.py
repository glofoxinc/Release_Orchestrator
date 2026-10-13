"""Build and enrich deployment tracking rows for release notes."""

from __future__ import annotations

import io
import re
from typing import Any

from docx import Document

from generators.release_notes_template_defaults import DEPLOYMENT_HEADERS

_DEPLOYMENT_ROW_COLS = 4


def _normalize_client_key(name: str) -> str:
    return re.sub(r"[\s\-_]+", "", (name or "").strip().lower())


def format_deployment_id_time(info: dict[str, Any]) -> str:
    """Format deployment ID + timestamp for pipe-delimited storage."""
    dep_id = (info.get("deployment_id") or "").strip()
    dep_date = (info.get("deployment_date") or "").strip()
    dep_time = (info.get("deployment_time") or "").strip()
    if not dep_id:
        return ""
    if dep_date and dep_time:
        return f"{dep_id}; {dep_date}, {dep_time}"
    if dep_date:
        return f"{dep_id}; {dep_date}"
    return dep_id


def format_deployment_id_time_docx(stored: str) -> str:
    """Render stored deployment ID/time on two lines in the Word table cell."""
    text = (stored or "").strip()
    if "; " in text:
        dep_id, rest = text.split("; ", 1)
        return f"{dep_id.strip()}\n{rest.strip()}"
    return text


def parse_deployment_id_time(stored: str) -> dict[str, str]:
    """Inverse of :func:`format_deployment_id_time` — split stored cell into parts."""
    empty = {"deployment_id": "", "deployment_date": "", "deployment_time": ""}
    text = (stored or "").strip()
    if not text:
        return empty
    if "; " not in text:
        return {**empty, "deployment_id": text}
    dep_id, rest = text.split("; ", 1)
    rest = rest.strip()
    if ", " in rest:
        dep_date, dep_time = rest.split(", ", 1)
    else:
        dep_date, dep_time = rest, ""
    return {
        "deployment_id": dep_id.strip(),
        "deployment_date": dep_date.strip(),
        "deployment_time": dep_time.strip(),
    }


def parse_deployment_rows(raw: str, *, min_cols: int = _DEPLOYMENT_ROW_COLS) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in (raw or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        cols = [c.strip() for c in line.split("|", min_cols - 1)]
        while len(cols) < min_cols:
            cols.append("")
        rows.append(cols[:min_cols])
    return rows


def extract_deployment_rows_from_docx(data: bytes) -> list[list[str]]:
    """Extract the deployment tracking table from generated Release Notes."""
    if not data:
        return []
    document = Document(io.BytesIO(data))
    expected = [_normalize_header(value) for value in DEPLOYMENT_HEADERS]
    for table in document.tables:
        if not table.rows:
            continue
        headers = [_normalize_header(cell.text) for cell in table.rows[0].cells]
        if headers[: len(expected)] != expected:
            continue
        rows: list[list[str]] = []
        for docx_row in table.rows[1:]:
            cells = [cell.text.strip() for cell in docx_row.cells[:_DEPLOYMENT_ROW_COLS]]
            while len(cells) < _DEPLOYMENT_ROW_COLS:
                cells.append("")
            id_time_lines = [
                line.strip()
                for line in cells[3].replace("\r", "\n").splitlines()
                if line.strip()
            ]
            if len(id_time_lines) > 1:
                cells[3] = f"{id_time_lines[0]}; {' '.join(id_time_lines[1:])}"
            elif id_time_lines:
                cells[3] = id_time_lines[0]
            rows.append(cells)
        return rows
    return []


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def format_deployment_rows(rows: list[list[str]]) -> str:
    return "\n".join("|".join(row) for row in rows)


def format_deployment_row(
    client: str,
    owner: str,
    status: str = "",
    deployment_id_time: str = "",
) -> str:
    return "|".join([client, owner, status, deployment_id_time])


def _match_deploy_info(client_label: str, deploy_by_client: dict[str, dict]) -> dict | None:
    if not client_label or not deploy_by_client:
        return None

    norm = _normalize_client_key(client_label)
    for key, info in deploy_by_client.items():
        if _normalize_client_key(key) == norm:
            return info

    if norm == "analyze":
        for key, info in deploy_by_client.items():
            if "analyze" in _normalize_client_key(key):
                return info

    for key, info in deploy_by_client.items():
        key_norm = _normalize_client_key(key)
        if key_norm.startswith(norm) or norm.startswith(key_norm):
            return info

    return None


def enrich_deployment_rows(
    rows: list[list[str]],
    deploy_by_client: dict[str, dict],
    *,
    overwrite: bool = False,
) -> list[list[str]]:
    """Fill Status and Deployment ID & Time when deploy info is available."""
    enriched: list[list[str]] = []
    for row in rows:
        cols = list(row)
        while len(cols) < _DEPLOYMENT_ROW_COLS:
            cols.append("")
        cols = cols[:_DEPLOYMENT_ROW_COLS]

        info = _match_deploy_info(cols[0], deploy_by_client)
        if info and info.get("deployment_id"):
            # Status column stays blank until release owner updates the DOCX manually.
            if overwrite or not cols[3].strip():
                cols[3] = format_deployment_id_time(info)

        enriched.append(cols)
    return enriched


def merge_parsed_deployments(
    rows: list[list[str]],
    parsed: list[Any],
    *,
    overwrite: bool = False,
) -> list[list[str]]:
    """Apply ParsedDeployment results onto existing deployment rows by client."""
    deploy_by_client = {
        p.client: {
            "deployment_id": p.deployment_id,
            "deployment_date": p.deployment_date,
            "deployment_time": p.deployment_time,
        }
        for p in parsed
        if getattr(p, "deployment_id", "")
    }
    return enrich_deployment_rows(rows, deploy_by_client, overwrite=overwrite)


def build_deployment_rows(
    client_owners: dict[str, str],
    deploy_by_client: dict[str, dict] | None = None,
) -> str:
    rows = [[client, owner, "", ""] for client, owner in sorted(client_owners.items())]
    if deploy_by_client:
        rows = enrich_deployment_rows(rows, deploy_by_client)
    return format_deployment_rows(rows)
