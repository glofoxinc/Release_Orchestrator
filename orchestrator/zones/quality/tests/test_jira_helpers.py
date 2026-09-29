"""Tests for pure helper functions in jira_client.py (no actual API calls)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")

import config
from jira_client import (
    ParsedDeployment,
    build_deployment_comment_adf,
    extract_ticket_info,
    group_issues_by_assignee,
    group_issues_by_client,
    match_deployments_to_tickets,
)

# ── build_deployment_comment_adf ──────────────────────────────────────

class TestBuildDeploymentCommentAdf:
    def test_structure_has_doc_type(self):
        adf = build_deployment_comment_adf("April 14 2026", "10:39 AM IST", "abc-123")
        assert adf["type"] == "doc"
        assert adf["version"] == 1
        assert len(adf["content"]) == 3

    def test_contains_deployment_date_and_time(self):
        adf = build_deployment_comment_adf("April 14 2026", "10:39 AM IST", "abc-123")
        first_para = adf["content"][0]["content"][0]["text"]
        assert "April 14 2026" in first_para
        assert "10:39 AM IST" in first_para

    def test_contains_deployment_id(self):
        adf = build_deployment_comment_adf("April 14 2026", "10:39 AM IST", "deploy-xyz")
        id_para = adf["content"][2]["content"]
        texts = [item["text"] for item in id_para]
        assert "deploy-xyz" in texts

    def test_deployment_id_label_is_bold(self):
        adf = build_deployment_comment_adf("April 14 2026", "10:39 AM IST", "id-1")
        label_node = adf["content"][2]["content"][0]
        assert label_node["text"] == "Deployment ID: "
        assert any(m["type"] == "strong" for m in label_node.get("marks", []))


# ── extract_ticket_info ───────────────────────────────────────────────

class TestExtractTicketInfo:
    def test_standard_project(self):
        with patch.object(config, "PROJECTS", [{"key": "AN", "multi_client": False}]):
            info = extract_ticket_info("Monthly report - Fix data issue", "AN-100")
            assert info["type"] == "Analyze"
            assert info["client"] == "Standard"
            assert info["report"] == "Monthly report"
            assert info["description"] == "Fix data issue"

    def test_multi_client_project(self):
        with patch.object(config, "PROJECTS", [{"key": "PIC", "multi_client": True}]):
            info = extract_ticket_info("Jetts - Monthly report - Fix data", "PIC-200")
            assert info["type"] == "Custom"
            assert info["client"] == "Jetts"
            assert info["report"] == "Monthly report"

    def test_multi_client_single_segment(self):
        with patch.object(config, "PROJECTS", [{"key": "PIC", "multi_client": True}]):
            info = extract_ticket_info("Stand-alone summary", "PIC-300")
            assert info["type"] == "Custom"

    def test_unknown_project_defaults_analyze(self):
        with patch.object(config, "PROJECTS", []):
            info = extract_ticket_info("Something - here", "ZZZ-1")
            assert info["type"] == "Analyze"


# ── group_issues_by_assignee ─────────────────────────────────────────

class TestGroupIssuesByAssignee:
    def test_groups_by_display_name(self):
        issues = [
            {"key": "T-1", "fields": {"assignee": {"displayName": "Alice"}}},
            {"key": "T-2", "fields": {"assignee": {"displayName": "Bob"}}},
            {"key": "T-3", "fields": {"assignee": {"displayName": "Alice"}}},
        ]
        groups = group_issues_by_assignee(issues)
        assert len(groups["Alice"]) == 2
        assert len(groups["Bob"]) == 1

    def test_unassigned_tickets(self):
        issues = [
            {"key": "T-1", "fields": {"assignee": None}},
            {"key": "T-2", "fields": {"assignee": {"displayName": "Alice"}}},
        ]
        groups = group_issues_by_assignee(issues)
        assert "Unassigned" in groups
        assert len(groups["Unassigned"]) == 1

    def test_sorted_alphabetically(self):
        issues = [
            {"key": "T-1", "fields": {"assignee": {"displayName": "Zara"}}},
            {"key": "T-2", "fields": {"assignee": {"displayName": "Alice"}}},
        ]
        groups = group_issues_by_assignee(issues)
        assert list(groups.keys()) == ["Alice", "Zara"]


# ── group_issues_by_client ───────────────────────────────────────────

class TestGroupIssuesByClient:
    def test_groups_by_client_prefix(self):
        issues = [
            {"key": "PIC-1", "fields": {"summary": "Jetts - Report A"}},
            {"key": "PIC-2", "fields": {"summary": "XPO - Dashboard"}},
            {"key": "PIC-3", "fields": {"summary": "Jetts - Report B"}},
        ]
        groups = group_issues_by_client(issues)
        assert len(groups["Jetts"]) == 2
        assert len(groups["XPO"]) == 1

    def test_unknown_when_no_separator(self):
        issues = [{"key": "AN-1", "fields": {"summary": "No dash here"}}]
        groups = group_issues_by_client(issues)
        assert "Unknown" in groups


# ── match_deployments_to_tickets ─────────────────────────────────────

class TestMatchDeploymentsToTickets:
    def test_matches_and_assigns_keys(self):
        parsed = [
            ParsedDeployment(client="Jetts", deployment_id="abc", deployment_date="", deployment_time=""),
        ]
        grouped = {"Jetts": [{"key": "PIC-1"}, {"key": "PIC-2"}]}
        result = match_deployments_to_tickets(parsed, grouped)
        assert result[0].matched_jira_client == "Jetts"
        assert result[0].ticket_keys == ["PIC-1", "PIC-2"]

    def test_sets_error_when_no_match(self):
        parsed = [
            ParsedDeployment(client="NoSuchClient", deployment_id="abc", deployment_date="", deployment_time=""),
        ]
        result = match_deployments_to_tickets(parsed, {"Jetts": [{"key": "PIC-1"}]})
        assert result[0].error
        assert "No matching" in result[0].error

    def test_question_marks_client_no_error(self):
        parsed = [
            ParsedDeployment(client="???", deployment_id="abc", deployment_date="", deployment_time=""),
        ]
        result = match_deployments_to_tickets(parsed, {"Jetts": [{"key": "PIC-1"}]})
        assert result[0].error == ""
