"""Release Notes E2E pipeline tests."""

from __future__ import annotations

import os
import subprocess
import sys

from orchestrator.paths import OPS_DIR, REPO_ROOT

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestReleaseNotesE2E:
    def test_fixture_publish_ok(self):
        from generators.release_notes_e2e import run_fixture_e2e

        result = run_fixture_e2e()
        assert result["ok"] is True
        assert result["publish"]["status"] == "ok"
        assert result["docx_bytes_len"] > 1000
        assert result["readiness"]["ready"] is True
        assert result["readiness"]["score"] >= 80

    def test_e2e_status(self):
        from generators.release_notes_e2e import e2e_status

        st = e2e_status()
        assert st["feature"] == "release_notes"
        assert st["ok"] is True
        assert len(st["pipeline_steps"]) >= 5

    def test_sample_data_matches_readiness(self):
        from generators.release_notes_insights import assess_release_notes_readiness
        from generators.release_notes_sample import sample_release_notes_data

        report = assess_release_notes_readiness(sample_release_notes_data())
        assert report.ready
        assert not report.blockers

    def test_cli_script(self):
        proc = subprocess.run(
            [sys.executable, str(OPS_DIR / "test_release_notes_e2e.py")],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0
        assert "Release Notes E2E" in proc.stdout
