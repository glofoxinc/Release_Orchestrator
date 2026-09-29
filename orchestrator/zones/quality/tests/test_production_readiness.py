"""Tests for shared production readiness + Slack MCP handoff."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


def test_slack_delivery_mode_cursor_mcp_without_token(monkeypatch):
    import config
    from release_mcp import slack_ops

    monkeypatch.setattr(config, "SLACK_ANNOUNCE", {
        "enabled": True,
        "channels": [
            {"key": "squad", "name": "insights-customize-squad", "channel_id": "C08HB93PEVD", "cc": []},
        ],
    })
    monkeypatch.setenv("SLACK_BOT_TOKEN", "")
    assert slack_ops.slack_delivery_mode() == "cursor_slack_mcp"


def test_handoff_for_slack_mcp():
    from release_mcp.slack_ops import handoff_for_slack_mcp

    preview = {
        "channels": [
            {
                "key": "squad",
                "name": "insights-customize-squad",
                "channel_id": "C08HB93PEVD",
                "text": "Deploy tonight",
            },
        ],
    }
    handoff = handoff_for_slack_mcp(preview)
    assert handoff["delivery"] == "cursor_slack_mcp"
    assert len(handoff["posts"]) == 1
    assert handoff["posts"][0]["mcp_tool"] == "slack_send_message"
    assert handoff["posts"][0]["channel_id"] == "C08HB93PEVD"


def test_assess_production_readiness_mcp_surface():
    import production_readiness as pr

    report = pr.assess_production_readiness(surface="mcp")
    assert "verified" in report
    assert report.get("slack_delivery") in {"cursor_slack_mcp", "bot_token", "disabled", "not_configured"}
    assert "schedule_ist_to_cst" in {v["name"] for v in report["verified"]}


def test_guided_slack_done_phrase():
    from release_mcp import guided

    plan = guided.interpret_message("slack done", workflow_id="wf-1")
    assert plan["inputs"]["slack_decision"] == "slack done"
