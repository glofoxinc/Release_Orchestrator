"""Phrase routing — fetch review vs fetch release list vs review call schedule."""

from __future__ import annotations

from unittest.mock import patch

from release_mcp import guided, release_ops


def test_fetch_review_start_path():
    plan = guided.interpret_message("fetch review tickets")
    assert plan["inputs"]["start_path"] == "fetch_review_tickets"


def test_fetch_review_shorthand():
    plan = guided.interpret_message("fetch review")
    assert plan["inputs"]["start_path"] == "fetch_review_tickets"


def test_fetch_release_tickets_list_action():
    plan = guided.interpret_message("fetch release tickets")
    assert plan["action"] == "list_release_tickets"
    assert "start_path" not in plan.get("inputs", {})


def test_fetch_release_not_confused_with_release_notes():
    plan = guided.interpret_message("create release notes")
    assert plan["inputs"].get("start_path") == "release_notes"


def test_review_call_schedule_handoff():
    plan = guided.interpret_message("review call schedule")
    assert plan["action"] == "daily_review_calendar_handoff"


def test_schedule_review_call_handoff():
    plan = guided.interpret_message("schedule review call")
    assert plan["action"] == "daily_review_calendar_handoff"


def test_format_extracted_list_lines():
    rows = [
        {"ticket": "PIC-1", "client": "Jetts", "summary": "Fix filter"},
        {"ticket": "AN-2", "summary": "Currency fix"},
    ]
    text = release_ops.format_extracted_list_lines(rows)
    assert "PIC-1 – Jetts – Fix filter" in text
    assert "AN-2 – Currency fix" in text


def test_list_release_ready_tickets_formats(monkeypatch):
    monkeypatch.setattr(
        release_ops,
        "fetch_release_tickets",
        lambda **kwargs: {
            "status": "ok",
            "extracted": [{"ticket": "PIC-99", "client": "X", "summary": "Y"}],
        },
    )
    monkeypatch.setattr(
        "release_gates.filter_extracted_outside_squad_assignees",
        lambda extracted, **kw: {"status": "ok", "kept": extracted},
    )
    out = release_ops.list_release_ready_tickets(projects=["PIC"])
    assert out["list_only"] is True
    assert out["ticket_count"] == 1
    assert "PIC-99" in out["formatted_list"]


def test_run_guided_list_release_tickets(monkeypatch):
    monkeypatch.setattr(
        release_ops,
        "list_release_ready_tickets",
        lambda **kwargs: {
            "status": "ok",
            "ticket_count": 2,
            "formatted_list": "PIC-1 – A – One\nPIC-2 – B – Two",
        },
    )
    with patch.object(guided.welcome, "resolve_team", return_value={"status": "ok", "team": {"id": "t1"}}):
        result = guided.run_guided("fetch release tickets")
    assert result["step"] == "ticket_list"
    assert "2 release-ready" in result["say_to_user"]
    assert "PIC-1" in result["say_to_user"]
