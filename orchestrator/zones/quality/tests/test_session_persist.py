"""Tests for central session persistence helpers."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDraftHasRestorableContent:
    def test_empty_draft_is_not_restorable(self):
        from session_persist import draft_has_restorable_content

        assert draft_has_restorable_content(None) is False
        assert draft_has_restorable_content({}) is False

    def test_release_session_blob_is_restorable(self):
        from session_persist import draft_has_restorable_content

        assert draft_has_restorable_content({"release_session": {"stk_created_key": "TCKT-1"}})

    def test_stk_extracted_in_session_is_restorable(self):
        from session_persist import draft_has_restorable_content

        assert draft_has_restorable_content(
            {"release_session": {"stk_extracted": [{"ticket": "AN-1"}]}}
        )


class TestPersistSession:
    def test_persist_session_delegates_to_release_session(self, tmp_path, monkeypatch):
        import deploy_draft as dd
        import release_session as rs
        from session_persist import persist_session

        path = tmp_path / ".deploy_draft.json"
        monkeypatch.setattr(dd, "draft_path", lambda app_dir=None: str(path))

        state = {
            "wiz_release": {"id": "1", "name": "v2026.3.08.10"},
            "shared_sharepoint_url": "https://x.sharepoint.com/a.docx",
            "release_session": {"stk_created_key": "TCKT-9"},
            "rn_version": "v2026.3.08.10",
            "rn_extracted": [{"ticket": "PIC-1"}],
        }
        with patch.object(rs, "save_release_session", wraps=rs.save_release_session) as saver:
            assert persist_session(state) is True
            saver.assert_called_once_with(state)
        assert path.is_file()


class TestLoadDeployDraftWithReason:
    def test_scope_mismatch_still_returns_draft_with_warning(self, tmp_path, monkeypatch):
        import deploy_draft as dd
        import team_scope

        path = tmp_path / ".deploy_draft.json"
        monkeypatch.setattr(dd, "draft_path", lambda app_dir=None: str(path))
        path.write_text(
            '{"schema_version": 2, "scope_fingerprints": {"PIC": "old"}, "wiz_release": {"name": "x"}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(
            team_scope,
            "snapshot_scope_matches",
            lambda _stored, lenient=False: (False, ["PIC", "AN"]),
        )

        draft, reason = dd.load_deploy_draft_with_reason()
        assert draft is not None
        assert draft.get("wiz_release", {}).get("name") == "x"
        assert draft.get("_scope_restore_blocked") is True
        assert draft.get("_scope_restore_changed") == ["PIC", "AN"]
        assert "PIC" in reason
        assert "AN" in reason

    def test_v1_draft_skips_scope_check(self, tmp_path, monkeypatch):
        import deploy_draft as dd

        path = tmp_path / ".deploy_draft.json"
        monkeypatch.setattr(dd, "draft_path", lambda app_dir=None: str(path))
        path.write_text(
            '{"schema_version": 1, "scope_fingerprints": {"PIC": "old"}, '
            '"release_session": {"rn_step": 2}}',
            encoding="utf-8",
        )

        draft, reason = dd.load_deploy_draft_with_reason()
        assert draft is not None
        assert reason == ""
        assert draft.get("release_session", {}).get("rn_step") == 2


class TestStkMidWizardRestore:
    def test_shipit_wizard_state_round_trips(self, tmp_path, monkeypatch):
        import deploy_draft as dd
        import release_session as rs

        path = tmp_path / ".deploy_draft.json"
        monkeypatch.setattr(dd, "draft_path", lambda app_dir=None: str(path))

        from approver_validator import ValidationResult, GroupCheck

        state = {
            "shared_stk_standalone_mode": True,
            "stk_step": 6,
            "stk_summary": "Glofox - Insights Customize BI - Prod Deployment - Release Version 2026.3.09.09",
            "stk_sharepoint": "https://example.sharepoint.com/Release%20Notes.docx",
            "stk_extracted": [{"type": "Analyze", "ticket": "AN-1", "summary": "Fix"}],
            "stk_description_adf": {"type": "doc", "version": 1, "content": []},
            "stk_impl_plan": "Take backups.",
            "stk_test_plan": "Validate reports.",
            "stk_backout_plan": "Restore backups.",
            "stk_business_impact": "Improves accuracy.",
            "stk_approver_groups": [{"name": "Insights Customize Approvers"}],
            "stk_approver_validation": ValidationResult(
                groups=[GroupCheck(name="Insights Customize Approvers", ok=True)],
                cached_at=1.0,
            ),
            "stk_release_PIC": {"id": "99", "name": "2026.3.09.09"},
            "stk_planned_start_date": __import__("datetime").date(2026, 9, 9),
            "stk_planned_start_time": __import__("datetime").time(10, 0),
            "stk_planned_end_date": __import__("datetime").date(2026, 9, 9),
            "stk_planned_end_time": __import__("datetime").time(16, 30),
            "stk_schedule_tz": "America/Chicago",
        }
        rs.save_release_session(state)
        assert path.is_file()

        loaded = rs.load_release_session()
        assert loaded is not None
        restored: dict = {}
        rs.apply_release_session(restored, loaded)

        assert restored["stk_step"] == 6
        assert restored["stk_extracted"][0]["ticket"] == "AN-1"
        assert restored["stk_impl_plan"] == "Take backups."
        assert restored["stk_release_PIC"]["name"] == "2026.3.09.09"
        validation = restored["stk_approver_validation"]
        assert isinstance(validation, dict)
        assert validation.get("all_ok") is True

        import release_critical as rc

        blockers = rc.service_ticket_create_blockers(restored)
        assert blockers == []
