"""Slack cascade and receipt gate tests."""

from __future__ import annotations

from unittest.mock import patch

import slack_cascade as sc
from release_mcp import guided, wizard, wizard_store


def test_cascade_order_playwright_first():
    with patch("browser_automation.prefer_playwright_slack", return_value=True), patch(
        "browser_automation.prefer_slack_mcp", return_value=True
    ), patch("browser_automation.enabled", return_value=True):
        assert sc.cascade_order()[0] == "playwright"
        assert "slack_mcp" in sc.cascade_order()
        assert sc.cascade_order()[-1] == "bot_token"


def test_receipts_complete_requires_both_channels():
    preview = {"channels": [{"key": "squad"}, {"key": "buddies"}]}
    assert not sc.receipts_complete(preview, {"squad": {"permalink": "https://slack.com/a"}})
    receipts = {
        "squad": {"permalink": "https://slack.com/a"},
        "buddies": {"ts": "123.456"},
    }
    assert sc.receipts_complete(preview, receipts)


def test_slack_done_blocked_without_receipts(tmp_path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_SLACK,
        artifacts={
            "service_ticket": {
                "key": "SHIPIT-1",
                "summary": "Prod Deployment",
                "url": "https://jira/SHIPIT-1",
            },
            "sharepoint_url": "https://abcfinancial.sharepoint.com/teams/x/Shared%20Documents/Release%20Notes.docx",
        },
        inputs={"version_name": "2026.3.09.11"},
    )
    with patch("release_mcp.wizard._slack_preview") as preview_mock:
        preview_mock.return_value = {
            "enabled": True,
            "channels": [
                {"key": "squad", "name": "insights-customize-squad"},
                {"key": "buddies", "name": "customize-bi-buddies"},
            ],
        }
        result = wizard.run_wizard(
            "update",
            workflow_id=session["id"],
            inputs={"slack_decision": "slack done"},
        )
    assert result["status"] == "needs_input"
    assert "missing" in result.get("prompt", "").lower() or "receipt" in result.get("prompt", "").lower()


def test_slack_done_allowed_with_both_receipts(tmp_path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_SLACK,
        artifacts={
            "service_ticket": {
                "key": "SHIPIT-1",
                "summary": "Prod Deployment",
                "url": "https://jira/SHIPIT-1",
            },
            "sharepoint_url": "https://abcfinancial.sharepoint.com/teams/x/Shared%20Documents/Release%20Notes.docx",
            "slack_receipts": {
                "squad": {"permalink": "https://slack.com/archives/C08HB93PEVD/p1"},
                "buddies": {"permalink": "https://slack.com/archives/C08KM1USMM1/p2"},
            },
        },
        inputs={"version_name": "2026.3.09.11", "workflow_mode": "service_ticket_only"},
    )
    with patch("release_mcp.wizard._slack_preview") as preview_mock, patch(
        "release_mcp.wizard._process_step"
    ) as next_step:
        preview_mock.return_value = {
            "enabled": True,
            "channels": [
                {"key": "squad", "name": "insights-customize-squad"},
                {"key": "buddies", "name": "customize-bi-buddies"},
            ],
        }
        next_step.return_value = {"status": "ok", "step": "complete"}
        result = wizard.run_wizard(
            "update",
            workflow_id=session["id"],
            inputs={"slack_decision": "slack done"},
        )
    assert result["status"] == "ok"


def test_guided_slack_receipt_phrase():
    plan = guided.interpret_message(
        "slack receipt squad https://grid-abcfitness.enterprise.slack.com/archives/C08HB93PEVD/p1",
        workflow_id="wf-1",
    )
    assert plan["action"] == "update"
    assert plan["inputs"]["slack_receipts"]["squad"]["permalink"].startswith("https://")
