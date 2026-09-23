"""Tests for Slack deployment announce reference examples."""

from __future__ import annotations

from datetime import date

import slack_announce as sa
import slack_reference as sr


def test_gold_standard_keys():
    assert "SHIPIT-17191" in sr.GOLD_STANDARD_KEYS
    assert sr.DEFAULT_REFERENCE_KEY == "SHIPIT-17191"


def test_fetch_slack_reference_17191():
    ref = sr.fetch_slack_reference("SHIPIT-17191")
    assert ref is not None
    assert "Our upcoming deployment" in ref.squad_preview
    assert "Deployment notes and the deployment ticket" in ref.squad_preview
    assert "Trent Vanest" in ref.squad_preview
    assert "Trent Vanest" not in ref.buddies_preview
    assert "Sushma Bhamidipati" in ref.buddies_preview


def test_engine_matches_reference_17191():
    ref = sr.fetch_slack_reference("SHIPIT-17191")
    assert ref is not None
    draft = sa.SlackAnnounceDraft(
        ticket_key=ref.ticket_key,
        ticket_summary=f"Glofox Insights Customize BI - Prod Deployment - Release Version {ref.version}",
        ticket_url=ref.jira_url,
        version=f"v{ref.version}",
        deploy_date=date(2026, 9, 23),
        sharepoint_url="https://example.sharepoint.com/file=Release%20Notes%202026.3.09.16.docx",
        sharepoint_label=ref.sharepoint_label,
    )
    squad, buddies = sa.build_channel_messages(draft)
    preview = {
        "channels": [
            {"name": squad.channel.name, "preview": squad.preview},
            {"name": buddies.channel.name, "preview": buddies.preview},
        ]
    }
    parity = sr.compare_preview_to_reference(preview, issue_key="SHIPIT-17191")
    assert parity["ok"] is True


def test_slack_reference_status_includes_examples():
    payload = sr.slack_reference_status()
    assert payload.get("reference")
    assert "SHIPIT-17191" in (payload.get("all_examples") or {})
    assert payload.get("body_rules")


def test_build_reference_payload_messages():
    payload = sr.build_reference_payload("SHIPIT-17191")
    messages = (payload.get("reference") or {}).get("messages") or {}
    assert "insights-customize-squad" in messages
    assert "customize-bi-buddies" in messages
