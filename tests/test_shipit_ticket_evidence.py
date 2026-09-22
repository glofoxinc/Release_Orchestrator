"""Rich Jira evidence parsing — SHIPIT-17036 / AN-5516 parity."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.shipit_evidence_plans import (
    build_evidence_business_impact,
    build_evidence_communication,
    build_evidence_description_adf,
    build_evidence_risks,
    build_evidence_verification,
    build_qa_evidence_test_plan,
)
from generators.shipit_ticket_evidence import (
    attach_offline_evidence,
    enrich_extracted_with_jira_evidence,
    parse_ticket_evidence,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "an_5516_evidence.json"

BASE_ENTRY = {
    "ticket": "AN-5516",
    "type": "Analyze",
    "client": "Standard",
    "report": "Visits Analysis - Member Details",
    "description": "Add Unique Visits column",
    "status": "Passed QA",
    "assignee": "Nikhila Sree Ramisetti",
}


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _an5516_issue() -> dict:
    fx = _load_fixture()
    return {"fields": {"summary": fx["summary"], "description": fx["description_plain"]}}


def _an5516_comments() -> list[dict]:
    fx = _load_fixture()
    return [{"body": fx["comment_plain"]}]


def _enriched_entry() -> dict:
    ev = parse_ticket_evidence(_an5516_issue(), _an5516_comments())
    return attach_offline_evidence(BASE_ENTRY, ev)


def _ctx(entry: dict | None = None) -> dict:
    e = entry or _enriched_entry()
    return {
        "extracted": [e],
        "sharepoint": "https://example.com/Release%20Notes.docx",
        "version": "2026.3.09.14",
        "workspaces": "Glofox Analyze",
        "scope_str": "Glofox Analyze",
        "dashboards": ["Visits Analysis - Member Details"],
        "window": {"sentence": "14 Sep 2026 10:00–16:00 IST"},
    }


def test_parse_an5516_qa_validator_and_date():
    ev = parse_ticket_evidence(_an5516_issue(), _an5516_comments())
    assert ev["qa_validator"] == "Nikhila Sree Ramisetti"
    assert ev["qa_date"] == "10 Sep 2026"
    assert ev["dashboard_definition"] == "one unique visit per calendar day"


def test_parse_an5516_numeric_example_and_cab_exceptions():
    ev = parse_ticket_evidence(_an5516_issue(), _an5516_comments())
    assert "51 event-based" in ev["numeric_example"]
    assert "19 distinct visit days" in ev["numeric_example"]
    assert ev.get("excel_signoff_gap") is True
    assert ev.get("performance_testing_gap") is True
    assert any("Option A vs Option B" in x for x in ev["cab_exceptions"])


def test_parse_an5516_product_decision_from_comments():
    ev = parse_ticket_evidence(_an5516_issue(), _an5516_comments())
    assert ev.get("product_decision") is not None
    assert "Option B" in ev["product_decision"]


def test_enrich_skips_when_evidence_present():
    entry = _enriched_entry()
    with patch("generators.shipit_ticket_evidence.jira_client.get_issue") as mock_get:
        result = enrich_extracted_with_jira_evidence([entry])
    mock_get.assert_not_called()
    assert result[0]["evidence"]["qa_validator"] == "Nikhila Sree Ramisetti"


def test_enrich_fetches_missing_evidence():
    with patch("generators.shipit_ticket_evidence._fetch_one") as mock_fetch:
        ev = parse_ticket_evidence(_an5516_issue(), _an5516_comments())
        mock_fetch.return_value = ("AN-5516", ev, None)
        result = enrich_extracted_with_jira_evidence([dict(BASE_ENTRY)])
    assert result[0]["evidence"]["artifact_column"] == "Unique Visits"


def test_rich_business_impact_includes_numeric_example():
    impact = build_evidence_business_impact(_ctx())
    assert "51 event-based" in impact
    assert "Unique Visits" in impact
    assert "Before:" in impact and "After:" in impact


def test_rich_verification_dashboard_reconcile():
    verify = build_evidence_verification(_ctx())
    assert "Glofox dashboard" in verify
    assert "multiple visits on the same day" in verify
    assert "Excel was raised on the ticket" in verify


def test_rich_risks_cab_exceptions():
    risks = build_evidence_risks(_ctx())
    assert "51 event-based" in risks
    assert "CAB exceptions" in risks
    assert "Option A vs Option B" in risks


def test_rich_qa_test_plan_validator_date():
    qa = build_qa_evidence_test_plan(_ctx())
    assert "Nikhila Sree Ramisetti" in qa
    assert "10 Sep 2026" in qa
    assert "Performance testing" in qa


def test_rich_communication_option_b_acceptance():
    comm = build_evidence_communication(_ctx())
    assert "Option B" in comm
    assert "insights-customize-squad" in comm


def test_rich_description_dashboard_rule():
    import adf_builder as adf

    adf_doc = build_evidence_description_adf(
        [_enriched_entry()],
        version_label="2026.3.09.14",
    )
    text = adf.adf_to_plain_text(adf_doc)
    assert "one unique visit per calendar day" in text
    assert "AN-5516" in text
