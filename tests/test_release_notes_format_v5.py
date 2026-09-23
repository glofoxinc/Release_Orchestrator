"""Release notes format v5: Assignee column, Testing Evidence structure, Release Summary layout."""

from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docx import Document

from generators.release_notes_generator import format_change_row, generate_release_notes_docx
from generators.release_notes_template_defaults import (
    CHANGE_HEADERS,
    TESTING_EVIDENCE_CLIENT_PLACEHOLDER,
    TESTING_EVIDENCE_TICKETS_LIST_HEADING,
    build_testing_evidence_client_names,
    build_testing_evidence_editor_text,
)


def _extracted_sample() -> list[dict]:
    return [
        {
            "type": "Analyze",
            "client": "Standard",
            "report": "Members and Clients KPIs",
            "description": "New paginated report by location",
            "ticket": "AN-5504",
            "assignee": "Narasimha",
        },
        {
            "type": "Custom",
            "client": "Lift",
            "report": "Membership Retention",
            "description": "Add new columns from Looker",
            "ticket": "PIC-4100",
            "assignee": "Chanti",
        },
    ]


class TestAssigneeColumn:
    def test_format_change_row_includes_assignee(self):
        row = format_change_row(
            ticket="PIC-4100",
            link="https://example/browse/PIC-4100",
            assignee="Chanti",
            test_by="Rekha",
            testing_status="Done",
        )
        parts = row.split("|")
        assert parts == [
            "PIC-4100",
            "https://example/browse/PIC-4100",
            "Chanti",
            "Rekha",
            "Done",
        ]

    def test_docx_change_table_has_assignee_header(self):
        extracted = _extracted_sample()
        result = generate_release_notes_docx(
            {
                "version": "v2026.3.09.08",
                "extracted": extracted,
                "change_rows": format_change_row(
                    ticket="PIC-4100",
                    link="https://example/browse/PIC-4100",
                    assignee="Chanti",
                    test_by="Rekha",
                    testing_status="Done",
                ),
            }
        )
        doc = Document(io.BytesIO(result))
        change_table = next(
            t
            for t in doc.tables
            if len(t.columns) == len(CHANGE_HEADERS)
            and t.rows[0].cells[0].text.strip() == "Ticket"
        )
        headers = [c.text.strip() for c in change_table.rows[0].cells]
        assert headers == list(CHANGE_HEADERS)
        values = [c.text.strip() for c in change_table.rows[1].cells]
        assert values[2] == "Chanti"


class TestReleaseNotesLayoutV6:
    def test_metadata_uses_gm_not_svp(self):
        result = generate_release_notes_docx(
            {"version": "v2026.3.09.08", "svp": "Rahul Das"},
        )
        doc = Document(io.BytesIO(result))
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "GM" in text
        assert "SVP" not in text

    def test_testing_evidence_starts_on_new_page(self):
        from docx.oxml.ns import qn

        extracted = _extracted_sample()
        result = generate_release_notes_docx(
            {
                "version": "v2026.3.09.08",
                "extracted": extracted,
                "change_rows": "AN-5504|https://example/browse/AN-5504|Narasimha|Rekha|Done",
                "deployment_rows": "Analyze|Navya||",
            }
        )
        doc = Document(io.BytesIO(result))
        heading = next(p for p in doc.paragraphs if p.text.strip().startswith("Testing Evidence"))
        p_pr = heading._p.pPr
        assert p_pr is not None
        assert p_pr.find(qn("w:pageBreakBefore")) is not None


class TestTestingEvidenceStructure:
    def test_client_names_from_deployment_and_extracted(self):
        clients = build_testing_evidence_client_names(
            _extracted_sample(),
            "Analyze|Navya||\nLift|Chanti||",
        )
        assert "Analyze (Standard)" in clients
        assert "Lift" in clients

    def test_client_names_exclude_analyze_when_no_an_tickets(self):
        custom_only = [
            {
                "type": "Custom",
                "project": "PIC",
                "client": "Xtreme Fitness",
                "report": "Sales League Report",
                "description": "Change to filter logic",
                "ticket": "PIC-5966",
            },
            {
                "type": "Custom",
                "project": "PIC",
                "client": "Jazzercise",
                "report": "Course Offering by Location",
                "description": "Class filter alignment",
                "ticket": "PIC-6057",
            },
        ]
        clients = build_testing_evidence_client_names(
            custom_only,
            "Analyze|Navya||\nXtreme Fitness|Bharathi||\nJazzercise|Lakshmi||",
        )
        assert "Analyze (Standard)" not in clients
        assert clients == ["Xtreme Fitness", "Jazzercise"]

    def test_editor_text_includes_clients_and_ticket_placeholders(self):
        text = build_testing_evidence_editor_text(
            _extracted_sample(),
            deployment_rows="Lift|Chanti||",
        )
        assert "Lift" in text
        assert TESTING_EVIDENCE_TICKETS_LIST_HEADING in text
        assert TESTING_EVIDENCE_CLIENT_PLACEHOLDER in text
        assert "AN-5504" in text
        assert "PIC-4100" in text

    def test_docx_testing_evidence_has_clients_and_ticket_placeholders(self):
        extracted = _extracted_sample()
        result = generate_release_notes_docx(
            {
                "version": "v2026.3.09.08",
                "extracted": extracted,
                "deployment_rows": "Analyze|Navya||\nLift|Chanti||",
                "testing_evidence_tickets": build_testing_evidence_editor_text(
                    extracted,
                    deployment_rows="Analyze|Navya||\nLift|Chanti||",
                ),
            }
        )
        doc = Document(io.BytesIO(result))
        text = "\n".join(p.text for p in doc.paragraphs)
        assert TESTING_EVIDENCE_TICKETS_LIST_HEADING in text
        assert TESTING_EVIDENCE_CLIENT_PLACEHOLDER in text
        assert "Lift" in text
        assert "AN-5504" in text
