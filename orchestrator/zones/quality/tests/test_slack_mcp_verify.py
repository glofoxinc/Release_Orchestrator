"""Tests for Slack MCP verification and E2E handoff."""

from __future__ import annotations

from slack_mcp_verify import (
    build_verification_report,
    merge_mcp_probe_results,
    parse_channel_id_from_slack_url,
)
from release_mcp import slack_mcp_ops


def test_parse_channel_id_from_slack_url():
    url = "https://grid-abcfitness.enterprise.slack.com/archives/C08HB93PEVD/p1234567890"
    assert parse_channel_id_from_slack_url(url) == "C08HB93PEVD"


def test_build_verification_report_marks_channel_blockers():
    report = merge_mcp_probe_results(
        channel_checks=[
            {
                "name": "insights-customize-squad",
                "channel_id": "C08HB93PEVD",
                "accessible": False,
                "error": "channel_not_found",
            },
            {
                "name": "customize-bi-buddies",
                "channel_id": "C08KM1USMM1",
                "accessible": False,
                "error": "channel_not_found",
            },
        ],
        user_checks=[
            {
                "key": "sushma",
                "name": "Sushma Bhamidipati",
                "configured_user_id": "U08LDAQ7SDV",
                "resolved_user_id": "U08LDAQ7SDV",
                "match": True,
            },
            {
                "key": "sai_anirudh",
                "name": "Sai Anirudh Karre",
                "configured_user_id": "U0BSG4ABZC0",
                "resolved_user_id": "U0BSG4ABZC0",
                "match": True,
            },
        ],
        delivery_mode="cursor_slack_mcp",
    )
    assert report["delivery_mode"] == "cursor_slack_mcp"
    assert report["config_ready"] is True
    assert report["send_ready"] is True
    assert report["e2e_ready"] is True
    assert any("Read probe failed" in w for w in report["warnings"])
    assert any(u["mcp_match"] is True for u in report["cc_users"])


def test_slack_mcp_verify_includes_cached_probes():
    payload = slack_mcp_ops.slack_mcp_verify()
    assert payload["delivery_mode"] == "cursor_slack_mcp"
    assert payload["cc_users"]
    assert payload.get("mcp_tools")


def test_slack_mcp_e2e_handoff_builds_two_posts():
    payload = slack_mcp_ops.slack_mcp_e2e_handoff(
        ticket_key="SHIPIT-17191",
        summary="Production Deployment – Insights Customize BI (v2026.2.04.14)",
        ticket_url="https://abcfinancial.atlassian.net/browse/SHIPIT-17191",
        version_name="2026.2.04.14",
        sharepoint_url="https://example.sharepoint.com/file=Release%20Notes%202026.2.04.14.docx",
        deploy_date="2026-04-14",
    )
    posts = (payload.get("slack_mcp") or {}).get("posts") or []
    assert len(posts) == 2
    assert posts[0]["channel_name"] == "insights-customize-squad"
    assert "Our upcoming deployment" in posts[0]["message"]
    assert "Deployment notes and the deployment ticket" in posts[0]["message"]
    assert "<@U0BSG4ABZC0>" in posts[0]["message"]
    assert "<@U0BSG4ABZC0>" not in posts[1]["message"]
    assert "SharePoint — Release Notes:" in posts[0]["message"]
    assert "SharePoint — Folder:" in posts[0]["message"]


def test_offline_report_without_probes_has_warnings():
    report = build_verification_report(delivery_mode="cursor_slack_mcp").to_dict()
    assert report["delivery_mode"] == "cursor_slack_mcp"
    assert any("not yet probed" in w for w in report["warnings"])


def test_verify_integrations_check_slack_mcp_uses_e2e_ready():
    import os
    import sys
    from unittest.mock import patch

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "platform", "ops"))
    from verify_integrations import Result, check_slack_mcp

    fake_report = {"e2e_ready": True, "blockers": []}
    with patch("release_mcp.slack_mcp_ops.slack_mcp_verify", return_value=fake_report):
        results = check_slack_mcp()
    assert len(results) == 1
    assert results[0].status == Result.PASS
