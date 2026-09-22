"""Tests for per-step MCP catalog."""

from __future__ import annotations

from release_mcp.steps.catalog import RELEASE_STEPS, step_catalog_payload
from release_mcp.steps.step_tools import release_step_status


def test_catalog_has_eight_release_steps():
    ids = {s["id"] for s in RELEASE_STEPS}
    assert "ticket_review" in ids
    assert "slack" in ids
    assert "onboarding" in ids


def test_step_catalog_payload_say_first():
    payload = step_catalog_payload()
    assert payload["steps"]
    assert payload["entry_phrases"]
    first = payload["steps"][0]
    assert first.get("say_first")


def test_release_step_status_slack():
    out = release_step_status("slack")
    assert out["ok"] is True
    assert out["step"]["id"] == "slack"
    assert out.get("say_first")


def test_release_step_status_full_catalog():
    out = release_step_status("")
    assert out.get("catalog")
    assert "onboarding" in out
