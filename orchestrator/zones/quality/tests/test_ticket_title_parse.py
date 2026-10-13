"""Tests for Jira title → report name + artifact type parsing."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.ticket_title_parse import format_report_display_name, refine_ticket_title_fields
from jira_client import extract_ticket_info


def test_visit_analysis_member_details_paginated():
    summary = "Add column - Visit Analysis - Member Details paginated report"
    refined = refine_ticket_title_fields(summary, report="Visit Analysis", description="Add column")
    assert "Member Details" in refined["report"]
    assert "Visit Analysis" in refined["report"]
    assert refined["asset_type"] == "Paginated report"
    assert "Paginated report" in refined["display_report"]


def test_insights_resolves_to_lead_conversion_dashboard():
    summary = "Fix Insights - Lead Conversion Dashboard - Add filter"
    refined = refine_ticket_title_fields(summary, report="Insights", description="Add filter")
    assert "Lead Conversion" in refined["report"]
    assert refined["asset_type"] == "Dashboard"
    assert "Dashboard" in refined["display_report"]


def test_extract_ticket_info_includes_display_report():
    import config
    from unittest.mock import patch

    with patch.object(config, "PROJECTS", [{"key": "AN", "multi_client": False}]):
        info = extract_ticket_info(
            "Update - Visit Analysis - Member Details paginated report",
            "AN-5500",
        )
    assert info.get("asset_type") == "Paginated report"
    assert "Member Details" in info.get("report", "")
    assert "Paginated report" in info.get("display_report", "")


def test_format_skips_redundant_suffix():
    assert format_report_display_name("Foo paginated report", "Paginated report") == "Foo (Paginated report)"
