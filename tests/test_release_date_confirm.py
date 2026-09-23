"""Release date confirmation — Jira fixVersion first, user confirm."""

from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import release_date_confirm


def test_proposal_jira_consensus():
    session = {"inputs": {"selection_mode": "status"}}
    with patch.object(
        release_date_confirm,
        "fetch_fix_versions_by_ticket",
        return_value={
            "PIC-6016": ["2026.3.09.18"],
            "PIC-6057": ["2026.3.09.18"],
        },
    ):
        proposal = release_date_confirm.build_release_date_proposal(
            session, ["PIC-6016", "PIC-6057"]
        )
    assert proposal["source"] == "jira_consensus"
    assert proposal["version_name"] == "2026.3.09.18"
    assert proposal["deploy_date"] == "2026-09-18"


def test_proposal_no_jira_suggests_t_plus_one():
    session = {"inputs": {"selection_mode": "status"}}

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 17)

    with patch.object(release_date_confirm, "date", _FixedDate), patch.object(
        release_date_confirm,
        "fetch_fix_versions_by_ticket",
        return_value={"PIC-6016": [], "PIC-6057": []},
    ):
        proposal = release_date_confirm.build_release_date_proposal(
            session, ["PIC-6016", "PIC-6057"]
        )
    assert proposal["source"] == "no_jira_fix_version"
    assert proposal["version_name"] == "2026.3.09.18"
    assert proposal["suggested_t_plus_one"]["version_name"] == "2026.3.09.18"


def test_confirmed_inputs_from_user_override():
    proposal = {
        "source": "no_jira_fix_version",
        "version_name": "2026.3.09.18",
        "deploy_date": "2026-09-18",
    }
    out = release_date_confirm.confirmed_inputs(
        {"version_name": "2026.3.09.20"},
        proposal,
    )
    assert out["version_name"] == "2026.3.09.20"
    assert out["release_date_confirmed"] is True
    assert out["planned_deploy_date"] == "2026-09-20"
    assert "planned_start_date" not in out


def test_wizard_gate_blocks_release_notes_until_confirm():
    from release_mcp import wizard, wizard_store

    session = wizard_store.create_session(
        "releaseops-full",
        step=wizard.STEP_RELEASE_NOTES,
        inputs={"selection_mode": "status", "projects": ["PIC"]},
        artifacts={
            "ticket_snapshot": {
                "selected_ticket_keys": ["PIC-6016"],
                "extracted": [{"ticket": "PIC-6016", "assignee": "Test"}],
            }
        },
    )
    with patch.object(
        release_date_confirm,
        "fetch_fix_versions_by_ticket",
        return_value={"PIC-6016": ["2026.3.09.18"]},
    ):
        result = wizard._process_release_notes(session)
    assert result["status"] == "awaiting_confirmation"
    assert result["step"] == wizard.STEP_RELEASE_DATE
    assert result["preview"]["release_date_proposal"]["source"] == "jira_consensus"
