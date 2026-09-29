"""Baseline evidence capture — quick mode for CI."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from orchestrator.paths import OPS_DIR, REPO_ROOT


def _load_capture_baseline_module():
    mod_path = OPS_DIR / "capture_baseline.py"
    spec = importlib.util.spec_from_file_location("capture_baseline_mod", mod_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capture_baseline_quick_writes_sanitized_artifact(tmp_path, monkeypatch):
    cb = _load_capture_baseline_module()
    launch = tmp_path / ".launch"
    monkeypatch.setattr(cb, "_LAUNCH", launch)
    monkeypatch.setattr(cb, "_BASELINE", launch / "baseline_evidence.json")

    def _fast_run(cmd, *, cwd=None):
        if "pytest" in cmd:
            return {"ok": True, "exit_code": 0, "detail": "1 passed"}
        return {"ok": True, "exit_code": 0, "detail": "ok"}

    monkeypatch.setattr(cb, "_run", _fast_run)

    payload = cb.capture_baseline(quick=True)
    assert payload.get("baseline_path")
    path = Path(payload["baseline_path"])
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "readiness" in data
    assert "checks" in data
    blob = path.read_text(encoding="utf-8").lower()
    assert "jira_api_token" not in blob
    assert "slack_bot_token" not in blob
