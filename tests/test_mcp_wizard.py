"""Tests for the durable, confirmation-gated Release Orchestrator MCP wizard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from approver_validator import ValidationResult
from release_mcp import wizard, wizard_store
import release_gates


@pytest.fixture(autouse=True)
def _slack_integrations_live_for_wizard(monkeypatch):
    """Slack send tests exercise live code paths; integrations are archived in workspace.yaml."""
    monkeypatch.setattr("release_mcp.slack_ops.is_archived", lambda _id: False)


@pytest.fixture(autouse=True)
def _disable_release_gates_in_wizard(monkeypatch):
    """Legacy wizard tests use statuses that are not gate-ready at every step."""
    monkeypatch.setattr(release_gates, "gates_root_enabled", lambda: False)
    monkeypatch.setattr(release_gates, "gate_enabled", lambda _name: False)
    monkeypatch.setattr(release_gates, "require_ready_for_review_comment_all", lambda: False)
    monkeypatch.setattr(
        release_gates,
        "filter_extracted_in_progress_review_candidates",
        lambda extracted: {
            "status": "ok",
            "kept": list(extracted),
            "held_back": [],
            "held_back_keys": [],
        },
    )
    monkeypatch.setattr(
        release_gates,
        "filter_extracted_review_completed_comments",
        lambda extracted: {
            "status": "disabled",
            "kept": list(extracted),
            "held_back": [],
            "held_back_keys": [],
        },
    )
    monkeypatch.setattr(
        release_gates,
        "filter_extracted_outside_squad_assignees",
        lambda extracted, **kwargs: {
            "status": "skipped",
            "kept": list(extracted),
            "skipped": [],
            "skipped_keys": [],
        },
    )


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    yield
    wizard_store.set_sessions_dir_override(None)
    wizard_store.set_token_secret_override(None)


@pytest.fixture(autouse=True)
def _mock_jira_reads_for_wizard(monkeypatch):
    """Wizard tests must never call live Jira (full-suite order can leave real credentials loaded)."""
    import github_pr_gate
    import jira_client
    import release_date_confirm

    monkeypatch.setattr(github_pr_gate, "gate_enabled", lambda: False)
    monkeypatch.setattr(github_pr_gate, "comment_on_fetch_enabled", lambda: False)
    monkeypatch.setattr(
        release_date_confirm,
        "fetch_fix_versions_by_ticket",
        lambda ticket_keys: {k: ["2026.3.08.12"] for k in ticket_keys},
    )
    monkeypatch.setattr(
        jira_client,
        "get_project_versions",
        lambda project_key, released=None: [{"id": "p1", "name": "2026.3.08.12"}],
    )
    monkeypatch.setattr(
        jira_client,
        "get_issues_for_version",
        lambda project_key, version_id: [
            {"key": "PIC-1"},
            {"key": "AN-1"},
        ],
    )
    monkeypatch.setattr(jira_client, "get_issue_comments", lambda issue_key: [])
    monkeypatch.setattr(
        jira_client,
        "get_issue",
        lambda issue_key: {
            "key": issue_key,
            "fields": {"fixVersions": [{"name": "2026.3.08.12"}]},
        },
    )


def _ticket(key: str, project: str, client: str, report: str) -> dict:
    return {
        "ticket": key,
        "summary": f"{client} - {report} - update",
        "status": "Done",
        "type": "Custom" if project == "PIC" else "Analyze",
        "client": client if project == "PIC" else "Standard",
        "report": report,
        "description": "update",
        "assignee": "Owner",
        "parent": key,
        "project": project,
        "fix_version": "2026.3.08.12",
        "link": f"https://example.atlassian.net/browse/{key}",
    }


def _fetch_result() -> dict:
    pic = _ticket("PIC-1", "PIC", "Jetts", "Monthly Report")
    an = _ticket("AN-1", "AN", "Standard", "New Members")
    return {
        "status": "ok",
        "projects": ["PIC", "AN"],
        "total_tickets": 2,
        "missing_versions": [],
        "extracted": [pic, an],
        "by_project": {
            "PIC": {
                "version": "2026.3.08.12",
                "version_id": "p1",
                "count": 1,
                "tickets": [
                    {
                        "key": "PIC-1",
                        "summary": pic["summary"],
                        "status": "Done",
                        "type": "Custom",
                        "client": "Jetts",
                        "report": "Monthly Report",
                        "assignee": "Owner",
                    }
                ],
            },
            "AN": {
                "version": "2026.3.08.12",
                "version_id": "a1",
                "count": 1,
                "tickets": [
                    {
                        "key": "AN-1",
                        "summary": an["summary"],
                        "status": "Live",
                        "type": "Analyze",
                        "client": "Standard",
                        "report": "New Members",
                        "assignee": "Owner",
                    }
                ],
            },
        },
    }


def _fetch_one_project(version_name="", projects=None, **_kwargs):
    full = _fetch_result()
    project = projects[0]
    info = full["by_project"][project]
    return {
        "status": "ok",
        "projects": [project],
        "total_tickets": info["count"],
        "missing_versions": [],
        "extracted": [item for item in full["extracted"] if item["project"] == project],
        "by_project": {project: info},
    }


def _start_locked() -> tuple[str, dict]:
    with patch(
        "release_mcp.wizard.release_ops.fetch_release_tickets",
        side_effect=_fetch_one_project,
    ):
        result = wizard.run_wizard(
            "start",
            inputs={
                "version_name": "2026.3.08.12",
                "projects": ["PIC", "AN"],
                "selection_mode": "fix_version",
            },
        )
    assert result["status"] == "awaiting_confirmation"
    return result["workflow_id"], result


def approver_validator_result():
    """Return an all-clear validation result without Jira calls."""
    return ValidationResult()


def test_start_asks_for_version_and_persists():
    result = wizard.run_wizard("start")
    assert result["status"] == "needs_input"
    assert result["step"] == wizard.STEP_TICKET_REVIEW
    session = wizard_store.load_session(result["workflow_id"])
    assert session["status"] == wizard_store.STATUS_ACTIVE


def test_ticket_selection_update_invalidates_old_confirmation():
    workflow_id, first = _start_locked()
    old_token = first["confirmation_token"]

    with patch(
        "release_mcp.wizard.release_ops.fetch_release_tickets",
        side_effect=_fetch_one_project,
    ):
        updated = wizard.run_wizard(
            "update",
            workflow_id=workflow_id,
            inputs={"selected_ticket_keys": ["PIC-1"]},
        )
    assert updated["preview"]["excluded_ticket_keys"] == ["AN-1"]

    stale = wizard.run_wizard(
        "confirm",
        workflow_id=workflow_id,
        confirmation_token=old_token,
    )
    assert stale["status"] == "confirmation_invalid"


def test_excluded_ticket_requires_separate_write_confirmation():
    workflow_id, first = _start_locked()
    with patch(
        "release_mcp.wizard.release_ops.fetch_release_tickets",
        side_effect=_fetch_one_project,
    ):
        selected = wizard.run_wizard(
            "update",
            workflow_id=workflow_id,
            inputs={"selected_ticket_keys": ["PIC-1"]},
        )
    with patch("release_mcp.wizard.exclusion_ops.preview_exclusion") as preview:
        preview.return_value = {
            "status": "dry_run",
            "project": "AN",
            "would_remove": ["AN-1"],
        }
        result = wizard.run_wizard(
            "confirm",
            workflow_id=workflow_id,
            confirmation_token=selected["confirmation_token"],
        )
    assert result["step"] == wizard.STEP_EXCLUSIONS
    assert result["status"] == "awaiting_confirmation"
    assert result["confirmation_token"] != first["confirmation_token"]


def test_full_happy_path_with_all_external_writes_mocked():
    import release_date_confirm

    workflow_id, ticket_preview = _start_locked()

    with patch(
        "release_mcp.wizard.release_ops.fetch_release_tickets",
        side_effect=_fetch_one_project,
    ):
        release_date = wizard.run_wizard(
            "confirm",
            workflow_id=workflow_id,
            confirmation_token=ticket_preview["confirmation_token"],
        )
    assert release_date["step"] == wizard.STEP_RELEASE_DATE
    assert release_date["status"] == "awaiting_confirmation"

    with (
        patch(
            "release_mcp.wizard.release_ops.fetch_release_tickets",
            side_effect=_fetch_one_project,
        ),
        patch.object(
            release_date_confirm,
            "fetch_fix_versions_by_ticket",
            return_value={"PIC-1": ["2026.3.08.12"], "AN-1": ["2026.3.08.12"]},
        ),
    ):
        release_notes = wizard.run_wizard(
            "confirm",
            workflow_id=workflow_id,
            confirmation_token=release_date["confirmation_token"],
        )
    assert release_notes["step"] == wizard.STEP_RELEASE_NOTES
    assert release_notes["status"] == "awaiting_confirmation"

    from generators.release_notes_publish import PublishResult

    docx_result = {
        "status": "ok",
        "version": "v2026.3.08.12",
        "docx_path": "C:/tmp/Release Notes 2026.3.08.12.docx",
        "docx_filename": "Release Notes 2026.3.08.12.docx",
        "docx_bytes": 1234,
    }
    readiness = MagicMock()
    readiness.ready = True
    publish_ok = PublishResult(status="ok", docx_bytes=b"fake-docx", readiness=readiness)
    with (
        patch(
            "release_mcp.wizard.release_ops.fetch_release_tickets",
            side_effect=_fetch_one_project,
        ),
        patch(
            "generators.release_notes_publish.publish_release_notes_docx",
            return_value=publish_ok,
        ),
        patch(
            "release_mcp.wizard.release_ops.write_release_notes_docx_bytes",
            return_value=docx_result,
        ),
    ):
        sharepoint = wizard.run_wizard(
            "confirm",
            workflow_id=workflow_id,
            confirmation_token=release_notes["confirmation_token"],
        )
    assert sharepoint["step"] == wizard.STEP_SHAREPOINT
    assert sharepoint["status"] == "needs_input"

    dry_run = {
        "status": "dry_run",
        "summary": "Production Deployment v2026.3.08.12",
        "ticket_count": 2,
    }
    with (
        patch("release_mcp.wizard._snapshot_drift", return_value={"has_drift": False}),
        patch("release_mcp.wizard.release_ops.create_service_ticket", return_value=dry_run),
        patch("release_mcp.wizard.approver_validator.validate_defaults") as approvers,
        patch("release_mcp.wizard.jira_client.find_tckt_by_summary", return_value=None),
    ):
        approvers.return_value = approver_validator_result()
        service_preview = wizard.run_wizard(
            "update",
            workflow_id=workflow_id,
            inputs={
                "sharepoint_url": (
                    "https://abcfinancial.sharepoint.com/:w:/r/teams/Glofox/"
                    "Release%20Notes%202026.3.08.12.docx"
                ),
            },
        )
    assert service_preview["step"] == wizard.STEP_SERVICE_TICKET
    assert service_preview["status"] == "awaiting_confirmation"
    assert "schedule" in service_preview["preview"]
    assert service_preview["preview"]["schedule"]["planned_start_iso"]

    created = {
        "status": "created",
        "key": "TCKT-1",
        "url": "https://example.atlassian.net/browse/TCKT-1",
        "summary": "Production Deployment v2026.3.08.12",
    }
    with (
        patch("release_mcp.wizard.release_ops.create_service_ticket", return_value=created),
        patch(
            "release_mcp.wizard.assignment_ops.verify_and_repair",
            return_value={"status": "verified", "warnings": []},
        ),
        patch(
            "release_mcp.wizard.slack_ops.build_slack_preview",
            return_value={"enabled": True, "can_send": True, "channels": []},
        ),
    ):
        slack = wizard.run_wizard(
            "confirm",
            workflow_id=workflow_id,
            confirmation_token=service_preview["confirmation_token"],
        )
    assert slack["step"] == wizard.STEP_SLACK
    assert slack["status"] == "needs_input"

    # Token is one-time: replaying the service-ticket token must fail.
    replay = wizard.run_wizard(
        "confirm",
        workflow_id=workflow_id,
        confirmation_token=service_preview["confirmation_token"],
    )
    assert replay["status"] == "confirmation_invalid"

    deploy_project = wizard.run_wizard(
        "update",
        workflow_id=workflow_id,
        inputs={"slack_decision": "skip"},
    )
    assert deploy_project["step"] == wizard.STEP_DEPLOY
    assert deploy_project["status"] == "needs_input"

    with patch("release_mcp.wizard._snapshot_drift", return_value={"has_drift": False}):
        deploy_info = wizard.run_wizard(
            "update",
            workflow_id=workflow_id,
            inputs={"deployment_project": "PIC"},
        )
    assert deploy_info["status"] == "needs_input"

    context = {
        "project_key": "PIC",
        "version": {"id": "p1", "name": "2026.3.08.12"},
        "issues": [],
        "selected": ["PIC-1"],
        "selected_default": ["PIC-1"],
        "selection_explicit": True,
        "missing_from_release": [],
        "multi_client": True,
        "grouped": {},
        "tickets_by_client": {"Jetts": ["PIC-1"]},
    }
    deploy_preview_payload = {
        "status": "dry_run",
        "would_update": ["PIC-1"],
        "would_skip": [],
        "errors": 0,
        "comment_preview": "The change has been deployed...",
    }
    with (
        patch("release_mcp.wizard._snapshot_drift", return_value={"has_drift": False}),
        patch("release_mcp.wizard._deploy_context", return_value=context),
        patch("release_mcp.wizard.deploy_ops.preview_deploy", return_value=deploy_preview_payload),
    ):
        deploy_preview = wizard.run_wizard(
            "update",
            workflow_id=workflow_id,
            inputs={
                "deployment_ticket_keys": ["PIC-1"],
                "deployment_info": {
                    "Jetts": {
                        "deployment_id": "11111111-1111-1111-1111-111111111111",
                        "deployment_date": "2026-08-12",
                        "deployment_time": "10:00 AM IST",
                    }
                },
            },
        )
    assert deploy_preview["status"] == "awaiting_confirmation"
    assert deploy_preview["preview"].get("comment_preview")

    deploy_result = {
        "status": "ok",
        "success": 1,
        "skipped": 0,
        "errors": 0,
        "undo_data": [{"key": "PIC-1", "comment_id": "1"}],
        "history_timestamp": "2026-08-12T00:00:00Z",
        "project": "PIC",
    }
    with patch("release_mcp.wizard.deploy_ops.execute_deploy", return_value=deploy_result):
        mark_release = wizard.run_wizard(
            "confirm",
            workflow_id=workflow_id,
            confirmation_token=deploy_preview["confirmation_token"],
        )
    assert mark_release["step"] == wizard.STEP_MARK_RELEASED
    assert mark_release["status"] == "needs_input"
    session = wizard_store.load_session(workflow_id)
    assert "PIC" in session["artifacts"]["deployment_results"]

    remaining = wizard.run_wizard(
        "update",
        workflow_id=workflow_id,
        inputs={"mark_version_released": False},
    )
    assert remaining["status"] == "needs_input"
    assert "AN" in remaining["preview"]["remaining_projects"]

    completed = wizard.run_wizard(
        "update",
        workflow_id=workflow_id,
        inputs={"deploy_remaining_projects": False},
    )
    assert completed["status"] == "completed"
    assert wizard_store.load_session(workflow_id)["status"] == wizard_store.STATUS_COMPLETED

    blocked = wizard.run_wizard(
        "confirm",
        workflow_id=workflow_id,
        confirmation_token=deploy_preview["confirmation_token"],
    )
    assert blocked["status"] == "error"
    assert "no longer accepts" in blocked["prompt"].lower() or "completed" in blocked["prompt"].lower()


def test_terminal_cancel_blocks_confirm():
    workflow_id, preview = _start_locked()
    wizard.run_wizard("cancel", workflow_id=workflow_id)
    blocked = wizard.run_wizard(
        "confirm",
        workflow_id=workflow_id,
        confirmation_token=preview["confirmation_token"],
    )
    assert blocked["status"] == "error"
    status = wizard.run_wizard("status", workflow_id=workflow_id)
    assert status["workflow_status"] == wizard_store.STATUS_CANCELLED


def test_structured_store_error_for_missing_session():
    result = wizard.run_wizard("resume", workflow_id="wf-does-not-exist")
    assert result["status"] == "error"
    assert result["error_code"] == "session_not_found"


def test_missing_from_release_blocks_deploy():
    workflow_id, ticket_preview = _start_locked()
    wizard.run_wizard(
        "confirm",
        workflow_id=workflow_id,
        confirmation_token=ticket_preview["confirmation_token"],
    )
    session = wizard_store.load_session(workflow_id)
    wizard_store.update_session(
        workflow_id,
        step=wizard.STEP_DEPLOY,
        inputs={
            "deployment_project": "PIC",
            "deployment_info": {
                "Jetts": {
                    "deployment_id": "11111111-1111-1111-1111-111111111111",
                    "deployment_date": "2026-08-12",
                    "deployment_time": "10:00 AM IST",
                }
            },
            "deployment_ticket_keys": ["PIC-99"],
        },
        artifacts={
            "ticket_snapshot": {
                "selected_ticket_keys": ["PIC-99"],
                "excluded_ticket_keys": [],
                "extracted": [],
            },
            "ticket_fetch": session["artifacts"]["ticket_fetch"],
        },
    )
    with patch(
        "release_mcp.wizard._snapshot_drift",
        return_value={
            "has_drift": True,
            "missing_from_release": ["PIC-99"],
            "projects": {},
        },
    ):
        result = wizard.run_wizard("resume", workflow_id=workflow_id)
    assert result["status"] == "blocked"
    assert "PIC-99" in (result.get("preview") or {}).get("missing_from_release", ["PIC-99"])


def test_partial_deploy_stays_on_deploy_and_skips_mark_released():
    workflow_id, _ = _start_locked()
    pending = {"would_update": ["PIC-1", "PIC-2"]}
    wizard_store.update_session(
        workflow_id,
        step=wizard.STEP_DEPLOY,
        inputs={
            "deployment_project": "PIC",
            "deployment_ticket_keys": ["PIC-1", "PIC-2"],
            "deployment_info": {
                "Jetts": {
                    "deployment_id": "11111111-1111-1111-1111-111111111111",
                    "deployment_date": "2026-08-12",
                    "deployment_time": "10:00 AM IST",
                }
            },
        },
        artifacts={
            "ticket_snapshot": {
                "selected_ticket_keys": ["PIC-1", "PIC-2"],
                "excluded_ticket_keys": [],
                "extracted": [],
            },
            "ticket_fetch": {"by_project": {"PIC": {"tickets": [{"key": "PIC-1"}, {"key": "PIC-2"}]}}},
            "deployment_context": {
                "project_key": "PIC",
                "version": {"id": "p1", "name": "2026.3.08.12"},
                "issues": [],
                "selected": ["PIC-1", "PIC-2"],
                "multi_client": True,
                "grouped": {},
            },
            "pending_preview": pending,
        },
    )
    session = wizard_store.store_confirmation(
        workflow_id,
        wizard.STEP_DEPLOY,
        pending,
    )
    token = session["confirmations"][wizard.STEP_DEPLOY]["token"]
    partial = {
        "status": "partial",
        "success": 1,
        "skipped": 0,
        "errors": 1,
        "log": [
            "✅ PIC-1 — comment posted",
            "❌ PIC-2 — FAILED to post comment: boom",
        ],
        "undo_data": [{"key": "PIC-1", "comment_id": "1"}],
        "history_timestamp": "2026-08-12T00:00:00Z",
    }
    with patch("release_mcp.wizard.deploy_ops.execute_deploy", return_value=partial) as execute:
        result = wizard.run_wizard(
            "confirm",
            workflow_id=workflow_id,
            confirmation_token=token,
        )
    assert execute.call_count == 1
    assert result["step"] == wizard.STEP_DEPLOY
    assert result["status"] == "error"
    assert "PIC-2" in (result["preview"].get("failed_keys") or [])

    context = {
        "project_key": "PIC",
        "version": {"id": "p1", "name": "2026.3.08.12"},
        "issues": [],
        "selected": ["PIC-2"],
        "selected_default": ["PIC-1", "PIC-2"],
        "selection_explicit": False,
        "missing_from_release": [],
        "multi_client": True,
        "grouped": {},
        "tickets_by_client": {"Jetts": ["PIC-1", "PIC-2"]},
    }
    with (
        patch("release_mcp.wizard._snapshot_drift", return_value={"has_drift": False}),
        patch("release_mcp.wizard._deploy_context", return_value=context),
    ):
        mark = wizard.run_wizard(
            "update",
            workflow_id=workflow_id,
            inputs={"mark_version_released": True},
        )
    assert mark["step"] == wizard.STEP_DEPLOY
    assert mark["status"] != "awaiting_confirmation" or mark.get("preview", {}).get("action") != "mark_released"


def test_tckt_failure_recovers_existing_ticket():
    workflow_id, _ = _start_locked()
    pending = {"draft": {"summary": "Production Deployment v2026.3.08.12"}}
    wizard_store.update_session(
        workflow_id,
        step=wizard.STEP_SERVICE_TICKET,
        drafts={"service_ticket": {"summary": "Production Deployment v2026.3.08.12"}},
        artifacts={
            "ticket_snapshot": {
                "selected_ticket_keys": ["PIC-1"],
                "extracted": [_ticket("PIC-1", "PIC", "Jetts", "Monthly Report")],
            },
            "sharepoint_url": "https://sharepoint.example/doc.docx",
            "pending_preview": pending,
        },
    )
    session = wizard_store.store_confirmation(
        workflow_id,
        wizard.STEP_SERVICE_TICKET,
        pending,
    )
    token = session["confirmations"][wizard.STEP_SERVICE_TICKET]["token"]
    existing = {
        "key": "TCKT-9",
        "url": "https://example.atlassian.net/browse/TCKT-9",
        "summary": "Production Deployment v2026.3.08.12",
    }
    with (
        patch(
            "release_mcp.wizard.release_ops.create_service_ticket",
            return_value={"status": "error", "error": "timeout"},
        ),
        patch("release_mcp.wizard.jira_client.find_tckt_by_summary", return_value=existing),
    ):
        result = wizard.run_wizard(
            "confirm",
            workflow_id=workflow_id,
            confirmation_token=token,
        )
    assert result["status"] == "error"
    assert result["preview"]["existing_tckt"]["key"] == "TCKT-9"
    assert result["preview"]["retry_safe"] is False
    assert "confirm" not in result["allowed_actions"]


def test_slack_partial_skips_already_sent_channels():
    import slack_announce as sa
    from release_mcp import slack_ops

    channels = [
        sa.SlackChannelTarget(
            key="squad",
            name="insights-customize-squad",
            channel_id="C1",
            cc=(),
        ),
        sa.SlackChannelTarget(
            key="buddies",
            name="customize-bi-buddies",
            channel_id="C2",
            cc=(),
        ),
    ]
    preview = {
        "channels": [
            {
                "key": "squad",
                "name": "insights-customize-squad",
                "text": "hi squad",
                "preview": "hi squad",
            },
            {
                "key": "buddies",
                "name": "customize-bi-buddies",
                "text": "hi buddies",
                "preview": "hi buddies",
            },
        ],
        "prior_results": [
            {
                "key": "squad",
                "ok": True,
                "permalink": "https://slack/1",
                "ts": "1.0",
            }
        ],
    }
    sent = sa.SlackSendResult(
        channel_name="customize-bi-buddies",
        ok=True,
        permalink="https://slack/2",
        ts="2.0",
    )
    with (
        patch("release_mcp.slack_ops.load_announce_config") as cfg_loader,
        patch("release_mcp.slack_ops.send_announce_messages", return_value=[sent]) as send,
    ):
        cfg_loader.return_value = sa.SlackAnnounceConfig(
            enabled=True,
            bot_token="xoxb-test",
            channels=channels,
        )
        result = slack_ops.send_slack_preview(preview, skip_channel_keys=["squad"])
    assert send.call_count == 1
    assert len(send.call_args.args[1]) == 1
    assert result["status"] == "sent"
    assert "squad" in result["sent_keys"]
    assert "buddies" in result["sent_keys"]


def test_slack_ops_apply_edits_reappends_canonical_cc():
    import slack_announce as sa
    from release_mcp import slack_ops

    channels = sa.default_channels()
    preview = {
        "channels": [
            {
                "key": "squad",
                "name": "insights-customize-squad",
                "text": "original",
                "preview": "original",
            }
        ]
    }
    edited = slack_ops.apply_slack_message_edits(
        preview,
        {"squad": "Hello Team,\nBody only — no CC line.\nThanks!"},
        channels=channels,
    )
    text = edited["channels"][0]["text"]
    assert "Body only" in text
    assert "<@U08LDAQ7SDV>" in text
    assert "<@U0BSG4ABZC0>" in text
    assert "<@U083R8TP1J9>" in text
    assert "<@U01H0UL5JGP>" in text
    assert text.rstrip().endswith(sa.format_cc_line(channels[0], for_preview=False))


def test_slack_ops_disabled_never_sends():
    from release_mcp import slack_ops

    with patch("release_mcp.slack_ops.load_announce_config") as cfg_loader:
        cfg_loader.return_value = MagicMock(enabled=False, channels=[])
        result = slack_ops.send_slack_preview(
            {
                "channels": [
                    {"key": "squad", "text": "hi", "preview": "hi"},
                ]
            }
        )
    assert result["status"] == "skipped"
    assert result["reason"]
    assert result["sent_keys"] == []


def test_send_slack_preview_ensures_cc_on_outbound_text():
    import slack_announce as sa
    from release_mcp import slack_ops

    channels = sa.default_channels()
    captured: list[str] = []

    def fake_send(cfg, messages):
        out = []
        for message in messages:
            captured.append(message.text)
            out.append(
                sa.SlackSendResult(
                    channel_name=message.channel.name,
                    ok=True,
                    ts="1",
                    permalink="p",
                )
            )
        return out

    preview = {
        "channels": [
            {
                "key": channels[0].key,
                "name": channels[0].name,
                "text": "Edited body without CC",
                "preview": "Edited body without CC",
            },
            {
                "key": channels[1].key,
                "name": channels[1].name,
                "text": "Edited buddies without CC",
                "preview": "Edited buddies without CC",
            },
        ]
    }
    with (
        patch("release_mcp.slack_ops.load_announce_config") as cfg_loader,
        patch("release_mcp.slack_ops.send_announce_messages", side_effect=fake_send),
    ):
        cfg_loader.return_value = sa.SlackAnnounceConfig(
            enabled=True,
            bot_token="xoxb-test",
            channels=channels,
        )
        result = slack_ops.send_slack_preview(preview)
    assert result["status"] == "sent"
    assert all("CC:" in text for text in captured)
    assert "<@U0BSG4ABZC0>" in captured[0]
    assert "<@U0BSG4ABZC0>" not in captured[1]


def test_multi_project_deploy_results_and_undo_preview():
    workflow_id, _ = _start_locked()
    wizard_store.update_session(
        workflow_id,
        step=wizard.STEP_COMPLETE,
        status=wizard_store.STATUS_COMPLETED,
        artifacts={
            "deployment_results": {
                "PIC": {
                    "undo_data": [
                        {"key": "PIC-1", "comment_id": "1", "transitioned": False},
                        {"key": "PIC-2", "comment_id": "2", "transitioned": False},
                    ],
                    "history_timestamp": "2026-08-12T01:00:00Z",
                },
                "AN": {
                    "undo_data": [
                        {"key": "AN-1", "comment_id": "3", "transitioned": False},
                    ],
                    "history_timestamp": "2026-08-12T02:00:00Z",
                },
            },
            "deployment_result": {
                "undo_data": [{"key": "AN-1", "comment_id": "3"}],
                "history_timestamp": "2026-08-12T02:00:00Z",
            },
        },
    )
    preview = wizard.run_wizard("undo", workflow_id=workflow_id)
    assert preview["status"] == "awaiting_confirmation"
    keys = {item["key"] for item in preview["preview"]["tickets"]}
    assert keys == {"PIC-1", "PIC-2", "AN-1"}
    assert len(preview["preview"]["history_timestamps"]) == 2


def test_exclusion_ticket_keys_can_expand_beyond_review():
    workflow_id, first = _start_locked()
    wizard.run_wizard(
        "confirm",
        workflow_id=workflow_id,
        confirmation_token=first["confirmation_token"],
    )
    wizard_store.update_session(workflow_id, step=wizard.STEP_EXCLUSIONS)
    with patch("release_mcp.wizard.exclusion_ops.preview_exclusion") as preview:
        preview.return_value = {
            "status": "dry_run",
            "project": "PIC",
            "would_remove": ["PIC-1"],
        }
        result = wizard.run_wizard(
            "update",
            workflow_id=workflow_id,
            inputs={"exclusion_ticket_keys": ["PIC-1"]},
        )
    assert result["step"] == wizard.STEP_EXCLUSIONS
    assert result["status"] == "awaiting_confirmation"
    assert "PIC-1" in result["preview"]["exclusion_ticket_keys"]


def test_consume_confirmation_is_one_time():
    session = wizard_store.create_session("releaseops-full", step="deploy")
    preview = {"would_update": ["PIC-1"]}
    session = wizard_store.store_confirmation(session["id"], "deploy", preview)
    token = session["confirmations"]["deploy"]["token"]
    wizard_store.consume_confirmation(session["id"], "deploy", token, preview)
    with pytest.raises(wizard_store.ConfirmationConsumedError):
        wizard_store.consume_confirmation(session["id"], "deploy", token, preview)


def test_wizard_applies_pre_review_gate(monkeypatch):
    monkeypatch.setattr(release_gates, "gates_root_enabled", lambda: True)
    monkeypatch.setattr(
        release_gates,
        "gate_enabled",
        lambda name: name == "pre_review",
    )
    fetch = _fetch_result()
    fetch["extracted"][0]["status"] = "In Review"
    fetch["extracted"][1]["status"] = "Open"
    fetch["by_project"]["PIC"]["tickets"][0]["status"] = "In Review"
    fetch["by_project"]["AN"]["tickets"][0]["status"] = "Open"

    def _fetch(version_name, projects=None, **_kwargs):
        project = projects[0]
        info = fetch["by_project"][project]
        return {
            "status": "ok",
            "projects": [project],
            "total_tickets": info["count"],
            "missing_versions": [],
            "extracted": [item for item in fetch["extracted"] if item["project"] == project],
            "by_project": {project: info},
        }

    with patch("release_mcp.wizard.release_ops.fetch_release_tickets", side_effect=_fetch):
        result = wizard.run_wizard(
            "start",
            inputs={"version_name": "2026.3.08.12", "projects": ["PIC", "AN"]},
        )
    assert result["status"] == "awaiting_confirmation"
    assert result["preview"]["selected_ticket_keys"] == ["PIC-1"]
    assert result["preview"]["pre_review_gate"]["held_back_keys"] == ["AN-1"]


def test_wizard_applies_post_qa_gate_before_release_notes(monkeypatch):
    monkeypatch.setattr(release_gates, "gates_root_enabled", lambda: True)
    monkeypatch.setattr(
        release_gates,
        "gate_enabled",
        lambda name: name == "post_qa",
    )
    fetch = _fetch_result()
    snapshot = {
        "selected_ticket_keys": ["PIC-1", "AN-1"],
        "excluded_ticket_keys": [],
        "extracted": fetch["extracted"],
    }
    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_RELEASE_NOTES,
        inputs={"version_name": "2026.3.08.12", "projects": ["PIC", "AN"]},
    )
    session = wizard_store.update_session(
        session["id"],
        artifacts={"ticket_snapshot": snapshot, "ticket_fetch": fetch},
    )

    def _issues(project_key, version_id):
        if project_key == "PIC":
            return [{"key": "PIC-1", "fields": {"summary": "ok", "status": {"name": "Done"}, "assignee": {}}}]
        return [{"key": "AN-1", "fields": {"summary": "bad", "status": {"name": "Open"}, "assignee": {}}}]

    with (
        patch(
            "release_mcp.wizard.release_ops.fetch_release_tickets",
            return_value=fetch,
        ),
        patch("release_mcp.wizard.jira_client.get_issues_for_version", side_effect=_issues),
    ):
        pending = wizard._process_release_notes(session)
    assert pending["status"] == "needs_input"
    assert pending["preview"]["qa_failed_keys"] == ["AN-1"]

    session = wizard_store.update_session(
        session["id"],
        inputs={
            **session["inputs"],
            "post_qa_apply": True,
            "release_date_confirmed": True,
        },
    )
    with (
        patch(
            "release_mcp.wizard.release_ops.fetch_release_tickets",
            return_value=fetch,
        ),
        patch("release_mcp.wizard.jira_client.get_issues_for_version", side_effect=_issues),
    ):
        processed = wizard._process_release_notes(session)
    assert processed["preview"]["ticket_count"] == 1
    assert processed["preview"]["post_qa_gate"]["qa_failed_keys"] == ["AN-1"]
    assert "AN-1" in processed["preview"]["draft"]["excluded_tickets"]


def test_release_date_proposal_suggests_t_plus_one_without_jira(monkeypatch):
    import release_date_confirm

    class _FixedDate(release_date_confirm.date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 15)

    monkeypatch.setattr(release_date_confirm, "date", _FixedDate)
    session = {
        "inputs": {"selection_mode": "status", "projects": ["PIC", "AN"]},
    }
    with monkeypatch.context() as m:
        m.setattr(
            release_date_confirm,
            "fetch_fix_versions_by_ticket",
            lambda keys: {k: [] for k in keys},
        )
        proposal = release_date_confirm.build_release_date_proposal(session, ["PIC-1"])
    assert proposal["source"] == "no_jira_fix_version"
    assert proposal["version_name"] == "2026.3.09.16"
