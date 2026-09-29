"""Canonical .state/ path resolution and migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.paths import (
    DEPLOY_DRAFT_FILE,
    ONBOARDING_STATE_FILE,
    OPERATOR_SIGNOFF_FILE,
    STATE_DIR,
    WIZARD_SESSIONS_DIR,
    wizard_sessions_dir,
)


def test_wizard_sessions_default_under_state():
    path = wizard_sessions_dir()
    assert path == WIZARD_SESSIONS_DIR
    assert "runtime" in str(path) and "state" in str(path)


def test_wizard_store_sessions_dir_uses_state(tmp_path, monkeypatch):
    import config
    import release_mcp.wizard_store as ws

    monkeypatch.setattr(config, "active_workspace_name", lambda: "")
    ws.set_sessions_dir_override(None)
    resolved = ws.sessions_dir()
    assert resolved == WIZARD_SESSIONS_DIR


def test_deploy_draft_path_under_state(monkeypatch):
    import config
    import deploy_draft

    monkeypatch.setattr(config, "active_workspace_name", lambda: "")
    path = Path(deploy_draft.draft_path())
    assert path == DEPLOY_DRAFT_FILE


def test_operator_signoff_under_state(monkeypatch):
    import config
    import operator_signoff as osign

    monkeypatch.setattr(config, "active_workspace_name", lambda: "")
    path = Path(osign.signoff_path())
    assert path == OPERATOR_SIGNOFF_FILE


def test_migrate_state_merges_legacy_sessions(tmp_path):
    import orchestrator.ops.migrate_state as mig

    state_dir = tmp_path / ".state"
    sessions_dir = state_dir / "mcp_wizard_sessions"
    legacy = tmp_path / ".mcp_wizard_sessions"
    legacy.mkdir(parents=True)
    (legacy / "wf-test.json").write_text('{"id":"wf-test"}', encoding="utf-8")

    mig.STATE_DIR = state_dir
    mig.WIZARD_SESSIONS_DIR = sessions_dir
    mig.LEGACY_SESSION_DIRS = (legacy,)
    mig.LEGACY_STATE_FILES = ()

    result = mig.migrate(apply=True)
    dest = sessions_dir / "wf-test.json"
    assert dest.is_file()
    assert any(a["action"] == "copy" for a in result["actions"])
