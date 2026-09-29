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
