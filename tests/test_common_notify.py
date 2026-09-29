"""Tests for shared Slack/Teams notifier helpers."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.notify import (
    NotifyResult,
    post_webhook,
    slack_deploy_payload,
    slack_weekly_payload,
    teams_deploy_payload,
)


class TestSlackDeployPayload:
    def test_header_contains_key_and_summary(self):
        p = slack_deploy_payload(ticket_key="TCKT-1", summary="My release")
        assert "TCKT-1" in p["text"]
        assert "My release" in p["blocks"][0]["text"]["text"]

    def test_window_block_included(self):
        p = slack_deploy_payload(ticket_key="T-1", summary="s", window="10:00-13:00")
        flat = json.dumps(p)
        assert "Window" in flat and "10:00-13:00" in flat

    def test_approvers_mentioned_with_at(self):
        p = slack_deploy_payload(ticket_key="T-1", summary="s", approvers=["alice", "bob"])
        assert "@alice" in json.dumps(p)
        assert "@bob" in json.dumps(p)

    def test_url_produces_action_button(self):
        p = slack_deploy_payload(ticket_key="T-1", summary="s", url="https://x")
        kinds = [b["type"] for b in p["blocks"]]
        assert "actions" in kinds

    def test_long_header_truncated(self):
        p = slack_deploy_payload(ticket_key="T-1", summary="x" * 300)
        assert len(p["blocks"][0]["text"]["text"]) <= 150

    def test_no_window_no_section(self):
        p = slack_deploy_payload(ticket_key="T-1", summary="s")
        assert all(b["type"] != "section" or "Window" not in json.dumps(b) for b in p["blocks"])


class TestSlackWeekly:
    def test_header_includes_period(self):
        p = slack_weekly_payload(period="2026-W15", highlights=[], blockers=[])
        assert "2026-W15" in json.dumps(p)

    def test_highlights_rendered(self):
        p = slack_weekly_payload(period="X", highlights=["shipped A", "delivered B"], blockers=[])
        assert "shipped A" in json.dumps(p)

    def test_blockers_rendered(self):
        p = slack_weekly_payload(period="X", highlights=[], blockers=["auth down"])
        assert "auth down" in json.dumps(p)

    def test_url_renders_link(self):
        p = slack_weekly_payload(period="X", highlights=[], blockers=[], url="https://page")
        assert "https://page" in json.dumps(p)

    def test_caps_items_at_ten(self):
        highlights = [f"item {i}" for i in range(20)]
        p = slack_weekly_payload(period="X", highlights=highlights, blockers=[])
        body = json.dumps(p)
        assert body.count("item") <= 15  # 10 rendered + header occurrences


class TestTeamsPayload:
    def test_message_card_shape(self):
        p = teams_deploy_payload(ticket_key="T-1", summary="s", url="https://x")
        assert p["@type"] == "MessageCard"
        assert "T-1" in p["title"]
        assert p["potentialAction"][0]["targets"][0]["uri"] == "https://x"

    def test_facts_include_window_and_approvers(self):
        p = teams_deploy_payload(ticket_key="T-1", summary="s", window="10-13", approvers=["a", "b"])
        facts = {f["name"]: f["value"] for f in p["sections"][0]["facts"]}
        assert facts["Window"] == "10-13"
        assert "a" in facts["Approvers"]

    def test_no_actions_when_no_url(self):
        p = teams_deploy_payload(ticket_key="T-1", summary="s")
        assert p["potentialAction"] == []


class TestPostWebhook:
    def test_success_returns_ok(self):
        def t(url, payload):
            return 200, "ok"

        result = post_webhook("https://hook", {"k": 1}, transport=t)
        assert result.ok and result.status == 200

    def test_empty_url_returns_error(self):
        result = post_webhook("", {}, transport=lambda u, p: (200, ""))
        assert not result.ok
        assert "URL" in result.error or "url" in result.error

    def test_non_2xx_returns_error_status(self):
        result = post_webhook("https://hook", {}, transport=lambda u, p: (500, "down"))
        assert not result.ok
        assert result.status == 500

    def test_exception_captured(self):
        def raiser(u, p):
            raise RuntimeError("offline")

        result = post_webhook("https://hook", {}, transport=raiser)
        assert not result.ok
        assert "offline" in result.error

    def test_result_dict_roundtrip(self):
        d = NotifyResult(ok=True, status=200).to_dict()
        assert d["ok"] and d["status"] == 200
