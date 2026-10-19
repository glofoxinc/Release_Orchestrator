"""SharePoint URL shape parity with fitness-bi-release-notes."""

from __future__ import annotations

import sharepoint_url as sp_url


def test_slack_has_download_and_folder_urls():
    version = "2026.3.09.11"
    download = sp_url.sharepoint_direct_download_url(
        "https://abcfinancial.sharepoint.com/teams/x/Shared%20Documents/Release%20Notes%202026.3.09.11.docx"
    )
    assert "download=1" in download
    folder_url, label = sp_url.resolve_sharepoint_folder_link(version_name=version)
    assert folder_url == "" or "sharepoint" in folder_url.lower() or "AllItems.aspx" in folder_url
    assert label


def test_month_folder_from_version():
    assert sp_url.month_folder_from_version("2026.3.09.11") == "2026-09"


def test_sibling_client_notes_url_same_folder():
    url = (
        "https://abcfinancial.sharepoint.com/:w:/r/teams/x/"
        "Release%20Notes%202026.4.10.15.docx?action=default"
    )
    sibling = sp_url.sibling_client_notes_url(url, "2026.4.10.15")
    assert "Client%20Release%20Notes%202026.4.10.15.docx" in sibling


def test_shipit_description_lists_both_sharepoint_docs():
    import adf_builder as adf
    from generators.shipit_evidence_plans import build_evidence_description_adf

    doc = build_evidence_description_adf(
        [
            {
                "ticket": "PIC-1",
                "type": "Custom",
                "client": "Lift",
                "report": "X",
                "description": "filters",
            }
        ],
        version_label="v2026.4.10.15",
        sharepoint_url="https://example.sharepoint.com/Release%20Notes%202026.4.10.15.docx",
        client_sharepoint_url="https://example.sharepoint.com/Client%20Release%20Notes%202026.4.10.15.docx",
    )
    plain = adf.adf_to_plain_text(doc)
    assert "Release Notes 2026.4.10.15.docx" in plain
    assert "Client Release Notes 2026.4.10.15.docx" in plain
