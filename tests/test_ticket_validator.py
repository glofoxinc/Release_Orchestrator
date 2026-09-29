"""Tests for ticket_validator.validate_coverage()."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from ticket_validator import ValidationWarning, apply_auto_fix, validate_coverage


def _extracted(ticket, report, description="fix", client="Standard"):
    return {
        "ticket": ticket,
        "type": "Analyze",
        "client": client,
        "report": report,
        "description": description,
    }


class TestValidateCoverage:
    def test_all_dashboards_covered_no_warnings(self):
        draft = {
            "extracted": [_extracted("AN-1", "New Members")],
            "description": "New Members changed.",
            "test_plan": "Validate New Members.",
            "business_impact": "New Members updated.",
            "implementation_plan": "Deploy New Members.",
            "backout_plan": "Rollback New Members.",
        }
        warnings = validate_coverage(draft)
        assert warnings == []

    def test_missing_dashboard_in_test_plan(self):
        draft = {
            "extracted": [
                _extracted("AN-1", "New Members"),
                _extracted("AN-2", "Daily Snapshot"),
            ],
            "description": "New Members, Daily Snapshot",
            "test_plan": "Validate New Members.",
            "business_impact": "New Members and Daily Snapshot updated.",
            "implementation_plan": "Deploy New Members, Daily Snapshot.",
            "backout_plan": "Rollback.",
        }
        warnings = validate_coverage(draft)
        codes = {w.code for w in warnings}
        assert "test_plan_missing_dashboards" in codes
        w = next(w for w in warnings if w.code == "test_plan_missing_dashboards")
        assert "Daily Snapshot" in w.missing

    def test_missing_dashboard_in_business_impact(self):
        draft = {
            "extracted": [_extracted("AN-1", "Revenue Analysis")],
            "description": "Revenue Analysis changed",
            "test_plan": "Validate Revenue Analysis.",
            "business_impact": "Some unrelated text.",
            "implementation_plan": "Deploy.",
            "backout_plan": "Rollback.",
        }
        warnings = validate_coverage(draft)
        assert any(w.code == "business_impact_missing_dashboards" for w in warnings)

    def test_unknown_ticket_reference_flagged(self):
        draft = {
            "extracted": [_extracted("AN-1", "New Members")],
            "description": "See AN-1 and AN-999",
            "test_plan": "Validate New Members.",
            "business_impact": "New Members updated.",
            "implementation_plan": "Deploy.",
            "backout_plan": "Rollback.",
        }
        warnings = validate_coverage(draft)
        w = next(w for w in warnings if w.code == "unknown_ticket_references")
        assert "AN-999" in w.missing
        assert "AN-1" not in w.missing

    def test_empty_sections_flagged(self):
        draft = {
            "extracted": [_extracted("AN-1", "New Members")],
            "description": "New Members",
        }
        warnings = validate_coverage(draft)
        codes = {w.code for w in warnings}
        assert "test_plan_empty" in codes
        assert "business_impact_empty" in codes
        assert "implementation_plan_empty" in codes
        assert "backout_plan_empty" in codes

    def test_no_extracted_skips_ref_check(self):
        draft = {
            "description": "AN-1 AN-999",
            "test_plan": "x",
            "business_impact": "y",
            "implementation_plan": "z",
            "backout_plan": "w",
        }
        warnings = validate_coverage(draft)
        assert not any(w.code == "unknown_ticket_references" for w in warnings)

    def test_adf_description_parsed(self):
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "New Members changed"}]}
            ],
        }
        draft = {
            "extracted": [_extracted("AN-1", "New Members")],
            "description": adf,
            "test_plan": "Validate New Members.",
            "business_impact": "New Members updated.",
            "implementation_plan": "Deploy.",
            "backout_plan": "Rollback.",
        }
        warnings = validate_coverage(draft)
        assert not any("missing_dashboards" in w.code for w in warnings)


class TestAutoFix:
    def test_append_test_plan_items(self):
        draft = {
            "extracted": [_extracted("AN-1", "A"), _extracted("AN-2", "B")],
            "description": "A, B",
            "test_plan": "Validate A.",
            "business_impact": "A and B updated.",
            "implementation_plan": "Deploy A and B.",
            "backout_plan": "Rollback.",
        }
        warnings = validate_coverage(draft)
        w = next(w for w in warnings if w.code == "test_plan_missing_dashboards")
        fixed = apply_auto_fix(draft, w)
        assert "B" in fixed["test_plan"]

    def test_auto_fix_no_op_when_action_missing(self):
        w = ValidationWarning(code="x", severity="warning", message="x", auto_fix=None)
        assert apply_auto_fix({"test_plan": "y"}, w) == {"test_plan": "y"}

    def test_append_business_impact(self):
        draft = {
            "extracted": [_extracted("AN-1", "A")],
            "description": "A changed",
            "test_plan": "Validate A.",
            "business_impact": "Nothing.",
            "implementation_plan": "Deploy A.",
            "backout_plan": "Rollback.",
        }
        warnings = validate_coverage(draft)
        w = next(w for w in warnings if w.code == "business_impact_missing_dashboards")
        fixed = apply_auto_fix(draft, w)
        assert "A" in fixed["business_impact"]


class TestValidationWarning:
    def test_to_dict(self):
        w = ValidationWarning(
            code="x", severity="warning", message="m",
            missing=["A"], section="test_plan",
            auto_fix={"action": "append_test_plan_items", "items": ["x"]},
        )
        d = w.to_dict()
        assert d["code"] == "x"
        assert d["missing"] == ["A"]
        assert d["auto_fix"]["action"] == "append_test_plan_items"
