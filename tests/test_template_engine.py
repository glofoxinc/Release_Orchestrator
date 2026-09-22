"""Tests for the Jinja2 template engine."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from template_engine import render_template


class TestDeploymentCommentTemplate:
    def test_renders_all_variables(self):
        result = render_template(
            "default/deployment_comment.j2",
            environment="Production",
            deployment_date="April 14 2026",
            deployment_time="10:39 AM IST",
            deployment_id="abc-123",
        )
        assert "Production" in result
        assert "April 14 2026" in result
        assert "10:39 AM IST" in result
        assert "abc-123" in result

    def test_deployment_comment_structure(self):
        result = render_template(
            "default/deployment_comment.j2",
            environment="UAT",
            deployment_date="March 01 2026",
            deployment_time="2:00 PM UTC",
            deployment_id="xyz-789",
        )
        assert "deployed to UAT" in result
        assert "Deployment ID: xyz-789" in result


class TestServiceTicketSummaryTemplate:
    def test_renders_summary(self):
        result = render_template(
            "default/service_ticket_summary.j2",
            environment="Production",
            team_name="Analytics",
            version_name="v2.1",
        )
        assert "Production" in result
        assert "Analytics" in result
        assert "v2.1" in result

    def test_summary_format(self):
        result = render_template(
            "default/service_ticket_summary.j2",
            environment="Staging",
            team_name="Data",
            version_name="v1.0",
        )
        assert "Deployment" in result
        assert "Data" in result


class TestReviewFormatTemplate:
    def test_renders_grouped_issues(self):
        grouped = {
            "Alice": [
                {"key": "PIC-1", "fields": {"summary": "Fix login bug"}},
                {"key": "PIC-2", "fields": {"summary": "Update dashboard"}},
            ],
        }
        result = render_template(
            "default/review_format.j2",
            grouped=grouped,
            base_url="https://jira.example.com",
        )
        assert "Alice" in result
        assert "PIC-1" in result
        assert "PIC-2" in result
        assert "https://jira.example.com/browse/PIC-1" in result
        assert "Fix login bug" in result

    def test_multiple_owners(self):
        grouped = {
            "Alice": [{"key": "PIC-1", "fields": {"summary": "Task A"}}],
            "Bob": [{"key": "PIC-2", "fields": {"summary": "Task B"}}],
        }
        result = render_template(
            "default/review_format.j2",
            grouped=grouped,
            base_url="https://jira.example.com",
        )
        assert "Alice" in result
        assert "Bob" in result
