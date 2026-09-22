"""Tests for the linked-ticket pre-flight verifier."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from linked_ticket_verifier import (
    DEFAULT_EXPECTED_STATES,
    VerificationReport,
    apply_release_label,
    human_summary,
    verify_tickets,
)


def _issue(
    *,
    state: str = "Done",
    summary: str = "A summary",
    ac_field: str = "Acceptance Criteria",
    ac_value: object = "Given X, When Y, Then Z",
) -> dict:
    return {
        "fields": {
            "status": {"name": state},
            "summary": summary,
            ac_field: ac_value,
        }
    }


class TestVerifyTickets:
    def test_all_pass(self):
        def fetch(key):
            return _issue()

        report = verify_tickets(["AN-1", "AN-2"], fetch=fetch)
        assert report.all_ok
        assert report.passed == 2
        assert report.total == 2

    def test_unexpected_state_fails(self):
        def fetch(key):
            return _issue(state="In Progress")

        report = verify_tickets(["AN-1"], fetch=fetch)
        assert not report.all_ok
        assert "state" in report.findings[0].issues[0]

    def test_ready_for_release_allowed(self):
        def fetch(key):
            return _issue(state="Ready for Release")

        report = verify_tickets(["AN-1"], fetch=fetch)
        assert report.all_ok

    def test_missing_summary_flagged(self):
        def fetch(key):
            return _issue(summary="")

        report = verify_tickets(["AN-1"], fetch=fetch)
        assert not report.findings[0].ok
        assert any("summary" in i for i in report.findings[0].issues)

    def test_missing_acceptance_criteria_flagged(self):
        def fetch(key):
            return _issue(ac_field="Other Field", ac_value="")

        report = verify_tickets(["AN-1"], fetch=fetch)
        assert not report.findings[0].ok
        assert any("acceptance" in i for i in report.findings[0].issues)

    def test_can_skip_ac_check(self):
        def fetch(key):
            return _issue(ac_field="x", ac_value="")

        report = verify_tickets(["AN-1"], fetch=fetch, require_acceptance_criteria=False)
        assert report.all_ok

    def test_not_found_flagged(self):
        def fetch(key):
            return None

        report = verify_tickets(["AN-999"], fetch=fetch)
        assert not report.findings[0].ok
        assert any("not found" in i for i in report.findings[0].issues)

    def test_fetch_exception_captured(self):
        def fetch(key):
            raise RuntimeError("timeout")

        report = verify_tickets(["AN-1"], fetch=fetch)
        assert not report.findings[0].ok
        assert "timeout" in report.findings[0].issues[0]

    def test_dedupes_repeated_keys(self):
        calls = {"n": 0}

        def fetch(key):
            calls["n"] += 1
            return _issue()

        report = verify_tickets(["AN-1", "AN-1", "AN-1"], fetch=fetch)
        assert report.total == 1
        assert calls["n"] == 1

    def test_custom_expected_states(self):
        def fetch(key):
            return _issue(state="Merged")

        report = verify_tickets(
            ["AN-1"], fetch=fetch, expected_states=("merged",)
        )
        assert report.all_ok

    def test_adf_acceptance_criteria(self):
        adf_ac = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Given X"}]},
        ]}

        def fetch(key):
            return _issue(ac_value=adf_ac)

        report = verify_tickets(["AN-1"], fetch=fetch)
        assert report.all_ok


class TestApplyReleaseLabel:
    def test_labels_only_passing_by_default(self):
        labels: list[tuple[str, str]] = []

        def labeler(key, label):
            labels.append((key, label))

        def fetch(key):
            return _issue() if key == "AN-1" else _issue(summary="")

        report = verify_tickets(["AN-1", "AN-2"], fetch=fetch)
        labelled = apply_release_label(report, label="release-v1", label_update=labeler)
        assert labelled == ["AN-1"]
        assert labels == [("AN-1", "release-v1")]

    def test_labels_all_when_only_passing_false(self):
        labels = []

        def labeler(k, label):
            labels.append(k)

        def fetch(key):
            return _issue(summary="") if key != "AN-1" else _issue()

        report = verify_tickets(["AN-1", "AN-2"], fetch=fetch)
        apply_release_label(report, label="x", label_update=labeler, only_passing=False)
        assert labels == ["AN-1", "AN-2"]

    def test_empty_label_rejected(self):
        with pytest.raises(ValueError):
            apply_release_label(
                VerificationReport(), label="", label_update=lambda k, label: None
            )

    def test_labeler_exception_swallowed(self):
        calls = []

        def labeler(k, label):
            calls.append(k)
            if k == "AN-1":
                raise RuntimeError("api down")

        def fetch(key):
            return _issue()

        report = verify_tickets(["AN-1", "AN-2"], fetch=fetch)
        labelled = apply_release_label(report, label="x", label_update=labeler)
        assert labelled == ["AN-2"]


class TestReportProperties:
    def test_empty_report_summary(self):
        assert "No tickets" in human_summary(VerificationReport())

    def test_all_pass_summary(self):
        def fetch(key):
            return _issue()

        report = verify_tickets(["A-1"], fetch=fetch)
        assert "pass" in human_summary(report).lower()

    def test_partial_fail_summary(self):
        def fetch(key):
            return None

        report = verify_tickets(["A-1", "A-2"], fetch=fetch)
        assert "/2" in human_summary(report) or "2" in human_summary(report)

    def test_default_expected_states_contains_done(self):
        assert "done" in DEFAULT_EXPECTED_STATES

    def test_to_dict_roundtrip(self):
        def fetch(key):
            return _issue()

        report = verify_tickets(["A-1"], fetch=fetch)
        d = report.to_dict()
        assert d["total"] == 1 and d["passed"] == 1
