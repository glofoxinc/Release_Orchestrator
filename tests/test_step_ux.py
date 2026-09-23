"""Tests for compact step UX helpers."""

from __future__ import annotations

from release_mcp import guided, step_ux


def test_progress_header_release_step():
    assert "3/" in step_ux.progress_header("release_notes")
    assert "Release notes" in step_ux.progress_header("release_notes")


def test_wrap_user_message_includes_say_line():
    out = step_ux.wrap_user_message("slack", "Preview ready.", status="awaiting_confirmation")
    assert "Step 6/" in out
    assert "`send slack`" in out


def test_interpret_full_release():
    plan = guided.interpret_message("full release")
    assert plan["intent"] == "full_release"
    assert plan["inputs"]["start_path"] == "fetch_review_tickets"


def test_primary_phrases_start_menu():
    assert "yes" in step_ux.primary_phrases("start_menu")
