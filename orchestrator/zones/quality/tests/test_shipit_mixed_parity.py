"""Mixed AN + PIC SHIPIT release — combined sprint parity."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.shipit_evidence_plans import (
    build_evidence_business_impact,
    build_evidence_communication,
    build_evidence_description_adf,
    build_evidence_implementation,
    build_evidence_verification,
)
from generators.shipit_ticket_evidence import attach_offline_evidence, parse_ticket_evidence

_FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _from_fixture(ticket: str, entry_meta: dict, fixture_name: str) -> dict:
    fx = _load(fixture_name)
    issue = {"fields": {"summary": fx["summary"], "description": fx["description_plain"]}}
    comments = [{"body": fx["comment_plain"]}] if fx.get("comment_plain") else []
    ev = parse_ticket_evidence(issue, comments)
    return attach_offline_evidence({**entry_meta, "ticket": ticket}, ev)


MIXED = [
    _from_fixture(
        "AN-5516",
        {
            "type": "Analyze",
            "client": "Standard",
            "report": "Visits Analysis - Member Details",
            "description": "Add Unique Visits column",
            "status": "Passed QA",
            "assignee": "Nikhila Sree Ramisetti",
        },
        "an_5516_evidence.json",
    ),
    _from_fixture(
        "PIC-6057",
        {
            "type": "Custom",
            "client": "Jazzercise",
            "report": "Course Offering by location",
            "description": "Class filters to match Looker logic",
            "status": "Ready for Release",
        },
        "pic_6057_evidence.json",
    ),
]


def _ctx():
    return {
        "extracted": MIXED,
        "sharepoint": "https://example.com/Release%20Notes.docx",
        "version": "2026.3.09.16",
    }


def test_mixed_description_covers_both_workspaces():
    import adf_builder as adf

    doc = build_evidence_description_adf(MIXED, version_label="2026.3.09.16")
    text = adf.adf_to_plain_text(doc)
    assert "AN-5516" in text
    assert "PIC-6057" in text
    assert "Glofox Analyze" in text
    assert "V2 Fitness BI" in text
    assert "Looker data validation" in text


def test_mixed_implementation_dual_workspace():
    impl = build_evidence_implementation(_ctx())
    assert "Glofox Analyze (AN-5516)" in impl
    assert "Jazzercise (PIC-6057)" in impl
    assert "Glofox Analyze and customer-facing V2 Fitness BI" in impl


def test_mixed_verification_analyze_and_looker():
    verify = build_evidence_verification(_ctx())
    assert "Glofox Analyze (AN-5516)" in verify
    assert "Glofox dashboard" in verify
    assert "Jazzercise (PIC-6057)" in verify
    assert "Looker" in verify


def test_mixed_business_impact_audience():
    impact = build_evidence_business_impact(_ctx())
    assert "AN-5516" in impact
    assert "PIC-6057" in impact
    assert "Glofox Analyze users" in impact
    assert "Jazzercise users" in impact


def test_mixed_communication_dual_scope():
    comm = build_evidence_communication(_ctx())
    assert "Pass QA / Ready for Release" in comm
    assert "AN-5516" in comm
