"""Golden-path release E2E — mocked Jira/Slack, full wizard through slack done."""

from __future__ import annotations

from unittest.mock import patch

from release_mcp import wizard, wizard_store


def test_golden_path_service_ticket_only_through_slack_done(tmp_path):
    """Simulate: SHIPIT step → send slack → both receipts → slack done → complete."""
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("golden-path-secret")

    session = wizard_store.create_session(
        "releaseops-tckt",
        step=wizard.STEP_SLACK,
        inputs={
            "workflow_mode": "service_ticket_only",
            "version_name": "2026.3.09.11",
        },
        artifacts={
            "sharepoint_url": (
                "https://abcfinancial.sharepoint.com/teams/ABCFitnessSolutionsLLC-Glofox-Customize/"
                "Shared%20Documents/Release%20Notes%202026.3.09.11.docx"
            ),
            "service_ticket": {
                "key": "SHIPIT-100",
                "summary": "Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.11",
                "url": "https://abcfinancial.atlassian.net/browse/SHIPIT-100",
            },
        },
    )

    preview = {
        "enabled": True,
        "channels": [
            {"key": "squad", "name": "insights-customize-squad", "channel_id": "C08HB93PEVD"},
            {"key": "buddies", "name": "customize-bi-buddies", "channel_id": "C08KM1USMM1"},
        ],
        "can_post_via_playwright": True,
        "can_post_via_slack_mcp": True,
    }

    with patch("release_mcp.wizard.config.slack_archived", return_value=False), patch(
        "release_mcp.wizard._slack_preview", return_value=preview
    ):
        send = wizard._process_slack(
            wizard_store.update_session(session["id"], inputs={"slack_decision": "playwright"})
        )
        assert send["status"] == "needs_input"

        blocked = wizard._process_slack(
            wizard_store.update_session(
                session["id"],
                inputs={"slack_decision": "slack done"},
            )
        )
        assert blocked["status"] == "needs_input"

        done = wizard._process_slack(
            wizard_store.update_session(
                session["id"],
                artifacts={
                    "slack_receipts": {
                        "squad": {
                            "permalink": "https://grid-abcfitness.enterprise.slack.com/archives/C08HB93PEVD/p1",
                        },
                        "buddies": {
                            "permalink": "https://grid-abcfitness.enterprise.slack.com/archives/C08KM1USMM1/p2",
                        },
                    }
                },
                inputs={"slack_decision": "slack done"},
            )
        )

    with patch("release_mcp.wizard._process_step") as next_step:
        next_step.return_value = {"status": "ok", "step": wizard.STEP_COMPLETE}
        with patch("release_mcp.wizard.config.slack_archived", return_value=False), patch(
            "release_mcp.wizard._slack_preview", return_value=preview
        ):
            final = wizard._process_slack(
                wizard_store.load_session(session["id"])
            )
    assert final["step"] == wizard.STEP_COMPLETE
