"""Review vs release-notes status split for MCP Step 1 vs Step 3."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")

from release_mcp import wizard, wizard_store
import config
from release_mcp import welcome as welcome_mod


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("test-secret")
    yield
    wizard_store.set_sessions_dir_override(None)
    wizard_store.set_token_secret_override(None)


def _ticket(key: str, project: str, status: str) -> dict:
    return {
        "ticket": key,
        "summary": f"{project} ticket",
        "status": status,
        "type": "Custom" if project == "PIC" else "Analyze",
        "client": "Jetts" if project == "PIC" else "Standard",
        "report": "Monthly Report",
        "description": "update",
        "assignee": "Owner",
        "parent": key,
        "project": project,
        "fix_version": "2026.3.09.15",
        "link": f"https://example.atlassian.net/browse/{key}",
    }


class TestReleaseNotesStatusConfig:
    def test_review_vs_release_defaults_differ(self):
        assert config.ticket_review_default_checked_statuses("PIC") == [
            "Review",
            "In Review",
            "Ready for Review",
            "In Progress",
        ]
        assert config.release_notes_default_statuses("PIC") == ["Ready for Release"]
        assert config.release_notes_default_statuses("AN") == ["QA(migrated)"]

    def test_welcome_exposes_both_status_maps(self):
        payload = welcome_mod.build_welcome()
        suggested = payload["suggested_defaults"]
        assert suggested["statuses_by_project"]["PIC"] != suggested["release_notes_statuses_by_project"]["PIC"]
        assert suggested["release_notes_statuses_by_project"]["PIC"] == ["Ready for Release"]
        assert suggested["release_notes_statuses_by_project"]["AN"] == ["QA(migrated)"]


class TestReleaseNotesRefetch:
    def test_intersects_locked_keys_with_release_ready_fetch(self):
        review_extracted = [
            _ticket("PIC-1", "PIC", "Review"),
            _ticket("PIC-2", "PIC", "Review"),
            _ticket("AN-1", "AN", "Passed QA"),
        ]
        release_extracted = [
            _ticket("PIC-1", "PIC", "Ready for Release"),
            _ticket("AN-1", "AN", "QA(migrated)"),
        ]
        snapshot = {
            "selected_ticket_keys": ["PIC-1", "PIC-2", "AN-1"],
            "excluded_ticket_keys": [],
            "extracted": review_extracted,
        }
        session = wizard_store.create_session(
            "releaseops-full",
            step=wizard.STEP_RELEASE_NOTES,
            inputs={
                "selection_mode": "status",
                "projects": ["PIC", "AN"],
                "statuses_by_project": {
                    "PIC": ["Review"],
                    "AN": ["Passed QA"],
                },
            },
        )
        session = wizard_store.update_session(
            session["id"],
            artifacts={"ticket_snapshot": snapshot},
        )

        def _fetch(**kwargs):
            statuses = kwargs.get("statuses_by_project") or {}
            if statuses.get("PIC") == ["Ready for Release"]:
                return {
                    "status": "ok",
                    "projects": ["PIC", "AN"],
                    "extracted": release_extracted,
                    "by_project": {},
                    "total_tickets": len(release_extracted),
                }
            return {
                "status": "ok",
                "projects": ["PIC", "AN"],
                "extracted": review_extracted,
                "by_project": {},
                "total_tickets": len(review_extracted),
            }

        with patch("release_mcp.wizard.release_ops.fetch_release_tickets", side_effect=_fetch):
            result = wizard._fetch_release_notes_extracted(session)

        assert result["status"] == "ok"
        assert result["release_ready_ticket_keys"] == ["PIC-1", "AN-1"]
        assert result["not_release_ready_keys"] == ["PIC-2"]

    def test_process_release_notes_blocks_when_none_release_ready(self):
        snapshot = {
            "selected_ticket_keys": ["PIC-9"],
            "excluded_ticket_keys": [],
            "extracted": [_ticket("PIC-9", "PIC", "Review")],
        }
        session = wizard_store.create_session(
            "releaseops-full",
            step=wizard.STEP_RELEASE_NOTES,
            inputs={
                "selection_mode": "status",
                "projects": ["PIC"],
                "statuses_by_project": {"PIC": ["Review"]},
            },
        )
        session = wizard_store.update_session(
            session["id"],
            artifacts={"ticket_snapshot": snapshot},
        )

        with patch(
            "release_mcp.wizard.release_ops.fetch_release_tickets",
            return_value={
                "status": "ok",
                "projects": ["PIC"],
                "extracted": [],
                "by_project": {},
                "total_tickets": 0,
            },
        ):
            result = wizard._process_release_notes(session)

        assert result["status"] == "needs_input"
        assert result["preview"]["not_release_ready_keys"] == ["PIC-9"]
        assert result["preview"]["release_ready_ticket_keys"] == []

    def test_direct_release_notes_fetch_without_lock(self):
        session = wizard_store.create_session(
            "releaseops-notes",
            step=wizard.STEP_RELEASE_NOTES,
            inputs={
                "selection_mode": "status",
                "projects": ["PIC"],
            },
        )

        release_extracted = [_ticket("PIC-3", "PIC", "Ready for Release")]

        with patch(
            "release_mcp.wizard.release_ops.fetch_release_tickets",
            return_value={
                "status": "ok",
                "projects": ["PIC"],
                "extracted": release_extracted,
                "by_project": {},
                "total_tickets": 1,
            },
        ):
            result = wizard._fetch_release_notes_extracted(session)

        assert result["status"] == "ok"
        assert result["release_ready_ticket_keys"] == ["PIC-3"]
        assert result["locked_keys"] == []

    def test_explicit_override_includes_not_release_ready_locked_ticket(self):
        review_extracted = [
            _ticket("PIC-1", "PIC", "Ready for Release"),
            _ticket("PIC-2", "PIC", "Review"),
        ]
        release_extracted = [_ticket("PIC-1", "PIC", "Ready for Release")]
        override_ticket = _ticket("PIC-2", "PIC", "Review")
        snapshot = {
            "selected_ticket_keys": ["PIC-1", "PIC-2"],
            "excluded_ticket_keys": [],
            "extracted": review_extracted,
        }
        session = wizard_store.create_session(
            "releaseops-full",
            step=wizard.STEP_RELEASE_NOTES,
            inputs={
                "selection_mode": "status",
                "projects": ["PIC"],
                "statuses_by_project": {"PIC": ["Review"]},
                "release_notes_include_ticket_keys": ["PIC-2"],
            },
        )
        session = wizard_store.update_session(
            session["id"],
            artifacts={"ticket_snapshot": snapshot},
        )

        def _fetch(**kwargs):
            statuses = kwargs.get("statuses_by_project") or {}
            if statuses.get("PIC") == ["Ready for Release"]:
                return {
                    "status": "ok",
                    "projects": ["PIC"],
                    "extracted": release_extracted,
                    "by_project": {},
                    "total_tickets": len(release_extracted),
                }
            return {
                "status": "ok",
                "projects": ["PIC"],
                "extracted": review_extracted,
                "by_project": {},
                "total_tickets": len(review_extracted),
            }

        with patch("release_mcp.wizard.release_ops.fetch_release_tickets", side_effect=_fetch), patch(
            "release_mcp.wizard.release_ops.fetch_tickets_by_keys",
            return_value={
                "status": "ok",
                "extracted": [override_ticket],
                "errors": {},
                "requested_keys": ["PIC-2"],
            },
        ):
            result = wizard._fetch_release_notes_extracted(session)

        assert result["status"] == "ok"
        assert result["release_ready_ticket_keys"] == ["PIC-1", "PIC-2"]
        assert result["explicit_override_keys"] == ["PIC-2"]
        assert result["not_release_ready_keys"] == []

    def test_process_release_notes_with_explicit_override(self):
        snapshot = {
            "selected_ticket_keys": ["PIC-9"],
            "excluded_ticket_keys": [],
            "extracted": [_ticket("PIC-9", "PIC", "Review")],
        }
        session = wizard_store.create_session(
            "releaseops-full",
            step=wizard.STEP_RELEASE_NOTES,
            inputs={
                "selection_mode": "status",
                "projects": ["PIC"],
                "statuses_by_project": {"PIC": ["Review"]},
                "release_notes_include_ticket_keys": ["PIC-9"],
                "version_name": "2026.3.09.18",
                "release_date_confirmed": True,
            },
        )
        session = wizard_store.update_session(
            session["id"],
            artifacts={"ticket_snapshot": snapshot},
        )
        override_ticket = _ticket("PIC-9", "PIC", "Review")

        with patch(
            "release_mcp.wizard.release_ops.fetch_release_tickets",
            return_value={
                "status": "ok",
                "projects": ["PIC"],
                "extracted": [],
                "by_project": {},
                "total_tickets": 0,
            },
        ), patch(
            "release_mcp.wizard.release_ops.fetch_tickets_by_keys",
            return_value={
                "status": "ok",
                "extracted": [override_ticket],
                "errors": {},
                "requested_keys": ["PIC-9"],
            },
        ), patch(
            "release_mcp.wizard.release_gates.gate_enabled",
            return_value=False,
        ):
            result = wizard._process_release_notes(session)

        assert result["status"] == "awaiting_confirmation"
        assert result["preview"]["explicit_override_keys"] == ["PIC-9"]
        assert result["preview"]["ticket_count"] == 1
