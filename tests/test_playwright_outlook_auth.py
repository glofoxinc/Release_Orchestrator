"""Playwright Outlook session readiness — no live browser."""

from __future__ import annotations

from pathlib import Path

import pytest

from daily_review_agent.playwright_outlook_auth import (
    outlook_readiness,
    outlook_scripts_ready,
    outlook_session_ready,
    profile_dir,
    session_marker_path,
)


def test_outlook_scripts_ready():
    assert outlook_scripts_ready() is True


def test_outlook_session_not_ready_without_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "daily_review_agent.playwright_outlook_auth._PROFILE_DIR",
        tmp_path / "missing-profile",
    )
    monkeypatch.setattr(
        "daily_review_agent.playwright_outlook_auth._SESSION_MARKER",
        tmp_path / "missing-profile" / ".outlook_session_ok",
    )
    assert outlook_session_ready() is False
    readiness = outlook_readiness()
    assert readiness["can_schedule"] is False
    assert any("outlook-login" in b.lower() for b in readiness["blockers"])


def test_outlook_session_ready_with_marker(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    prof.mkdir()
    marker = prof / ".outlook_session_ok"
    marker.write_text('{"ok": true}', encoding="utf-8")
    monkeypatch.setattr("daily_review_agent.playwright_outlook_auth._PROFILE_DIR", prof)
    monkeypatch.setattr("daily_review_agent.playwright_outlook_auth._SESSION_MARKER", marker)
    assert outlook_session_ready() is True


def test_profile_paths_under_agent_state():
    assert "playwright-outlook-profile" in str(profile_dir())
    assert session_marker_path().name == ".outlook_session_ok"
