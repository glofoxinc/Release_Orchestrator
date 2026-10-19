"""Extended MCP release_ops coverage — status-only, deploy helpers."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")


def test_fetch_status_mode_empty_statuses_needs_input():
    from release_mcp import release_ops

    result = release_ops.fetch_release_tickets(
        selection_mode="status",
        statuses_by_project={},
    )
    assert result["status"] == "needs_input"


def test_build_docx_data_omits_version_when_flag_false():
    from release_mcp.release_ops import _build_docx_data

    data = _build_docx_data(
        [{"type": "Analyze", "ticket": "AN-1", "report": "R", "description": "x"}],
        "",
        include_fix_version_metadata=False,
    )
    assert data["version"] == ""
    assert data["release_date"] == ""


def test_generate_release_notes_docx_no_tickets(monkeypatch):
    from release_mcp import release_ops

    monkeypatch.setattr(
        release_ops,
        "fetch_release_tickets",
        lambda *a, **k: {"status": "ok", "extracted": [], "projects": ["PIC"]},
    )
    result = release_ops.generate_release_notes_docx_file("2026.3.09.09")
    assert result["status"] == "error"


def test_generate_client_release_notes_docx_file_pic_only(tmp_path):
    from release_mcp import release_ops

    dest = tmp_path / "Client Release Notes 2026.4.10.15.docx"
    result = release_ops.generate_client_release_notes_docx_file(
        "2026.4.10.15",
        output_path=str(dest),
        extracted_override=[
            {
                "ticket": "AN-5596",
                "project": "AN",
                "type": "Analyze",
                "client": "Standard",
                "report": "Class Utilization",
                "description": "rename",
            },
            {
                "ticket": "PIC-6326",
                "project": "PIC",
                "type": "Custom",
                "client": "Lift",
                "report": "Corporate Partnership Analysis",
                "description": "Australia update",
            },
        ],
    )
    assert result["ok"] is True
    assert result["client_ticket_count"] == 1
    assert result["client_clients"] == ["Lift"]
    assert dest.exists()
    assert dest.stat().st_size > 1000


def test_list_all_teams_cached(monkeypatch, tmp_path):
    import config

    ws_root = tmp_path / "workspace.yaml"
    ws_root.write_text(
        "workspace:\n  name: Root\n  projects:\n    - key: PIC\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_WS_PATH", str(ws_root))
    monkeypatch.setattr(config, "_WORKSPACES_DIR", str(tmp_path / "workspaces"))
    config.invalidate_teams_list_cache()

    first = config.list_all_teams()
    second = config.list_all_teams()
    assert first == second
    assert first[0]["name"] == "Root"
