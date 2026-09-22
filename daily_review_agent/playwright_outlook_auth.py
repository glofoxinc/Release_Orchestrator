"""Playwright Outlook web session — profile path, login bootstrap, readiness."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daily_review_agent.teams_mcp import _node_exe

from daily_review_agent.paths import PLAYWRIGHT_PROFILE_DIR, REPO_ROOT, script

_PROJECT_ROOT = REPO_ROOT
_PROFILE_DIR = PLAYWRIGHT_PROFILE_DIR
_SESSION_MARKER = _PROFILE_DIR / ".outlook_session_ok"
_LOGIN_SCRIPT = script("outlook_login.mjs")
_SCHEDULE_SCRIPT = script("schedule_outlook_playwright.mjs")


def profile_dir() -> Path:
    return _PROFILE_DIR


def session_marker_path() -> Path:
    return _SESSION_MARKER


def outlook_scripts_ready() -> bool:
    return _LOGIN_SCRIPT.is_file() and _SCHEDULE_SCRIPT.is_file()


def outlook_session_ready() -> bool:
    """True when Edge profile has a recorded successful Outlook web sign-in."""
    if not _PROFILE_DIR.is_dir():
        return False
    if _SESSION_MARKER.is_file():
        try:
            data = json.loads(_SESSION_MARKER.read_text(encoding="utf-8"))
            if data.get("ok"):
                return True
        except json.JSONDecodeError:
            pass
    cookies = _PROFILE_DIR / "Default" / "Network" / "Cookies"
    if cookies.is_file() and cookies.stat().st_size > 4096:
        return True
    legacy_cookies = _PROFILE_DIR / "Default" / "Cookies"
    return legacy_cookies.is_file() and legacy_cookies.stat().st_size > 4096


def outlook_readiness() -> dict[str, Any]:
    blockers: list[str] = []
    if not outlook_scripts_ready():
        blockers.append("Playwright Outlook scripts missing (schedule_outlook_playwright.mjs / outlook_login.mjs)")
    if not outlook_session_ready():
        blockers.append(
            "Outlook web not signed in — run: python -m daily_review_agent --outlook-login "
            "(sign in with abcfitness.com in Edge, one time)"
        )
    return {
        "can_schedule": len(blockers) == 0,
        "blockers": blockers,
        "profile_dir": str(_PROFILE_DIR),
        "session_marker": str(_SESSION_MARKER),
        "note": "Primary ABC calendar path — Playwright → Outlook web (no Graph MSAL, no Outlook COM)",
    }


def run_outlook_login(*, wait_minutes: int = 10) -> dict[str, Any]:
    """Open Edge with agent profile; wait for abcfitness.com Outlook calendar sign-in."""
    if not _LOGIN_SCRIPT.is_file():
        return {"ok": False, "error": f"Missing {_LOGIN_SCRIPT}"}

    try:
        proc = subprocess.run(
            [_node_exe(), str(_LOGIN_SCRIPT), str(max(1, wait_minutes))],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=max(120, wait_minutes * 60 + 60),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Outlook login timed out ({wait_minutes} min)"}

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {"ok": False, "error": (proc.stderr or "no output")[:500], "exit_code": proc.returncode}
    try:
        data = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"Invalid login JSON: {exc}", "raw": stdout[:300]}

    if data.get("ok"):
        _SESSION_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_MARKER.write_text(
            json.dumps(
                {
                    "ok": True,
                    "signed_in_at": datetime.now(timezone.utc).isoformat(),
                    "url": data.get("url"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return data
