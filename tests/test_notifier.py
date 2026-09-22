"""Tests for the deployment notifier."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notifier import NotifyConfig, announce_deployment, build_deploy_context

TICKET = {
    "ticket_key": "TCKT-1",
    "summary": "Production release",
    "planned_start": "2026-04-20 10:00",
    "planned_end": "2026-04-20 13:00",
    "approvers": [{"displayName": "Alice"}, {"displayName": "Bob"}],
    "jira_url": "https://jira.example/browse/TCKT-1",
}


class TestBuildDeployContext:
    def test_flattens_approver_dicts(self):
        ctx = build_deploy_context(TICKET)
        assert ctx["approvers"] == ["Alice", "Bob"]

    def test_window_derived_from_planned_times(self):
        ctx = build_deploy_context(TICKET)
        assert "2026-04-20 10:00" in ctx["window"] and "2026-04-20 13:00" in ctx["window"]

    def test_ticket_key_preserved(self):
        assert build_deploy_context(TICKET)["ticket_key"] == "TCKT-1"

    def test_missing_window_is_empty(self):
        ctx = build_deploy_context({"ticket_key": "T"})
        assert ctx["window"] == ""

    def test_plain_approver_strings(self):
        ctx = build_deploy_context({"approvers": ["Carol", "Dave"]})
        assert ctx["approvers"] == ["Carol", "Dave"]

    def test_url_from_env_fallback(self, monkeypatch):
        monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example")
        ctx = build_deploy_context({"ticket_key": "T-9"})
        assert ctx["url"] == "https://jira.example/browse/T-9"


class TestNotifyConfig:
    def test_from_env_reads_slack_and_teams(self, monkeypatch):
        monkeypatch.setenv("SLACK_DEPLOY_WEBHOOK", "https://slack")
        monkeypatch.setenv("TEAMS_DEPLOY_WEBHOOK", "https://teams")
        cfg = NotifyConfig.from_env()
        assert cfg.slack_url == "https://slack"
        assert cfg.teams_url == "https://teams"

    def test_any_configured(self):
        assert NotifyConfig(slack_url="x").any_configured()
        assert NotifyConfig(teams_url="x").any_configured()
        assert not NotifyConfig().any_configured()


class TestAnnounceDeployment:
    def test_sends_to_both_when_configured(self):
        captured = []

        def transport(url, payload):
            captured.append((url, payload))
            return 200, "ok"

        cfg = NotifyConfig(slack_url="https://slack", teams_url="https://teams")
        outcome = announce_deployment(TICKET, cfg, transport=transport)
        assert outcome.ok
        assert outcome.slack.ok and outcome.teams.ok
        urls = [c[0] for c in captured]
        assert "https://slack" in urls and "https://teams" in urls

    def test_skips_when_none_configured(self):
        outcome = announce_deployment(TICKET, NotifyConfig(), transport=lambda u, p: (200, ""))
        assert "no webhooks configured" in outcome.skipped

    def test_records_individual_failures(self):
        def transport(url, payload):
            if "slack" in url:
                return 500, "down"
            return 200, "ok"

        cfg = NotifyConfig(slack_url="https://slack", teams_url="https://teams")
        outcome = announce_deployment(TICKET, cfg, transport=transport)
        assert not outcome.ok
        assert not outcome.slack.ok
        assert outcome.teams.ok

    def test_slack_only(self):
        cfg = NotifyConfig(slack_url="https://slack")
        outcome = announce_deployment(TICKET, cfg, transport=lambda u, p: (200, ""))
        assert outcome.slack and outcome.teams is None
        assert "teams" in outcome.skipped

    def test_outcome_dict_shape(self):
        cfg = NotifyConfig(slack_url="https://slack")
        outcome = announce_deployment(TICKET, cfg, transport=lambda u, p: (200, ""))
        d = outcome.to_dict()
        assert "slack" in d and d["slack"]["ok"]

    def test_exception_from_transport_is_captured(self):
        def transport(url, payload):
            raise ConnectionError("host unreachable")

        cfg = NotifyConfig(slack_url="https://slack")
        outcome = announce_deployment(TICKET, cfg, transport=transport)
        assert not outcome.ok
        assert "unreachable" in outcome.slack.error

    def test_payload_contains_ticket_key(self):
        captured = {}

        def transport(url, payload):
            captured["p"] = payload
            return 200, ""

        cfg = NotifyConfig(slack_url="https://slack")
        announce_deployment(TICKET, cfg, transport=transport)
        assert "TCKT-1" in json.dumps(captured["p"])
