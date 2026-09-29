"""Tests for Customize BI deployment Slack announcements."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import slack_announce as sa


def test_extract_version_from_summary():
    summary = "Production Deployment – Customize BI Team - Multi-Client - Report Updates (v2026.3.08.05)"
    assert sa.extract_version_label(summary) == "v2026.3.08.05"
    assert sa.extract_version_label("no version", "2026.3.07.29") == "v2026.3.07.29"


def test_sharepoint_label_from_file_query():
    url = (
        "https://abcfinancial.sharepoint.com/:w:/r/teams/x/_layouts/15/Doc.aspx"
        "?file=Release%20Notes%202026.3.08.05.docx&action=default"
    )
    assert sa.sharepoint_label_from_url(url, "v2026.3.08.05") == ("Release Notes 2026.3.08.05.docx")


def test_format_deploy_day_zero_pads():
    assert sa.format_deploy_day(date(2026, 8, 5)) == "Wednesday, August 05, 2026"
    # 2026-07-29 is a Wednesday (calendar weekday from deploy date).
    assert sa.format_deploy_day(date(2026, 7, 29)) == "Wednesday, July 29, 2026"


def test_build_messages_match_channel_ccs():
    draft = sa.SlackAnnounceDraft(
        ticket_key="TCKT-112175",
        ticket_summary=("Production Deployment – Customize BI Team - Multi-Client - Report Updates (v2026.3.08.05)"),
        ticket_url="https://abcfinancial.atlassian.net/browse/TCKT-112175",
        version="v2026.3.08.05",
        deploy_date=date(2026, 8, 5),
        sharepoint_url="https://example.sharepoint.com/file=Release%20Notes%202026.3.08.05.docx",
        sharepoint_label="Release Notes 2026.3.08.05.docx",
    )
    messages = sa.build_channel_messages(draft)
    assert len(messages) == 2
    squad, buddies = messages

    assert squad.channel.name == "insights-customize-squad"
    assert buddies.channel.name == "customize-bi-buddies"
    assert "Sai Anirudh Karre" in squad.preview
    assert "Zeke Brustkern" in squad.preview
    assert "Eoin George" in squad.preview
    assert "Sai Anirudh Karre" not in buddies.preview
    assert "<@U0BSG4ABZC0>" in squad.text
    assert "<@U083R8TP1J9>" in squad.text
    assert "<@U01H0UL5JGP>" in squad.text
    assert "<@U0BSG4ABZC0>" not in buddies.text
    assert "Wednesday, August 05, 2026" in squad.preview
    assert "Our upcoming deployment is scheduled for" in squad.preview
    assert "Production Deployment" in squad.preview
    assert "SharePoint — Download:" in squad.preview
    assert "SharePoint — Folder:" in squad.preview
    assert "Release Notes 2026.3.08.05.docx" in squad.preview
    assert "<@U08LDAQ7SDV>" in squad.text
    assert "Sushma Bhamidipati" in buddies.preview


def test_load_announce_config_applies_channel_ids(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    cfg = sa.load_announce_config(
        {
            "slack_announce": {
                "enabled": True,
                "channel_ids": {
                    "insights-customize-squad": "C111",
                    "customize-bi-buddies": "C222",
                },
            }
        }
    )
    assert cfg.can_send()
    by_name = {c.name: c.channel_id for c in cfg.channels}
    assert by_name["insights-customize-squad"] == "C111"
    assert by_name["customize-bi-buddies"] == "C222"


def test_operator_gold_standard_buddies_channel_2026_3_09_23():
    """Match live #customize-bi-buddies posts (operator screenshot 2026-09-22)."""
    draft = sa.SlackAnnounceDraft(
        ticket_key="SHIPIT-17191",
        ticket_summary="Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.23",
        ticket_url="https://abcfinancial.atlassian.net/browse/SHIPIT-17191",
        version="v2026.3.09.23",
        deploy_date=date(2026, 9, 23),
        sharepoint_url="https://abcfinancial.sharepoint.com/:w:/r/teams/x/Release%20Notes%202026.3.09.23.docx",
        sharepoint_label="Release Notes 2026.3.09.23.docx",
    )
    _squad, buddies = sa.build_channel_messages(draft)
    preview = buddies.preview
    assert "Our upcoming deployment is scheduled for Wednesday, September 23, 2026." in preview
    assert "Deployment notes and the deployment ticket are below for reference:" in preview
    assert "SharePoint — Download: Release Notes 2026.3.09.23.docx" in preview
    assert "SharePoint — Folder:" in preview
    assert "Service Desk: Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.23" in preview
    assert "CC: @Sushma Bhamidipati" in preview
    assert "Sai Anirudh Karre" not in preview
    assert "Thanks!" not in preview


def test_shipit_17191_style_message_preview():
    """Match operator-approved Slack copy (SHIPIT-17191 / 2026.3.09.16)."""
    draft = sa.SlackAnnounceDraft(
        ticket_key="SHIPIT-17191",
        ticket_summary="Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.16",
        ticket_url="https://abcfinancial.atlassian.net/browse/SHIPIT-17191",
        version="v2026.3.09.16",
        deploy_date=date(2026, 9, 16),
        sharepoint_url="https://abcfinancial.sharepoint.com/:w:/r/teams/x/Release%20Notes%202026.3.09.16.docx",
        sharepoint_label="Release Notes 2026.3.09.16.docx",
    )
    squad, buddies = sa.build_channel_messages(draft)
    assert "Wednesday, September 16, 2026" in squad.preview
    assert "Our upcoming deployment is scheduled for" in squad.preview
    assert "Deployment notes and the deployment ticket are below for reference:" in squad.preview
    assert "Release Notes 2026.3.09.16.docx" in squad.preview
    assert "Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.16" in squad.preview
    assert "Sushma Bhamidipati" in squad.preview
    assert "Sai Anirudh Karre" in squad.preview
    assert "Sai Anirudh Karre" not in buddies.preview
    assert "Sushma Bhamidipati" in buddies.preview
    assert "SharePoint — Download:" in squad.preview
    assert "SharePoint — Folder:" in squad.preview


def test_load_announce_config_workspace_channels_cc():
    cfg = sa.load_announce_config(
        {
            "slack_announce": {
                "channels": [
                    {
                        "key": "squad",
                        "name": "insights-customize-squad",
                        "cc": ["sushma", "sai_anirudh", "zeke", "eoin"],
                    },
                    {
                        "key": "buddies",
                        "name": "customize-bi-buddies",
                        "cc": ["sushma"],
                    },
                ],
            }
        }
    )
    assert [c.name for c in cfg.channels] == [
        "insights-customize-squad",
        "customize-bi-buddies",
    ]
    assert len(cfg.channels[0].cc) == 4
    assert len(cfg.channels[1].cc) == 1


def test_send_announce_without_token():
    cfg = sa.SlackAnnounceConfig(enabled=True, bot_token="", channels=sa.default_channels())
    draft = sa.draft_from_session(
        ticket_key="TCKT-1",
        summary="Prod (v2026.3.08.05)",
        ticket_url="https://x/browse/TCKT-1",
        planned_start=date(2026, 8, 5),
        sharepoint_url="",
    )
    messages = sa.build_channel_messages(draft, cfg.channels)
    results = sa.send_announce_messages(cfg, messages)
    assert all(not r.ok for r in results)
    assert "SLACK_BOT_TOKEN" in results[0].error


def test_send_announce_posts_both_channels(monkeypatch):
    cfg = sa.SlackAnnounceConfig(
        enabled=True,
        bot_token="xoxb-test",
        channels=[
            sa.SlackChannelTarget(
                key="squad",
                name="insights-customize-squad",
                channel_id="C111",
                cc=(),
            ),
            sa.SlackChannelTarget(
                key="buddies",
                name="customize-bi-buddies",
                channel_id="C222",
                cc=(),
            ),
        ],
    )
    draft = sa.draft_from_session(
        ticket_key="TCKT-1",
        summary="Prod (v2026.3.08.05)",
        ticket_url="https://x/browse/TCKT-1",
        planned_start=date(2026, 8, 5),
        sharepoint_url="",
    )
    messages = sa.build_channel_messages(draft, cfg.channels)
    posted: list[str] = []

    def fake_api(method, token, payload=None, params=None):
        if method == "chat.postMessage":
            posted.append(payload["channel"])
            return {"ok": True, "ts": "1.2"}
        if method == "chat.getPermalink":
            return {"ok": True, "permalink": "https://slack/msg"}
        raise AssertionError(method)

    with patch.object(sa, "_slack_api", side_effect=fake_api):
        results = sa.send_announce_messages(cfg, messages)

    assert posted == ["C111", "C222"]
    assert all(r.ok for r in results)
    assert results[0].permalink.startswith("https://slack")


def test_draft_from_session_uses_planned_start():
    draft = sa.draft_from_session(
        ticket_key="TCKT-111620",
        summary=("Production Deployment – Customize BI Team - Jazzercise / Jetts - Report Updates (v2026.3.07.29)"),
        ticket_url="https://abcfinancial.atlassian.net/browse/TCKT-111620",
        planned_start=date(2026, 7, 29),
        sharepoint_url="",
    )
    assert draft.version == "v2026.3.07.29"
    assert draft.deploy_date == date(2026, 7, 29)
    preview = sa.build_channel_messages(draft)[0].preview
    assert "Wednesday, July 29, 2026" in preview
    assert "Customize BI Team" in preview
    # Slack stays historical — no dual-timezone window line.
    assert "Deployment window" not in preview
    assert "IST" not in preview
    assert "CDT" not in preview


def test_ensure_canonical_cc_survives_body_edit_without_cc():
    channel = sa.default_channels()[0]
    edited = "Hello Team,\nUpdated body for squad — please review.\nThanks!"
    safe = sa.ensure_canonical_cc(edited, channel, for_preview=False)
    assert "Updated body for squad" in safe
    assert safe.rstrip().endswith(sa.format_cc_line(channel, for_preview=False))
    assert "<@U0BSG4ABZC0>" in safe
    assert not sa.missing_required_cc_tokens(safe, channel)


def test_ensure_canonical_cc_replaces_tampered_cc_line():
    channel = sa.default_channels()[1]  # buddies — Sushma only
    tampered = "Hello\nThanks!\nCC: @someone-else"
    safe = sa.ensure_canonical_cc(tampered, channel, for_preview=False)
    assert "@someone-else" not in safe
    assert "<@U08LDAQ7SDV>" in safe
    assert "<@U0BSG4ABZC0>" not in safe
    assert "<@U083R8TP1J9>" not in safe


def test_validate_announce_config_accepts_workspace_defaults():
    cfg = sa.load_announce_config(
        {
            "slack_announce": {
                "enabled": True,
                "channels": [
                    {
                        "key": "squad",
                        "name": "insights-customize-squad",
                        "cc": ["sushma", "sai_anirudh", "zeke", "eoin"],
                    },
                    {
                        "key": "buddies",
                        "name": "customize-bi-buddies",
                        "cc": ["sushma"],
                    },
                ],
            }
        }
    )
    issues = sa.validate_announce_config(cfg)
    assert not [i for i in issues if i.level == "error"]


def test_validate_announce_config_flags_wrong_channel_or_cc():
    people = sa.default_cc_people()
    cfg = sa.SlackAnnounceConfig(
        enabled=True,
        bot_token="",
        channels=[
            sa.SlackChannelTarget(
                key="squad",
                name="wrong-channel",
                cc=(people["sushma"],),
            ),
        ],
    )
    codes = {i.code for i in sa.validate_announce_config(cfg) if i.level == "error"}
    assert "channel_name_mismatch" in codes or "missing_channel" in codes
    assert "cc_mismatch" in codes or "missing_channel" in codes


def test_deployer_slack_gate_open_when_disabled():
    assert sa.deployer_slack_gate_open(enabled=False, sent=False, skipped=False)
    assert not sa.deployer_slack_gate_open(enabled=True, sent=False, skipped=False)
    assert sa.deployer_slack_gate_open(enabled=True, sent=True, skipped=False)
    assert sa.deployer_slack_gate_open(enabled=True, sent=False, skipped=True)


def test_deployer_slack_gate_open_when_not_sendable():
    """Missing bot token must not block deploy — same as disabled."""
    assert sa.deployer_slack_gate_open(enabled=True, sent=False, skipped=False, can_send=False)


def test_slack_gate_applies():
    cfg = sa.SlackAnnounceConfig(enabled=True, bot_token="", channels=[])
    assert not sa.slack_gate_applies(cfg)
    cfg2 = sa.SlackAnnounceConfig(
        enabled=True, bot_token="xoxb-test", channels=[sa.SlackChannelTarget(key="a", name="a")]
    )
    assert sa.slack_gate_applies(cfg2)
    cfg3 = sa.SlackAnnounceConfig(
        enabled=False, bot_token="xoxb-test", channels=[sa.SlackChannelTarget(key="a", name="a")]
    )
    assert not sa.slack_gate_applies(cfg3)


def test_pending_and_merge_partial_retry():
    channels = sa.default_channels()
    draft = sa.draft_from_session(
        ticket_key="TCKT-1",
        summary="Prod (v2026.3.08.05)",
        ticket_url="https://x/browse/TCKT-1",
        planned_start=date(2026, 8, 5),
        sharepoint_url="",
    )
    messages = sa.build_channel_messages(draft, channels)
    prior = [
        sa.SlackSendResult(
            channel_name="insights-customize-squad",
            ok=True,
            permalink="https://slack/1",
            ts="1.0",
        ),
        sa.SlackSendResult(
            channel_name="customize-bi-buddies",
            ok=False,
            error="channel_not_found",
        ),
    ]
    pending = sa.pending_channel_messages(messages, prior)
    assert [m.channel.name for m in pending] == ["customize-bi-buddies"]
    retry = [
        sa.SlackSendResult(
            channel_name="customize-bi-buddies",
            ok=True,
            permalink="https://slack/2",
            ts="2.0",
        )
    ]
    merged = sa.merge_send_results(prior, retry)
    assert all(r.ok for r in merged)
    assert len(merged) == 2


def test_draft_from_session_includes_download_and_folder_links():
    draft = sa.draft_from_session(
        ticket_key="SHIPIT-17191",
        summary="Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.23",
        ticket_url="https://abcfinancial.atlassian.net/browse/SHIPIT-17191",
        planned_start=date(2026, 9, 23),
        sharepoint_url=(
            "https://abcfinancial.sharepoint.com/:w:/r/teams/x/Release%20Notes%202026.3.09.23.docx?action=default"
        ),
    )
    assert draft.sharepoint_download_url.endswith("action=download")
    assert "Release Notes/2026" in draft.sharepoint_folder_label
    preview = sa.build_channel_messages(draft)[0].preview
    assert "SharePoint — Download:" in preview
    assert "SharePoint — Folder:" in preview
