"""Tests for MCP production readiness assessment."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


def test_assess_mcp_production_structure():
    from release_mcp import mcp_readiness

    report = mcp_readiness.assess_mcp_production()
    assert "verified" in report
    assert "unverified" in report
    assert "operator_required" in report
    assert "say_to_user" in report
    assert report["automated_score_pct"] >= 0
    names = {v["name"] for v in report["verified"]}
    assert "schedule_ist_to_cst" in names


def test_schedule_model_check_passes():
    import production_readiness as pr

    ok, detail = pr._schedule_model_ok()
    assert ok is True
    assert "IST" in detail


def test_guided_interprets_production_ready():
    from release_mcp import guided

    plan = guided.interpret_message("production ready")
    assert plan["action"] == "readiness"


def test_guided_emergency_profile_on_active_workflow():
    from release_mcp import guided

    plan = guided.interpret_message(
        "emergency deployment",
        workflow_id="wf-123",
    )
    assert plan["action"] == "update"
    assert plan["inputs"]["deployment_profile"] == "emergency"


def test_wizard_schedule_uses_deployment_profile(monkeypatch):
    from datetime import date

    from release_mcp import wizard

    session = {
        "inputs": {
            "deployment_profile": "normal",
            "version_name": "2026.3.09.11",
            "planned_start_date": "2026-09-11",
            "planned_end_date": "2026-09-11",
        },
        "artifacts": {},
    }
    sched = wizard._service_schedule(session)
    assert sched["source_timezone"] == "Asia/Kolkata"
    assert "IST" in sched["window"]["primary"]
    assert sched["planned_start_iso"].endswith(("-0500", "-0600")) or "-05" in sched["planned_start_iso"]
