"""Focused tests for headless service_ticket_plans / history / deploy / exclusion ops."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


def _plan_ctx(**overrides):
    extracted = overrides.pop(
        "extracted",
        [
            {
                "type": "Analyze",
                "client": "Standard",
                "report": "Visit Analysis",
                "description": "Fix drill-through",
                "ticket": "PIC-1",
            },
            {
                "type": "Custom",
                "client": "Acme",
                "report": "Custom Board",
                "description": "Client metric",
                "ticket": "AN-2",
            },
        ],
    )
    base = {
        "extracted": extracted,
        "sharepoint": "https://sharepoint.example/doc.docx",
        "window": {"sentence": "Deploy Mon 10:00–13:00 IST", "note": ""},
        "version_name": "v2026.3.08.10",
        "scope_str": "Standard (Analyze) and Custom",
        "clients": ["Acme"],
        "dashboards": ["Visit Analysis", "Custom Board"],
        "descriptions": [e for e in extracted if e.get("description")],
        "workspaces": "Standard / Acme",
        "has_analyze": True,
        "has_custom": True,
    }
    base.update(overrides)
    return base


class TestServiceTicketPlans:
    def test_consolidate_and_builders(self):
        import service_ticket_plans as plans

        ctx = _plan_ctx()
        consolidated = plans.consolidate_by_report(ctx["extracted"])
        assert consolidated
        implementation = plans.build_impl(ctx)
        verification = plans.build_test(ctx)
        backout = plans.build_backout(ctx)
        impact = plans.build_impact(ctx)
        communication = plans.build_communication(ctx)

        assert "PIC-1" in implementation
        assert "AN-2" in implementation
        assert "Visit Analysis" in implementation
        assert "PIC-1" in verification
        assert "Visit Analysis" in verification
        assert "pre-deployment backup" in backout
        assert "Visit Analysis" in impact
        assert "insights-customize-squad" in communication
        assert "PIC-1" in communication
        assert "AN-2" in communication
        assert plans.build_reason(ctx) == "Production Deployment"

    def test_ui_aliases_still_resolve(self):
        from release_platform.ui.service_ticket import step4_plans

        ctx = _plan_ctx()
        assert step4_plans._build_impl(ctx).strip()
        assert step4_plans._consolidate_by_report(ctx["extracted"])


class TestDeploymentHistory:
    def test_save_load_mark_reverted_max_200(self, tmp_path, monkeypatch):
        import deployment_history as dh

        hist = tmp_path / ".deployment_history.json"
        monkeypatch.setattr(dh, "history_path", lambda app_dir=None: str(hist))

        for i in range(205):
            dh.save_history({"timestamp": f"ts-{i}", "n": i})

        data = dh.load_history()
        assert len(data) == 200
        assert data[0]["n"] == 204

        assert dh.mark_history_entry_reverted("ts-204") is True
        data = dh.load_history()
        assert data[0]["reverted"] is True
        assert data[0]["success"] == 0
        assert "reverted_at" in data[0]

    def test_corrupt_raises(self, tmp_path):
        import deployment_history as dh

        hist = tmp_path / "bad.json"
        hist.write_text("{not-json", encoding="utf-8")
        with pytest.raises(dh.HistoryLoadError):
            dh.load_history(str(hist))

    def test_helpers_wrapper_marks_reverted(self, tmp_path, monkeypatch):
        from release_platform.ui import helpers

        history_file = tmp_path / ".deployment_history.json"
        history_file.write_text(
            json.dumps([{"timestamp": "2026-07-01T12:00:00+00:00", "success": 3}]),
            encoding="utf-8",
        )
        monkeypatch.setattr(helpers, "_history_path", lambda: str(history_file))
        helpers.mark_history_entry_reverted("2026-07-01T12:00:00+00:00")
        data = json.loads(history_file.read_text(encoding="utf-8"))
        assert data[0]["reverted"] is True


class TestDeployOps:
    def _issue(self, key: str, done: bool = False) -> dict:
        return {
            "key": key,
            "fields": {
                "status": {
                    "name": "Done" if done else "In Progress",
                    "statusCategory": {"key": "done" if done else "indeterminate"},
                }
            },
        }

    def test_preview_skips_existing_comment(self):
        import deploy_ops

        tickets = [
            ("PIC", {"deployment_date": "2026-08-10", "deployment_time": "10:00", "deployment_id": "D1"},
             self._issue("PIC-1")),
        ]
        with patch(
            "deploy_ops.jira_client.check_deployment_comments",
            return_value=({"PIC-1": True}, {}),
        ), patch("deploy_ops.jira_client.add_deployment_comment") as add_cmt:
            result = deploy_ops.preview_deploy(
                tickets,
                release={"name": "2026.3.08.10", "id": "9"},
                project_key="PIC",
            )
        assert result["status"] == "dry_run"
        assert result["would_skip"] == ["PIC-1"]
        assert result["would_update"] == []
        add_cmt.assert_not_called()

    def test_execute_deploy_and_undo(self, tmp_path, monkeypatch):
        import deploy_ops
        import deployment_history as dh

        hist = tmp_path / ".deployment_history.json"
        monkeypatch.setattr(dh, "history_path", lambda app_dir=None: str(hist))

        filled = {
            "PIC": {
                "deployment_date": "2026-08-10",
                "deployment_time": "10:00",
                "deployment_id": "D-99",
            }
        }
        issues = [self._issue("PIC-1"), self._issue("PIC-2", done=True)]
        tickets = deploy_ops.build_tickets_to_process(
            filled=filled,
            selected_keys={"PIC-1", "PIC-2"},
            project_key="PIC",
            issues=issues,
            multi_client=False,
        )

        with patch(
            "deploy_ops.jira_client.check_deployment_comments",
            return_value=({"PIC-1": False, "PIC-2": False}, {}),
        ), patch("deploy_ops.jira_client.add_deployment_comment", return_value={"id": "c1"}) as add_cmt, \
             patch("deploy_ops.jira_client.transition_to_done", return_value=True) as trans, \
             patch("deploy_ops.jira_client.delete_comment") as del_cmt, \
             patch("deploy_ops.jira_client.find_transition_by_name", return_value="21"), \
             patch("deploy_ops.jira_client.transition_issue") as trans_issue:
            result = deploy_ops.execute_deploy(
                tickets,
                filled=filled,
                release={"name": "2026.3.08.10", "id": "9"},
                project_key="PIC",
                selected_keys={"PIC-1", "PIC-2"},
                issues=issues,
            )
            assert result["success"] == 2
            assert result["history_timestamp"]
            assert add_cmt.call_count == 2
            # PIC-2 already Done — no transition
            assert trans.call_count == 1

            undo = deploy_ops.undo_deploy(
                result["undo_data"],
                history_timestamp=result["history_timestamp"],
            )
            assert undo["ok"] == 2
            assert del_cmt.call_count == 2
            assert trans_issue.call_count == 1

        data = json.loads(hist.read_text(encoding="utf-8"))
        assert data[0]["reverted"] is True

    def test_execute_dry_run_no_writes(self):
        import deploy_ops

        tickets = [
            ("PIC", {"deployment_date": "2026-08-10", "deployment_time": "10:00", "deployment_id": "D1"},
             self._issue("PIC-1")),
        ]
        with patch(
            "deploy_ops.jira_client.check_deployment_comments",
            return_value=({"PIC-1": False}, {}),
        ), patch("deploy_ops.jira_client.add_deployment_comment") as add_cmt, \
             patch("deploy_ops.deployment_history.save_history") as save_h:
            result = deploy_ops.execute_deploy(
                tickets,
                filled={"PIC": tickets[0][1]},
                release={"name": "R", "id": "1"},
                project_key="PIC",
                selected_keys=["PIC-1"],
                dry_run=True,
            )
        assert result["status"] == "dry_run"
        assert result["would_update"] == ["PIC-1"]
        add_cmt.assert_not_called()
        save_h.assert_not_called()

    def test_mark_release(self):
        import deploy_ops

        with patch("deploy_ops.jira_client.release_version", return_value=True) as rel:
            assert deploy_ops.mark_release("42")["status"] == "released"
            rel.assert_called_once_with("42")


class TestExclusionOps:
    def test_preview_default_dry_run(self):
        import exclusion_ops

        version = {"id": "100", "name": "2026.3.08.10"}
        issues = [{"key": "PIC-1", "fields": {}}, {"key": "PIC-2", "fields": {}}]
        with patch("exclusion_ops.jira_client.get_project_versions", return_value=[version]), \
             patch("exclusion_ops.jira_client.get_issues_for_version", return_value=issues), \
             patch("exclusion_ops.jira_client.remove_fix_version_from_issues") as remove:
            result = exclusion_ops.remove_fix_versions(
                "PIC",
                "2026.3.08.10",
                ["PIC-1", "PIC-9"],
            )
        assert result["status"] == "dry_run"
        assert result["would_remove"] == ["PIC-1"]
        assert result["not_on_version"] == ["PIC-9"]
        remove.assert_not_called()

    def test_confirmed_remove(self):
        import exclusion_ops

        version = {"id": "100", "name": "2026.3.08.10"}
        issues = [{"key": "PIC-1", "fields": {"fixVersions": [{"id": "100"}]}}]
        with patch("exclusion_ops.jira_client.get_project_versions", return_value=[version]), \
             patch("exclusion_ops.jira_client.get_issues_for_version", return_value=issues), \
             patch(
                 "exclusion_ops.jira_client.remove_fix_version_from_issues",
                 return_value={"success": ["PIC-1"], "skipped": [], "errors": []},
             ) as remove:
            result = exclusion_ops.remove_fix_versions(
                "PIC",
                "2026.3.08.10",
                ["PIC-1"],
                dry_run=False,
            )
        assert result["status"] == "ok"
        assert result["success"] == ["PIC-1"]
        remove.assert_called_once()
        assert remove.call_args.args[0] == ["PIC-1"]
        assert remove.call_args.args[1] == "100"
