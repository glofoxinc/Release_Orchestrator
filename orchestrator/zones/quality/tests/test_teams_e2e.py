"""Teams E2E readiness and attendee resolution tests."""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestTeamsReadiness:
    def test_readiness_steps_all_ok_when_configured(self):
        from ms_graph import GraphClient, GraphCredentials
        import teams_schedule as ts

        client = GraphClient(credentials=GraphCredentials("t", "c", "s"))
        cfg = ts.load_schedule_config(
            {
                "enabled": True,
                "organizer_upn": "owner@abcfitness.com",
                "default_attendees": [{"email": "a@abcfitness.com", "name": "A"}],
            },
            graph=client,
        )
        steps = ts.readiness_steps(cfg)
        assert all(s["ok"] for s in steps)
        assert cfg.can_schedule()

    def test_attendees_for_kind_uses_overrides(self):
        import teams_schedule as ts

        cfg = ts.load_schedule_config({
            "default_attendees": [{"email": "default@abcfitness.com"}],
            "review_attendees": [{"email": "review@abcfitness.com"}],
            "deployment_attendees": [{"email": "deploy@abcfitness.com"}],
        })
        assert cfg.attendees_for_kind("review")[0].email == "review@abcfitness.com"
        assert cfg.attendees_for_kind("deployment")[0].email == "deploy@abcfitness.com"

    def test_status_includes_readiness_steps(self):
        import teams_schedule as ts

        st = ts.status(ts.load_schedule_config({"enabled": False}))
        assert "readiness_steps" in st
        assert st["pending_step_count"] >= 1


class TestTeamsE2ECli:
    def test_dry_run_script(self):
        from orchestrator.paths import OPS_DIR, REPO_ROOT

        proc = subprocess.run(
            [sys.executable, str(OPS_DIR / "test_teams_schedule.py"), "--dry-run"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0
        assert "Teams schedule E2E" in proc.stdout
        assert "isOnlineMeeting" in proc.stdout
