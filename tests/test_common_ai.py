"""Tests for the shared AI helpers (offline fallback and injected LLM)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.ai import (
    ProgressState,
    RiskAssessment,
    classify_progress_state,
    rate_risk,
    suggest_acceptance_criteria,
    summarize_release,
)


class TestClassifyProgressState:
    def test_delivered_for_done_status(self):
        p = classify_progress_state(status="Done")
        assert p.state == "delivered"
        assert p.confidence > 0.9

    def test_blocked_for_explicit_blocker(self):
        p = classify_progress_state(status="In Progress", blocker="API returning 500")
        assert p.state == "blocked"

    def test_blocked_for_blocked_status(self):
        p = classify_progress_state(status="Blocked")
        assert p.state == "blocked"

    def test_at_risk_for_stale_ticket(self):
        p = classify_progress_state(status="In Progress", days_since_update=14)
        assert p.state == "at_risk"

    def test_at_risk_for_risk_keyword(self):
        p = classify_progress_state(status="In Progress", description="This has slipped the deadline")
        assert p.state == "at_risk"

    def test_in_progress_default(self):
        p = classify_progress_state(status="In Progress")
        assert p.state == "in_progress"

    def test_empty_blocker_is_not_blocker(self):
        p = classify_progress_state(status="In Progress", blocker="no blockers")
        assert p.state == "in_progress"

    def test_dict_roundtrip(self):
        p = ProgressState("at_risk", 0.7, "why")
        d = p.to_dict()
        assert d["state"] == "at_risk" and 0 <= d["confidence"] <= 1

    def test_na_blocker_treated_as_none(self):
        assert classify_progress_state(status="In Progress", blocker="N/A").state == "in_progress"


class TestRateRisk:
    def test_low_risk_small_release(self):
        r = rate_risk(ticket_count=2, client_count=1, dashboard_count=1)
        assert r.level == "low"

    def test_medium_risk_medium_release(self):
        r = rate_risk(ticket_count=15, client_count=3, dashboard_count=5, text_blob="refactor semantic model")
        assert r.level in {"medium", "high"}

    def test_high_risk_large_release(self):
        r = rate_risk(
            ticket_count=30,
            client_count=6,
            dashboard_count=10,
            text_blob="revenue payment semantic model migrate",
        )
        assert r.level == "high"
        assert "revenue" in r.signals
        assert "payment" in r.signals

    def test_signal_deduplication(self):
        r = rate_risk(ticket_count=30, client_count=6, dashboard_count=10)
        assert r.score > 0

    def test_dict_has_level_and_signals(self):
        d = RiskAssessment(level="low", score=1, signals=["a"]).to_dict()
        assert d["level"] == "low" and d["signals"] == ["a"]


class TestSummarizeRelease:
    def test_empty_list(self):
        s = summarize_release([])
        assert "No tickets" in s or "no tickets" in s.lower()

    def test_offline_text_mentions_ticket_count(self):
        tickets = [
            {"ticket": "AN-1", "description": "Add filter", "client": "Standard", "report": "New Members"},
            {"ticket": "PIC-2", "description": "Fix currency", "client": "Jetts", "report": "Revenue"},
        ]
        s = summarize_release(tickets)
        assert "2" in s
        assert "release" in s.lower()

    def test_offline_mentions_clients(self):
        tickets = [
            {"ticket": "PIC-1", "description": "fix", "client": "Jetts", "report": "R"},
            {"ticket": "PIC-2", "description": "update", "client": "Lift", "report": "R"},
        ]
        s = summarize_release(tickets)
        assert "Jetts" in s and "Lift" in s

    def test_llm_branch_uses_response(self):
        tickets = [{"ticket": "A-1", "description": "add filter", "client": "Standard"}]
        s = summarize_release(tickets, llm=lambda p: "Custom LLM sentence.")
        assert s == "Custom LLM sentence."

    def test_llm_exception_falls_back(self):
        def boom(p):
            raise RuntimeError("offline")

        s = summarize_release(
            [{"ticket": "A-1", "description": "add filter", "client": "Standard"}],
            llm=boom,
        )
        assert "release" in s.lower()


class TestAcceptanceCriteria:
    def test_empty_returns_empty(self):
        assert suggest_acceptance_criteria("") == []

    def test_single_sentence_generates_one_bullet(self):
        out = suggest_acceptance_criteria("Add join type filter to New Members")
        assert len(out) >= 1
        assert "Given" in out[0]

    def test_bullets_rephrased(self):
        out = suggest_acceptance_criteria("- One\n- Two\n- Three")
        assert len(out) == 3

    def test_llm_branch_used(self):
        out = suggest_acceptance_criteria("x", llm=lambda p: "AC 1\nAC 2\nAC 3")
        assert out == ["AC 1", "AC 2", "AC 3"]

    def test_llm_failure_falls_back(self):
        def bad(p):
            raise RuntimeError()

        out = suggest_acceptance_criteria("Fix the currency bug", llm=bad)
        assert out

    def test_deduplicates_bullets(self):
        out = suggest_acceptance_criteria("- Same\n- Same\n- Different")
        assert len(out) == 2
