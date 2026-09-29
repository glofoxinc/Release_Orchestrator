"""Daily Review — one meeting per review date."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from daily_review_agent import runner


def test_schedule_is_active_false_without_schedule_file(tmp_path, monkeypatch):
    import daily_review_agent.schedule_registry as schedule_registry

    state_file = tmp_path / "schedule.json"
    monkeypatch.setattr(schedule_registry, "_STATE", state_file)
    assert schedule_registry.schedule_is_active() is False


def test_dry_run_allowed_without_force_when_on_demand(monkeypatch):
    cfg = runner.load_agent_config()
    cfg.enabled = True
    fake_start = __import__("datetime").datetime(2026, 9, 26, 11, 30)
    fake_end = __import__("datetime").datetime(2026, 9, 26, 12, 0)
    monkeypatch.setattr(runner, "load_agent_config", lambda: cfg)
    monkeypatch.setattr(
        runner,
        "run_preflight",
        lambda *a, **k: {"ready": True, "blockers": [], "fix_commands": []},
    )
    monkeypatch.setattr(runner, "schedule_is_active", lambda **kw: False)
    monkeypatch.setattr(
        runner,
        "resolve_review_issues",
        lambda c: {"issues": [], "by_project": {}, "status": "ok", "total": 0, "errors": []},
    )
    monkeypatch.setattr(runner, "ticket_rows", lambda issues: [])
    monkeypatch.setattr(runner, "meeting_window", lambda c: (fake_start, fake_end))
    monkeypatch.setattr(
        runner,
        "schedule_review_meeting",
        lambda *a, **k: {"ok": True, "dry_run": True},
    )
    monkeypatch.setattr(runner, "run_slack_delivery", lambda *a, **k: {"ok": True, "skipped": True})
    monkeypatch.setattr(runner, "post_summary_via_mcp", lambda *a, **k: {"ok": True, "dry_run": True})

    result = runner.run_daily_agent(dry_run=True, force=False)
    assert result["status"] == "ok"


def test_live_run_blocked_without_force_when_on_demand(monkeypatch):
    cfg = runner.load_agent_config()
    cfg.enabled = True
    monkeypatch.setattr(runner, "load_agent_config", lambda: cfg)
    monkeypatch.setattr(
        runner,
        "run_preflight",
        lambda *a, **k: {"ready": True, "blockers": [], "fix_commands": []},
    )
    monkeypatch.setattr(runner, "schedule_is_active", lambda **kw: False)

    result = runner.run_daily_agent(dry_run=False, force=False)
    assert result["status"] == "on_demand_only"


def test_already_scheduled_for_date_detects_prior_success(tmp_path, monkeypatch):
    state_path = tmp_path / "last_run.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "meeting_date": "2026-09-26",
                "schedule_ok": True,
                "event_id": "evt-1",
                "join_url": "https://teams.microsoft.com/l/meetup-join/example",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "_STATE_PATH", state_path)
    prior = runner._already_scheduled_for_date("2026-09-26")
    assert prior is not None
    assert prior.get("event_id") == "evt-1"


def test_run_daily_agent_skips_duplicate_meeting(tmp_path, monkeypatch):
    state_path = tmp_path / "last_run.json"
    monkeypatch.setattr(runner, "_STATE_PATH", state_path)
    state_path.write_text(
        json.dumps(
            {
                "meeting_date": "2026-09-26",
                "schedule_ok": True,
                "event_id": "evt-1",
            }
        ),
        encoding="utf-8",
    )

    class _Cfg:
        enabled = True
        timezone = "UTC"
        meeting_subject = "Daily Review"
        jira_team_name = "Team"
        playwright_mcp_fallback_enabled = False
        teams_mcp_enabled = False
        teams_post_summary = False
        slack = None

    fake_start = __import__("datetime").datetime(2026, 9, 26, 11, 30)
    fake_end = __import__("datetime").datetime(2026, 9, 26, 12, 0)

    with (
        patch.object(runner, "load_agent_config", return_value=_Cfg()),
        patch.object(runner, "readiness_report", return_value={}),
        patch.object(runner, "run_preflight", return_value={"ready": True}),
        patch.object(runner, "schedule_is_active", return_value=True),
        patch.object(runner, "resolve_review_issues", return_value={"issues": [], "by_project": {}}),
        patch.object(runner, "ticket_rows", return_value=[]),
        patch.object(runner, "meeting_window", return_value=(fake_start, fake_end)),
    ):
        result = runner.run_daily_agent(dry_run=False, force=False)

    assert result["status"] == "already_scheduled"
