"""Regression tests from pin-to-pin platform audit (Sep 2026)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


def test_fetch_combined_issues_survives_jira_error(monkeypatch):
    import streamlit as st
    from release_platform.ui import ticket_source as ts

    def boom(*_args, **_kwargs):
        raise RuntimeError("Jira unavailable")

    monkeypatch.setattr(
        st,
        "session_state",
        {
            "rn_locked_ticket_source": {
                "mode": ts.MODE_STATUS,
                "summary": "PIC: Review",
                "statuses": {"PIC": ["Review"]},
                "releases": {},
            },
            "rn_step": 2,
        },
        raising=False,
    )
    monkeypatch.setattr(ts.jira_client, "get_issues_for_statuses", boom)

    issues = ts.fetch_combined_issues("rn_", issues_cache_prefix="_rn_issues_")
    assert issues == []
    assert "_rn_fetch_error_PIC" in st.session_state


def test_get_selection_mode_importable_from_tr_selection():
    from release_platform.ui.ticket_review.selection import get_selection_mode

    assert callable(get_selection_mode)


def test_ensure_release_notes_draft_fills_status_only_blockers(monkeypatch):
    import streamlit as st

    from generators.release_notes_insights import assess_release_notes_readiness, readiness_data_from_session
    from release_platform.ui import helpers
    from release_platform.ui import ticket_source as ts
    from release_platform.ui.release_notes.step3_edit import ensure_release_notes_draft

    extracted = [
        {
            "type": "Analyze",
            "client": "Standard",
            "report": "Dashboard A",
            "description": "Update",
            "ticket": "AN-10",
            "assignee": "Alice",
        },
    ]
    state = {
        "rn_extracted": extracted,
        "rn_version": "",
        "rn_date": "",
        "rn_change_rows": "",
        "rn_analyze_report_rows": "",
        "rn_summary_p1": "",
        "rn_testing_evidence_tickets": "",
        "rn_locked_ticket_source": {
            "mode": ts.MODE_STATUS,
            "summary": "PIC: Review",
            "statuses": {"PIC": ["Review"]},
            "releases": {},
        },
        "rn_step": 2,
    }
    monkeypatch.setattr(st, "session_state", state, raising=False)
    monkeypatch.setattr(helpers.config, "PROJECTS", [
        {"key": "PIC", "name": "PIC"},
        {"key": "AN", "name": "AN"},
    ])
    monkeypatch.setattr(helpers.config, "RELEASE_META", {
        "dev_team": "BI Team",
        "release_owner": "Alice",
        "senior_mgr": "",
        "director": "",
        "svp": "",
        "environment": "Production",
    })

    before = assess_release_notes_readiness(
        {
            **readiness_data_from_session(state),
            "include_fix_version_metadata": False,
        }
    )
    assert not any("Release version is empty" in item.message for item in before.blockers)

    ensure_release_notes_draft()

    # Status mode now always sets version from deploy date (user requirement: always include version)
    assert state.get("rn_version")
    assert state.get("rn_version").startswith("v20")
    assert state["rn_change_rows"]
    from release_platform.ui.helpers import build_rn_readiness_payload

    payload = build_rn_readiness_payload(state)
    # Status mode now includes version metadata (derived from deploy date)
    assert payload.get("include_fix_version_metadata") is True
    assert payload.get("version")
    after = assess_release_notes_readiness(payload)
    assert after.ready


def test_ensure_release_notes_draft_fills_version_for_fix_version_mode(monkeypatch):
    import streamlit as st

    from generators.release_notes_insights import assess_release_notes_readiness
    from release_platform.ui import helpers
    from release_platform.ui import ticket_source as ts
    from release_platform.ui.release_notes.step3_edit import ensure_release_notes_draft

    extracted = [
        {
            "type": "Analyze",
            "client": "Standard",
            "report": "Dashboard A",
            "description": "Update",
            "ticket": "AN-10",
            "assignee": "Alice",
        },
    ]
    state = {
        "rn_extracted": extracted,
        "rn_version": "",
        "rn_date": "",
        "rn_change_rows": "",
        "rn_analyze_report_rows": "",
        "rn_summary_p1": "",
        "rn_testing_evidence_tickets": "",
        "rn_locked_ticket_source": {
            "mode": ts.MODE_FIX_VERSION,
            "summary": "PIC: 2026.3.07.06",
            "statuses": {},
            "releases": {"PIC": {"id": "1", "name": "2026.3.07.06"}},
        },
        "rn_release_PIC": {"id": "1", "name": "2026.3.07.06"},
        "rn_step": 2,
    }
    monkeypatch.setattr(st, "session_state", state, raising=False)
    monkeypatch.setattr(helpers.config, "PROJECTS", [
        {"key": "PIC", "name": "PIC"},
        {"key": "AN", "name": "AN"},
    ])
    monkeypatch.setattr(helpers.config, "RELEASE_META", {
        "dev_team": "BI Team",
        "release_owner": "Alice",
        "senior_mgr": "",
        "director": "",
        "svp": "",
        "environment": "Production",
    })

    ensure_release_notes_draft()

    assert state["rn_version"].startswith("v")
    assert state["rn_change_rows"]
    from release_platform.ui.helpers import build_rn_readiness_payload

    after = assess_release_notes_readiness(build_rn_readiness_payload(state))
    assert after.ready


def test_tr_step2_group_imports_config():
    import release_platform.ui.ticket_review.step2_group as step2

    assert hasattr(step2, "config")
    assert step2.config.PROJECTS


def test_ensure_step1_context_honors_locked_statuses(monkeypatch):
    import streamlit as st
    from release_platform.ui.ticket_review import step2_group as step2
    from release_platform.ui.ticket_review.selection import MODE_STATUS

    monkeypatch.setattr(
        st,
        "session_state",
        {
            "tr_step": 2,
            "tr_locked_ticket_source": {
                "mode": MODE_STATUS,
                "summary": "PIC: Review",
                "statuses": {"PIC": ["Review"], "AN": ["Passed QA"]},
                "releases": {},
            },
        },
        raising=False,
    )
    monkeypatch.setattr(step2, "get_snapshot", lambda: None)

    assert step2._ensure_step1_context() is True


def test_resolve_rn_extracted_from_all_extracted_and_change_rows():
    from release_platform.ui.helpers import resolve_rn_extracted_from_state

    all_extracted = [
        {"ticket": "AN-1", "type": "Analyze", "report": "R", "description": "x"},
        {"ticket": "PIC-2", "type": "Custom", "client": "Lift", "report": "R", "description": "y"},
    ]
    resolved = resolve_rn_extracted_from_state(
        {
            "rn_extracted": [],
            "rn_all_extracted": all_extracted,
            "rn_change_rows": "AN-1|https://example/browse/AN-1||QA|Done",
        }
    )
    assert len(resolved) == 1
    assert resolved[0]["ticket"] == "AN-1"


def test_readiness_ready_when_restored_change_rows_without_extracted():
    from generators.release_notes_insights import assess_release_notes_readiness
    from release_platform.ui.helpers import build_rn_readiness_payload

    state = {
        "rn_version": "",
        "rn_extracted": [],
        "rn_change_rows": "AN-1|https://example/browse/AN-1|Alice|QA|Done",
        "rn_testing_evidence_tickets": "AN-1\n  Add testing screenshot(s) for this ticket.",
        "rn_summary_p1": "This release delivers dashboard updates.",
    }
    report = assess_release_notes_readiness(build_rn_readiness_payload(state))
    assert report.ready
    assert report.score >= 80


def test_build_rn_readiness_payload_resolves_empty_version_with_tickets():
    from release_platform.ui.helpers import build_rn_readiness_payload

    payload = build_rn_readiness_payload(
        {
            "rn_extracted": [{"type": "Analyze", "ticket": "AN-1", "report": "R", "description": "x"}],
            "rn_version": "",
            "rn_change_rows": "1|AN-1|AN-1|AN-0|https://example/browse/AN-1|R|x|QA||Done",
        }
    )
    assert payload["version"].startswith("v")
    assert payload["dev_team"]
    assert payload["release_owner"]
