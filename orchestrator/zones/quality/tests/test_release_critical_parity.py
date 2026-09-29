"""Strict release-critical parity contract — Platform vs MCP shared core."""

from __future__ import annotations

import os
import sys
from datetime import date, time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


def _complete_stk_state(**overrides):
    base = {
        "stk_summary": "Deploy v2026.3.08.12",
        "stk_description_adf": {"type": "doc", "version": 1, "content": []},
        "stk_extracted": [{"type": "Analyze", "ticket": "PIC-1"}],
        "stk_impl_plan": "impl",
        "stk_test_plan": "test",
        "stk_backout_plan": "back",
        "stk_business_impact": "impact",
        "stk_sharepoint": "https://contoso.sharepoint.com/sites/bi/Shared%20Documents/release.docx",
        "shared_sharepoint_url": "https://contoso.sharepoint.com/sites/bi/Shared%20Documents/release.docx",
        "shared_docx_generated": True,
        "shared_snapshot": {"ticket_keys": ["PIC-1"], "issues": []},
        "stk_approvers": [{"accountId": "abc123"}],
        "stk_approver_groups": [{"name": "Command Center"}],
    }
    base.update(overrides)
    return base


class TestSharedBlockersParity:
    def test_ui_wrapper_matches_shared_blockers(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow
        import release_critical as rc

        monkeypatch.setattr(st, "session_state", _complete_stk_state(), raising=False)
        ui_blockers = workflow.service_ticket_create_blockers(_complete_stk_state())
        shared = rc.service_ticket_create_blockers(_complete_stk_state())
        assert ui_blockers == shared

    def test_empty_summary_blocked_on_both_surfaces(self):
        import release_critical as rc

        state = _complete_stk_state(stk_summary="")
        report = rc.service_ticket_validation_report(state)
        assert not report.ready
        assert any("summary" in b.lower() for b in report.blockers)

    def test_standalone_skips_doc_and_snapshot_blockers(self):
        import release_critical as rc

        state = _complete_stk_state(
            shared_docx_generated=False,
            shared_snapshot=None,
            shared_stk_standalone_mode=True,
        )
        flags = rc.WorkflowFlags(service_ticket_standalone=True)
        blockers = rc.service_ticket_create_blockers(state, flags=flags)
        assert blockers == []

    def test_mcp_blocked_decision_includes_platform_blockers(self):
        import release_critical as rc

        blocked, blockers = rc.mcp_service_ticket_blocked(
            preflight_status="ok",
            approver_all_ok=True,
            duplicate_blocked=False,
            platform_blockers=["Implementation Steps is empty."],
        )
        assert blocked is True
        assert "Implementation Steps is empty." in blockers

    def test_github_pr_gate_blocks_shipit_without_override(self, monkeypatch):
        import release_critical as rc

        state = _complete_stk_state(
            github_pr_gate={
                "status": "ok",
                "blocking_count": 1,
                "tickets_with_blocking_prs": [{"ticket": "PIC-99"}],
            }
        )
        blockers = rc.service_ticket_create_blockers(state)
        assert any("GitHub PR gate" in b for b in blockers)

    def test_github_pr_override_skips_block(self, monkeypatch):
        import release_critical as rc

        state = _complete_stk_state(
            allow_github_pr_override=True,
            github_pr_gate={
                "status": "ok",
                "blocking_count": 1,
                "tickets_with_blocking_prs": [{"ticket": "PIC-99"}],
            },
        )
        blockers = rc.github_pr_create_blockers(state)
        assert blockers == []

    def test_mcp_blocked_preflight_and_duplicate(self):
        import release_critical as rc

        blocked, blockers = rc.mcp_service_ticket_blocked(
            preflight_status="preflight_failed",
            approver_all_ok=False,
            duplicate_blocked=True,
            platform_blockers=[],
        )
        assert blocked is True
        assert len(blockers) >= 3


class TestWorkflowCheckpointsParity:
    def test_checkpoints_match_prerequisites_progress(self, monkeypatch):
        import streamlit as st

        import release_critical as rc
        from release_platform.ui import workflow

        state = _complete_stk_state(stk_created_key="TCKT-1")
        monkeypatch.setattr(st, "session_state", state, raising=False)
        progress = workflow.get_workflow_progress()
        checkpoints = rc.workflow_checkpoints(state)
        for key in ("ticket_review", "release_notes", "sharepoint", "service_ticket"):
            assert progress[key] == checkpoints[key]

    def test_prerequisites_service_ticket_needs_sharepoint(self):
        import release_critical as rc

        state = {
            "shared_snapshot": {"ticket_keys": ["PIC-1"]},
            "shared_docx_generated": True,
            "shared_sharepoint_url": "",
        }
        result = rc.check_app_prerequisites("service_ticket", state)
        assert result.ok is False
        assert any("SharePoint" in m for m in result.missing)


class TestWizardMappingParity:
    def test_wizard_session_maps_to_same_blockers_as_platform(self):
        import release_critical as rc

        session = {
            "inputs": {
                "workflow_mode": "",
                "planned_start_date": date(2026, 8, 20),
                "planned_end_date": date(2026, 8, 20),
                "planned_start_time": time(10, 0),
                "planned_end_time": time(13, 0),
                "schedule_timezone": "Asia/Kolkata",
            },
            "drafts": {
                "service_ticket": {
                    "summary": "",
                    "description_adf": {"type": "doc"},
                    "implementation_plan": "x",
                    "test_plan": "x",
                    "backout_plan": "x",
                    "business_impact": "x",
                }
            },
            "artifacts": {
                "sharepoint_url": "https://contoso.sharepoint.com/sites/bi/doc.docx",
                "release_notes_docx": b"bytes",
                "ticket_snapshot": {"ticket_keys": ["PIC-1"], "extracted": [{"ticket": "PIC-1"}]},
                "approver_validation": {"all_ok": True},
            },
        }
        platform_state = rc.wizard_session_to_platform_state(session)
        blockers = rc.service_ticket_create_blockers(platform_state)
        assert any("summary" in b.lower() for b in blockers)


class TestRecoveryContract:
    def test_platform_recovery_domains_populated(self):
        from recovery_contract import platform_recovery_snapshot

        platform_state = _complete_stk_state(
            stk_created_key="TCKT-99",
            wiz_filled={"Acme": {"deployment_id": "1", "deployment_date": "d", "deployment_time": "t"}},
            wiz_release={"id": "1", "name": "2026.3.08.12"},
        )
        platform = platform_recovery_snapshot(platform_state)
        assert platform.domains["snapshot"] is True
        assert platform.domains["service_ticket"] is True
        assert platform.domains["deploy"] is True

    def test_wizard_recovery_snapshot(self):
        from recovery_contract import wizard_recovery_snapshot

        wizard = wizard_recovery_snapshot(
            {
                "artifacts": {
                    "ticket_snapshot": {"ticket_keys": ["PIC-1"]},
                    "sharepoint_url": "https://contoso.sharepoint.com/doc.docx",
                    "release_notes_docx": b"x",
                    "service_ticket": {"key": "TCKT-99"},
                },
                "drafts": {"deployment_info": {"Acme": {}}},
                "inputs": {"version_name": {"name": "2026.3.08.12"}},
            }
        )
        assert wizard.domains["snapshot"] is True
        assert wizard.domains["service_ticket"] is True

    def test_recovery_domains_constant(self):
        from recovery_contract import RECOVERY_DOMAINS

        assert "snapshot" in RECOVERY_DOMAINS
        assert "deploy" in RECOVERY_DOMAINS


class TestDeployAndSlackGates:
    def test_slack_gate_blocks_deploy_when_enabled(self, monkeypatch):
        import release_critical as rc
        import slack_announce as sa

        cfg = sa.SlackAnnounceConfig(
            enabled=True,
            bot_token="xoxb-test-token",
            channels=[sa.SlackChannelTarget(key="squad", name="insights-customize-squad")],
        )
        monkeypatch.setattr(sa, "load_announce_config", lambda _ws: cfg)
        blockers = rc.deploy_execution_blockers(
            {
                "wiz_filled": {"x": {}},
                "wiz_release": {"name": "R1"},
                "stk_slack_sent": False,
                "stk_slack_skipped": False,
            }
        )
        assert any("Slack" in b for b in blockers)

    def test_slack_gate_open_when_enabled_but_not_sendable(self, monkeypatch):
        import release_critical as rc
        import slack_announce as sa

        cfg = sa.load_announce_config({"slack_announce": {"enabled": True}})
        monkeypatch.setattr(sa, "load_announce_config", lambda _ws: cfg)
        blockers = rc.deploy_execution_blockers(
            {
                "wiz_filled": {"x": {}},
                "wiz_release": {"name": "R1"},
                "stk_slack_sent": False,
                "stk_slack_skipped": False,
            }
        )
        assert not any("Slack" in b for b in blockers)

    def test_slack_skip_opens_deploy_gate(self, monkeypatch):
        import release_critical as rc
        import slack_announce as sa

        cfg = sa.load_announce_config({"slack_announce": {"enabled": True}})
        monkeypatch.setattr(sa, "load_announce_config", lambda _ws: cfg)
        blockers = rc.deploy_execution_blockers(
            {
                "wiz_filled": {"x": {}},
                "wiz_release": {"name": "R1"},
                "stk_slack_skipped": True,
            }
        )
        assert not any("Slack" in b for b in blockers)

    def test_slack_gate_open_when_archived(self, monkeypatch):
        import config
        import release_critical as rc

        monkeypatch.setattr(config, "slack_archived", lambda: True)
        blockers = rc.deploy_execution_blockers(
            {
                "wiz_filled": {"x": {}},
                "wiz_release": {"name": "R1"},
                "stk_slack_sent": False,
                "stk_slack_skipped": False,
            }
        )
        assert not any("Slack" in b for b in blockers)


class TestMcpAtomicValidationTool:
    def test_validate_service_ticket_tool_registered(self):
        server = pytest.importorskip("release_mcp.server")
        assert callable(getattr(server, "validate_service_ticket", None))

    def test_validate_service_ticket_tool_matches_shared_core(self):
        server = pytest.importorskip("release_mcp.server")

        result = server.validate_service_ticket(
            {"summary": "", "description_adf": {}, "extracted": []},
            standalone=False,
            shared_docx_generated=False,
            has_snapshot=False,
        )
        assert result["ready"] is False
        assert result["blockers"]


class TestReviewWarningsParity:
    def test_review_warnings_match_step5_contract(self):
        import release_critical as rc

        warnings = rc.service_ticket_review_warnings(_complete_stk_state(stk_impl_plan=""))
        assert "Implementation Steps is empty." in warnings
