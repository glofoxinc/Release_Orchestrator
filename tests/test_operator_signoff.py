"""Tests for operator sign-off persistence."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


def test_record_and_launch_complete(tmp_path, monkeypatch):
    import operator_signoff as osign

    path = str(tmp_path / "signoff.json")
    monkeypatch.setattr(osign, "signoff_path", lambda _app_dir=None: path)

    assert not osign.signoff_status(path)["launch_complete"]
    osign.record_signoff(osign.SIGNOFF_SHIPIT_DRY_RUN, detail="v2026.3.09.11", path=path)
    assert not osign.signoff_status(path)["launch_complete"]
    osign.record_signoff(osign.SIGNOFF_SLACK_LIVE, detail="posted", path=path)
    assert osign.signoff_status(path)["launch_complete"]

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    assert "shipit_dry_run" in data["signoffs"]


def test_production_readiness_launch_complete(monkeypatch):
    import production_readiness as pr

    monkeypatch.setattr(
        pr.onboarding,
        "assess_setup",
        lambda **kw: {"jira_ready": True, "fully_ready": True},
    )
    monkeypatch.setattr(
        pr.integration_readiness,
        "summarize_readiness",
        lambda **kw: {"blocking_pending": [], "items": []},
    )
    monkeypatch.setattr(pr, "slack_delivery_mode", lambda: "cursor_slack_mcp")
    monkeypatch.setattr(
        "release_mcp.slack_mcp_ops.slack_mcp_verify",
        lambda **kw: {"e2e_ready": True, "blockers": [], "delivery_mode": "cursor_slack_mcp"},
    )
    monkeypatch.setattr(
        pr.osign,
        "signoff_status",
        lambda path=None: {
            "shipit_dry_run": True,
            "slack_live_confirm": True,
            "launch_complete": True,
            "missing": [],
            "signoffs": {
                "shipit_dry_run": {"detail": "test"},
                "slack_live_confirm": {"detail": "test"},
            },
            "updated_at": "2026-09-11T00:00:00+00:00",
        },
    )

    report = pr.assess_production_readiness(surface="both")
    assert report["launch_complete"] is True
    assert not any(r["name"] == "live_shipit_dry_run" for r in report["operator_required"])


def test_guided_signoff_phrase():
    from release_mcp import guided

    plan = guided.interpret_message("shipit confirmed")
    assert plan["action"] == "signoff"
    assert plan["inputs"]["signoff_id"] == "shipit_dry_run"
