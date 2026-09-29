"""SHIPIT test/demo ticket mode and disposal."""

from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import patch

import config
import jira_client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")


def test_is_test_shipit_summary_markers():
    from shipit_test_mode import is_test_shipit_summary, merge_test_draft

    assert is_test_shipit_summary(
        "TEST SHIPIT Demo Validation - Insights Customize BI - DO NOT DEPLOY (v2026.3.09.11)"
    )
    assert not is_test_shipit_summary(
        "Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.09"
    )
    draft = merge_test_draft({
        "approver_groups": [{"name": "Insights Customize Approvers"}],
        "approvers": [{"accountId": "person"}],
        "team": "team-id",
        "assignment_group": {"name": "group"},
        "affected_services": [{"id": "service"}],
    })
    assert draft["approver_groups"] == []
    assert draft["approvers"] == []
    assert draft["team"] is None
    assert draft["assignment_group"] is None
    assert draft["affected_services"] == []


def test_parse_release_version_date_standard_shape():
    from shipit_test_mode import parse_release_version_date

    assert parse_release_version_date("2026.3.09.11") == date(2026, 9, 11)
    assert parse_release_version_date("not-a-version") is None


def test_create_tckt_issue_skips_team_defaults_for_test_summary():
    fields = {
        "description": {"type": "doc", "version": 1, "content": []},
    }
    summary = "TEST SHIPIT Demo Validation - DO NOT DEPLOY (v2026.3.09.11)"
    with patch.object(config, "SERVICE_DESK_ENABLED", True), \
         patch.object(config, "SERVICE_DESK_CREATE_MODE", "summary_only"), \
         patch.object(config, "TCKT_SERVICE_DESK_ID", "2046"), \
         patch.object(config, "TCKT_REQUEST_TYPE_ID", "2969"), \
         patch.object(config, "TCKT_REQUEST_TYPE_NAME", "Manual Change"), \
         patch.object(config, "TCKT_FIELDS", {
             "team": "customfield_10700",
             "assignment_group": "customfield_13073",
             "approver_groups": "customfield_11794",
             "affected_services": "customfield_11754",
         }), \
         patch.object(config, "TCKT_DEFAULTS", {
             "team": "team-uuid",
             "assignment_group": {"name": "Command Center"},
             "approver_groups": [{"name": "Insights Customize Approvers"}],
             "affected_services": [{"id": "glofox-service"}],
         }), \
         patch("jira_client.validate_service_desk_create_payload", return_value=[]), \
         patch("jira_client.create_service_desk_request") as mock_sd, \
         patch("jira_client.apply_supplemental_tckt_fields", return_value=[]) as mock_supp:
        mock_sd.return_value = {"issueKey": "SHIPIT-999"}
        result, _rt = jira_client.create_tckt_issue(summary, fields)

    assert result["key"] == "SHIPIT-999"
    supplemental_call = mock_supp.call_args.args[1]
    assert "customfield_10700" not in supplemental_call
    assert "customfield_11794" not in supplemental_call
    assert "customfield_11754" not in supplemental_call


def test_release_ops_test_mode_uses_version_date_for_schedule():
    from release_mcp import release_ops

    sample = [{
        "ticket": "AN-TEST",
        "type": "Analyze",
        "client": "Standard",
        "report": "New Members",
        "description": "demo",
    }]
    with patch.object(
        release_ops,
        "build_summary_from_reference_pattern",
        return_value="Production Deployment",
    ), patch.object(release_ops, "parse_fix_version_date", return_value=date(2026, 11, 11)):
        result = release_ops.create_service_ticket(
            "2026.3.09.11",
            sharepoint_url="https://example.com/Release%20Notes.docx",
            dry_run=True,
            test_mode=True,
            extracted_override=sample,
            draft_overrides={"summary": "TEST SHIPIT Demo - DO NOT DEPLOY (v2026.3.09.11)"},
        )
    assert result["status"] == "dry_run"
    assert result.get("test_mode") is True
    # Test SHIPIT still uses the release-notes version date, not today.
    assert "2026-09-11" in result["planned_start"]
    assert "Sep 11, 2026" in (result.get("deployment_window") or "")


def test_dispose_test_shipit_blocks_production_summary():
    with patch("jira_client.get_issue") as mock_get:
        mock_get.return_value = {
            "fields": {"summary": "Glofox - Insights Customize BI - Prod Deployment"},
        }
        out = jira_client.dispose_test_shipit_ticket("SHIPIT-1")
    assert out["status"] == "blocked"


def test_validate_fix_version_rejects_bad_shape():
    from shipit_test_mode import validate_fix_version_name

    ok, err = validate_fix_version_name("2026.9.11.11")
    assert not ok
    assert err and ("quarter" in err.lower() or "2026.3.09.11" in err)


def test_prod_summary_in_release_ops_dry_run():
    from release_mcp import release_ops

    sample = [{
        "ticket": "AN-1",
        "type": "Analyze",
        "client": "Standard",
        "report": "New Members",
        "description": "fix",
    }]
    result = release_ops.create_service_ticket(
        "2026.3.09.11",
        sharepoint_url="https://example.com/Release%20Notes.docx",
        dry_run=True,
        extracted_override=sample,
    )
    assert result["status"] == "dry_run"
    assert "Glofox Insights Customize BI - Prod Deployment" in result["summary"]
    assert result.get("test_mode") is False
    assert "cab_quality" in result
    assert result["cab_quality"]["total"] > 0


def test_test_mode_excludes_affected_services_from_create_payload():
    from release_mcp import release_ops

    sample = [{
        "ticket": "AN-TEST",
        "type": "Analyze",
        "client": "Standard",
        "report": "New Members",
        "description": "demo",
    }]
    captured_fields = {}

    def mock_create(summary, fields):
        captured_fields.update(fields)
        return {"key": "SHIPIT-TEST"}, type("RT", (), {"to_dict": lambda s: {"status": "ok"}})()

    with patch("jira_client.create_tckt_issue", mock_create):
        release_ops.create_service_ticket(
            "2026.3.09.11",
            sharepoint_url="https://example.com/Release%20Notes.docx",
            dry_run=False,
            test_mode=True,
            extracted_override=sample,
        )

    assert config.TCKT_FIELDS["affected_services"] not in captured_fields


def test_prod_shipit_payload_uses_release_specific_plans():
    from adf_builder import adf_to_plain_text
    from generators.release_notes_sample import sample_release_notes_data
    from release_mcp import release_ops

    captured = {}

    def mock_create(summary, fields):
        captured["summary"] = summary
        captured["fields"] = fields
        return {"key": "SHIPIT-PREVIEW"}, type("RT", (), {"to_dict": lambda s: {"status": "ok"}})()

    sample = sample_release_notes_data()["extracted"]
    with patch("jira_client.create_tckt_issue", mock_create), patch(
        "jira_client.add_schedule_window_comment"
    ), patch("jira_client.edit_issue"):
        release_ops.create_service_ticket(
            "2026.3.09.11",
            sharepoint_url="https://abcfinancial.sharepoint.com/release-notes.docx",
            dry_run=False,
            extracted_override=sample,
        )

    fields = captured["fields"]
    cf = config.TCKT_FIELDS
    impl = adf_to_plain_text(fields[config.service_desk_field("implementation_steps")])
    comm = adf_to_plain_text(fields[cf["communication_plan"]])

    assert "Glofox Insights Customize BI - Prod Deployment" in captured["summary"]
    assert fields[cf["reason_for_change"]] == "Production Deployment"
    assert "insights-customize-squad" in comm
    assert "Pre-deployment backups" in impl
    assert "Do not change Production RLS" in impl


def test_rekha_shipit_16769_field_parity():
    """Prod SHIPIT should match SHIPIT-17036 / 16769 field pattern (approver groups only)."""
    from release_mcp import release_ops

    sample = [{
        "ticket": "AN-5516",
        "type": "Analyze",
        "client": "Standard",
        "report": "Visits Analysis",
        "description": "Add Unique Visits column",
    }]

    # Mock the Jira create to capture what fields we send
    captured_fields = {}

    def mock_create(summary, fields):
        captured_fields.update(fields)
        return {"key": "SHIPIT-TEST"}, type("RT", (), {"to_dict": lambda s: {"status": "ok"}})()

    with patch("jira_client.create_tckt_issue", mock_create):
        result = release_ops.create_service_ticket(
            "2026.3.09.14",
            sharepoint_url="https://example.com/Release%20Notes.docx",
            dry_run=False,
            extracted_override=sample,
        )

    # SHIPIT-17036 parity checks:
    # 1. Summary matches Sushma's format
    assert "Glofox Insights Customize BI - Prod Deployment" in result["summary"]

    # 2. Impact/Urgency should NOT be in fields (Rekha leaves these unset)
    cf = config.TCKT_FIELDS
    assert cf.get("impact") not in captured_fields or captured_fields.get(cf.get("impact")) is None
    assert cf.get("urgency") not in captured_fields or captured_fields.get(cf.get("urgency")) is None

    # 3. Change type and risk should be set
    assert cf.get("change_type") in captured_fields
    assert cf.get("change_risk") in captured_fields

    # 4. Team should not be set (Rekha's have team: None)
    # Note: team is handled by jira_client.create_tckt_issue, not in captured_fields

    # 5. Production uses the exact Glofox service from Rekha's SHIPIT-16769
    affected = captured_fields[cf["affected_services"]]
    assert affected == [{
        "id": (
            "ari:cloud:graph::service/551d8872-09ec-11eb-9a52-0a77f3f45304/"
            "28fa658e-0f6f-11f0-a0fc-0afff3dd3477"
        ),
    }]


def test_invalid_version_needs_input():
    from release_mcp import release_ops

    result = release_ops.create_service_ticket(
        "2026.9.11.11",
        sharepoint_url="https://example.com/x.docx",
        dry_run=True,
        extracted_override=[{"ticket": "AN-1", "type": "Analyze", "client": "S", "report": "R", "description": "d"}],
    )
    assert result["status"] == "needs_input"
    assert "version_name" in result.get("missing", [])


def test_dispose_test_shipit_comment_cancel_delete():
    with patch("jira_client.get_issue") as mock_get, \
         patch("jira_client.add_plain_comment", return_value={"id": "c1"}) as mock_comment, \
         patch("jira_client.find_transition_by_name", return_value="31"), \
         patch("jira_client.transition_issue", return_value=True), \
         patch("jira_client.delete_issue", return_value=True) as mock_delete:
        mock_get.return_value = {
            "fields": {"summary": "TEST SHIPIT Demo - DO NOT DEPLOY"},
        }
        out = jira_client.dispose_test_shipit_ticket("SHIPIT-17076")
    assert out["status"] == "deleted"
    mock_comment.assert_called_once()
    mock_delete.assert_called_once_with("SHIPIT-17076")
