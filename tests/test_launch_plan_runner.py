"""Launch plan runner smoke tests."""

from __future__ import annotations

from release_mcp import launch_plan_runner as lpr


def test_phase0_preflight_runs():
    result = lpr.phase0_preflight(quick_tests=True)
    assert result["phase"] == "phase0_preflight"
    assert "pytest" in result
    assert "slack_e2e_ready" in result


def test_phase2_onboarding_validation():
    result = lpr.phase2_onboarding_validation()
    assert result["phase"] == "phase2_onboarding_validation"
    assert result["both_track_items"] > 0
    assert not result["missing_required_steps"]


def test_run_all_phases_writes_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(lpr, "_LAUNCH_DIR", tmp_path)
    monkeypatch.setattr(lpr, "_EVIDENCE_FILE", tmp_path / "launch_evidence.json")
    summary = lpr.run_all_phases(quick_tests=True)
    assert summary.get("phases")
    assert (tmp_path / "launch_evidence.json").is_file()
