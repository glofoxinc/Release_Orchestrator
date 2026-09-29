"""Assignee roster check at Ticket Review fetch."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from release_mcp import guided
import release_gates


def test_erasmo_not_in_squad_roster():
    extracted = [
        {
            "ticket": "AN-5483",
            "assignee": "Erasmo García",
            "summary": "Net Member Movement",
            "status": "Passed QA",
        }
    ]
    check = release_gates.build_assignee_check(extracted)
    assert check["outside_squad_count"] == 1
    assert check["outside_squad_keys"] == ["AN-5483"]
    assert release_gates.assignee_in_squad("Bharathi Aribolu")


def test_exclude_assignee_pattern():
    extracted = [
        {"ticket": "AN-5483", "assignee": "Erasmo García"},
        {"ticket": "PIC-6016", "assignee": "Bharathi Aribolu"},
    ]
    keys = release_gates.keys_matching_assignee_patterns(extracted, ["Erasmo"])
    assert keys == ["AN-5483"]


def test_outside_squad_assignees_skipped_at_fetch():
    extracted = [
        {"ticket": "PIC-6016", "assignee": "Bharathi Aribolu", "status": "Review"},
        {"ticket": "PIC-5852", "assignee": "Gabriel Barbosa", "status": "Review"},
        {"ticket": "AN-5483", "assignee": "Erasmo García", "status": "Passed QA"},
    ]
    payload = release_gates.filter_extracted_outside_squad_assignees(extracted)
    kept_keys = [item["ticket"] for item in payload["kept"]]
    assert kept_keys == ["PIC-6016"]
    assert set(payload["skipped_keys"]) == {"PIC-5852", "AN-5483"}


def test_guided_interpret_exclude_assignee():
    plan = guided.interpret_message(
        "exclude assignee Erasmo",
        workflow_id="wf-test",
    )
    assert plan["intent"] == "exclude_assignee"
    assert plan["inputs"]["exclude_assignee_names"] == ["Erasmo"]
