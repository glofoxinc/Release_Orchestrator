"""Tests for integration_readiness summary."""

from __future__ import annotations

import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestIntegrationReadiness:
    def test_team_scope_ready_when_boards_configured(self, monkeypatch):
        import config
        import integration_readiness

        monkeypatch.setattr(
            config,
            "PROJECTS",
            [
                {"key": "PIC", "scope": {"board_id": "490"}},
                {"key": "AN", "scope": {"board_id": "3634"}},
            ],
        )
        items = integration_readiness.collect_readiness_items()
        scope = next(i for i in items if i.id == "team_scope")
        assert scope.status == "ready"
        assert scope.category == "ready"

    def test_team_scope_pending_when_blocking(self, monkeypatch):
        import config
        import integration_readiness

        monkeypatch.setattr(
            config,
            "PROJECTS",
            [{"key": "PIC", "scope": {"allow_project_wide": False}}],
        )
        items = integration_readiness.collect_readiness_items()
        scope = next(i for i in items if i.id == "team_scope")
        assert scope.status == "pending"
        assert scope.category == "blocking"

    def test_summarize_counts(self):
        from integration_readiness import summarize_readiness

        summary = summarize_readiness()
        assert "items" in summary
        assert summary["ready_count"] >= 1
        assert "blocking_pending" in summary

    def test_exclude_external_credential_items(self, monkeypatch):
        import integration_readiness
        from release_mcp import slack_ops

        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        items = integration_readiness.collect_readiness_items(include_excluded=False)
        ids = {i.id for i in items}
        if slack_ops.slack_delivery_mode() == "cursor_slack_mcp":
            assert "slack_announce" in ids
        else:
            assert "slack_announce" not in ids
        assert "sharepoint_playwright" in ids
        assert "teams_playwright" in ids

    def test_archived_integrations_skipped(self):
        import config
        import integration_readiness

        assert not config.slack_archived()
        assert config.teams_archived()
        assert config.sharepoint_upload_archived()
        items = integration_readiness.collect_readiness_items()
        slack = next(i for i in items if i.id == "slack_announce")
        teams = next(i for i in items if i.id == "teams_schedule")
        sp = next(i for i in items if i.id == "sharepoint_upload")
        assert slack.status in {"partial", "ready"}
        assert teams.status == "skipped"
        assert sp.status == "skipped"
