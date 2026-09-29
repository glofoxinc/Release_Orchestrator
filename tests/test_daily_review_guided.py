"""Guided daily review orchestrator smoke tests."""

from __future__ import annotations

from release_mcp import daily_review_guided


def test_daily_review_welcome_starts_flow():
    result = daily_review_guided.run_daily_review_guided("daily review welcome")
    assert result.get("workflow_id")
    assert result.get("step") == "welcome"
    assert "Daily Review Agent" in result.get("say_to_user", "")
    assert "yes" in result.get("user_can_say", [])


def test_daily_review_advances_to_setup_on_yes():
    first = daily_review_guided.run_daily_review_guided("daily review welcome")
    wid = first["workflow_id"]
    second = daily_review_guided.run_daily_review_guided("yes", workflow_id=wid)
    assert second.get("step") in {"setup", "mcp", "outlook", "teams"}
    say = second.get("say_to_user", "")
    assert (
        "setup_report" in second
        or "Checklist" in say
        or "Teams" in say
        or "Outlook" in say
    )


def test_daily_review_help_returns_status():
    first = daily_review_guided.run_daily_review_guided("daily review welcome")
    help_result = daily_review_guided.run_daily_review_guided("help", workflow_id=first["workflow_id"])
    assert help_result.get("workflow_id") == first["workflow_id"]
    assert help_result.get("say_to_user")
