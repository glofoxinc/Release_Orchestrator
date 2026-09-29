"""Tests for tenant-safe team ticket scoping."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import team_scope
from team_scope import TeamScopeError

pytestmark = pytest.mark.real_scope


class TestScopeStructure:
    def test_blocking_when_empty(self):
        scope = team_scope.parse_scope({})
        errors = team_scope.validate_scope_structure(scope, project_key="PIC")
        assert errors
        status = team_scope.scope_status("PIC", scope=scope, validation_errors=errors)
        assert status["state"] == "blocking"

    def test_project_wide_explicit(self):
        scope = team_scope.parse_scope({"allow_project_wide": True})
        assert team_scope.validate_scope_structure(scope, project_key="PIC") == []
        clause = team_scope.build_team_scope_clause(scope)
        assert clause == ""

    def test_owns_version_requires_project_wide(self):
        scope = team_scope.parse_scope({"filter_id": "1", "owns_version": True})
        errors = team_scope.validate_scope_structure(scope, project_key="PIC")
        assert any("allow_project_wide" in err for err in errors)

    def test_rejects_order_by_in_custom_jql(self):
        scope = team_scope.parse_scope({"jql": "labels = x ORDER BY key"})
        errors = team_scope.validate_scope_structure(scope, project_key="PIC")
        assert any("ORDER BY" in err for err in errors)

    def test_labels_and_components_or_lists(self):
        scope = team_scope.parse_scope({
            "labels_any": ["team-a", "team-b"],
            "components_any": ["Customize"],
        })
        clause = team_scope.build_team_scope_clause(scope)
        assert 'labels in ("team-a", "team-b")' in clause
        assert 'component in ("Customize")' in clause

    def test_filter_and_custom_jql_combined(self):
        scope = team_scope.parse_scope({"filter_id": "12345", "jql": "status != Done"})
        clause = team_scope.build_team_scope_clause(scope)
        assert "filter = 12345" in clause
        assert "(status != Done)" in clause

    def test_scoped_version_jql_shape(self):
        scope = team_scope.parse_scope({"filter_id": "99"})
        jql = team_scope.build_scoped_version_jql("PIC", "10001", scope, resolved_filter_id="99")
        assert jql.startswith("project = PIC AND fixVersion = 10001 AND (filter = 99)")
        assert jql.endswith("ORDER BY key ASC")

    def test_fingerprint_stable(self):
        scope = team_scope.parse_scope({"filter_id": "42", "labels_any": ["x"]})
        fp1 = team_scope.scope_fingerprint("PIC", scope, resolved_filter_id="42")
        fp2 = team_scope.scope_fingerprint("PIC", scope, resolved_filter_id="42")
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_config_fingerprint_ignores_resolved_board_filter(self):
        scope = team_scope.parse_scope({"board_id": "490", "filter_id": ""})
        config_fp = team_scope.scope_config_fingerprint("PIC", scope)
        runtime_fp = team_scope.scope_fingerprint("PIC", scope, resolved_filter_id="99999")
        assert config_fp != runtime_fp
        assert config_fp == team_scope.scope_config_fingerprint("PIC", scope)

    def test_snapshot_scope_matches_detects_change(self):
        scope_a = team_scope.parse_scope({"filter_id": "1"})
        scope_b = team_scope.parse_scope({"filter_id": "2"})
        stored = {"PIC": team_scope.scope_config_fingerprint("PIC", scope_a)}
        current = {"PIC": team_scope.scope_config_fingerprint("PIC", scope_b)}
        with patch.object(team_scope, "collect_scope_fingerprints", return_value=current):
            ok, changed = team_scope.snapshot_scope_matches(stored, lenient=True)
        assert not ok
        assert changed == ["PIC"]

    def test_lenient_scope_accepts_runtime_fingerprint(self):
        scope = team_scope.parse_scope({"board_id": "490", "filter_id": ""})
        config_fp = team_scope.scope_config_fingerprint("PIC", scope)
        runtime_fp = team_scope.scope_fingerprint("PIC", scope, resolved_filter_id="99999")
        assert config_fp != runtime_fp
        with patch.object(team_scope, "scope_from_project", return_value=scope), patch.object(
            team_scope, "resolve_filter_id", return_value="99999"
        ):
            assert team_scope.fingerprint_compatible_with_config(
                "PIC",
                runtime_fp,
                current_config_fp=config_fp,
            )
        stored = {"PIC": runtime_fp}
        current = {"PIC": config_fp}
        with patch.object(team_scope, "collect_scope_fingerprints", return_value=current), patch.object(
            team_scope, "scope_from_project", return_value=scope
        ), patch.object(team_scope, "resolve_filter_id", return_value="99999"):
            ok, changed = team_scope.snapshot_scope_matches(stored, lenient=True)
        assert ok
        assert changed == []


class TestBoardFilterResolution:
    def test_parse_board_url(self):
        assert team_scope.normalize_scope_id("https://x.atlassian.net/jira/boards/12345") == "12345"

    def test_resolve_board_uses_cache(self, monkeypatch):
        team_scope.clear_board_filter_cache()
        calls: list[str] = []

        def resolver(board_id: str) -> str:
            calls.append(board_id)
            return "777"

        scope = team_scope.parse_scope({"board_id": "55"})
        assert team_scope.resolve_filter_id(scope, board_resolver=resolver) == "777"
        assert team_scope.resolve_filter_id(scope, board_resolver=resolver) == "777"
        assert calls == ["55"]


class TestWriteGuards:
    def test_keys_outside_scoped_version(self):
        with patch("jira_client.get_issue_keys_for_version", return_value=["PIC-1", "PIC-2"]):
            outside = team_scope.keys_outside_scoped_version("PIC", "9", ["PIC-9"])
        assert outside == ["PIC-9"]

    def test_mark_released_requires_owns_version(self):
        scope = team_scope.parse_scope({"filter_id": "1", "owns_version": False})
        with patch.object(team_scope, "scope_from_project", return_value=scope):
            with pytest.raises(TeamScopeError):
                team_scope.assert_can_mark_version_released("PIC")


class TestJiraClientScopedReads:
    @patch("jira_client._search_jql_paginated")
    @patch("jira_client.build_scoped_version_jql", return_value="project = PIC AND fixVersion = 9 ORDER BY key ASC")
    def test_get_issues_uses_scoped_jql(self, _build, mock_search):
        import jira_client

        mock_search.return_value = [{"key": "PIC-1"}]
        issues = jira_client.get_issues_for_version("PIC", "9")
        assert issues[0]["key"] == "PIC-1"
        _build.assert_called_once_with("PIC", "9")
        mock_search.assert_called_once()


class TestDeployOpsScopeGuard:
    def test_execute_blocks_out_of_scope_keys(self):
        import deploy_ops

        tickets = [
            ("PIC", {"deployment_date": "d", "deployment_time": "t", "deployment_id": "i"}, {"key": "PIC-9"}),
        ]
        with patch.object(
            deploy_ops,
            "_guard_scoped_write_keys",
            return_value={"status": "error", "error": "blocked"},
        ):
            result = deploy_ops.execute_deploy(
                tickets,
                filled={"PIC": {"deployment_date": "d", "deployment_time": "t", "deployment_id": "i"}},
                release={"id": "1", "name": "R"},
                project_key="PIC",
            )
        assert result["status"] == "error"

    def test_mark_release_blocked_without_owns_version(self):
        import deploy_ops

        with patch.object(
            deploy_ops.team_scope,
            "assert_can_mark_version_released",
            side_effect=TeamScopeError("nope"),
        ):
            result = deploy_ops.mark_release("42", project_key="PIC")
        assert result["status"] == "blocked"


class TestReleaseOpsScope:
    def test_fetch_blocked_when_unscoped(self, monkeypatch):
        import config
        from release_mcp import release_ops

        monkeypatch.setattr(
            config,
            "PROJECTS",
            [{"key": "PIC", "scope": team_scope.default_scope_dict()}],
        )
        result = release_ops.fetch_release_tickets("2026.1.01.01", projects=["PIC"])
        assert result["status"] == "blocked"
        assert "PIC" in result["scope_blocked_projects"]
