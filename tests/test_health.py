"""Tests for setup health checks."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")

import config
from release_platform.ui.health import collect_setup_issues


class TestCollectSetupIssues:
    def test_reports_missing_projects(self):
        with patch.object(config, "PROJECTS", []), \
             patch.object(config, "JIRA_API_TOKEN", "real-token"), \
             patch.object(config, "JIRA_EMAIL", "a@b.com"), \
             patch.object(config, "SLACK_ANNOUNCE", {"enabled": False}), \
             patch.object(config, "CONFIG_WARNINGS", []):
            titles = [i.title for i in collect_setup_issues()]
        assert "No Jira projects configured" in titles

    def test_reports_shipit_incomplete_when_sd_enabled(self):
        with patch.object(config, "SERVICE_DESK_ENABLED", True), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", ""), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", ""), \
             patch.object(config, "TCKT_ISSUE_TYPE_ID", ""), \
             patch.object(config, "TCKT_FIELDS", {}), \
             patch.object(config, "TCKT_DEFAULTS", {"approver_groups": []}), \
             patch.object(config, "PROJECTS", [{"key": "PIC", "scope": {"allow_project_wide": True}}]), \
             patch.object(config, "JIRA_API_TOKEN", "real-token"), \
             patch.object(config, "JIRA_EMAIL", "a@b.com"), \
             patch.object(config, "SLACK_ANNOUNCE", {"enabled": False}), \
             patch.object(config, "CONFIG_WARNINGS", []):
            titles = [i.title for i in collect_setup_issues()]
        assert "SHIPIT configuration incomplete" in titles

    def test_all_good_when_configured(self):
        with patch.object(config, "PROJECTS", [{
            "key": "PIC",
            "scope": {"allow_project_wide": True},
        }]), \
             patch.object(config, "SERVICE_DESK_ENABLED", True), \
             patch.object(config, "TCKT_SERVICE_DESK_ID", "1"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "2"), \
             patch.object(config, "TCKT_ISSUE_TYPE_ID", "10502"), \
             patch.object(config, "TCKT_FIELDS", {"approver_groups": "customfield_1"}), \
             patch.object(config, "TCKT_DEFAULTS", {"approver_groups": [{"name": "Approvers"}]}), \
             patch.object(config, "JIRA_API_TOKEN", "real-token-value"), \
             patch.object(config, "JIRA_EMAIL", "a@b.com"), \
             patch.object(config, "SLACK_ANNOUNCE", {"enabled": False}), \
             patch.object(config, "CONFIG_WARNINGS", []):
            issues = collect_setup_issues()
        assert any(i.title == "Setup looks good" for i in issues)
