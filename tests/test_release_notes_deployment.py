"""Tests for deployment row mapping and table column widths."""

from __future__ import annotations

import io
import os
import sys

from docx import Document
from docx.oxml.ns import qn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.release_notes_deployment import (
    build_deployment_rows,
    enrich_deployment_rows,
    extract_deployment_rows_from_docx,
    format_deployment_id_time,
    merge_parsed_deployments,
    parse_deployment_id_time,
    parse_deployment_rows,
)
from generators.release_notes_generator import generate_release_notes_docx
from generators.release_notes_template_defaults import (
    CHANGE_COLUMN_WIDTHS,
    CHANGE_TABLE_WIDTH,
    DEPLOYMENT_COLUMN_WIDTHS,
    DEPLOYMENT_TABLE_WIDTH,
    EXCLUDED_COLUMN_WIDTHS,
    EXCLUDED_TABLE_WIDTH,
)
from jira_client import ParsedDeployment
from tests.test_reference_template import _reference_like_data


def test_format_deployment_id_time_multiline():
    result = format_deployment_id_time(
        {
            "deployment_id": "abc-123",
            "deployment_date": "14/04/26",
            "deployment_time": "10:39",
        }
    )
    assert result == "abc-123; 14/04/26, 10:39"


def test_parse_deployment_id_time_roundtrip():
    info = {
        "deployment_id": "d2e458c2-22fb-40dd-b1d9-5bd84926fbf0",
        "deployment_date": "August 14 2026",
        "deployment_time": "10:37 AM IST",
    }
    stored = format_deployment_id_time(info)
    parsed = parse_deployment_id_time(stored)
    assert parsed["deployment_id"] == info["deployment_id"]
    assert parsed["deployment_date"] == info["deployment_date"]
    assert parsed["deployment_time"] == info["deployment_time"]


def test_parse_deployment_id_time_id_only():
    parsed = parse_deployment_id_time("just-a-uuid")
    assert parsed["deployment_id"] == "just-a-uuid"
    assert parsed["deployment_date"] == ""
    assert parsed["deployment_time"] == ""


def test_parse_deployment_id_time_date_only():
    parsed = parse_deployment_id_time("uuid-x; August 14 2026")
    assert parsed["deployment_id"] == "uuid-x"
    assert parsed["deployment_date"] == "August 14 2026"
    assert parsed["deployment_time"] == ""


def test_parse_deployment_id_time_empty():
    parsed = parse_deployment_id_time("")
    assert parsed == {"deployment_id": "", "deployment_date": "", "deployment_time": ""}


def test_extract_deployment_rows_from_generated_docx():
    data = _reference_like_data()
    data["deployment_rows"] = (
        "Jazzercise|Nikhath|Deployed|"
        "d2e458c2-22fb-40dd-b1d9-5bd84926fbf0; August 14 2026, 10:37 AM IST"
    )
    docx_bytes = generate_release_notes_docx(data)
    rows = extract_deployment_rows_from_docx(docx_bytes)
    assert rows == [
        [
            "Jazzercise",
            "Nikhath",
            "Deployed",
            "d2e458c2-22fb-40dd-b1d9-5bd84926fbf0; August 14 2026, 10:37 AM IST",
        ]
    ]


def test_enrich_deployment_rows_fills_status_and_id():
    rows = [["Jetts", "Navya", "", ""]]
    deploy = {
        "Jetts": {
            "deployment_id": "abc-123",
            "deployment_date": "14/04/26",
            "deployment_time": "10:39",
            "status": "Deployed",
        }
    }
    enriched = enrich_deployment_rows(rows, deploy)
    assert enriched[0][2] == "Deployed"
    assert enriched[0][3].startswith("abc-123")


def test_enrich_does_not_overwrite_existing_values():
    rows = [["Jetts", "Navya", "In Progress", "manual"]]
    deploy = {
        "Jetts": {
            "deployment_id": "abc-123",
            "deployment_date": "14/04/26",
            "deployment_time": "10:39",
            "status": "Deployed",
        }
    }
    enriched = enrich_deployment_rows(rows, deploy, overwrite=False)
    assert enriched[0][2] == "In Progress"
    assert enriched[0][3] == "manual"


def test_merge_parsed_deployments_matches_client():
    rows = [["Jazzercise", "Nikhath", "", ""]]
    parsed = [
        ParsedDeployment(
            client="Jazzercise",
            deployment_id="uuid-1",
            deployment_date="15/07/26",
            deployment_time="09:15",
        )
    ]
    merged = merge_parsed_deployments(rows, parsed)
    assert merged[0][2] == "Deployed"
    assert "uuid-1" in merged[0][3]


def test_build_deployment_rows_sorted():
    text = build_deployment_rows(
        {"Jetts": "Navya", "Analyze": "Navya"},
        {
            "Jetts": {
                "deployment_id": "id-j",
                "deployment_date": "01/01/26",
                "deployment_time": "10:00",
            }
        },
    )
    rows = parse_deployment_rows(text)
    assert [r[0] for r in rows] == ["Analyze", "Jetts"]
    jetts = next(r for r in rows if r[0] == "Jetts")
    assert jetts[2] == "Deployed"
    assert jetts[3].startswith("id-j")


def _table_widths(table) -> tuple[int, ...]:
    grid = table._tbl.find(qn("w:tblGrid"))
    assert grid is not None
    return tuple(int(gc.get(qn("w:w"))) for gc in grid.findall(qn("w:gridCol")))


def _table_total_width(table) -> int | None:
    tbl_pr = table._tbl.tblPr
    if tbl_pr is None:
        return None
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        return None
    value = tbl_w.get(qn("w:w"))
    if value in (None, "0"):
        return 0
    return int(value)


def test_generated_tables_use_reference_column_widths():
    from generators.release_notes_parity import _change_table, _deploy_table

    doc = Document(io.BytesIO(generate_release_notes_docx(_reference_like_data())))
    deploy = _deploy_table(doc)
    change = _change_table(doc)
    assert _table_widths(deploy) == DEPLOYMENT_COLUMN_WIDTHS
    assert _table_total_width(deploy) == DEPLOYMENT_TABLE_WIDTH
    assert _table_widths(change) == CHANGE_COLUMN_WIDTHS
    assert _table_total_width(change) == CHANGE_TABLE_WIDTH
    excluded = next(t for t in doc.tables if len(t.columns) == 8 and t.rows[0].cells[0].text.strip() == "S.No")
    assert _table_widths(excluded) == EXCLUDED_COLUMN_WIDTHS
    assert _table_total_width(excluded) == EXCLUDED_TABLE_WIDTH

    layout = change._tbl.tblPr.find(qn("w:tblLayout"))
    assert layout is not None
    assert layout.get(qn("w:type")) == "fixed"
