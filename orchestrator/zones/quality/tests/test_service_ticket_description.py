"""Tests for release-note-aligned SHIPIT description generation."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

SAMPLE = [
    {
        "type": "Analyze",
        "client": "Standard",
        "report": "Visits Analysis",
        "description": "Add Unique Visits column",
        "ticket": "AN-5516",
        "status": "Passed QA",
        "assignee": "Narasimha",
        "link": "https://abcfinancial.atlassian.net/browse/AN-5516",
    },
    {
        "type": "Custom",
        "client": "Lift",
        "report": "Membership Retention",
        "description": "Add new columns",
        "ticket": "PIC-6010",
        "status": "Ready for Review",
        "assignee": "Rekha",
        "link": "https://abcfinancial.atlassian.net/browse/PIC-6010",
    },
]


def test_description_matches_release_notes_structure():
    from adf_builder import adf_links, adf_to_plain_text
    from generators.service_ticket_description import build_service_ticket_description_adf

    adf_doc = build_service_ticket_description_adf(
        SAMPLE,
        "https://abcfinancial.sharepoint.com/release-notes.docx",
        version_label="v2026.3.09.14",
        window={"sentence": "Sep 14, 2026, 10:30 AM – 11:30 AM IST"},
    )
    plain = adf_to_plain_text(adf_doc)
    links = adf_links(adf_doc)

    assert "Release Summary" in plain
    assert "Affected Clients" in plain
    assert "Glofox Analyze" in plain
    assert "Lift" in plain
    assert "Deployment Window" in plain
    assert "Key Highlights" in plain
    assert "Reports / Dashboards Delivered" in plain
    assert "Ticket Details" in plain
    assert "AN-5516" in plain
    assert "PIC-6010" in plain
    assert "Release Notes Documentation" in plain
    sharepoint_links = [
        href for _label, href in links
        if href.startswith("https://abcfinancial.sharepoint.com")
    ]
    assert sharepoint_links


def test_description_uses_local_release_notes_label_without_link():
    from adf_builder import adf_links, adf_to_plain_text
    from generators.service_ticket_description import build_service_ticket_description_adf

    adf_doc = build_service_ticket_description_adf(
        SAMPLE,
        r"C:\Users\LYal01\Desktop\Release Notes 2026.3.09.14.docx",
        version_label="v2026.3.09.14",
    )
    plain = adf_to_plain_text(adf_doc)

    assert "Release Notes Documentation" in plain
    assert "Release Notes 2026.3.09.14.docx" in plain
    sharepoint_links = [
        href for _label, href in adf_links(adf_doc)
        if "sharepoint" in href.lower()
    ]
    assert not sharepoint_links
