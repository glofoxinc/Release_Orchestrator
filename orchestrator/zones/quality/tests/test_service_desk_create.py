"""Tests for Service Desk change-ticket create (Request Type at creation time)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

import config
import jira_client
from jira_client import RequestTypeStatus


class TestBuildServiceDeskRequestFieldValues:
    def test_summary_only_mode_sends_summary_only(self):
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "summary_only"), \
             patch.object(config, "TCKT_FIELDS", {
                 "implementation_steps": "customfield_11720",
                 "business_impact": "customfield_14549",
             }):
            out = jira_client._build_service_desk_request_field_values(
                "Production Deployment – Test",
                {
                    "description": {"type": "doc", "version": 1, "content": []},
                    "customfield_11720": {"type": "doc", "version": 1, "content": []},
                    "customfield_14549": {"type": "doc", "version": 1, "content": []},
                },
            )
        assert out == {"summary": "Production Deployment – Test"}

    def test_flattens_every_rich_text_field_including_description(self):
        """The request form declares these as type: string, so ADF must not be sent."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Step one"}],
                }
            ],
        }
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_FIELDS", {
            "implementation_plan": "customfield_11760",
            "business_impact": "customfield_14549",
            "approvers": "customfield_11752",
        }):
            out = jira_client._build_service_desk_request_field_values(
                "Summary",
                {
                    "description": adf,
                    "customfield_11760": adf,
                    "customfield_14549": adf,
                    "customfield_11752": [{"accountId": "abc"}],
                },
            )
        assert out["summary"] == "Summary"
        assert out["description"] == "Step one"
        assert out["customfield_11760"] == "Step one"
        assert out["customfield_14549"] == "Step one"
        # Approvers are not on the request form at all.
        assert "customfield_11752" not in out

    def test_keeps_fields_the_request_form_requires(self):
        """Assignment Group, Affects PF and Outage Required are required on create."""
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_FIELDS", {
            "assignment_group": "customfield_13073",
            "affects_pf": "customfield_13074",
            "outage_required": "customfield_13075",
            "change_type": "customfield_11757",
        }):
            out = jira_client._build_service_desk_request_field_values(
                "Summary",
                {
                    "customfield_13073": {"id": "12712"},
                    "customfield_13074": [{"id": "12660"}],
                    "customfield_13075": [{"id": "12659"}],
                    "customfield_11757": {"id": "10905"},
                    "priority": {"name": "Medium"},
                },
            )
        assert out["customfield_13073"] == {"id": "12712"}
        assert out["customfield_13074"] == [{"id": "12660"}]
        assert out["customfield_13075"] == [{"id": "12659"}]
        # Change type and priority are not on the request form.
        assert "customfield_11757" not in out
        assert "priority" not in out

    def test_no_adf_flag_is_sent(self):
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "summary_only"), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", "2046"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "2969"), \
             patch.object(config, "TCKT_FIELDS", {}), \
             patch("jira_client._sd_post", return_value={"issueKey": "SHIPIT-1"}) as mock_post:
            jira_client.create_service_desk_request("Summary", {})

        body = mock_post.call_args.args[1]
        assert body["requestFieldValues"] == {"summary": "Summary"}
        assert "isAdfRequest" not in body


class TestBuildSupplementalTcktFields:
    def test_restores_adf_for_description_and_plans(self):
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Impact"}]}
            ],
        }
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_FIELDS", {
            "business_impact": "customfield_14549",
            "implementation_plan": "customfield_11760",
        }):
            out = jira_client._build_supplemental_tckt_fields({
                "description": adf,
                "customfield_14549": adf,
                "customfield_11760": adf,
            })
        assert out["description"] == adf
        assert out["customfield_14549"] == adf
        assert out["customfield_11760"] == adf

    def test_includes_approvers_team_and_change_type(self):
        fields = {
            "priority": {"name": "Medium"},
            "customfield_11752": [{"accountId": "abc"}],
            "customfield_11794": [{"name": "Command Center"}],
            "customfield_10700": "team-uuid",
            "customfield_11757": {"id": "10905"},
        }
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_FIELDS", {
            "approvers": "customfield_11752",
            "approver_groups": "customfield_11794",
            "team": "customfield_10700",
            "change_type": "customfield_11757",
        }):
            out = jira_client._build_supplemental_tckt_fields(fields)
        assert out["priority"] == {"name": "Medium"}
        assert out["customfield_11752"] == [{"accountId": "abc"}]
        assert out["customfield_10700"] == "team-uuid"
        assert out["customfield_11757"] == {"id": "10905"}


class TestNormalizeTeamValue:
    def test_string_stays_plain_uuid(self):
        # Object form is rejected by abcfinancial's atlassian-team field on edit.
        assert jira_client._normalize_team_value("abc-123") == "abc-123"

    def test_dict_unwraps_to_plain_id(self):
        assert jira_client._normalize_team_value({"id": "abc"}) == "abc"


class TestSupplementalEditBatches:
    def test_shipit_summary_only_batches(self):
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "summary_only"), \
             patch.object(config, "TCKT_FIELDS", {
            "implementation_steps": "customfield_11720",
            "verification_steps": "customfield_11721",
            "rollback_steps": "customfield_11722",
            "business_impact": "customfield_14549",
            "communication_plan": "customfield_11717",
            "reason_for_change": "customfield_11715",
            "approver_groups": "customfield_11794",
            "change_type": "customfield_11757",
        }):
            batches = jira_client._supplemental_edit_batches({
                "description": {"type": "doc", "version": 1, "content": []},
                "customfield_11720": {"type": "doc", "version": 1, "content": []},
                "customfield_11721": {"type": "doc", "version": 1, "content": []},
                "customfield_11717": {"type": "doc", "version": 1, "content": []},
                "customfield_11715": "Reason text",
                "customfield_11794": [{"name": "Insights Customize Approvers"}],
                "customfield_11757": {"id": "21532"},
            })
        labels = [label for label, _ in batches]
        assert "description ADF" in labels
        assert "communication plan / reason for change" in labels
        assert "approvals / schedule / classification" in labels
        assert "approvers / groups / change type" not in labels

    def test_team_is_isolated_from_approvers(self):
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_FIELDS", {
            "approvers": "customfield_11752",
            "approver_groups": "customfield_11794",
            "team": "customfield_10700",
            "change_type": "customfield_11757",
            "business_impact": "customfield_14549",
            "assignment_group": "customfield_13073",
        }):
            batches = jira_client._supplemental_edit_batches({
                "customfield_11752": [{"accountId": "a"}],
                "customfield_11794": [{"name": "Command Center"}],
                "customfield_10700": "team-uuid",
                "customfield_11757": {"id": "10905"},
                "customfield_14549": {"type": "doc", "version": 1, "content": []},
                "priority": {"name": "Medium"},
            })
        labels = [label for label, _ in batches]
        assert "approvers / groups / change type" in labels
        assert "team" in labels
        assert "plans / description ADF" in labels
        team_batch = next(b for label, b in batches if label == "team")
        assert team_batch == {"customfield_10700": "team-uuid"}
        assert "customfield_10700" not in next(
            b for label, b in batches if label.startswith("approvers")
        )

    def test_apply_continues_after_team_failure(self):
        with patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_FIELDS", {
            "approvers": "customfield_11752",
            "team": "customfield_10700",
            "change_type": "customfield_11757",
        }), \
             patch("jira_client.edit_issue") as mock_edit:
            mock_edit.side_effect = [
                True,  # approvers batch
                jira_client.JiraApiError("bad team", status_code=400),
            ]
            warnings = jira_client.apply_supplemental_tckt_fields(
                "TCKT-1",
                {
                    "customfield_11752": [{"accountId": "a"}],
                    "customfield_11757": {"id": "10905"},
                    "customfield_10700": "team-uuid",
                },
            )
        assert mock_edit.call_count == 2
        assert any("team" in w.lower() for w in warnings)
        first_batch = mock_edit.call_args_list[0].args[1]
        assert "customfield_11752" in first_batch
        assert "customfield_10700" not in first_batch


class TestCreateTcktIssue:
    def test_uses_service_desk_create_when_configured(self):
        fields = {
            "description": {"type": "doc", "version": 1, "content": []},
            "customfield_11752": [{"accountId": "abc"}],
            "customfield_10700": "team-uuid",
        }
        with patch.object(config, "SERVICE_DESK_ENABLED", True), \
             patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", "15"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"), \
             patch.object(config, "TCKT_REQUEST_TYPE_NAME", "Submit A Normal or Emergency Change"), \
             patch.object(config, "TCKT_FIELDS", {
                 "assignment_group": "customfield_13073",
                 "affects_pf": "customfield_13074",
                 "outage_required": "customfield_13075",
                 "approvers": "customfield_11752",
                 "approver_groups": "customfield_11794",
                 "team": "customfield_10700",
                 "change_type": "customfield_11757",
             }), \
             patch.object(config, "TCKT_DEFAULTS", {
                 "assignment_group": {"id": "12712"},
                 "affects_pf": [{"id": "12660"}],
                 "outage_required": [{"id": "12659"}],
                 "team": "team-uuid",
             }), \
             patch("jira_client.validate_service_desk_create_payload", return_value=[]), \
             patch("jira_client.create_service_desk_request") as mock_sd, \
             patch("jira_client.edit_issue") as mock_edit:
            mock_sd.return_value = {"issueKey": "TCKT-999"}
            result, rt = jira_client.create_tckt_issue("Deploy v1", fields)

        assert result["key"] == "TCKT-999"
        assert rt.ok
        mock_sd.assert_called_once()
        assert mock_edit.call_count >= 2  # approvers batch + team batch (isolated)
        edited: dict = {}
        for call in mock_edit.call_args_list:
            edited.update(call.args[1])
        assert edited["customfield_11752"] == [{"accountId": "abc"}]
        assert edited["customfield_10700"] == "team-uuid"
        call_fields = mock_sd.call_args.args[1]
        assert call_fields["customfield_13073"] == {"id": "12712"}
        sd_values = jira_client._build_service_desk_request_field_values("Deploy v1", call_fields)
        assert "customfield_10700" not in sd_values
        assert "customfield_11752" not in sd_values

    def _sd_configured(self):
        return (
            patch.object(config, "SERVICE_DESK_ENABLED", True),
            patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"),
            patch.object(config, "TCKT_SERVICE_DESK_ID", "15"),
            patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"),
            patch.object(config, "TCKT_FIELDS", {"affected_services": "customfield_11754"}),
            patch.object(config, "TCKT_DEFAULTS", {}),
            patch("jira_client.validate_service_desk_create_payload", return_value=[]),
        )

    def test_retries_without_fields_the_request_form_rejected(self):
        fields = {
            "description": {"type": "doc", "version": 1, "content": []},
            "customfield_11754": [{"id": "ari:cloud:graph::service/x"}],
        }
        rejection = jira_client.JiraApiError(
            "Jira rejected the request (HTTP 400).",
            status_code=400,
            field_errors={"customfield_11754": "Field cannot be set."},
        )
        sd1, sd2, sd3, sd4, sd5, sd6, sd7 = self._sd_configured()
        with sd1, sd2, sd3, sd4, sd5, sd6, sd7, \
             patch(
                 "jira_client.create_service_desk_request",
                 side_effect=[rejection, {"issueKey": "TCKT-500"}],
             ) as mock_sd, \
             patch("jira_client.edit_issue") as mock_edit:
            result, rt = jira_client.create_tckt_issue("Deploy v1", fields)

        assert result["key"] == "TCKT-500"
        assert rt.ok
        assert mock_sd.call_count == 2
        retry_fields = mock_sd.call_args_list[1].args[1]
        assert "customfield_11754" not in retry_fields
        # The rejected value is still applied, just after creation.
        assert mock_edit.call_args.args[1]["customfield_11754"] == fields["customfield_11754"]

    def test_required_field_rejection_is_not_deferred(self):
        """Dropping a required field from the retry only trades one 400 for another."""
        rejection = jira_client.JiraApiError(
            "Please provide a value for required field 'Business Impact'",
            status_code=400,
            field_errors={
                "customfield_14549": "Please provide a value for required field",
            },
        )
        sd1, sd2, sd3, sd4, sd5, sd6, sd7 = self._sd_configured()
        with sd1, sd2, sd3, sd4, sd5, sd6, sd7, \
             patch(
                 "jira_client.create_service_desk_request", side_effect=rejection,
             ) as mock_sd, \
             pytest.raises(jira_client.JiraApiError, match="required field"):
            jira_client.create_tckt_issue("Deploy v1", {"customfield_14549": "x"})

        assert mock_sd.call_count == 1

    def test_retry_failure_reports_the_original_error(self):
        first = jira_client.JiraApiError(
            "Field with id 'customfield_11754' has these errors : []",
            status_code=400,
            field_errors={"customfield_11754": "has these errors : []"},
        )
        second = jira_client.JiraApiError("something else entirely", status_code=400)
        sd1, sd2, sd3, sd4, sd5, sd6, sd7 = self._sd_configured()
        with sd1, sd2, sd3, sd4, sd5, sd6, sd7, \
             patch(
                 "jira_client.create_service_desk_request",
                 side_effect=[first, second],
             ), \
             pytest.raises(jira_client.JiraApiError, match="has these errors"):
            jira_client.create_tckt_issue(
                "Deploy v1", {"customfield_11754": [{"id": "svc"}]},
            )

    def test_400_without_named_fields_is_raised(self):
        rejection = jira_client.JiraApiError(
            "Jira rejected the request (HTTP 400).", status_code=400,
        )
        sd1, sd2, sd3, sd4, sd5, sd6, sd7 = self._sd_configured()
        with sd1, sd2, sd3, sd4, sd5, sd6, sd7, \
             patch(
                 "jira_client.create_service_desk_request", side_effect=rejection,
             ) as mock_sd, \
             pytest.raises(jira_client.JiraApiError, match="HTTP 400"):
            jira_client.create_tckt_issue("Deploy v1", {})

        assert mock_sd.call_count == 1

    def test_failed_post_create_edit_still_returns_the_ticket_key(self):
        """A follow-up edit failure must never look like a create failure."""
        sd1, sd2, sd3, sd4, sd5, sd6, sd7 = self._sd_configured()
        with sd1, sd2, sd3, sd4, sd5, sd6, sd7, \
             patch(
                 "jira_client.create_service_desk_request",
                 return_value={"issueKey": "TCKT-501"},
             ), \
             patch(
                 "jira_client.edit_issue",
                 side_effect=jira_client.JiraApiError("edit blew up"),
             ):
            result, rt = jira_client.create_tckt_issue(
                "Deploy v1", {"priority": {"name": "Medium"}},
            )

        assert result["key"] == "TCKT-501"
        assert rt.ok
        assert "edit blew up" in result["supplementalWarning"]

    def test_preflight_blocks_create_before_api_call(self):
        sd1, sd2, sd3, sd4, sd5, sd6, sd7 = self._sd_configured()
        with sd1, sd2, sd3, sd4, sd5, \
             patch(
                 "jira_client.validate_service_desk_create_payload",
                 return_value=["Required form field is missing: Business Impact"],
             ), \
             patch("jira_client.create_service_desk_request") as mock_sd, \
             pytest.raises(jira_client.JiraApiError, match="preflight"):
            jira_client.create_tckt_issue("Deploy v1", {})

        mock_sd.assert_not_called()

    def test_falls_back_to_plain_create_when_sd_not_configured(self):
        with patch.object(config, "SERVICE_DESK_ENABLED", False), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", ""), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", ""), \
             patch("jira_client.create_issue", return_value={"key": "TCKT-1"}) as mock_create, \
             patch(
                 "jira_client.set_request_type_detailed",
                 return_value=RequestTypeStatus(RequestTypeStatus.DISABLED, "missing"),
             ) as mock_rt:
            result, rt = jira_client.create_tckt_issue("Deploy v1", {})

        mock_create.assert_called_once()
        mock_rt.assert_called_once_with("TCKT-1")
        assert result["key"] == "TCKT-1"
        assert rt.status == RequestTypeStatus.DISABLED


class TestValidateServiceDeskCreatePayload:
    def _form_fields(self):
        return [
            {"fieldId": "summary", "name": "Change Summary", "required": True,
             "jiraSchema": {"type": "string"}},
            {"fieldId": "description", "name": "Full change description", "required": True,
             "jiraSchema": {"type": "string"}},
            {"fieldId": "customfield_14549", "name": "Business Impact", "required": True,
             "jiraSchema": {"type": "string"}},
            {"fieldId": "customfield_13073", "name": "Assignment Group", "required": True,
             "jiraSchema": {"type": "option"},
             "validValues": [{"value": "12712", "label": "Insights Analyze/Customize"}]},
            {"fieldId": "attachment", "name": "Attachment", "required": False},
        ]

    def test_reports_missing_required_fields(self):
        with patch.object(config, "SERVICE_DESK_ENABLED", True), \
             patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", "15"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"), \
             patch.object(config, "TCKT_FIELDS", {
                 "business_impact": "customfield_14549",
                 "assignment_group": "customfield_13073",
                 "approvers": "customfield_11752",
             }), \
             patch("jira_client.get_request_type_fields", return_value=self._form_fields()):
            problems = jira_client.validate_service_desk_create_payload(
                "Deploy",
                {"description": {"type": "doc", "version": 1, "content": []}},
            )

        joined = "\n".join(problems)
        assert "Business Impact" in joined
        assert "Assignment Group" in joined

    def test_passes_when_all_required_fields_present(self):
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Impact"}]}
            ],
        }
        with patch.object(config, "SERVICE_DESK_ENABLED", True), \
             patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", "15"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"), \
             patch.object(config, "TCKT_FIELDS", {
                 "business_impact": "customfield_14549",
                 "assignment_group": "customfield_13073",
                 "approvers": "customfield_11752",
             }), \
             patch("jira_client.get_request_type_fields", return_value=self._form_fields()):
            problems = jira_client.validate_service_desk_create_payload(
                "Deploy",
                {
                    "description": adf,
                    "customfield_14549": adf,
                    "customfield_13073": {"id": "12712"},
                },
            )

        assert problems == []

    def test_summary_only_preflight_checks_summary_only(self):
        with patch.object(config, "SERVICE_DESK_ENABLED", True), \
             patch.object(config, "SERVICE_DESK_CREATE_MODE", "summary_only"), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", "2046"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "2969"), \
             patch("jira_client.get_request_type_fields", return_value=self._form_fields()):
            missing = jira_client.validate_service_desk_create_payload("", {})
            ok = jira_client.validate_service_desk_create_payload(
                "Deploy",
                {"customfield_11720": {"type": "doc", "version": 1, "content": []}},
            )

        assert any("Summary is required" in p for p in missing)
        assert ok == []

    def test_rejects_invalid_option_ids(self):
        with patch.object(config, "SERVICE_DESK_ENABLED", True), \
             patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", "15"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"), \
             patch.object(config, "TCKT_FIELDS", {
                 "assignment_group": "customfield_13073",
                 "approvers": "customfield_11752",
             }), \
             patch("jira_client.get_request_type_fields", return_value=self._form_fields()):
            problems = jira_client.validate_service_desk_create_payload(
                "Deploy",
                {
                    "description": "desc",
                    "customfield_14549": "impact",
                    "customfield_13073": {"id": "99999"},
                },
            )

        assert any("invalid option" in p for p in problems)

    def test_skipped_when_service_desk_disabled(self):
        with patch.object(config, "SERVICE_DESK_ENABLED", False):
            assert jira_client.validate_service_desk_create_payload("x", {}) == []


class TestFindTcktBySummary:
    SUMMARY = "Production Deployment - Glofox - Report Updates (v2026.8.03)"

    def _issues(self, *summaries: str) -> dict:
        return {
            "issues": [
                {"key": f"TCKT-{i}", "fields": {"summary": s}}
                for i, s in enumerate(summaries, start=1)
            ]
        }

    def test_finds_matching_summary_ignoring_case_and_padding(self):
        with patch("jira_client._post", return_value=self._issues(self.SUMMARY.upper())):
            found = jira_client.find_tckt_by_summary(f"  {self.SUMMARY}  ")
        assert found["key"] == "TCKT-1"

    def test_returns_none_when_nothing_matches(self):
        with patch("jira_client._post", return_value=self._issues("Something else")):
            assert jira_client.find_tckt_by_summary(self.SUMMARY) is None

    def test_returns_none_for_blank_summary_without_querying(self):
        with patch("jira_client._post") as mock_post:
            assert jira_client.find_tckt_by_summary("   ") is None
        mock_post.assert_not_called()

    def test_query_is_scoped_to_reporter_and_recent_window(self):
        with patch("jira_client._post", return_value={"issues": []}) as mock_post, \
             patch.object(config, "TCKT_PROJECT_KEY", "TCKT"):
            jira_client.find_recent_tckt_issues(within_minutes=15)

        jql = mock_post.call_args.args[1]["jql"]
        assert "project = TCKT" in jql
        assert "reporter = currentUser()" in jql
        assert "created >= -15m" in jql

    def test_handles_empty_response_body(self):
        with patch("jira_client._post", return_value=None):
            assert jira_client.find_recent_tckt_issues() == []


class TestGetIssueRequestTypeId:
    def test_reads_request_type_from_sd_api(self):
        with patch("jira_client._sd_get", return_value={"requestTypeId": "1223"}):
            assert jira_client.get_issue_request_type_id("TCKT-1") == "1223"

    def test_reads_nested_request_type_object(self):
        with patch("jira_client._sd_get", return_value={"requestType": {"id": "1223"}}):
            assert jira_client.get_issue_request_type_id("TCKT-1") == "1223"

    def test_returns_none_on_failure(self):
        with patch("jira_client._sd_get", side_effect=jira_client.JiraApiError("x")):
            assert jira_client.get_issue_request_type_id("TCKT-1") is None
