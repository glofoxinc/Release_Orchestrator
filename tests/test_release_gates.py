"""Tests for pre-review and post-QA release gates."""

from __future__ import annotations

from unittest.mock import patch

import release_gates


def _issue(key: str, status: str, summary: str = "Test") -> dict:
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": status},
            "assignee": {
                "displayName": "Alice",
                "emailAddress": "alice@example.com",
            },
            "project": {"key": key.split("-")[0]},
        },
    }


class TestPreReviewGate:
    def test_holds_back_non_review_status(self):
        issues = [
            _issue("PIC-1", "In Review"),
            _issue("PIC-2", "To Do"),
        ]
        result = release_gates.classify_pre_review(issues)
        assert [i["key"] for i in result.ready] == ["PIC-1"]
        assert result.blocked[0].key == "PIC-2"

    def test_run_pre_review_dry_run_slack_preview(self):
        issues = [_issue("PIC-2", "To Do")]
        with patch.object(release_gates, "gate_enabled", return_value=True):
            with patch("release_gates.slack_notify_enabled", return_value=True):
                with patch("slack_assignee_notify.notify_gate_tickets") as notify:
                    notify.return_value = {"status": "dry_run", "recipient_count": 1}
                    payload = release_gates.run_pre_review_gate(
                        issues, version_name="2026.1.01.01", notify=True, dry_run=True,
                    )
        assert payload["blocked_count"] == 1
        notify.assert_called_once()


class TestPostQaGate:
    def test_blocks_non_qa_status(self):
        issues = [
            _issue("PIC-1", "Done"),
            _issue("PIC-2", "In Progress"),
        ]
        result = release_gates.classify_post_qa(issues)
        assert [i["key"] for i in result.ready] == ["PIC-1"]
        assert result.blocked[0].key == "PIC-2"

    def test_excluded_text_format(self):
        blocked = release_gates.classify_post_qa([_issue("PIC-9", "Open")]).blocked
        text = release_gates.format_excluded_table_text(blocked)
        assert "PIC-9" in text
        assert "|" in text

    def test_merge_excluded_text_dedupes(self):
        existing = "1|PIC-1|x|Done|Alice|reason||"
        blocked = release_gates.classify_post_qa([_issue("PIC-1", "Open")]).blocked
        merged = release_gates.merge_excluded_text(existing, blocked)
        assert merged.count("PIC-1") == 1


class TestMcpGateOps:
    def test_pre_review_gate_mcp(self):
        from release_mcp import gate_ops

        issues = [_issue("PIC-1", "To Do")]
        with patch.object(release_gates, "gate_enabled", return_value=True):
            with patch.object(gate_ops, "_resolve_issues_for_version", return_value=(issues, [])):
                out = gate_ops.pre_review_gate("2026.1.01.01", notify=False)
        assert out["blocked_count"] == 1


class TestUiFeatureFlags:
    def test_ticket_review_filter_off_when_gate_disabled(self):
        with patch.object(
            release_gates,
            "_section",
            return_value={"enabled": False, "filter_ticket_review": True},
        ):
            assert release_gates.gate_enabled("pre_review") is False
            assert release_gates.ticket_review_pre_review_enabled() is False

    def test_ticket_review_filter_on_when_flag_set(self):
        with patch.object(
            release_gates,
            "_section",
            return_value={"enabled": True, "filter_ticket_review": True},
        ):
            assert release_gates.ticket_review_pre_review_enabled() is True

    def test_release_notes_qa_filter_off_by_default(self):
        with patch.object(
            release_gates,
            "_section",
            return_value={"enabled": True, "filter_release_notes": False},
        ):
            assert release_gates.post_qa_release_notes_enabled() is False
