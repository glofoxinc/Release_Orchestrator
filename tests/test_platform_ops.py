"""Tests for platform-ops hardening: SharePoint, history, draft, logging, health."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestSharePointUrl:
    def test_rejects_non_sharepoint_host(self):
        from sharepoint_url import validate_sharepoint_url

        assert validate_sharepoint_url("https://example.com/a.docx") is False
        assert validate_sharepoint_url("ftp://x.sharepoint.com/a") is False
        assert validate_sharepoint_url("") is False

    def test_accepts_sharepoint_hosts(self):
        from sharepoint_url import validate_sharepoint_url

        assert validate_sharepoint_url("https://contoso.sharepoint.com/sites/team/doc.docx")
        assert validate_sharepoint_url("https://sharepoint.example/sites/Release%20Notes.docx")
        assert validate_sharepoint_url(
            "https://abcfinancial.sharepoint.com/:w:/r/teams/x/_layouts/15/Doc.aspx?file=a.docx"
        )

    def test_link_shape_soft_gate(self):
        from sharepoint_url import has_sharepoint_link_shape, validate_sharepoint_url

        url = "https://contoso.sharepoint.com/"
        assert validate_sharepoint_url(url) is True
        assert validate_sharepoint_url(url, require_link_shape=True) is False
        assert has_sharepoint_link_shape("https://contoso.sharepoint.com/sites/x/Release.docx")


class TestDeploymentHistoryAudit:
    def test_build_and_update_keeps_legacy_fields(self, tmp_path, monkeypatch):
        import deployment_history as dh

        hist = tmp_path / ".deployment_history.json"
        monkeypatch.setattr(dh, "history_path", lambda app_dir=None: str(hist))

        entry = dh.build_history_entry(
            project="PIC",
            version="v2026.3.08.10",
            clients={"Acme": {"tickets": ["PIC-1"]}},
            success=1,
            sharepoint_url="https://x.sharepoint.com/sites/doc.docx",
            tckt_key="TCKT-1",
            tckt_url="https://jira/browse/TCKT-1",
            slack_results=[
                {"channel_name": "insights-customize-squad", "ok": True, "permalink": "https://slack/p1"},
                {"channel_name": "customize-bi-buddies", "ok": False, "error": "not_in_channel"},
            ],
            project_results=[{"project": "PIC", "success": 1}],
        )
        dh.save_history(entry)
        data = dh.load_history()
        assert data[0]["project"] == "PIC"
        assert data[0]["tckt_key"] == "TCKT-1"
        assert data[0]["sharepoint_url"].endswith("doc.docx")
        assert len(data[0]["slack_results"]) == 2

        assert dh.record_mark_released(entry["timestamp"], version_id="42", version_name="v2026.3.08.10")
        data = dh.load_history()
        assert data[0]["mark_released"]["status"] == "released"

        assert dh.mark_history_entry_reverted(entry["timestamp"])
        data = dh.load_history()
        assert data[0]["reverted"] is True
        assert data[0]["success"] == 0

    def test_legacy_entry_still_loads(self, tmp_path, monkeypatch):
        import deployment_history as dh

        hist = tmp_path / ".deployment_history.json"
        hist.write_text(
            json.dumps(
                [
                    {
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "project": "AN",
                        "version": "v1",
                        "clients": {},
                        "success": 2,
                        "skipped": 0,
                        "errors": 0,
                        "undo_data": [],
                    }
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(dh, "history_path", lambda app_dir=None: str(hist))
        data = dh.load_history()
        normalized = dh.normalize_history_entry(data[0])
        assert normalized["tckt_key"] == ""
        assert normalized["slack_results"] == []


class TestDeployDraft:
    def test_round_trip(self, tmp_path, monkeypatch):
        import deploy_draft as dd

        path = tmp_path / ".deploy_draft.json"
        monkeypatch.setattr(dd, "draft_path", lambda app_dir=None: str(path))

        state = {
            "wiz_step": 4,
            "wiz_project": "PIC",
            "wiz_release": {"id": "1", "name": "v2026.3.08.10"},
            "wiz_filled": {"Acme": {"deployment_id": "D1"}},
            "wiz_deploy_selected_keys": {"PIC-1", "PIC-2"},
            "shared_sharepoint_url": "https://x.sharepoint.com/a.docx",
            "stk_created_key": "TCKT-9",
        }
        dd.save_deploy_draft(state)
        loaded = dd.load_deploy_draft()
        assert loaded is not None
        assert loaded["wiz_project"] == "PIC"
        assert set(loaded["wiz_deploy_selected_keys"]) == {"PIC-1", "PIC-2"}

        restored: dict = {}
        keys = dd.apply_deploy_draft(restored, loaded)
        assert "wiz_filled" in keys
        assert restored["wiz_deploy_selected_keys"] == {"PIC-1", "PIC-2"}

        dd.clear_deploy_draft()
        assert dd.load_deploy_draft() is None


class TestLoggingRedaction:
    def test_redacts_bot_token_and_sets_context(self):
        from common.logger import (
            clear_log_context,
            get_log_context,
            redact_secrets,
            set_log_context,
            setup_logging,
        )

        setup_logging(level="INFO", json_format=False)
        assert "***" in redact_secrets("token=xoxb-1234567890-abcdefgh")
        assert "***" in redact_secrets("Authorization: Bearer secrettokenvalue")
        set_log_context(workflow_id="wf-1", release_id="rel-9", token="should-not-store")
        ctx = get_log_context()
        assert ctx["workflow_id"] == "wf-1"
        assert ctx["release_id"] == "rel-9"
        assert "token" not in ctx
        clear_log_context()
        assert get_log_context() == {}


class TestConfigSlackSchemaAndPlaceholders:
    def test_unknown_cc_key_warns(self):
        import config

        warnings = config.validate_slack_announce_schema(
            {
                "channels": [{"key": "squad", "name": "insights-customize-squad", "cc": ["nobody"]}],
                "cc": {},
            }
        )
        assert any("unknown cc key" in w for w in warnings)

    def test_placeholder_detection(self):
        import config

        assert config.is_placeholder_credential("your-api-token-here")
        assert config.is_placeholder_credential("xoxb-your-bot-token")
        assert not config.is_placeholder_credential("xoxb-real-token-value-12345")


class TestHealthSlackAndPlaceholders:
    def test_slack_token_missing_not_shown_on_home(self):
        """Slack announce token is optional — home health must not nag about it."""
        import config
        from release_platform.ui.health import collect_setup_issues

        with (
            patch.object(config, "PROJECTS", [{
                "key": "PIC",
                "scope": {"allow_project_wide": True},
            }]),
            patch.object(config, "SERVICE_DESK_ENABLED", False),
            patch.object(config, "JIRA_API_TOKEN", "real-token-value"),
            patch.object(config, "JIRA_EMAIL", "a@b.com"),
            patch.object(config, "SLACK_ANNOUNCE", {"enabled": True, "channel_ids": {}}),
            patch.object(config, "CONFIG_WARNINGS", []),
            patch.dict(os.environ, {"SLACK_BOT_TOKEN": ""}, clear=False),
        ):
            titles = [i.title for i in collect_setup_issues()]
        assert "Slack bot token missing" not in titles
        assert "Placeholder credentials" not in titles
        assert "Setup looks good" in titles

    def test_all_good_when_configured(self):
        import config
        from release_platform.ui.health import collect_setup_issues

        with (
            patch.object(config, "PROJECTS", [{
                "key": "PIC",
                "scope": {"allow_project_wide": True},
            }]),
            patch.object(config, "SERVICE_DESK_ENABLED", True),
            patch.object(config, "TCKT_SERVICE_DESK_ID", "1"),
            patch.object(config, "TCKT_REQUEST_TYPE_ID", "2"),
            patch.object(config, "TCKT_ISSUE_TYPE_ID", "10502"),
            patch.object(config, "TCKT_FIELDS", {"approvers": "customfield_1"}),
            patch.object(config, "JIRA_API_TOKEN", "real-token-value"),
            patch.object(config, "JIRA_EMAIL", "a@b.com"),
            patch.object(config, "SLACK_ANNOUNCE", {"enabled": False}),
            patch.object(config, "CONFIG_WARNINGS", []),
            patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-real"}, clear=False),
        ):
            issues = collect_setup_issues()
        assert any(i.title == "Setup looks good" for i in issues)


class TestVerifyIntegrationsHelpers:
    def test_sharepoint_check_and_placeholders_mock(self, monkeypatch):
        import importlib.util
        from pathlib import Path

        monkeypatch.setenv("MOCK_MODE", "true")
        path = Path(__file__).resolve().parents[1] / "scripts" / "verify_integrations.py"
        spec = importlib.util.spec_from_file_location("verify_integrations", path)
        assert spec and spec.loader
        vi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vi)

        sp = vi.check_sharepoint("https://example.com/x")
        url_check = next(r for r in sp if r.name == "SharePoint URL shape")
        assert url_check.status == vi.Result.FAIL
        sp_ok = vi.check_sharepoint("https://contoso.sharepoint.com/sites/a.docx")
        url_ok = next(r for r in sp_ok if r.name == "SharePoint URL shape")
        assert url_ok.status == vi.Result.PASS

        ph = vi.check_placeholders()
        assert ph.status == vi.Result.MOCK

        assert vi._default_project_key("an") == "AN"
        assert vi._default_project_key(None)
        search = vi.check_search(None)
        assert search.status == vi.Result.MOCK


class TestSlackPreflightReadonly:
    def test_disabled_skips(self):
        import slack_announce as sa

        cfg = sa.SlackAnnounceConfig(enabled=False, bot_token="", channels=[])
        results = sa.preflight_slack_readonly(cfg)
        assert results[0].ok is True
        assert "skipped" in results[0].message.lower()

    def test_missing_token(self):
        import slack_announce as sa

        cfg = sa.SlackAnnounceConfig(
            enabled=True,
            bot_token="",
            channels=sa.default_channels(),
        )
        results = sa.preflight_slack_readonly(cfg)
        assert results[0].ok is False


class TestDeployConfirmGate:
    def test_step5_requires_explicit_confirm_helper(self):
        """Deploy execution is gated behind _render_confirm_gate, not on render."""
        import inspect

        from release_platform.ui import step5_execute

        src = inspect.getsource(step5_execute.render)
        assert "confirm_key" in src
        assert "_render_confirm_gate" in src
        assert "Confirm & Deploy" in inspect.getsource(step5_execute._render_confirm_gate)


class TestVerifyWorkspaceAndServiceDesk:
    def test_workspace_and_service_desk_config_checks(self, monkeypatch):
        import importlib.util
        from pathlib import Path

        monkeypatch.setenv("MOCK_MODE", "true")
        path = Path(__file__).resolve().parents[1] / "scripts" / "verify_integrations.py"
        spec = importlib.util.spec_from_file_location("verify_integrations", path)
        assert spec and spec.loader
        vi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vi)

        ws = vi.check_workspace_slack_schema()
        assert ws.status in (vi.Result.PASS, vi.Result.FAIL)

        sd = vi.check_service_desk(live=False)
        assert isinstance(sd, list) and sd
        assert sd[0].status in (
            vi.Result.PASS,
            vi.Result.FAIL,
            vi.Result.SKIP,
            vi.Result.MOCK,
        )
