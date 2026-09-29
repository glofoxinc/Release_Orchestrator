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
    assert kept_keys == {"PIC-1"}
    assert set(result["held_back_keys"]) == {"PIC-2", "PIC-3"}


def test_review_status_requires_ready_for_review_comment(monkeypatch):
    monkeypatch.setattr(rg.jira_client, "get_issue_comments", lambda _key: [])
    extracted = [{"ticket": "PIC-9", "status": "Review", "summary": "no comment"}]
    result = rg.filter_extracted_in_progress_review_candidates(extracted)
    assert result["kept"] == []
    assert result["held_back_keys"] == ["PIC-9"]


def test_ready_for_release_requires_comment_all_statuses(monkeypatch):
    monkeypatch.setattr(rg.jira_client, "get_issue_comments", lambda key: [{"body": "ready for release"}] if key == "PIC-1" else [])
    extracted = [
        {"ticket": "PIC-1", "status": "Ready for Release", "summary": "has comment"},
        {"ticket": "PIC-2", "status": "Ready for Release", "summary": "status only"},
    ]
    result = rg.filter_extracted_ready_for_release_comments(extracted)
    assert [row["ticket"] for row in result["kept"]] == ["PIC-1"]
    assert result["held_back_keys"] == ["PIC-2"]


def test_an_default_statuses_match_pic_review():
    import config

    assert "Review" in config.ticket_review_default_checked_statuses("AN")
    assert "In Progress" in config.ticket_review_default_checked_statuses("AN")
    assert "Passed QA" not in config.ticket_review_default_checked_statuses("AN")
