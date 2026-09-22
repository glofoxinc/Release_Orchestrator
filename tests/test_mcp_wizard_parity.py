"""MCP wizard parity with platform UI — SharePoint, deploy prefill, gates."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

import release_gates
from release_mcp import wizard
from release_mcp.release_notes_preview import build_structured_preview


@pytest.fixture(autouse=True)
def _disable_release_gates_in_wizard(monkeypatch):
    monkeypatch.setattr(release_gates, "gates_root_enabled", lambda: False)
    monkeypatch.setattr(release_gates, "gate_enabled", lambda _name: False)


class TestMcpWizardParityHelpers:
    def test_structured_preview_has_sections(self):
        draft = {
            "version": "v2026.3.08.12",
            "release_date": "12-August-2026",
            "summary_p1": "This release delivers updates.",
            "extracted": [{"type": "Analyze", "client": "Standard", "report": "R1", "ticket": "AN-1"}],
            "change_rows": "1|AN-1||||||||",
        }
        preview = build_structured_preview(draft)
        assert preview["metadata"]["version"] == "v2026.3.08.12"
        assert preview["release_summary"]
        assert "delivered_reports" in preview
        assert "testing_evidence" in preview
        assert "ticket_details" in preview

    def test_sharepoint_step_offers_graph_upload(self, tmp_path: Path):
        session = {
            "id": "sess",
            "step": wizard.STEP_SHAREPOINT,
            "inputs": {"sharepoint_upload": "graph"},
            "artifacts": {
                "release_notes_docx": {
                    "docx_path": str(tmp_path / "notes.docx"),
                    "docx_filename": "Release Notes 2026.3.08.12.docx",
                }
            },
            "drafts": {},
        }
        docx = tmp_path / "notes.docx"
        docx.write_bytes(b"fake-docx")

        def _passthrough_update(_id, **kw):
            merged = {**session, **kw}
            if "artifacts" in kw:
                merged["artifacts"] = {**session.get("artifacts", {}), **kw["artifacts"]}
            if "inputs" in kw:
                merged["inputs"] = {**session.get("inputs", {}), **kw["inputs"]}
            return merged

        def _store_confirmation(_id, step, preview):
            merged = _passthrough_update(_id, artifacts={"pending_preview": preview})
            merged["confirmations"] = {step: {"token": "test-token", "preview": preview}}
            return merged

        with patch("release_mcp.wizard.wizard_store.update_session", side_effect=_passthrough_update), patch(
            "release_mcp.wizard.wizard_store.store_confirmation",
            side_effect=_store_confirmation,
        ), patch(
            "release_mcp.wizard.config.sharepoint_upload_archived",
            return_value=False,
        ), patch(
            "release_mcp.wizard.sharepoint_ops.sharepoint_upload_status",
            return_value={"can_upload": False},
        ), patch(
            "release_mcp.wizard.sharepoint_ops.sharepoint_upload_release_notes",
            return_value={"ok": True, "dry_run": True, "plan": {"folder_path": "/x"}},
        ):
            result = wizard._process_sharepoint(session)

        assert result["status"] == "awaiting_confirmation"
        assert result["preview"]["action"] == "sharepoint_upload"

    def test_deploy_prefill_suggestion_when_info_missing(self):
        session = {
            "inputs": {"deployment_project": "PIC"},
            "artifacts": {
                "ticket_snapshot": {"selected_ticket_keys": ["PIC-1"]},
                "release_notes_docx": {},
            },
            "drafts": {
                "release_notes": {
                    "deployment_rows": "Jetts|Owner|Done|abc-123 · Aug 20 2026 · 10:00 AM",
                }
            },
        }
        context = {
            "project_key": "PIC",
            "tickets_by_client": {"Jetts": ["PIC-1"]},
            "selected_default": ["PIC-1"],
        }
        suggested, sources = wizard._suggest_deployment_info(session, context)
        assert suggested or sources

    def test_consolidation_suggestions_helper(self):
        session = {
            "artifacts": {
                "ticket_snapshot": {
                    "extracted": [
                        {"ticket": "AN-1", "type": "Analyze", "client": "Standard", "report": "Members", "description": "Fix A"},
                        {"ticket": "AN-2", "type": "Analyze", "client": "Standard", "report": "Members", "description": "Fix B"},
                    ]
                }
            }
        }
        suggestions = wizard._consolidation_suggestions_for_session(session)
        assert suggestions
        assert suggestions[0]["tickets"] == ["AN-1", "AN-2"]

    def test_mark_released_skipped_without_owns_version(self):
        session = {
            "inputs": {},
            "artifacts": {
                "deployment_context": {"project_key": "PIC"},
                "deployment_results": {"PIC": {"success": 1, "errors": 0}},
                "deployed_projects": [],
            },
        }
        with patch("release_mcp.wizard.team_scope.scope_from_project") as scope_mock, patch(
            "release_mcp.wizard._after_project",
            return_value={"status": "ok", "step": "complete"},
        ) as after:
            scope_mock.return_value = type("Scope", (), {"owns_version": False})()
            wizard._process_mark_released(session)
        after.assert_called_once()
