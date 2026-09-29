"""Tests for release notes readiness insights."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


def test_build_release_summary_from_tickets():
    from generators.release_notes_insights import build_release_summary_paragraph

    extracted = [
        {
            "type": "Analyze",
            "client": "Standard",
            "report": "Promo look up",
            "description": "New paginated report",
            "ticket": "AN-1",
            "assignee": "Alice",
        },
        {
            "type": "Custom",
            "client": "Lift",
            "report": "ABC Customize",
            "description": "New paginated report migrated from Looker",
            "ticket": "PIC-2",
            "assignee": "Bob",
        },
    ]
    text = build_release_summary_paragraph(extracted)
    assert "paginated report" in text.lower()
    assert "Lift" in text


def test_is_generic_release_summary():
    from generators.release_notes_insights import is_generic_release_summary

    assert is_generic_release_summary(
        "This release includes reporting enhancements and semantic model updates."
    )
    assert not is_generic_release_summary(
        "This release delivers 2 dashboard(s) across 1 Analyze (Standard) ticket(s)."
    )


def test_draft_builds_deployment_skeleton():
    from generators.release_notes_draft import build_release_notes_draft_from_extracted

    extracted = [
        {"type": "Analyze", "client": "Standard", "report": "R1", "ticket": "AN-1", "assignee": "Alice"},
    ]
    draft = build_release_notes_draft_from_extracted(extracted, "2026.3.08.12")
    assert "Analyze" in draft["deployment_rows"]
    assert "Alice" in draft["deployment_rows"]
    assert draft["summary_p2"] == ""


def test_readiness_flags_missing_tickets():
    from generators.release_notes_insights import assess_release_notes_readiness

    report = assess_release_notes_readiness({"version": "v1.0.0"})
    assert not report.ready
    assert any(item.level == "blocker" for item in report.insights)


def test_readiness_ok_for_complete_draft():
    from generators.release_notes_insights import assess_release_notes_readiness

    extracted = [
        {
            "type": "Analyze",
            "client": "Standard",
            "report": "Dashboard A",
            "description": "Update",
            "ticket": "AN-10",
            "assignee": "Alice",
        },
    ]
    report = assess_release_notes_readiness(
        {
            "version": "v2026.3.08.12",
            "dev_team": "BI Team",
            "release_owner": "Alice",
            "extracted": extracted,
            "summary_p1": "This release delivers 1 dashboard across 1 Analyze (Standard) ticket(s).",
            "change_rows": "1|AN-10|AN-10|AN-9|https://example/browse/AN-10|Dashboard A|Update|QA||Done",
            "analyze_report_rows": "Analyze|Dashboard A|AN-10|Alice|Dashboard|Existing",
            "screenshot_names": "AN-10",
            "sanity_checklist": "Verify dashboard loads",
        }
    )
    assert report.ready
    assert report.stats["total_tickets"] == 1
    assert report.score >= 95


def test_readiness_score_penalizes_blockers():
    from generators.release_notes_insights import assess_release_notes_readiness

    report = assess_release_notes_readiness({"version": "", "extracted": [], "change_rows": ""})
    assert not report.ready
    assert report.score < 100
    assert report.score_breakdown.get("blockers", 0) >= 1
