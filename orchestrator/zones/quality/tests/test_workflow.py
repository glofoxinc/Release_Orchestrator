"""Tests for release workflow prerequisites and blockers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


def _state(**kwargs):
    base = {
        "shared_snapshot": {"ticket_keys": ["PIC-1"], "issues": []},
        "shared_docx_generated": True,
        "shared_sharepoint_url": "https://sharepoint.example/doc.docx",
    }
    base.update(kwargs)
    return base


class TestCheckAppPrerequisites:
    def test_ticket_review_always_ok(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        result = workflow.check_app_prerequisites("ticket_review")
        assert result.ok is True

    def test_release_notes_needs_snapshot(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        result = workflow.check_app_prerequisites("release_notes")
        assert result.ok is False
        assert any("Ticket Review" in m for m in result.missing)

    def test_service_ticket_needs_doc_and_sharepoint(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(
            st,
            "session_state",
            _state(shared_docx_generated=False, shared_sharepoint_url=""),
            raising=False,
        )
        result = workflow.check_app_prerequisites("service_ticket")
        assert result.ok is False
        assert len(result.missing) >= 2
        release_fixes = [app for app, _ in result.fixes if app == "release_notes"]
        assert len(release_fixes) == 1

    def test_service_ticket_standalone_skips_prerequisites(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        workflow.enable_service_ticket_standalone()
        result = workflow.check_app_prerequisites("service_ticket")
        assert result.ok is True
        assert result.missing == []

    def test_release_notes_standalone_skips_snapshot(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        workflow.enable_release_notes_standalone()
        result = workflow.check_app_prerequisites("release_notes")
        assert result.ok is True
        assert result.missing == []

    def test_service_ticket_ok_when_ready(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", _state(), raising=False)
        result = workflow.check_app_prerequisites("service_ticket")
        assert result.ok is True

    def test_deployer_needs_tckt(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", _state(), raising=False)
        result = workflow.check_app_prerequisites("release_deployer")
        assert result.ok is False
        assert any("Service Ticket" in m for m in result.missing)

    def test_deployer_standalone_skips_prerequisites(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        workflow.enable_deployer_standalone()
        result = workflow.check_app_prerequisites("release_deployer")
        assert result.ok is True
        assert result.missing == []


class TestServiceTicketCreateBlockers:
    def test_blocks_missing_sharepoint(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", _state(), raising=False)
        ss = {
            "stk_summary": "Deploy v1",
            "stk_description_adf": {"type": "doc"},
            "stk_extracted": [{"type": "Analyze", "ticket": "PIC-1"}],
            "stk_impl_plan": "plan",
            "stk_test_plan": "test",
            "stk_backout_plan": "back",
            "stk_business_impact": "impact",
            "stk_sharepoint": "",
        }
        blockers = workflow.service_ticket_create_blockers(ss)
        assert any("SharePoint" in b for b in blockers)

    def test_standalone_skips_doc_and_snapshot_blockers(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", {"shared_stk_standalone_mode": True}, raising=False)
        ss = {
            "stk_summary": "Deploy v1",
            "stk_description_adf": {"type": "doc"},
            "stk_extracted": [{"type": "Analyze", "ticket": "PIC-1"}],
            "stk_impl_plan": "plan",
            "stk_test_plan": "test",
            "stk_backout_plan": "back",
            "stk_business_impact": "impact",
            "stk_sharepoint": "https://sharepoint.example/doc.docx",
            "stk_approvers": [{"accountId": "abc123"}],
            "stk_approver_groups": [{"name": "Command Center"}],
        }
        blockers = workflow.service_ticket_create_blockers(ss)
        assert blockers == []
        assert not any("Release Notes" in b for b in blockers)
        assert not any("Ticket Review" in b for b in blockers)

    def test_no_blockers_when_complete(self, monkeypatch):
        import streamlit as st

        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", _state(), raising=False)
        ss = {
            "stk_summary": "Deploy v1",
            "stk_description_adf": {"type": "doc"},
            "stk_extracted": [{"type": "Analyze", "ticket": "PIC-1"}],
            "stk_impl_plan": "plan",
            "stk_test_plan": "test",
            "stk_backout_plan": "back",
            "stk_business_impact": "impact",
            "stk_sharepoint": "https://sharepoint.example/doc.docx",
            "stk_approvers": [{"accountId": "abc123"}],
            "stk_approver_groups": [{"name": "Command Center"}],
        }
        assert workflow.service_ticket_create_blockers(ss) == []

    def test_approvers_from_workspace_defaults_not_blocker(self, monkeypatch):
        import streamlit as st

        import config
        from release_platform.ui import workflow

        monkeypatch.setattr(st, "session_state", _state(), raising=False)
        ss = {
            "stk_summary": "Deploy v1",
            "stk_description_adf": {"type": "doc"},
            "stk_extracted": [{"type": "Analyze", "ticket": "PIC-1"}],
            "stk_impl_plan": "plan",
            "stk_test_plan": "test",
            "stk_backout_plan": "back",
            "stk_business_impact": "impact",
            "stk_sharepoint": "https://sharepoint.example/doc.docx",
        }
        with monkeypatch.context() as m:
            m.setattr(
                config,
                "TCKT_DEFAULTS",
                {
                    **config.TCKT_DEFAULTS,
                    "approvers": [{"accountId": "default-user"}],
                    "approver_groups": [{"name": "Command Center"}],
                },
            )
            blockers = workflow.service_ticket_create_blockers(ss)
        assert blockers == []


class TestLockPendingTicketReview:
    def test_locks_from_cached_selection(self, monkeypatch):
        import streamlit as st

        from release_platform.ui.helpers import (
            get_snapshot_ticket_keys,
            lock_pending_ticket_review,
            ticket_issues_cache_key,
        )
        from release_platform.ui.ticket_review.jira_team_filter import team_filter_cache_suffix

        base_key = ticket_issues_cache_key("PIC", "99")
        cache_key = f"{base_key}_{team_filter_cache_suffix('PIC')}"
        state = {
            "shared_release_PIC": {"id": "99", "name": "2026.3.07.29"},
            "tr_selected_keys": {"PIC-1", "PIC-2"},
            cache_key: [
                {"key": "PIC-1", "fields": {"summary": "A"}},
                {"key": "PIC-2", "fields": {"summary": "B"}},
            ],
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        outcome = lock_pending_ticket_review()
        assert outcome["ok"] is True
        assert outcome["count"] == 2
        assert get_snapshot_ticket_keys() == {"PIC-1", "PIC-2"}


class TestSharepointHelpers:
    def test_validate_sharepoint_url(self):
        from release_platform.ui.workflow import validate_sharepoint_url

        assert validate_sharepoint_url("https://x.sharepoint.com/a.docx") is True
        assert validate_sharepoint_url("https://example.com/a.docx") is False
        assert validate_sharepoint_url("ftp://x.com") is False
        assert validate_sharepoint_url("") is False

    def test_save_sharepoint_url_syncs_stk(self, monkeypatch):
        import streamlit as st

        from release_platform.ui.workflow import save_sharepoint_url

        state = {}
        monkeypatch.setattr(st, "session_state", state, raising=False)
        save_sharepoint_url("  https://sp/doc  ")
        assert state["shared_sharepoint_url"] == "https://sp/doc"
        assert state["stk_sharepoint"] == "https://sp/doc"

    def test_sync_sharepoint_from_shared(self, monkeypatch):
        import streamlit as st

        from release_platform.ui.helpers import sync_sharepoint_from_shared

        state = {"shared_sharepoint_url": "https://sp/release.docx"}
        monkeypatch.setattr(st, "session_state", state, raising=False)
        sync_sharepoint_from_shared()
        assert state["stk_sharepoint"] == "https://sp/release.docx"

    def test_sync_sharepoint_does_not_overwrite_user_edit(self, monkeypatch):
        import streamlit as st

        from release_platform.ui.helpers import sync_sharepoint_from_shared

        state = {
            "shared_sharepoint_url": "https://sp/from-rn.docx",
            "stk_sharepoint": "https://sp/user-edited.docx",
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        sync_sharepoint_from_shared()
        assert state["stk_sharepoint"] == "https://sp/user-edited.docx"
