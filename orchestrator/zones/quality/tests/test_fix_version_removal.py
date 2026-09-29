"""Tests for fix version removal on issues."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

import jira_client


class TestRemoveFixVersionFromIssue:
    def test_removes_matching_version(self):
        issue = {
            "fields": {
                "fixVersions": [
                    {"id": "100", "name": "Release A"},
                    {"id": "200", "name": "Release B"},
                ]
            }
        }
        with patch("jira_client.edit_issue") as mock_edit:
            removed = jira_client.remove_fix_version_from_issue("PIC-1", "100", issue=issue)

        assert removed is True
        mock_edit.assert_called_once_with(
            "PIC-1",
            {"fixVersions": [{"id": "200"}]},
        )

    def test_returns_false_when_version_not_present(self):
        issue = {"fields": {"fixVersions": [{"id": "200", "name": "Release B"}]}}
        with patch("jira_client.edit_issue") as mock_edit:
            removed = jira_client.remove_fix_version_from_issue("PIC-1", "100", issue=issue)

        assert removed is False
        mock_edit.assert_not_called()

    def test_fetches_issue_when_fix_versions_missing(self):
        with patch("jira_client._get", return_value={"fields": {"fixVersions": [{"id": "100"}]}}), \
             patch("jira_client.edit_issue") as mock_edit:
            removed = jira_client.remove_fix_version_from_issue("PIC-1", "100")

        assert removed is True
        mock_edit.assert_called_once_with("PIC-1", {"fixVersions": []})


class TestRemoveFixVersionFromIssues:
    def test_batch_collects_success_skipped_errors(self):
        issues_by_key = {
            "PIC-1": {"fields": {"fixVersions": [{"id": "100"}]}},
            "PIC-2": {"fields": {"fixVersions": [{"id": "200"}]}},
        }

        def _side_effect(key, version_id, issue=None):
            if key == "PIC-1":
                return True
            return False

        with patch("jira_client.remove_fix_version_from_issue", side_effect=_side_effect):
            result = jira_client.remove_fix_version_from_issues(
                ["PIC-1", "PIC-2", "PIC-3"],
                "100",
                issues_by_key=issues_by_key,
            )

        assert result["success"] == ["PIC-1"]
        assert result["skipped"] == ["PIC-2", "PIC-3"]
        assert result["errors"] == []


class TestDefaultExclusionHelpers:
    def test_get_snapshot_included_keys_for_project(self):
        from release_platform.ui.helpers import get_default_exclusion_keys, get_snapshot_included_keys_for_project

        issues = [{"key": "PIC-1"}, {"key": "PIC-2"}, {"key": "PIC-3"}]
        snapshot = {
            "release_PIC": {"id": "1", "name": "R1"},
            "ticket_keys": ["PIC-1", "PIC-2", "AN-9"],
        }

        with patch("ui.helpers.get_snapshot", return_value=snapshot):
            included = get_snapshot_included_keys_for_project("PIC")
            excluded = get_default_exclusion_keys(issues, "PIC", "1")

        assert included == {"PIC-1", "PIC-2"}
        assert excluded == {"PIC-3"}

    def test_exclusion_defaults_require_raw_fix_version_list(self):
        """Regression: filtered deploy list hides Ticket Review exclusions.

        Step 3 must call get_default_exclusion_keys on the raw fix-version
        list. Using the snapshot-filtered list always returns empty.
        """
        from release_platform.ui.helpers import apply_deploy_issue_filter, get_default_exclusion_keys

        raw_issues = [
            {"key": "PIC-1"},
            {"key": "PIC-2"},
            {"key": "PIC-3"},  # deselected in Ticket Review, still on fix version
        ]
        release = {"id": "1", "name": "R1"}
        snapshot = {
            "release_PIC": {"id": "1", "name": "R1"},
            "ticket_keys": ["PIC-1", "PIC-2"],
        }

        with patch("ui.helpers.get_snapshot", return_value=snapshot), \
             patch("ui.workflow.is_deployer_standalone", return_value=False):
            filtered, meta = apply_deploy_issue_filter(raw_issues, "PIC", release)
            defaults_on_filtered = get_default_exclusion_keys(filtered, "PIC", "1")
            defaults_on_raw = get_default_exclusion_keys(raw_issues, "PIC", "1")

        assert [iss["key"] for iss in filtered] == ["PIC-1", "PIC-2"]
        assert meta["removed"] == ["PIC-3"]
        assert defaults_on_filtered == set()  # broken if Step 3 used this
        assert defaults_on_raw == {"PIC-3"}  # correct Exclude Tickets source

    def test_filter_after_exclusion_drops_removed_ticket(self):
        """After fix-version removal, deploy candidates no longer include it."""
        from release_platform.ui.helpers import apply_deploy_issue_filter

        # Post-refresh: PIC-3 no longer on the fix version.
        raw_after_exclude = [{"key": "PIC-1"}, {"key": "PIC-2"}]
        release = {"id": "1", "name": "R1"}
        snapshot = {
            "release_PIC": {"id": "1", "name": "R1"},
            "ticket_keys": ["PIC-1", "PIC-2"],
        }

        with patch("ui.helpers.get_snapshot", return_value=snapshot), \
             patch("ui.workflow.is_deployer_standalone", return_value=False):
            filtered, meta = apply_deploy_issue_filter(
                raw_after_exclude, "PIC", release,
            )

        assert [iss["key"] for iss in filtered] == ["PIC-1", "PIC-2"]
        assert meta["removed"] == []
        assert meta["missing_from_release"] == []


class TestExcludeStepRawListContract:
    """Document the Step 3 select-and-proceed contract without Streamlit AppTest."""

    def test_step3_module_exposes_raw_loader_and_continue_helpers(self):
        from release_platform.ui import step3_exclude_fix as step3

        assert callable(step3._load_raw_issues)
        assert callable(step3._apply_exclusion_and_continue)
        assert callable(step3._sync_filtered_deploy_issues)
        assert callable(step3._refresh_release_issues)
