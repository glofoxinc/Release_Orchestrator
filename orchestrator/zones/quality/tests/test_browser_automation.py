"""Browser automation handoffs — Playwright MCP + Slack MCP."""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


def test_sharepoint_folder_url_from_config(monkeypatch):
    import config

    monkeypatch.setattr(config, "BROWSER_AUTOMATION", {
        "enabled": True,
        "sharepoint": {
            "enabled": True,
            "hostname": "abcfinancial.sharepoint.com",
            "site_path": "/teams/ABCFitnessSolutionsLLC-Glofox-Customize",
            "folder_path": "Shared Documents/Glofox - Customize/Release Notes",
            "auto_quarter_subfolder": True,
            "viewid": "ba435012-557c-4c11-9c9b-638fba9707f6",
        },
    })
    from browser_automation import resolve_sharepoint_folder_url, resolve_sharepoint_quarter_label

    url = resolve_sharepoint_folder_url(version_name="2026.3.09.23")
    assert "abcfinancial.sharepoint.com" in url
    assert "/teams/" in url
    assert "Glofox" in url
    assert resolve_sharepoint_quarter_label(version_name="2026.3.09.23") == "2026 - Q3"
    assert "2026%20-%20Q3" in url or "2026 - Q3" in url


def test_parse_sharepoint_folder_browse_url():
    from sharepoint_url import parse_sharepoint_folder_browse_url

    url = (
        "https://abcfinancial.sharepoint.com/teams/ABCFitnessSolutionsLLC-Glofox-Customize/"
        "Shared%20Documents/Forms/AllItems.aspx?"
        "id=%2Fteams%2FABCFitnessSolutionsLLC%2DGlofox%2DCustomize%2FShared%20Documents%2F"
        "Glofox%20%2D%20Customize%2FRelease%20Notes%2F2026%20%2D%20Q3"
        "&viewid=ba435012%2D557c%2D4c11%2D9c9b%2D638fba9707f6"
    )
    parsed = parse_sharepoint_folder_browse_url(url)
    assert parsed["site_path"] == "/teams/ABCFitnessSolutionsLLC-Glofox-Customize"
    assert parsed["folder_path"] == "Shared Documents/Glofox - Customize/Release Notes"
    assert parsed["viewid"].startswith("ba435012")


def test_sharepoint_playwright_handoff_steps():
    from browser_automation import build_sharepoint_upload_handoff

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(b"fake")
        path = tmp.name
    try:
        handoff = build_sharepoint_upload_handoff(
            path,
            version_name="2026.3.09.14",
        )
    finally:
        os.unlink(path)

    assert handoff["delivery"] == "cursor_playwright_mcp"
    assert handoff["mcp"] == "playwright"
    assert handoff.get("quarter_folder")
    assert len(handoff["steps"]) >= 7
    assert handoff["steps"][0]["mcp_tool"] == "browser_navigate"
    assert any("quarter folder" in (s.get("title") or "").lower() for s in handoff["steps"])


def test_playwright_slack_send_code_inserts_hyperlinks():
    from browser_automation import playwright_slack_send_code

    compose = {
        "plain_fallback": "Hello Team,\nSharePoint: Release Notes.docx",
        "blocks": [
            {
                "type": "line",
                "parts": [
                    {"type": "text", "text": "SharePoint: "},
                    {
                        "type": "link",
                        "url": "https://example.sharepoint.com/doc.docx",
                        "label": "Release Notes.docx",
                    },
                ],
            }
        ],
    }
    code = playwright_slack_send_code(compose)
    assert "clipboard" in code
    assert "data-stringify-type" in code
    assert "example.sharepoint.com" in code
    assert "Release Notes.docx" in code


def test_playwright_slack_send_code_plain_text_legacy():
    from browser_automation import playwright_slack_send_code

    code = playwright_slack_send_code("Hello Team,\nLine two\nThanks!")
    assert "Shift" in code
    assert "sent plain text" in code


def test_slack_channel_url_includes_team_and_skip_today(monkeypatch):
    import config

    monkeypatch.setattr(config, "BROWSER_AUTOMATION", {
        "enabled": True,
        "slack": {
            "enabled": True,
            "team_id": "E05KG0EFGUW",
            "workspace_url": "https://app.slack.com/client",
            "prefer_playwright": True,
        },
    })
    from browser_automation import build_slack_channel_url, prefer_playwright_slack

    url = build_slack_channel_url("C08KM1USMM1")
    assert "E05KG0EFGUW" in url
    assert "C08KM1USMM1" in url
    assert "skip_today=1" in url
    assert prefer_playwright_slack() is True


def test_build_playwright_slack_compose_includes_links_and_mentions():
    from datetime import date

    import slack_announce as sa
    from browser_automation import build_playwright_slack_compose

    draft = sa.SlackAnnounceDraft(
        ticket_key="SHIPIT-17191",
        ticket_summary="Glofox Insights Customize BI - Prod Deployment - Release Version 2026.3.09.23",
        ticket_url="https://abcfinancial.atlassian.net/browse/SHIPIT-17191",
        version="v2026.3.09.23",
        deploy_date=date(2026, 9, 23),
        sharepoint_url="https://abcfinancial.sharepoint.com/:w:/r/teams/x/Release%20Notes%202026.3.09.23.docx",
        sharepoint_label="Release Notes 2026.3.09.23.docx",
    )
    channel = sa.default_channels()[1]
    compose = build_playwright_slack_compose(draft, channel)
    link_parts = [
        part
        for block in compose["blocks"]
        for part in (block.get("parts") or [])
        if part.get("type") == "link"
    ]
    assert len(link_parts) == 3
    assert link_parts[0]["url"].startswith("https://abcfinancial.sharepoint.com")
    assert "AllItems.aspx" in link_parts[1]["url"] or "sharepoint.com" in link_parts[1]["url"]
    assert link_parts[2]["url"].endswith("SHIPIT-17191")
    mention_parts = [p for p in compose["blocks"][-1]["parts"] if p.get("type") == "mention"]
    assert len(mention_parts) == 1
    assert mention_parts[0]["user_id"] == "U08LDAQ7SDV"


def test_slack_playwright_handoff_two_channels():
    from release_mcp import browser_ops

    handoff = browser_ops.slack_playwright_handoff(
        ticket_key="SHIPIT-999",
        summary="Prod Deployment",
        ticket_url="https://abcfinancial.atlassian.net/browse/SHIPIT-999",
        version_name="2026.3.09.14",
        sharepoint_url="https://abcfinancial.sharepoint.com/:w:/r/teams/x/Release%20Notes.docx",
        deploy_date="2026-09-14",
    )
    channels = handoff.get("channels") or []
    assert len(channels) == 2
    assert all(c.get("steps") for c in channels)
    assert all(c.get("playwright_compose", {}).get("blocks") for c in channels)
    assert handoff.get("slack_mcp", {}).get("posts")


def test_enrich_slack_preview_delivery_modes():
    from release_mcp import browser_ops

    preview = {
        "enabled": True,
        "channels": [
            {
                "key": "squad",
                "name": "insights-customize-squad",
                "channel_id": "C08HB93PEVD",
                "text": "Deploy tonight",
            },
            {
                "key": "buddies",
                "name": "customize-bi-buddies",
                "channel_id": "C08KM1USMM1",
                "text": "Deploy tonight",
            },
        ],
    }
    enriched = browser_ops.enrich_slack_preview(preview)
    assert enriched.get("can_post_via_slack_mcp") is True
    assert enriched.get("can_post_via_playwright") is True
    modes = {m["id"] for m in enriched.get("delivery_modes") or []}
    assert "slack_mcp" in modes
    assert "playwright" in modes


def test_sharepoint_browser_upload_enabled_default():
    from browser_automation import sharepoint_browser_upload_enabled

    assert sharepoint_browser_upload_enabled() is True


def test_slack_auto_handoff_after_shipit_respects_never_post(monkeypatch):
    import config
    from browser_automation import slack_auto_handoff_after_shipit

    monkeypatch.setattr(
        config,
        "SLACK_ANNOUNCE",
        {"never_post_unless_asked": True},
    )
    assert slack_auto_handoff_after_shipit() is False

    monkeypatch.setattr(
        config,
        "SLACK_ANNOUNCE",
        {"never_post_unless_asked": False},
    )
    assert slack_auto_handoff_after_shipit() is True


def test_guided_upload_sharepoint_phrase():
    from release_mcp import guided

    plan = guided.interpret_message("upload sharepoint", workflow_id="wf-1")
    assert plan["inputs"]["sharepoint_upload"] == "playwright"


def test_guided_send_slack_playwright_phrase():
    from release_mcp import guided

    plan = guided.interpret_message("send slack playwright", workflow_id="wf-1")
    assert plan["inputs"]["slack_via_playwright"] is True
    assert plan["inputs"]["slack_decision"] == "playwright"
