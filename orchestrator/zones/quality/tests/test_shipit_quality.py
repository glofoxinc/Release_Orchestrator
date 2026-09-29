"""SHIPIT CAB quality assessor."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.shipit_quality import assess_shipit_draft
from generators.shipit_ticket_evidence import attach_offline_evidence, parse_ticket_evidence

_FIX = Path(__file__).parent / "fixtures" / "an_5516_evidence.json"


def _enriched_an5516():
    fx = json.loads(_FIX.read_text(encoding="utf-8"))
    issue = {"fields": {"summary": fx["summary"], "description": fx["description_plain"]}}
    comments = [{"body": fx["comment_plain"]}]
    ev = parse_ticket_evidence(issue, comments)
    entry = attach_offline_evidence(
        {
            "ticket": "AN-5516",
            "type": "Analyze",
            "client": "Standard",
            "report": "Visits Analysis - Member Details",
            "description": "Add Unique Visits column",
            "status": "Passed QA",
            "assignee": "Nikhila Sree Ramisetti",
        },
        ev,
    )
    return entry


def test_assess_ready_draft_scores_high():
    from generators.shipit_evidence_plans import (
        build_evidence_business_impact,
        build_evidence_communication,
        build_evidence_implementation,
        build_evidence_risks,
        build_evidence_rollback,
        build_evidence_verification,
        build_qa_evidence_test_plan,
    )
    import adf_builder as adf
    from generators.shipit_evidence_plans import build_evidence_description_adf

    extracted = [_enriched_an5516()]
    ctx = {"extracted": extracted, "sharepoint": "https://example.com/doc.docx", "version": "2026.3.09.14"}
    desc = adf.adf_to_plain_text(build_evidence_description_adf(extracted, version_label="2026.3.09.14"))
    plans = {
        "implementation_plan": build_evidence_implementation(ctx),
        "verification_plan": build_evidence_verification(ctx),
        "rollback_plan": build_evidence_rollback(ctx),
        "business_impact": build_evidence_business_impact(ctx),
        "communication_plan": build_evidence_communication(ctx),
        "risks_management": build_evidence_risks(ctx),
        "qa_test_plan": build_qa_evidence_test_plan(ctx),
    }
    result = assess_shipit_draft(
        ctx,
        summary="Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.14",
        description_plain=desc,
        plans=plans,
    )
    assert result["score_pct"] >= 85
    assert result["ready_for_cab"] is True
