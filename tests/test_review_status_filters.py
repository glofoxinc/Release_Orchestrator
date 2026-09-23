"""Ticket review status + comment filters (In Progress / review-done)."""

from __future__ import annotations

import release_gates as rg


def test_in_progress_requires_ready_for_review_comment(monkeypatch):
    def _comments(key: str):
        if key == "PIC-1":
            return [{"body": "Ready for review — please check"}]
        return []

    monkeypatch.setattr(rg.jira_client, "get_issue_comments", _comments)
    extracted = [
        {"ticket": "PIC-1", "status": "In Progress", "summary": "ok"},
        {"ticket": "PIC-2", "status": "In Progress", "summary": "no comment"},
        {"ticket": "PIC-3", "status": "Review", "summary": "plain review"},
    ]
    result = rg.filter_extracted_in_progress_review_candidates(extracted)
    kept_keys = {row["ticket"] for row in result["kept"]}
    assert kept_keys == {"PIC-1", "PIC-3"}
    assert result["held_back_keys"] == ["PIC-2"]


def test_an_default_statuses_match_pic_review():
    import config

    assert "Review" in config.ticket_review_default_checked_statuses("AN")
    assert "In Progress" in config.ticket_review_default_checked_statuses("AN")
    assert "Passed QA" not in config.ticket_review_default_checked_statuses("AN")
