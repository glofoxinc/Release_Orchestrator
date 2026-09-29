"""Track-aware production readiness tiers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


def test_release_track_excludes_daily_review_unverified(monkeypatch):
    import production_readiness as pr

    monkeypatch.setattr(
        pr,
        "_assess_daily_review_readiness",
        lambda: {
            "verified": [],
            "unverified": [{"name": "daily_review_mcp", "detail": "missing teams"}],
            "operator_required": [],
        },
    )
    report = pr.assess_readiness_tiers(track="release", surface="mcp")
    names = {row["name"] for row in report.get("unverified") or []}
    assert "daily_review_mcp" not in names
    assert "release_capable" in report
    assert "integration_ready" in report


def test_both_track_includes_daily_review(monkeypatch):
    import production_readiness as pr

    monkeypatch.setattr(
        pr,
        "_assess_daily_review_readiness",
        lambda: {
            "verified": [],
            "unverified": [{"name": "daily_review_mcp", "detail": "missing teams"}],
            "operator_required": [],
        },
    )
    report = pr.assess_readiness_tiers(track="both", surface="mcp")
    names = {row["name"] for row in report.get("unverified") or []}
    assert "daily_review_mcp" in names


def test_slack_read_probe_does_not_block_send_ready():
    from slack_mcp_verify import merge_mcp_probe_results

    report = merge_mcp_probe_results(
        channel_checks=[
            {
                "name": "insights-customize-squad",
                "channel_id": "C08HB93PEVD",
                "accessible": False,
                "error": "channel_not_found",
            },
        ],
        delivery_mode="cursor_slack_mcp",
    )
    assert report["config_ready"] is True
    assert report["send_ready"] is True
    assert report["e2e_ready"] is True
    assert not any("cannot access" in b for b in report.get("blockers") or [])


def test_wizard_store_scoped_deploy_fingerprint():
    from release_mcp import wizard_store

    wizard_store.set_sessions_dir_override(None)
    session = wizard_store.create_session("wf-test", step="deploy", inputs={})
    sid = session["id"]
    fp_pic = wizard_store.write_fingerprint("deploy", {"project": "PIC"})
    fp_an = wizard_store.write_fingerprint("deploy", {"project": "AN"})
    wizard_store.record_write_fingerprint(sid, "deploy", fp_pic, scope="PIC", result={"project": "PIC"})
    loaded = wizard_store.load_session(sid)
    assert wizard_store.find_applied_write(loaded, "deploy", fp_pic, scope="PIC")
    assert wizard_store.find_applied_write(loaded, "deploy", fp_an, scope="AN") is None
    wizard_store.delete_session(sid)
