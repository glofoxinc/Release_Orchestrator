"""Review-complete comment gate — exclude tickets already reviewed in Jira comments."""

from __future__ import annotations

from unittest.mock import patch

import release_gates


def test_ticket_has_review_completed_comment_matches_phrase():
    comments = [{"body": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "review completed!"}]}]}}]
    with patch("release_gates.jira_client.get_issue_comments", return_value=comments):
        done, snippet = release_gates.ticket_has_review_completed_comment("PIC-5983")
    assert done is True
    assert "review completed" in snippet


def test_filter_extracted_holds_back_reviewed_ticket():
    extracted = [
        {"ticket": "PIC-1", "summary": "A", "status": "Review"},
        {"ticket": "PIC-2", "summary": "B", "status": "Review"},
    ]

    def _comments(key: str):
        if key == "PIC-1":
            return [{"body": "review completed"}]
        return []

    with patch("release_gates.skip_review_completed_comments_enabled", return_value=True), patch(
        "release_gates.jira_client.get_issue_comments", side_effect=_comments
    ):
        result = release_gates.filter_extracted_review_completed_comments(extracted)

    assert [t["ticket"] for t in result["kept"]] == ["PIC-2"]
    assert result["held_back_keys"] == ["PIC-1"]
