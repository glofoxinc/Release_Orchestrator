"""Release Notes — ready-for-release Jira comment gate (mirrors review-call pattern)."""

from __future__ import annotations

from unittest.mock import patch

import release_gates as rg
from release_mcp import release_ops


def test_ticket_has_ready_for_release_comment(monkeypatch):
    def _comments(key: str):
        if key == "PIC-9":
            return [{"body": "QA done — ready for release"}]
        return []

    monkeypatch.setattr(rg.jira_client, "get_issue_comments", _comments)
    ok, snippet = rg.ticket_has_ready_for_release_comment("PIC-9")
    assert ok is True
    assert "ready for release" in snippet.lower()
    assert rg.ticket_has_ready_for_release_comment("PIC-10")[0] is False


def test_merge_release_ready_comment_candidates(monkeypatch):
    monkeypatch.setattr(rg, "include_ready_for_release_comments_enabled", lambda: True)
    monkeypatch.setattr(
        rg,
        "ready_for_release_comment_candidate_statuses",
        lambda project_keys=None: {"PIC": ["Passed QA", "In Progress"]},
    )

    def _comments(key: str):
        if key == "PIC-100":
            return [{"body": "Ready for release after QA sign-off"}]
        return []

    monkeypatch.setattr(rg.jira_client, "get_issue_comments", _comments)

    status_fetch = {
        "status": "ok",
        "extracted": [
            {"ticket": "PIC-1", "status": "Ready for Release", "summary": "status match"},
        ],
    }
    candidate_fetch = {
        "status": "ok",
        "extracted": [
            {"ticket": "PIC-100", "status": "Passed QA", "summary": "comment match"},
            {"ticket": "PIC-101", "status": "In Progress", "summary": "no comment"},
        ],
    }

    with patch.object(release_ops, "fetch_release_tickets", return_value=candidate_fetch):
        result = release_ops._merge_release_ready_comment_candidates(
            list(status_fetch["extracted"]),
            projects=["PIC"],
            release_notes_statuses_by_project={"PIC": ["Ready for Release"]},
        )

    keys = {row["ticket"] for row in result["extracted"]}
    assert keys == {"PIC-1", "PIC-100"}
    assert result["comment_included_keys"] == ["PIC-100"]


def test_fetch_release_notes_extracted_applies_comment_gate(monkeypatch):
    monkeypatch.setattr(rg, "include_ready_for_release_comments_enabled", lambda: True)
    monkeypatch.setattr(
        rg,
        "ready_for_release_comment_candidate_statuses",
        lambda project_keys=None: {"PIC": ["Passed QA"]},
    )
    monkeypatch.setattr(rg.jira_client, "get_issue_comments", lambda key: [])

    release_fetch = {
        "status": "ok",
        "extracted": [{"ticket": "PIC-1", "status": "Ready for Release", "summary": "a"}],
    }
    candidate_fetch = {
        "status": "ok",
        "extracted": [{"ticket": "PIC-2", "status": "Passed QA", "summary": "b"}],
    }

    def _fetch(*args, **kwargs):
        if kwargs.get("statuses_by_project") == {"PIC": ["Ready for Release"]}:
            return release_fetch
        return candidate_fetch

    with patch.object(release_ops, "fetch_release_tickets", side_effect=_fetch):
        with patch.object(
            rg,
            "ticket_has_ready_for_release_comment",
            lambda key: (key == "PIC-2", "ready for release"),
        ):
            result = release_ops.fetch_release_notes_extracted(
                selection_mode="status",
                projects=["PIC"],
                release_notes_statuses_by_project={"PIC": ["Ready for Release"]},
            )

    assert result["status"] == "ok"
    assert sorted(result["release_ready_ticket_keys"]) == ["PIC-1", "PIC-2"]
    assert result["comment_included_keys"] == ["PIC-2"]
