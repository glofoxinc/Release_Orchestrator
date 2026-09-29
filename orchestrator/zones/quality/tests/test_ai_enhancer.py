"""Tests for ai_enhancer — project-level AI wrapper."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ai_enhancer

EXTRACTED = [
    {
        "ticket": "AN-1",
        "type": "Analyze",
        "client": "Standard",
        "report": "New Members",
        "description": "add join type filter",
    },
    {
        "ticket": "AN-2",
        "type": "Analyze",
        "client": "Standard",
        "report": "Revenue Analysis",
        "description": "fix currency display",
    },
    {"ticket": "PIC-3", "type": "Custom", "client": "Jetts", "report": "Payouts", "description": "update measures"},
    {"ticket": "PIC-4", "type": "Custom", "client": "Lift", "report": "Attrition", "description": "new filter"},
]


class TestSummarizeTicketSet:
    def test_empty_returns_no_tickets_message(self):
        s = ai_enhancer.summarize_ticket_set([])
        assert "no tickets" in s.lower()

    def test_offline_has_length(self):
        s = ai_enhancer.summarize_ticket_set(EXTRACTED)
        assert isinstance(s, str) and len(s) > 40

    def test_llm_override_used(self):
        s = ai_enhancer.summarize_ticket_set(EXTRACTED, llm=lambda p: "LLM said so.")
        assert s == "LLM said so."


class TestRateReleaseRisk:
    def test_risk_level_for_small_release(self):
        risk = ai_enhancer.rate_release_risk(EXTRACTED[:1])
        assert risk.level == "low"

    def test_risk_scales_with_scope(self):
        wide = [
            {
                "ticket": f"AN-{i}",
                "type": "Analyze",
                "client": f"C{i}",
                "report": f"R{i}",
                "description": "refactor semantic model migrate revenue",
            }
            for i in range(30)
        ]
        risk = ai_enhancer.rate_release_risk(wide)
        assert risk.level == "high"

    def test_risk_extra_text_factored_in(self):
        risk = ai_enhancer.rate_release_risk(EXTRACTED, extra_text="security payment revenue")
        assert risk.score > 0


class TestAcceptanceCriteria:
    def test_uses_description(self):
        out = ai_enhancer.generate_acceptance_criteria_for_ticket(EXTRACTED[0])
        assert any("join type" in c.lower() for c in out)

    def test_llm_path(self):
        out = ai_enhancer.generate_acceptance_criteria_for_ticket(
            EXTRACTED[0], llm=lambda p: "AC line 1\nAC line 2"
        )
        assert out == ["AC line 1", "AC line 2"]

    def test_empty_ticket_returns_empty(self):
        out = ai_enhancer.generate_acceptance_criteria_for_ticket({})
        assert out == []


class TestEnhanceDraft:
    def test_populates_ai_fields(self):
        draft = {"summary": "Release", "extracted": EXTRACTED}
        out = ai_enhancer.enhance_draft(draft)
        assert "ai_summary" in out and out["ai_summary"]
        assert "ai_risk" in out and out["ai_risk"]["level"] in {"low", "medium", "high"}
        assert "ai_acceptance_criteria" in out

    def test_does_not_overwrite_existing_values(self):
        draft = {
            "summary": "x",
            "extracted": EXTRACTED,
            "ai_summary": "kept",
            "ai_acceptance_criteria": ["kept"],
        }
        out = ai_enhancer.enhance_draft(draft)
        assert out["ai_summary"] == "kept"
        assert out["ai_acceptance_criteria"] == ["kept"]

    def test_uses_llm_for_fresh_draft(self):
        draft = {"summary": "x", "extracted": EXTRACTED}
        out = ai_enhancer.enhance_draft(draft, llm=lambda p: "Mock LLM summary.")
        assert out["ai_summary"] == "Mock LLM summary."

    def test_does_not_mutate_input(self):
        draft = {"summary": "x", "extracted": EXTRACTED}
        ai_enhancer.enhance_draft(draft)
        assert "ai_summary" not in draft
