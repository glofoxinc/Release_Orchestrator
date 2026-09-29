"""SHIPIT-17036 gold-standard parity — evidence-based service ticket content."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import config

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generators.shipit_evidence_plans import (
    build_evidence_business_impact,
    build_evidence_communication,
    build_evidence_description_adf,
    build_evidence_implementation,
    build_evidence_rollback,
    build_evidence_risks,
    build_evidence_verification,
    build_qa_evidence_test_plan,
)
from generators.shipit_ticket_evidence import attach_offline_evidence, parse_ticket_evidence
from shipit_reference import DEFAULT_REFERENCE_KEY, build_shipit_summary

import json
from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "an_5516_evidence.json"


def _an5516_evidence() -> dict:
    fx = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    issue = {"fields": {"summary": fx["summary"], "description": fx["description_plain"]}}
    comments = [{"body": fx["comment_plain"]}]
    return parse_ticket_evidence(issue, comments)


SAMPLE_AN5516 = [
    attach_offline_evidence(
        {
            "ticket": "AN-5516",
            "type": "Analyze",
            "client": "Standard",
            "report": "Visits Analysis - Member Details",
            "description": "Add Unique Visits column",
            "status": "Passed QA",
            "assignee": "Nikhila Sree Ramisetti",
        },
        _an5516_evidence(),
    )
]


def _ctx(**overrides):
    base = {
        "extracted": SAMPLE_AN5516,
        "sharepoint": "https://example.com/Release%20Notes.docx",
        "version": "2026.3.09.14",
        "workspaces": "Glofox Analyze",
        "scope_str": "Glofox Analyze",
        "dashboards": ["Visits Analysis - Member Details"],
        "window": {"sentence": "14 Sep 2026 10:00–16:00 IST"},
    }
    base.update(overrides)
    return base


def test_default_reference_is_shipit_17036():
    assert DEFAULT_REFERENCE_KEY == "SHIPIT-17036"


def test_summary_format_matches_17036():
    summary = build_shipit_summary(version_name="2026.3.09.14")
    assert summary == (
        "Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.14"
    )


def test_description_has_17036_sections():
    adf = build_evidence_description_adf(
        SAMPLE_AN5516,
        version_label="2026.3.09.14",
        window={"sentence": "14 Sep 2026 10:00–16:00"},
    )
    import adf_builder as adf_mod
    text = adf_mod.adf_to_plain_text(adf)
    assert "What is changing, in business terms" in text
    assert "Who is affected" in text
    assert "Not included in this change" in text
    assert "How it is deployed" in text
    assert "Supporting records" in text
    assert "AN-5516" in text


def test_business_impact_before_after_pattern():
    impact = build_evidence_business_impact(_ctx())
    assert "Before:" in impact
    assert "After:" in impact
    assert "Audience and boundary:" in impact
    assert "Ticket:" in impact
    assert "AN-5516" in impact
    assert "51 event-based" in impact
    assert "Unique Visits" in impact
    assert "Measured impact:" in impact
    assert "No measured time saving" not in impact
    assert "Release notes:" not in impact
    assert "example.com" not in impact


def test_implementation_pre_deploy_and_rls_guard():
    impl = build_evidence_implementation(_ctx())
    assert "Pre-deployment backups" in impl
    assert "Visits Analysis - Member Details" in impl
    assert "AN-5516" in impl
    assert "Do not change Production RLS" in impl


def test_verification_numbered_checklist():
    verify = build_evidence_verification(_ctx())
    assert verify.startswith("1.")
    assert "Excel (and PDF if used)" in verify
    assert "Roll back if" in verify
    assert "Glofox dashboard" in verify


def test_rollback_restore_pattern():
    rollback = build_evidence_rollback(_ctx())
    assert "pre-deployment backups" in rollback.lower()
    assert "AN-5516" in rollback


def test_communication_four_phases():
    comm = build_evidence_communication(_ctx())
    assert "Pre-deployment" in comm
    assert "During deployment" in comm
    assert "After success" in comm
    assert "After rollback" in comm
    assert "insights-customize-squad" in comm
    assert "Release version:" not in comm
    assert "Change ticket:" not in comm
    assert "Release notes:" not in comm


def test_shipit_plan_adf_bolds_communication_phases():
    import adf_builder as adf_mod

    comm = build_evidence_communication(_ctx())
    doc = adf_mod.shipit_plan_to_doc(comm)

    def _bold_texts(node: dict) -> list[str]:
        found: list[str] = []
        if node.get("type") == "text" and any(
            m.get("type") == "strong" for m in (node.get("marks") or [])
        ):
            found.append(node.get("text", ""))
        for child in node.get("content") or []:
            found.extend(_bold_texts(child))
        return found

    bold = _bold_texts(doc)
    for phase in ("Pre-deployment", "During deployment", "After success", "After rollback"):
        assert phase in bold


def test_risks_management_overall_and_shared():
    risks = build_evidence_risks(_ctx())
    assert "Overall" in risks
    assert "Shared controls" in risks
    assert "Do not describe residual risk as low" in risks
    assert "CAB exceptions" in risks
    assert "51 event-based" in risks


def test_qa_evidence_test_plan():
    qa = build_qa_evidence_test_plan(_ctx())
    assert "AN-5516" in qa
    assert "Passed QA" in qa
    assert "Performance testing" in qa
    assert "Nikhila Sree Ramisetti" in qa
    assert "10 Sep 2026" in qa


def test_release_ops_includes_risks_and_qa_fields():
    from release_mcp import release_ops

    captured_fields = {}

    def mock_create(summary, fields):
        captured_fields.update(fields)
        return {"key": "SHIPIT-TEST"}, type("RT", (), {"to_dict": lambda s: {"status": "ok"}})()

    with patch("jira_client.create_tckt_issue", mock_create):
        result = release_ops.create_service_ticket(
            "2026.3.09.14",
            sharepoint_url="https://example.com/Release%20Notes.docx",
            dry_run=False,
            extracted_override=SAMPLE_AN5516,
        )

    assert "Glofox Insights Customize BI - Prod Deployment" in result["summary"]
    assert config.TCKT_FIELDS["risks_management"] in captured_fields
    assert config.TCKT_FIELDS["qa_test_plan"] in captured_fields
    assert config.TCKT_FIELDS.get("impact") not in captured_fields or (
        captured_fields.get(config.TCKT_FIELDS.get("impact")) is None
    )
