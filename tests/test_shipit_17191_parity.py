"""SHIPIT-17191 gold-standard parity — multi-custom Customize BI release."""

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
    build_evidence_risks,
    build_evidence_rollback,
    build_evidence_verification,
    build_qa_evidence_test_plan,
)
from generators.shipit_ticket_evidence import attach_offline_evidence, parse_ticket_evidence
import shipit_reference

_FIX6057 = Path(__file__).parent / "fixtures" / "pic_6057_evidence.json"
_FIX5966 = Path(__file__).parent / "fixtures" / "pic_5966_evidence.json"


def _load(name: Path) -> dict:
    return json.loads(name.read_text(encoding="utf-8"))


def _entry(ticket: str, client: str, report: str, description: str, fixture: Path, status: str) -> dict:
    fx = _load(fixture)
    issue = {"fields": {"summary": fx["summary"], "description": fx["description_plain"]}}
    comments = [{"body": fx.get("comment_plain") or ""}] if fx.get("comment_plain") else []
    ev = parse_ticket_evidence(issue, comments)
    return attach_offline_evidence(
        {
            "ticket": ticket,
            "type": "Custom",
            "client": client,
            "report": report,
            "description": description,
            "status": status,
            "assignee": "Nikhila Sree Ramisetti",
        },
        ev,
    )


SAMPLE_PIC = [
    _entry(
        "PIC-6057",
        "Jazzercise",
        "Course Offering by location",
        "Class filters to match Looker logic",
        _FIX6057,
        "Ready for Release",
    ),
    _entry(
        "PIC-5966",
        "Xtreme Fitness",
        "Sales League Report",
        "Change to Filter Logic",
        _FIX5966,
        "Ready for Release",
    ),
]


def _ctx(**overrides):
    base = {
        "extracted": SAMPLE_PIC,
        "sharepoint": "https://example.com/Release%20Notes%202026.3.09.16.docx",
        "version": "2026.3.09.16",
        "workspaces": "customer-facing V2 Fitness BI workspace",
        "scope_str": "Custom",
        "dashboards": ["Course Offering by location", "Sales League Report"],
    }
    base.update(overrides)
    return base


def test_gold_standard_includes_17191():
    assert "SHIPIT-17191" in shipit_reference.GOLD_STANDARD_KEYS


def test_description_multi_custom_sections():
    import adf_builder as adf

    doc = build_evidence_description_adf(
        SAMPLE_PIC,
        version_label="2026.3.09.16",
        sharepoint_url="https://example.com/Release%20Notes.docx",
    )
    text = adf.adf_to_plain_text(doc)
    assert "What is changing, in business terms" in text
    assert "Jazzercise" in text
    assert "PIC-6057" in text
    assert "PIC-5966" in text
    assert "customer-facing V2 Fitness BI workspace" in text
    assert "Looker data validation" in text


def test_business_impact_multi_custom_before_after():
    impact = build_evidence_business_impact(_ctx())
    assert "PIC-6057" in impact
    assert "PIC-5966" in impact
    assert "Before:" in impact
    assert "Looker" in impact
    assert "Audience and boundary:" in impact


def test_implementation_per_client_lines():
    impl = build_evidence_implementation(_ctx())
    assert "Jazzercise (PIC-6057)" in impl
    assert "Xtreme Fitness (PIC-5966)" in impl
    assert "customer-facing V2 Fitness BI workspace" in impl
    assert "Looker-aligned" in impl


def test_verification_tc_and_looker_steps():
    verify = build_evidence_verification(_ctx())
    assert verify.startswith("1.")
    assert "Looker" in verify
    assert "TC-01" in verify
    assert "TC-02" in verify
    assert "TC-03" in verify
    assert "customer-facing report" in verify


def test_rollback_halt_further_publishes():
    rollback = build_evidence_rollback(_ctx())
    assert "halt further publishes" in rollback.lower()
    assert "PIC-6057" in rollback


def test_communication_custom_approvals():
    comm = build_evidence_communication(_ctx())
    assert "Ready for Release" in comm
    assert "Looker validation" in comm
    assert "Philip Dudley" in comm
    assert "No mass client announcement" in comm


def test_risks_per_client_sections():
    risks = build_evidence_risks(_ctx())
    assert "Jazzercise class filters (PIC-6057)" in risks
    assert "Xtreme Fitness filter logic (PIC-5966)" in risks
    assert "TC-01" in risks


def test_qa_plan_multi_ticket_evidence():
    qa = build_qa_evidence_test_plan(_ctx())
    assert "PIC-6057" in qa
    assert "PIC-5966" in qa
    assert "Looker" in qa
    assert "Philip Dudley" in qa
