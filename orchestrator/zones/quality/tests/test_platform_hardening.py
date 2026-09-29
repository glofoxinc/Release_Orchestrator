"""Tests for platform hardening (status drift, persist merge, MCP status-only)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")


def test_status_snapshot_drift_ok(monkeypatch):
    from release_platform.ui.helpers import check_snapshot_drift

    snap = {
        "selection_mode": "status",
        "status_filters": {"PIC": ["Review"]},
        "ticket_keys": ["PIC-1", "PIC-2"],
        "excluded_keys": [],
        "scope_fingerprints": {},
    }
    monkeypatch.setattr(
        "ui.helpers.get_snapshot",
        lambda: snap,
    )
    monkeypatch.setattr(
        "ui.helpers.check_snapshot_scope_drift",
        lambda: None,
    )
    monkeypatch.setattr(
        "ui.helpers.fetch_issues_for_snapshot",
        lambda _snap: [{"key": "PIC-1"}, {"key": "PIC-2"}],
    )

    result = check_snapshot_drift()
    assert result is not None
    assert result["status"] == "ok"


def test_build_draft_status_only_metadata():
    from datetime import date

    from generators.release_notes_draft import (
        build_release_notes_draft_from_extracted,
        resolve_release_version_metadata,
    )

    draft = build_release_notes_draft_from_extracted(
        [{"type": "Analyze", "ticket": "AN-1", "report": "R", "description": "x"}],
        "",
        include_fix_version_metadata=False,
    )
    assert draft["version"] == ""
    assert draft["release_date"] == ""
    assert not draft["include_fix_version_metadata"]

    version, date_label = resolve_release_version_metadata(deploy_on=date(2026, 9, 14))
    assert version == "v2026.3.09.14"
    assert date_label == "14-September-2026"
    status_draft = build_release_notes_draft_from_extracted(
        [{"type": "Analyze", "ticket": "AN-1", "report": "R", "description": "x"}],
        version.lstrip("v"),
        include_fix_version_metadata=True,
    )
    assert status_draft["version"] == "v2026.3.09.14"
    assert status_draft["release_date"] == "14-September-2026"


def test_fetch_release_tickets_status_mode(monkeypatch):
    from release_mcp import release_ops

    monkeypatch.setattr(
        release_ops.jira_client,
        "get_issues_for_statuses",
        lambda pk, statuses, jira_team_ids=None: [{"key": f"{pk}-1", "fields": {"summary": "x"}}],
    )
    monkeypatch.setattr(release_ops, "improve_extracted", lambda x: x)
    monkeypatch.setattr(
        release_ops.team_scope,
        "scope_status",
        lambda _pk: {"blocking": False},
    )

    result = release_ops.fetch_release_tickets(
        selection_mode="status",
        statuses_by_project={"PIC": ["Review"]},
    )
    assert result["status"] == "ok"
    assert result["include_fix_version_metadata"] is False


def test_persist_deploy_draft_delegates_to_session(monkeypatch):
    import release_session as rs
    from session_persist import persist_deploy_draft, persist_session

    state = {"rn_version": "v1", "shared_snapshot": {"ticket_keys": ["A-1"]}}
    calls: list[str] = []

    def _save(s):
        calls.append("save")
        return "/tmp/x.json"

    monkeypatch.setattr(rs, "save_release_session", _save)
    assert persist_deploy_draft(state) is True
    assert persist_session(state) is True
    assert calls == ["save", "save"]


def test_persistence_schema_keys():
    from persistence.schema import PLATFORM_RECOVERY_KEYS

    assert "shared_snapshot" in PLATFORM_RECOVERY_KEYS
    assert "rn_change_rows" in PLATFORM_RECOVERY_KEYS


def test_platform_recovery_keys_golden_round_trip(tmp_path, monkeypatch):
    """Core PLATFORM_RECOVERY_KEYS survive save → load → apply."""
    import deploy_draft as dd
    import release_session as rs
    from persistence.schema import PLATFORM_RECOVERY_KEYS

    path = tmp_path / ".deploy_draft.json"
    monkeypatch.setattr(dd, "draft_path", lambda app_dir=None: str(path))

    import datetime as dt

    state: dict = {
        "shared_snapshot": {"ticket_keys": ["PIC-1"], "selection_mode": "status"},
        "shared_jira_teams_locked": True,
        "shared_jira_teams_locked_values": {"PIC": [{"id": "t1", "name": "A"}]},
        "shared_sharepoint_url": "https://example.sharepoint.com/doc.docx",
        "shared_docx_generated": True,
        "shared_docx_filename": "Release Notes 2026.3.09.09.docx",
        "rn_change_rows": "PIC-1|Analyze|R|Fix",
        "rn_summary_p1": "Summary paragraph.",
        "rn_step": 3,
        "stk_summary": "Prod Deployment",
        "stk_step": 2,
        "wiz_release": {"id": "1", "name": "2026.3.09.09"},
        "stk_planned_start_date": dt.date(2026, 9, 9),
        "stk_planned_end_date": dt.date(2026, 9, 9),
        "stk_planned_start_time": dt.time(10, 0),
        "stk_planned_end_time": dt.time(13, 0),
        "stk_slack_deploy_date": dt.date(2026, 9, 9),
    }

    rs.save_release_session(state)
    loaded = rs.load_release_session()
    assert loaded is not None

    restored: dict = {}
    rs.apply_release_session(restored, loaded)
    for key in (
        "shared_snapshot",
        "shared_jira_teams_locked_values",
        "shared_sharepoint_url",
        "rn_change_rows",
        "stk_summary",
        "wiz_release",
    ):
        assert key in restored, f"missing recovery key {key}"


def test_team_filter_restore_round_trip(tmp_path, monkeypatch):
    import deploy_draft as dd
    import release_session as rs

    path = tmp_path / ".deploy_draft.json"
    monkeypatch.setattr(dd, "draft_path", lambda app_dir=None: str(path))

    locked_values = {
        "PIC": [{"id": "team-1", "name": "Squad A"}],
        "AN": [{"id": "team-2", "name": "Squad B"}],
    }
    state = {
        "shared_jira_teams_locked": True,
        "shared_jira_teams_locked_values": locked_values,
        "shared_snapshot": {
            "ticket_keys": ["PIC-1"],
            "jira_team_filters": locked_values,
            "selection_mode": "status",
        },
    }
    rs.save_release_session(state)
    loaded = rs.load_release_session()
    assert loaded is not None

    restored: dict = {}
    rs.apply_release_session(restored, loaded)
    assert restored.get("shared_jira_teams_locked") is True
    assert restored["shared_jira_teams_locked_values"]["PIC"][0]["id"] == "team-1"
    assert restored["shared_snapshot"]["jira_team_filters"]["AN"][0]["name"] == "Squad B"


def test_step1_continue_label_mode_aware(monkeypatch):
    from release_platform.ui import ticket_source as ts

    ss: dict = {}
    monkeypatch.setattr(ts.st, "session_state", ss)
    ss[ts.mode_session_key("rn_")] = ts.MODE_FIX_VERSION
    assert ts.step1_continue_label("rn_") == "Confirm fix version(s) \u2192"
    ss[ts.mode_session_key("rn_")] = ts.MODE_STATUS
    assert ts.step1_continue_label("rn_") == "Confirm statuses \u2192"
