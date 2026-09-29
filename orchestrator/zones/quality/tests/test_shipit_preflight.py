"""Tests for shipit_preflight module."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestShipitPreflight:
    def test_metadata_ok_when_configured(self):
        import config
        import shipit_preflight as sp

        with patch.object(config, "TCKT_PROJECT_KEY", "SHIPIT"), patch.object(
            config, "TCKT_ISSUE_TYPE_ID", "10401"
        ), patch.object(config, "TCKT_SERVICE_DESK_ID", "2046"), patch.object(
            config, "TCKT_REQUEST_TYPE_ID", "2969"
        ):
            out = sp.preflight_service_desk_metadata()
        assert out["status"] == "ok"
        assert out["project_key"] == "SHIPIT"

    def test_assignment_group_skip_when_blank(self):
        import shipit_preflight as sp

        out = sp.preflight_assignment_group(group_name="")
        assert out["status"] == "skip"

    def test_assignment_group_ok_when_group_exists(self, monkeypatch):
        import jira_client
        import shipit_preflight as sp

        monkeypatch.delenv("MOCK_MODE", raising=False)
        monkeypatch.setattr(
            jira_client,
            "get_group",
            lambda _name: {"name": "Insights Analyze/Customize", "groupId": "abc"},
        )
        out = sp.preflight_assignment_group(group_name="Insights Analyze/Customize")
        assert out["status"] == "ok"
        assert out["group_name"] == "Insights Analyze/Customize"

    def test_assignment_group_fail_when_missing(self, monkeypatch):
        import jira_client
        import shipit_preflight as sp

        monkeypatch.delenv("MOCK_MODE", raising=False)
        monkeypatch.setattr(jira_client, "get_group", lambda _name: None)
        out = sp.preflight_assignment_group(group_name="No Such Group")
        assert out["status"] == "fail"

    def test_assignment_group_warn_on_jira_400(self, monkeypatch):
        import jira_client
        import shipit_preflight as sp

        monkeypatch.delenv("MOCK_MODE", raising=False)
        err = jira_client.JiraApiError("bad", status_code=400)
        monkeypatch.setattr(jira_client, "get_group", lambda _name: (_ for _ in ()).throw(err))
        out = sp.preflight_assignment_group(group_name="Bad/Group")
        assert out["status"] == "warn"

    def test_dry_run_safe_offline_fallback(self, monkeypatch):
        import jira_client
        import shipit_preflight as sp

        err = jira_client.JiraApiError("PIC missing", status_code=404)

        def _boom(**_kwargs):
            raise err

        monkeypatch.setattr(sp, "preflight_shipit_create_dry_run", _boom)
        out = sp.preflight_shipit_create_dry_run_safe(
            version_name="2026.3.09.11",
            sharepoint_url="https://example.com/Release%20Notes%202026.3.09.11.docx",
        )
        assert out.get("offline_fallback") is True
        assert out.get("jira_error") == str(err)
        assert out.get("status") in {"dry_run", "preflight_failed"}
