"""Cross-platform path helpers."""

from __future__ import annotations

from pathlib import Path

import orchestrator.paths as paths


def test_venv_python_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "is_windows", lambda: True)
    root = tmp_path / "repo"
    root.mkdir()
    expected = root / ".venv" / "Scripts" / "python.exe"
    assert paths.venv_python(repo_root=root) == expected


def test_venv_python_posix(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "is_windows", lambda: False)
    root = tmp_path / "repo"
    root.mkdir()
    expected = root / ".venv" / "bin" / "python"
    assert paths.venv_python(repo_root=root) == expected


def test_venv_pip_argv_uses_venv_python(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "is_windows", lambda: False)
    root = tmp_path / "repo"
    root.mkdir()
    py = paths.venv_python(repo_root=root)
    assert paths.venv_pip_argv(repo_root=root) == [str(py), "-m", "pip"]


def test_json_path_forward_slashes(tmp_path):
    nested = tmp_path / "a" / "b" / "c.exe"
    nested.parent.mkdir(parents=True)
    nested.touch()
    result = paths.json_path(nested)
    assert "\\" not in result
    assert "/a/b/c.exe" in result.replace("\\", "/")


def test_project_mcp_config_under_orchestrator():
    assert paths.PROJECT_MCP_CONFIG == paths.ORCH_ROOT / ".cursor" / "mcp.json"
