"""Tests for unified session restore (Phase 0)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestSessionRestoreSummary:
    def test_restore_summary_includes_domains(self):
        from session_restore import _restore_summary_lines

        draft = {
            "release_session": {
                "shared_snapshot": {"ticket_keys": ["AN-1"]},
                "shared_docx_generated": True,
                "shared_sharepoint_url": "https://example.sharepoint.com/x",
            },
            "wiz_release": {"name": "2026.3.09.09"},
        }
        lines = _restore_summary_lines(draft)
        assert any("Ticket Review" in line for line in lines)
        assert any("Release Notes" in line for line in lines)
        assert any("SharePoint" in line for line in lines)


class TestDeployDraftBytes:
    def test_bytes_round_trip(self):
        import deploy_draft as dd

        raw = b"PK fake docx bytes"
        serialized = dd._serialize_value(raw)
        assert isinstance(serialized, dict)
        restored = dd.deserialize_persisted_value("rn_docx_bytes", serialized)
        assert restored == raw

    def test_docx_sidecar_externalizes_large_bytes(self, tmp_path, monkeypatch):
        import deploy_draft as dd

        draft_file = tmp_path / ".deploy_draft.json"
        monkeypatch.setattr(dd, "draft_path", lambda app_dir=None: str(draft_file))
        raw = b"PK" * 5000
        serialized = dd._serialize_value(raw, key="rn_docx_bytes")
        assert "__docx_sidecar__" in serialized
        sidecar = serialized["__docx_sidecar__"]
        assert os.path.isfile(sidecar)
        restored = dd.deserialize_persisted_value("rn_docx_bytes", serialized)
        assert restored == raw


class TestNavigateToApp:
    def test_navigate_does_not_wipe_by_default(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import helpers

        calls: list[str] = []

        def fake_rerun():
            calls.append("rerun")

        monkeypatch.setattr(st, "session_state", {"tr_step": 2, "tr_selected_keys": {"AN-1"}}, raising=False)
        monkeypatch.setattr(helpers.st, "rerun", fake_rerun, raising=False)
        helpers.navigate_to_app("ticket_review")
        assert st.session_state["tr_step"] == 2
        assert st.session_state["active_app"] == "ticket_review"

    def test_navigate_reset_clears_prefix(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import helpers

        monkeypatch.setattr(st, "session_state", {"tr_step": 2, "rn_step": 1}, raising=False)
        monkeypatch.setattr(helpers.st, "rerun", lambda: None, raising=False)
        helpers.navigate_to_app("ticket_review", reset=True)
        assert "tr_step" not in st.session_state


class TestFixVersionFingerprintRebuild:
    def test_rebuild_from_fingerprint_with_release_name(self, monkeypatch):
        import streamlit as st
        from release_platform.ui import ticket_source as ts

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        fp = "fix_version|PIC:12345#2026.3.09.09|AN:|teams:all"
        rebuilt = ts.rebuild_locked_from_fingerprint("tr_", fp)
        assert rebuilt is not None
        assert rebuilt["releases"]["PIC"]["id"] == "12345"
        assert rebuilt["releases"]["PIC"]["name"] == "2026.3.09.09"
