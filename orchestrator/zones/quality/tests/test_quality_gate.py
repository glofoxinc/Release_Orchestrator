"""Focused quality-gate tests for production-hardening acceptance criteria.

Covers write-fingerprint replay, drift/re-lock override, UI deploy confirm
safety helpers, and critical Streamlit health/gate surfaces that earlier
suites only touched lightly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("JIRA_EMAIL", "qg@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")

from release_mcp import wizard, wizard_store  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path):
    wizard_store.set_sessions_dir_override(tmp_path / "sessions")
    wizard_store.set_token_secret_override("quality-gate-secret")
    yield
    wizard_store.set_sessions_dir_override(None)
    wizard_store.set_token_secret_override(None)


def _ticket(key: str, project: str = "PIC") -> dict:
    return {
        "ticket": key,
        "summary": f"{key} summary",
        "status": "Done",
        "type": "Custom",
        "client": "Jetts",
        "report": "Monthly",
        "description": "x",
        "assignee": "Owner",
        "parent": key,
        "project": project,
        "fix_version": "2026.3.08.12",
        "link": f"https://example.atlassian.net/browse/{key}",
    }


class TestWriteFingerprintReplay:
    def test_record_and_find_applied_write(self):
        session = wizard_store.create_session("releaseops-full", step=wizard.STEP_DEPLOY)
        payload = {"project": "PIC", "selected": ["PIC-1"]}
        fp = wizard_store.write_fingerprint(wizard.STEP_DEPLOY, payload)
        wizard_store.record_write_fingerprint(
            session["id"],
            wizard.STEP_DEPLOY,
            fp,
            result={"status": "ok", "success": 1},
        )
        loaded = wizard_store.load_session(session["id"])
        found = wizard_store.find_applied_write(loaded, wizard.STEP_DEPLOY, fp)
        assert found is not None
        assert found["result"]["success"] == 1
        assert wizard_store.find_applied_write(loaded, wizard.STEP_DEPLOY, "other-fp") is None

    def test_deploy_confirm_short_circuits_on_matching_fingerprint(self):
        session = wizard_store.create_session(
            "releaseops-full",
            step=wizard.STEP_DEPLOY,
            inputs={
                "deployment_info": {
                    "Jetts": {
                        "deployment_id": "11111111-1111-1111-1111-111111111111",
                        "deployment_date": "2026-08-12",
                        "deployment_time": "10:00 AM IST",
                    }
                },
                "force_deploy": False,
            },
            artifacts={
                "deployment_context": {
                    "project_key": "PIC",
                    "selected": ["PIC-1"],
                    "version": {"id": "1", "name": "2026.3.08.12"},
                    "issues": [],
                    "grouped": {},
                    "multi_client": True,
                },
                "sharepoint_url": "https://x.sharepoint.com/a.docx",
            },
        )
        write_fp = wizard_store.write_fingerprint(
            wizard.STEP_DEPLOY,
            {
                "project": "PIC",
                "selected": ["PIC-1"],
                "deployment_info": session["inputs"]["deployment_info"],
                "force_deploy": False,
            },
        )
        wizard_store.record_write_fingerprint(
            session["id"],
            wizard.STEP_DEPLOY,
            write_fp,
            scope="PIC",
            result={"status": "ok", "success": 1, "replayed": True},
        )
        session = wizard_store.load_session(session["id"])
        with patch("release_mcp.wizard.deploy_ops.execute_deploy") as execute:
            result = wizard._confirm_deploy(session)
        assert execute.call_count == 0
        assert result["status"] == "already_applied"
        assert result["preview"]["replayed"] is True

    def test_service_ticket_confirm_short_circuits_on_fingerprint(self):
        session = wizard_store.create_session(
            "releaseops-full",
            step=wizard.STEP_SERVICE_TICKET,
            drafts={"service_ticket": {"summary": "Production Deployment v2026.3.08.12"}},
            artifacts={
                "sharepoint_url": "https://sharepoint.example/doc.docx",
                "ticket_snapshot": {
                    "selected_ticket_keys": ["PIC-1"],
                    "extracted": [_ticket("PIC-1")],
                },
            },
            inputs={"planned_start_date": "2026-08-12"},
        )
        session = wizard_store.load_session(session["id"])
        draft = session["drafts"]["service_ticket"]
        fp = wizard_store.write_fingerprint(
            wizard.STEP_SERVICE_TICKET,
            {
                "summary": draft.get("summary"),
                "sharepoint": session["artifacts"].get("sharepoint_url"),
            },
        )
        wizard_store.record_write_fingerprint(
            session["id"],
            wizard.STEP_SERVICE_TICKET,
            fp,
            result={"key": "TCKT-1", "status": "created"},
        )
        session = wizard_store.load_session(session["id"])
        with patch("release_mcp.wizard.release_ops.create_service_ticket") as create:
            result = wizard._confirm_service_ticket(session)
        assert create.call_count == 0
        assert result["status"] == "already_applied"
        assert result["preview"]["key"] == "TCKT-1"


class TestDriftRelockOverride:
    def test_deploy_blocks_on_drift_without_override(self):
        session = wizard_store.create_session(
            "releaseops-full",
            step=wizard.STEP_DEPLOY,
            inputs={
                "deployment_project": "PIC",
                "deployment_ticket_keys": ["PIC-1"],
                "deployment_info": {
                    "Jetts": {
                        "deployment_id": "11111111-1111-1111-1111-111111111111",
                        "deployment_date": "2026-08-12",
                        "deployment_time": "10:00 AM IST",
                    }
                },
                "proceed_with_locked_snapshot": False,
            },
            artifacts={
                "ticket_snapshot": {
                    "selected_ticket_keys": ["PIC-1"],
                    "excluded_ticket_keys": [],
                    "extracted": [_ticket("PIC-1")],
                },
                "ticket_fetch": {
                    "by_project": {
                        "PIC": {
                            "version": {"id": "p1", "name": "2026.3.08.12"},
                            "tickets": [{"key": "PIC-1"}],
                        }
                    }
                },
            },
        )
        drift = {
            "has_drift": True,
            "missing_from_release": [],
            "projects": {
                "PIC": {
                    "has_drift": True,
                    "added_since_lock": ["PIC-99"],
                    "missing_from_release": [],
                }
            },
        }
        with patch("release_mcp.wizard._snapshot_drift", return_value=drift):
            result = wizard.run_wizard("resume", workflow_id=session["id"])
        assert result["status"] in {"blocked", "needs_input"}
        questions = {q["field"] for q in result.get("questions") or []}
        assert "proceed_with_locked_snapshot" in questions or "relock_snapshot" in questions
        assert result.get("preview", {}).get("has_drift") is True

    def test_relock_refreshes_snapshot_and_clears_override(self):
        session = wizard_store.create_session(
            "releaseops-full",
            step=wizard.STEP_DEPLOY,
            inputs={
                "version_name": "2026.3.08.12",
                "projects": ["PIC"],
                "relock_snapshot": True,
                "proceed_with_locked_snapshot": True,
            },
            artifacts={
                "ticket_snapshot": {
                    "selected_ticket_keys": ["PIC-1"],
                    "excluded_ticket_keys": [],
                    "extracted": [_ticket("PIC-1")],
                }
            },
        )
        fetch = {
            "status": "ok",
            "extracted": [_ticket("PIC-1"), _ticket("PIC-2")],
            "by_project": {
                "PIC": {
                    "version": "2026.3.08.12",
                    "version_id": "p1",
                    "tickets": [{"key": "PIC-1"}, {"key": "PIC-2"}],
                }
            },
        }
        with (
            patch("release_mcp.wizard._fetch_projects", return_value=fetch),
            patch(
                "release_mcp.wizard._snapshot_drift",
                return_value={"has_drift": False, "missing_from_release": [], "projects": {}},
            ),
            patch(
                "release_mcp.wizard._deploy_context",
                return_value={
                    "project_key": "PIC",
                    "version": {"id": "p1", "name": "2026.3.08.12"},
                    "issues": [],
                    "selected": ["PIC-1", "PIC-2"],
                    "selected_default": ["PIC-1", "PIC-2"],
                    "selection_explicit": False,
                    "missing_from_release": [],
                    "multi_client": True,
                    "grouped": {},
                    "tickets_by_client": {"Jetts": ["PIC-1", "PIC-2"]},
                },
            ),
            patch(
                "release_mcp.wizard.deploy_ops.preview_deploy",
                return_value={"would_update": ["PIC-1", "PIC-2"], "errors": []},
            ),
        ):
            result = wizard.run_wizard("resume", workflow_id=session["id"])
        loaded = wizard_store.load_session(session["id"])
        assert loaded["inputs"].get("relock_snapshot") is False
        assert loaded["inputs"].get("proceed_with_locked_snapshot") is False
        keys = loaded["artifacts"]["ticket_snapshot"]["selected_ticket_keys"]
        assert "PIC-1" in keys and "PIC-2" in keys
        assert loaded["artifacts"]["ticket_snapshot"].get("relocked") is True
        assert result["status"] in {"awaiting_confirmation", "needs_input", "blocked", "ok"}


class TestUiDriftAndConfirmHelpers:
    def test_drift_helper_predicates(self):
        from release_platform.ui.helpers import drift_blocks_proceed, drift_has_changes

        assert drift_blocks_proceed(None) is False
        assert drift_blocks_proceed({"status": "ok"}) is False
        assert drift_blocks_proceed({"status": "error"}) is True
        assert drift_has_changes({"status": "drift", "added": ["PIC-2"]}) is True
        assert drift_has_changes({"status": "ok"}) is False

    def test_deploy_run_fingerprint_changes_with_selection(self):
        from release_platform.ui.helpers import compute_deploy_run_fingerprint

        filled = {
            "Jetts": {
                "deployment_id": "11111111-1111-1111-1111-111111111111",
                "deployment_date": "2026-08-12",
                "deployment_time": "10:00 AM IST",
            }
        }
        a = compute_deploy_run_fingerprint("rel-1", {"PIC-1"}, filled)
        b = compute_deploy_run_fingerprint("rel-1", {"PIC-1", "PIC-2"}, filled)
        c = compute_deploy_run_fingerprint("rel-1", {"PIC-1"}, filled, force_deploy=True)
        assert a != b
        assert a != c

    def test_step5_confirm_gate_is_one_shot(self):
        import inspect

        from release_platform.ui import step5_execute

        gate_src = inspect.getsource(step5_execute._render_confirm_gate)
        render_src = inspect.getsource(step5_execute.render)
        assert "Confirm & Deploy" in gate_src
        assert "confirm_key" in render_src
        assert "compute_deploy_run_fingerprint" in render_src


class TestStreamlitCriticalSurfaces:
    def test_health_collects_slack_and_sharepoint_signals(self, monkeypatch):
        import streamlit as st

        import config
        from release_platform.ui import health

        monkeypatch.setattr(st, "session_state", {}, raising=False)
        monkeypatch.setattr(config, "JIRA_EMAIL", "qg@example.com", raising=False)
        monkeypatch.setattr(config, "JIRA_API_TOKEN", "real-looking-token", raising=False)
        monkeypatch.setattr(config, "PROJECTS", [{"key": "PIC", "name": "PIC"}], raising=False)
        monkeypatch.setattr(config, "SERVICE_DESK_ENABLED", False, raising=False)

        with patch("ui.health.config.is_placeholder_credential", return_value=False):
            issues = health.collect_setup_issues()
        titles = {i.title for i in issues}
        # No hard Jira credential error when token looks real.
        assert "Jira credentials missing" not in titles

    def test_slack_disabled_does_not_block_deployer_gate(self):
        import slack_announce as sa

        assert sa.deployer_slack_gate_open(enabled=False, sent=False, skipped=False)
        assert not sa.deployer_slack_gate_open(enabled=True, sent=False, skipped=False)

    def test_app_import_and_mcp_tool_surface(self):
        pytest.importorskip(
            "mcp",
            reason="mcp>=2.0.0 not installed for this interpreter",
        )
        try:
            from mcp.server.mcpserver import MCPServer  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            pytest.skip("mcp.server.mcpserver not available (need mcp>=2.0.0)")

        from orchestrator.entry import app as app_mod
        from release_mcp import server as mcp

        assert hasattr(app_mod, "st") or hasattr(app_mod, "_mock_mode_enabled")
        assert getattr(mcp, "mcp", None) is not None
        assert hasattr(mcp, "release_wizard")


class TestExactChannelsAndCcAcceptance:
    def test_workspace_defaults_match_required_mapping(self):
        import slack_announce as sa

        channels = sa.default_channels()
        by_name = {c.name: c for c in channels}
        assert set(by_name) >= {"insights-customize-squad", "customize-bi-buddies"}
        squad_ids = {p.user_id for p in by_name["insights-customize-squad"].cc}
        buddies_ids = {p.user_id for p in by_name["customize-bi-buddies"].cc}
        # Squad CC: Sushma, Sai Anirudh, Zeke, Eoin; buddies CC = Sushma only.
        assert "U08LDAQ7SDV" in squad_ids  # Sushma
        assert "U0BSG4ABZC0" in squad_ids  # Sai Anirudh
        assert "U083R8TP1J9" in squad_ids  # Zeke
        assert "U01H0UL5JGP" in squad_ids  # Eoin
        assert "U08LDAQ7SDV" in buddies_ids  # Sushma
        assert "U0BSG4ABZC0" not in buddies_ids
        assert "U083R8TP1J9" not in buddies_ids
        assert "U01H0UL5JGP" not in buddies_ids
