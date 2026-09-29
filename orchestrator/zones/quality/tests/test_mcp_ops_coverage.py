"""Targeted coverage for MCP ops modules (teams, gates, operator guide, sharepoint)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")


@pytest.fixture
def live_integrations(monkeypatch):
    """Bypass archived integration flags so MCP ops bodies execute in tests."""
    monkeypatch.setattr("integration_archive.is_archived", lambda _id: False)
    monkeypatch.setattr("release_mcp.teams_ops.is_archived", lambda _id: False)
    monkeypatch.setattr("release_mcp.sharepoint_ops.is_archived", lambda _id: False)
    monkeypatch.setattr("release_mcp.slack_ops.is_archived", lambda _id: False)
    monkeypatch.setattr("config.slack_archived", lambda: False)
    monkeypatch.setattr("config.teams_archived", lambda: False)
    monkeypatch.setattr("config.sharepoint_upload_archived", lambda: False)


class TestOperatorGuideEnrich:
    def test_enrich_attaches_guide(self):
        from release_mcp.operator_guide import enrich_tool_response

        out = enrich_tool_response({"status": "ok", "count": 1}, tool="tckt_history")
        assert out["status"] == "ok"
        assert out["count"] == 1
        assert "operator_guide" in out
        assert out["operator_guide"].get("workflow_mode") == "full"

    def test_enrich_non_dict_passthrough(self):
        from release_mcp.operator_guide import enrich_tool_response

        assert enrich_tool_response("plain", tool="x") == "plain"


class TestTeamsOpsValidation:
    def test_invalid_kind(self, live_integrations):
        from release_mcp import teams_ops

        out = teams_ops.teams_schedule_meeting(kind="invalid", start="2026-09-09T10:00:00")
        assert out["ok"] is False
        assert "kind must be" in out["error"]

    def test_invalid_start_datetime(self, live_integrations):
        from release_mcp import teams_ops

        out = teams_ops.teams_schedule_meeting(kind="review", start="not-a-date")
        assert out["ok"] is False
        assert "Invalid start datetime" in out["error"]

    def test_missing_event_id_on_update(self, live_integrations):
        from release_mcp import teams_ops

        out = teams_ops.teams_update_meeting(
            event_id="",
            kind="review",
            start="2026-09-09T10:00:00",
        )
        assert out["ok"] is False
        assert "event_id is required" in out["error"]

    def test_missing_event_id_on_cancel(self, live_integrations):
        from release_mcp import teams_ops

        out = teams_ops.teams_cancel_meeting(event_id="")
        assert out["ok"] is False
        assert "event_id is required" in out["error"]

    def test_schedule_dry_run_builds_draft(self, monkeypatch, live_integrations):
        from release_mcp import teams_ops
        import teams_schedule as ts

        cfg = ts.load_schedule_config({"enabled": False})
        monkeypatch.setattr(teams_ops, "_cfg", lambda graph=None: cfg)
        monkeypatch.setattr(
            ts,
            "schedule_meeting",
            lambda c, draft, dry_run=True: ts.ScheduleResult(ok=True, dry_run=dry_run, event_id="evt-1"),
        )
        out = teams_ops.teams_schedule_meeting(
            kind="deployment",
            start="2026-09-09T10:00:00",
            end="2026-09-09T11:00:00",
            attendees=[{"email": "a@example.com", "name": "A"}],
            dry_run=True,
        )
        assert out["ok"] is True


class TestGateOps:
    def test_resolve_issues_success(self, monkeypatch):
        from release_mcp import gate_ops

        versions = [{"id": "99", "name": "2026.3.09.09"}]
        issues = [{"key": "PIC-1", "fields": {"summary": "x"}}]

        monkeypatch.setattr("jira_client.get_project_versions", lambda pk: versions)
        monkeypatch.setattr(
            "jira_client.get_issues_for_version",
            lambda pk, vid: issues if pk == "PIC" else [],
        )
        resolved, errors = gate_ops._resolve_issues_for_version("2026.3.09.09", ["PIC"])
        assert errors == []
        assert resolved == issues

    def test_resolve_issues_filters_ticket_keys(self, monkeypatch):
        from release_mcp import gate_ops

        versions = [{"id": "99", "name": "2026.3.09.09"}]
        issues = [
            {"key": "PIC-1", "fields": {}},
            {"key": "PIC-2", "fields": {}},
        ]
        monkeypatch.setattr("jira_client.get_project_versions", lambda pk: versions)
        monkeypatch.setattr("jira_client.get_issues_for_version", lambda pk, vid: issues)
        resolved, errors = gate_ops._resolve_issues_for_version(
            "2026.3.09.09",
            ["PIC"],
            ticket_keys=["PIC-2"],
        )
        assert errors == []
        assert [i["key"] for i in resolved] == ["PIC-2"]

    def test_pre_review_requires_version(self):
        from release_mcp import gate_ops

        out = gate_ops.pre_review_gate("")
        assert out["status"] == "error"
        assert "version_name is required" in out["errors"][0]

    def test_post_qa_version_not_found(self, monkeypatch):
        from release_mcp import gate_ops

        monkeypatch.setattr("jira_client.get_project_versions", lambda pk: [])
        out = gate_ops.post_qa_gate("missing-version", projects=["PIC"])
        assert out["status"] == "error"

    def test_release_gate_status_shape(self):
        from release_mcp import gate_ops

        out = gate_ops.release_gate_status()
        assert out["status"] == "ok"
        assert "pre_review_enabled" in out
        assert "slack" in out

    def test_post_qa_with_issues(self, monkeypatch):
        from release_mcp import gate_ops

        issues = [{
            "key": "AN-2",
            "fields": {
                "summary": "QA fail",
                "status": {"name": "QA Failed"},
                "assignee": {"displayName": "Dev"},
            },
        }]
        monkeypatch.setattr(
            gate_ops,
            "_resolve_issues_for_version",
            lambda version_name, projects=None, ticket_keys=None: (issues, []),
        )
        out = gate_ops.post_qa_gate("2026.3.09.09", dry_run=True)
        assert out.get("scope")
        assert "warnings" not in out or isinstance(out.get("warnings"), list)

    def test_pre_review_with_issues(self, monkeypatch):
        from release_mcp import gate_ops

        issues = [{
            "key": "AN-1",
            "fields": {
                "summary": "Test",
                "status": {"name": "Done"},
                "assignee": None,
            },
        }]
        monkeypatch.setattr(
            gate_ops,
            "_resolve_issues_for_version",
            lambda version_name, projects=None, ticket_keys=None: (issues, []),
        )
        out = gate_ops.pre_review_gate("2026.3.09.09", dry_run=True)
        assert "ready" in out or "counts" in out or "status" in out


class TestSharepointOpsErrors:
    def test_download_failure(self, monkeypatch, live_integrations):
        from release_mcp import sharepoint_ops

        monkeypatch.setattr(
            "sharepoint_upload.download_by_web_url",
            lambda cfg, url: (_ for _ in ()).throw(RuntimeError("network down")),
        )
        out = sharepoint_ops.sharepoint_download_release_notes("https://example.sharepoint.com/x")
        assert out["ok"] is False
        assert "network down" in out["error"]


class TestJiraAddLabel:
    def test_add_label_calls_put(self, monkeypatch):
        import jira_client

        calls: list[tuple] = []

        def fake_put(path, body):
            calls.append((path, body))
            return MagicMock(status_code=204)

        monkeypatch.setattr(jira_client, "_put", fake_put)
        jira_client.add_label("PIC-1", "release-v2026")
        assert calls == [
            ("/issue/PIC-1", {"update": {"labels": [{"add": "release-v2026"}]}}),
        ]


class TestReleaseOpsHelpers:
    def test_parse_fix_version_name(self):
        from release_mcp import release_ops

        parsed = release_ops.parse_fix_version_name("Release 2026.3.07.06")
        assert parsed == ("v2026.3.07.06", "06-July-2026")

    def test_parse_fix_version_name_invalid(self):
        from release_mcp import release_ops

        assert release_ops.parse_fix_version_name("not-a-version") is None

    def test_team_scope_status_missing_project(self):
        from release_mcp import release_ops

        out = release_ops.team_scope_status("")
        assert out["status"] == "error"

    def test_team_scope_status_ok(self, monkeypatch):
        from release_mcp import release_ops

        monkeypatch.setattr(
            "jira_client.validate_team_scope",
            lambda pk, version_id="": {"configured": True, "blocking": False},
        )
        out = release_ops.team_scope_status("PIC")
        assert out["status"] == "ok"


class TestSharepointOpsUpload:
    def test_upload_dry_run(self, monkeypatch, live_integrations, tmp_path):
        from release_mcp import sharepoint_ops
        import sharepoint_upload as sp

        doc = tmp_path / "notes.docx"
        doc.write_bytes(b"PK")
        monkeypatch.setattr(
            sp,
            "upload_release_notes",
            lambda cfg, path, remote_name=None, dry_run=True: sp.UploadResult(
                ok=True,
                dry_run=dry_run,
            ),
        )
        out = sharepoint_ops.sharepoint_upload_release_notes(str(doc), dry_run=True)
        assert out["ok"] is True


class TestParsingModule:
    def test_parse_change_rows_normalizes_legacy(self):
        from generators.parsing import parse_change_rows

        raw = "PIC-1|https://jira/browse/PIC-1|Owner|Pass|Done"
        rows = parse_change_rows(raw)
        assert len(rows) == 1
        assert rows[0][0] == "PIC-1"
        assert rows[0][3] == "Pass"


class TestMcpServerEnrichedTools:
    def test_workspace_config_includes_payload(self, tmp_path, monkeypatch):
        server = pytest.importorskip(
            "release_mcp.server",
            reason="mcp>=2.0.0 not installed for this interpreter",
        )
        import yaml

        ws_file = tmp_path / "workspace.yaml"
        ws_file.write_text(
            yaml.dump({"workspace": {"name": "Test", "projects": [{"key": "PIC"}]}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(server.config, "get_active_workspace_path", lambda: str(ws_file))
        out = server.workspace_config()
        assert out["status"] == "ok"
        assert out["operator_guide"]["tool"] == "workspace_config"
        assert "data" in out

    def test_deployment_metrics_empty_history(self, monkeypatch):
        server = pytest.importorskip(
            "release_mcp.server",
            reason="mcp>=2.0.0 not installed for this interpreter",
        )
        monkeypatch.setattr("deployment_history.load_history", lambda: [])
        out = server.deployment_metrics(days=7)
        assert out["status"] == "ok"
        assert out["operator_guide"]["tool"] == "deployment_metrics"
