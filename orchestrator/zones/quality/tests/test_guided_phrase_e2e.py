"""E2E phrase routing + workflow auto-chain tests (all user-facing commands)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from release_mcp import guided, phrase_catalog, release_ops, wizard, wizard_store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    yield
    wizard_store.set_sessions_dir_override(None)
    wizard_store.set_token_secret_override(None)


def _match_interpret(plan: dict, expected: dict) -> None:
    assert plan.get("action") == expected.get("action")
    inputs = plan.get("inputs") or {}
    if "start_path" in expected:
        assert inputs.get("start_path") == expected["start_path"]
    if expected.get("confirm_defaults"):
        assert inputs.get("confirm_defaults") == "yes"


@pytest.mark.parametrize(
    ("phrase", "flow_id"),
    phrase_catalog.all_phrases(),
)
def test_catalog_phrase_routes(phrase: str, flow_id: str):
    flow = phrase_catalog.flow_by_id(flow_id)
    assert flow is not None
    expected = dict(flow["interpret"])
    if flow_id == "full_release" and phrase == "yes":
        pytest.skip("yes without workflow defaults to fetch review — tested separately")
    plan = guided.interpret_message(phrase)
    _match_interpret(plan, expected)


def test_fetch_release_never_starts_wizard_lock():
    plan = guided.interpret_message("fetch release tickets")
    assert plan["action"] == "list_release_tickets"
    assert plan.get("workflow_id") is None


def test_create_release_notes_confirm_at_step():
    session = wizard_store.create_session("releaseops-full", step=wizard.STEP_RELEASE_NOTES)
    wizard_store.update_session(
        session["id"],
        confirmations={wizard.STEP_RELEASE_NOTES: {"token": "tok-rn", "status": "pending"}},
    )
    plan = guided.interpret_message("create release notes", workflow_id=session["id"])
    assert plan["action"] == "confirm"


def test_create_shipit_confirm_at_step():
    session = wizard_store.create_session("releaseops-full", step=wizard.STEP_SERVICE_TICKET)
    wizard_store.update_session(
        session["id"],
        confirmations={wizard.STEP_SERVICE_TICKET: {"token": "tok-st", "status": "pending"}},
    )
    plan = guided.interpret_message("create shipit", workflow_id=session["id"])
    assert plan["action"] == "confirm"


def test_run_guided_review_call_schedule_e2e(monkeypatch):
    monkeypatch.setattr(
        "daily_review_agent.ticket_pipeline.resolve_review_issues",
        lambda cfg: {"issues": [{"key": "PIC-1"}]},
    )
    monkeypatch.setattr(
        "daily_review_agent.schedule.collect_meeting_attendees",
        lambda cfg, issues: [{"email": "a@abcfitness.com"}],
    )
    result = guided.run_guided("review call schedule")
    assert result["step"] == "daily_review_calendar_playwright"
    assert result.get("handoff", {}).get("mcp") == "playwright"
    assert "calendar done" in (result.get("user_can_say") or [])


def test_confirm_release_notes_auto_chains_sharepoint_playwright(tmp_path: Path):
    docx_path = tmp_path / "Release Notes 2026.3.08.12.docx"
    docx_path.write_bytes(b"docx")
    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_RELEASE_NOTES,
        drafts={
            "release_notes": {
                "version": "v2026.3.08.12",
                "summary_p1": "Release summary.",
                "change_rows": "1|PIC-1||||||||",
                "extracted": [{"ticket": "PIC-1", "client": "X", "summary": "Y"}],
            }
        },
        artifacts={
            "ticket_snapshot": {"selected_ticket_keys": ["PIC-1"], "extracted": []},
        },
        inputs={"release_date_confirmed": True},
    )
    publish = MagicMock()
    publish.status = "ok"
    publish.docx_bytes = b"docx"
    publish.error = None
    publish.readiness = MagicMock(ready=True)
    publish.hyperlink_check = {}
    publish.to_dict = lambda: {"status": "ok"}

    with (
        patch("generators.release_notes_publish.publish_release_notes_docx", return_value=publish),
        patch(
            "release_mcp.wizard.release_ops.write_release_notes_docx_bytes",
            return_value={
                "status": "ok",
                "docx_path": str(docx_path),
                "docx_filename": docx_path.name,
                "docx_bytes": 4,
            },
        ),
        patch("release_mcp.wizard.assess_release_notes_readiness") as assess,
        patch("browser_automation.sharepoint_browser_upload_enabled", return_value=True),
    ):
        assess.return_value = MagicMock(ready=True)
        result = wizard._confirm_release_notes(session)

    assert result["step"] == wizard.STEP_SHAREPOINT
    loaded = wizard_store.load_session(session["id"])
    assert loaded["inputs"].get("sharepoint_upload") == "playwright"


def test_confirm_shipit_auto_chains_slack_playwright():
    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_SERVICE_TICKET,
        drafts={"service_ticket": {"summary": "Production Deployment v2026.3.08.12"}},
        artifacts={
            "sharepoint_url": "https://abcfinancial.sharepoint.com/doc.docx",
            "ticket_snapshot": {
                "selected_ticket_keys": ["PIC-1"],
                "extracted": [{"ticket": "PIC-1", "summary": "s", "client": "c"}],
            },
        },
        inputs={
            "planned_start_date": "2026-08-12",
            "planned_end_date": "2026-08-12",
            "workflow_mode": "full",
        },
    )
    with (
        patch(
            "release_mcp.wizard.release_ops.create_service_ticket",
            return_value={
                "status": "created",
                "key": "SHIPIT-999",
                "summary": "Production Deployment v2026.3.08.12",
                "url": "https://jira/SHIPIT-999",
            },
        ),
        patch("release_mcp.wizard.assignment_ops.verify_and_repair", return_value={"ok": True}),
        patch("release_mcp.wizard._run_teams_meeting", return_value=None),
        patch("browser_automation.slack_auto_handoff_after_shipit", return_value=True),
        patch("release_mcp.wizard.config.slack_archived", return_value=False),
    ):
        result = wizard._confirm_service_ticket(session)

    assert result["step"] == wizard.STEP_SLACK
    loaded = wizard_store.load_session(session["id"])
    assert loaded["inputs"].get("slack_decision") == "playwright"
    assert loaded["inputs"].get("slack_via_playwright") is True


def test_shipit_only_completes_after_slack_done():
    session = wizard_store.create_session(
        "releaseops-tckt",
        step=wizard.STEP_SLACK,
        inputs={"workflow_mode": "service_ticket_only", "slack_decision": "playwright"},
        artifacts={
            "sharepoint_url": "https://abcfinancial.sharepoint.com/doc.docx",
            "service_ticket": {
                "key": "SHIPIT-100",
                "summary": "Deploy",
                "url": "https://jira/SHIPIT-100",
            },
        },
    )
    with patch("release_mcp.wizard.config.slack_archived", return_value=False):
        result = wizard._process_slack(session)
    assert result["step"] == wizard.STEP_SLACK
    assert result["status"] == "needs_input"

    session = wizard_store.update_session(
        session["id"],
        inputs={"slack_decision": "slack done"},
    )
    with patch("release_mcp.wizard.config.slack_archived", return_value=False):
        blocked = wizard._process_slack(session)
    assert blocked["step"] == wizard.STEP_SLACK
    assert blocked["status"] == "needs_input"

    session = wizard_store.update_session(
        session["id"],
        artifacts={
            "slack_receipts": {
                "squad": {"permalink": "https://slack.com/archives/C08HB93PEVD/p1"},
                "buddies": {"permalink": "https://slack.com/archives/C08KM1USMM1/p2"},
            }
        },
        inputs={"slack_decision": "slack done"},
    )
    with patch("release_mcp.wizard.config.slack_archived", return_value=False):
        done = wizard._process_slack(session)
    assert done["step"] == wizard.STEP_COMPLETE


def test_catalog_cheat_sheet_covers_all_flows():
    text = phrase_catalog.format_e2e_cheat_sheet()
    for flow in phrase_catalog.PHRASE_E2E_FLOWS:
        assert flow["phrases"][0] in text
