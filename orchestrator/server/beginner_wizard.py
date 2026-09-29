"""Linear beginner onboarding — one step, then say **continue**."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from release_mcp import env_onboarding as env_ob
from release_mcp import onboarding_store
from release_mcp import onboarding_team_flow as team_flow
from release_mcp import unified_onboarding as uo

from orchestrator.paths import REPO_ROOT as _PROJECT_ROOT
_ENV_FILE = _PROJECT_ROOT / ".env"
_VENV_PY = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

_CONTINUE_PHRASES = frozenset({
    "continue",
    "next",
    "next step",
    "next setup step",
    "done",
    "step done",
    "setup done",
    "ok",
})
_WELCOME_PHRASES = frozenset({
    "welcome onboard",
    "welcome onboarding",
    "onboard me",
    "first time setup",
})


def _step(
    step_id: str,
    title: str,
    *,
    auto: Callable[[], dict[str, Any]] | None = None,
    check: Callable[[], bool] | None = None,
    prompt: str,
    say_next: str = "continue",
    tracks: frozenset[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "auto": auto,
        "check": check,
        "prompt": prompt,
        "say_next": say_next,
        "tracks": tracks or frozenset({uo.TRACK_RELEASE, uo.TRACK_BOTH, uo.TRACK_DAILY_REVIEW}),
    }


def _auto_venv() -> dict[str, Any]:
    if _VENV_PY.is_file():
        return {"ok": True, "detail": "Virtual environment already exists."}
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(_PROJECT_ROOT / ".venv")],
            cwd=str(_PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail": f"Could not create venv: {exc}"}
    if not _VENV_PY.is_file():
        return {"ok": False, "detail": "venv created but python.exe not found."}
    return {"ok": True, "detail": "Created .venv"}


def _auto_pip() -> dict[str, Any]:
    if not _VENV_PY.is_file():
        return {"ok": False, "detail": "Run venv step first."}
    try:
        subprocess.run(
            [str(_VENV_PY), "-m", "pip", "install", "-r", "requirements-mcp.txt", "-q"],
            cwd=str(_PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        subprocess.run(
            [str(_VENV_PY), "-m", "pip", "install", "-e", ".", "-q"],
            cwd=str(_PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail": f"pip install failed: {exc}"}
    return {"ok": True, "detail": "Python packages installed."}


def _auto_env_file() -> dict[str, Any]:
    env_ob.ensure_env_file_from_example()
    return {"ok": True, "detail": "`.env` ready (from .env.example)."}


def _auto_mcp_merge() -> dict[str, Any]:
    from release_mcp import mcp_installer

    track = onboarding_store.get_track() or uo.TRACK_RELEASE
    return mcp_installer.merge_starter_servers(track=track, backup=True)


def _auto_dr_npm() -> dict[str, Any]:
    script = _PROJECT_ROOT / "orchestrator" / "ops" / "daily_review" / "setup.ps1"
    if not script.is_file():
        return {"ok": True, "detail": "Daily Review npm script not found — skip or run later."}
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(_PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail": f"npm setup failed: {exc}"}
    return {"ok": True, "detail": "Daily Review npm bridge installed."}


def _mcp_ready() -> bool:
    from release_mcp import mcp_installer

    track = onboarding_store.get_track() or uo.TRACK_RELEASE
    return bool(mcp_installer.install_status(track=track).get("ready"))


def _production_ready() -> bool:
    import production_readiness as pr

    return bool(pr.assess_production_readiness(surface="both").get("production_ready"))


def wizard_steps(*, track: str | None = None) -> list[dict[str, Any]]:
    track = track or onboarding_store.get_track() or uo.TRACK_RELEASE
    all_steps = [
        _step(
            "welcome",
            "Welcome — pick your path",
            check=lambda: bool(onboarding_store.get_track()),
            prompt=(
                "**Welcome aboard.** We go **one step at a time** — when a step is finished, say **`continue`**.\n\n"
                "**Pick one (say it now):**\n"
                "- **`release only`** — weekly PIC/AN release *(most teams)*\n"
                "- **`daily review only`** — 6 PM review path\n"
                "- **`both`** — release + daily review"
            ),
            say_next="release only · both · continue",
        ),
        _step(
            "install_venv",
            "Install Python environment",
            auto=_auto_venv,
            check=lambda: _VENV_PY.is_file(),
            prompt="Setting up Python virtual environment (`.venv`)…",
        ),
        _step(
            "install_packages",
            "Install Python packages",
            auto=_auto_pip,
            check=lambda: _VENV_PY.is_file(),
            prompt="Installing packages (1–2 min)…",
        ),
        _step(
            "create_env",
            "Create `.env` file",
            auto=_auto_env_file,
            check=lambda: _ENV_FILE.is_file(),
            prompt="Creating local `.env` from template…",
        ),
        _step(
            "jira_env",
            "Jira credentials",
            check=lambda: env_ob.assess_env_params()["credentials_ready"],
            prompt=(
                "Tell me your Jira details in plain English — I write `.env` for you:\n"
                "- `org is abcfinancial`\n"
                "- `email you@abcfitness.com`\n"
                "- Paste API token in `.env` only (Atlassian → Security → API tokens)\n\n"
                "Say **`env checklist`** to see all fields."
            ),
            say_next="env checklist · continue",
        ),
        _step(
            "pick_team",
            "Pick team + projects",
            check=lambda: env_ob.assess_env_params()["team_ready"],
            prompt=team_flow.format_team_pick_prompt(),
            say_next="use glofox · continue",
        ),
        _step(
            "crew_lock",
            "Lock team crew",
            check=team_flow.team_crew_env_configured,
            prompt=(
                "**Glofox:** say **`crew done`** (auto).\n"
                "**Ignite/ETL:** add crew → **`crew done`**."
            ),
            say_next="crew done · continue",
        ),
        _step(
            "mcp_install",
            "Install Cursor MCP (auto)",
            auto=_auto_mcp_merge,
            check=_mcp_ready,
            prompt="Installing generic MCP blocks (release-orchestrator + playwright) into Cursor…",
        ),
        _step(
            "cursor_reload",
            "Reload Cursor MCP",
            check=lambda: onboarding_store.manual_confirmed("cursor_mcp"),
            prompt=(
                "**Your turn (30 sec):** Cursor → **Settings** → **MCP** → **Reload**.\n\n"
                "Then say **`mcp configured`** or **`continue`**."
            ),
            say_next="mcp configured · continue",
        ),
        _step(
            "playwright_signin",
            "Playwright sign-in",
            check=lambda: onboarding_store.manual_confirmed("playwright_plugin"),
            prompt=(
                "**Your turn (one-time):** Sign in to **M365** + **Slack web** in the Playwright browser.\n\n"
                "Then say **`playwright confirmed`** or **`continue`**."
            ),
            say_next="playwright confirmed · continue",
        ),
        _step(
            "dr_npm",
            "Daily Review npm",
            auto=_auto_dr_npm,
            check=uo._dr_npm_ok,
            prompt="Installing Daily Review npm bridge…",
            tracks=frozenset({uo.TRACK_DAILY_REVIEW, uo.TRACK_BOTH}),
        ),
        _step(
            "teams_login",
            "Teams login",
            check=lambda: onboarding_store.manual_confirmed("teams_mcp"),
            prompt="Say **`teams_login`** in chat once, then **`teams done`** or **`continue`**.",
            say_next="teams done · continue",
            tracks=frozenset({uo.TRACK_DAILY_REVIEW, uo.TRACK_BOTH}),
        ),
        _step(
            "verify",
            "Final check",
            check=_production_ready,
            prompt="Almost done — say **`production ready`** to see the report, then **`continue`**.",
            say_next="production ready · continue",
        ),
        _step(
            "complete",
            "Ready to release",
            check=lambda: True,
            prompt="**Setup complete.** Say **`test shipit`** (dry-run) or **`fetch review tickets`**.",
            say_next="test shipit · fetch review tickets",
        ),
    ]
    return [s for s in all_steps if track in s["tracks"] or s["id"] in {"welcome", "complete"}]


def _wizard_index() -> int:
    return int(onboarding_store.load_state().get("wizard_step_index") or 0)


def _set_wizard_index(index: int) -> None:
    onboarding_store.merge_state({"wizard_step_index": max(0, index), "wizard_mode": "beginner"})


def _step_done(step: dict[str, Any]) -> bool:
    try:
        return bool(step["check"]()) if step.get("check") else False
    except Exception:  # noqa: BLE001
        return False


def _run_auto(step: dict[str, Any]) -> dict[str, Any]:
    fn = step.get("auto")
    if not fn:
        return {"ok": True, "skipped": True}
    try:
        result = fn()
        return result if isinstance(result, dict) else {"ok": True, "detail": str(result)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}


def _is_fresh_welcome(message: str) -> bool:
    lowered = (message or "").lower().strip()
    return any(p in lowered for p in _WELCOME_PHRASES)


def process_message(message: str) -> dict[str, Any]:
    """Drive linear beginner onboarding from chat."""
    raw = (message or "").strip()
    lowered = raw.lower()

    if _is_fresh_welcome(raw):
        reset_wizard()
        onboarding_store.merge_state({"wizard_started": True})

    track = uo.resolve_track_phrase(lowered)
    if track:
        uo.set_track(track)

    if env_ob.is_env_onboarding_message(raw):
        env_ob.process_env_message(raw)

    team_updates = team_flow.interpret_team_onboard_message(raw, onboarding_store.load_state())
    if team_updates:
        onboarding_store.merge_state(team_updates)

    uo.apply_progress_from_message(raw)

    steps = wizard_steps()
    idx = min(_wizard_index(), len(steps) - 1)
    step = steps[idx]
    auto_log: dict[str, Any] | None = None

    wants_continue = lowered in _CONTINUE_PHRASES or lowered in {"yes", "mcp configured", "playwright confirmed", "teams done"}

    if wants_continue and _step_done(step) and step["id"] != "complete":
        idx = min(idx + 1, len(steps) - 1)
        _set_wizard_index(idx)
        step = steps[idx]

    if step.get("auto") and not _step_done(step):
        auto_log = _run_auto(step)
        if auto_log.get("ok") and _step_done(step) and step["id"] != "complete":
            idx = min(idx + 1, len(steps) - 1)
            _set_wizard_index(idx)
            step = steps[idx]

    total = len(steps)
    lines = [f"**Onboarding {idx + 1}/{total} — {step['title']}**", ""]

    if auto_log and not auto_log.get("skipped"):
        mark = "✅" if auto_log.get("ok") else "❌"
        detail = auto_log.get("detail") or auto_log.get("message") or auto_log.get("error") or "Done"
        lines.append(f"{mark} {detail}")
        lines.append("")

    if step["id"] == "jira_env":
        lines.append(env_ob.format_env_checklist(compact=True))
        if not env_ob.assess_env_params()["credentials_ready"]:
            lines.append("")
            lines.append(env_ob.format_next_env_question())
    else:
        lines.append(step["prompt"])

    done = _step_done(step)
    if done and step["id"] != "complete":
        nxt = steps[min(idx + 1, len(steps) - 1)]
        lines.extend(["", "---", f"**Next:** {nxt['title']}", f"**Say:** `{nxt.get('say_next', 'continue')}`"])
    elif not done:
        lines.extend(["", f"**When done, say:** `{step.get('say_next', 'continue')}`"])

    return {
        "wizard_step": step["id"],
        "wizard_index": idx,
        "wizard_total": total,
        "step_done": done,
        "auto": auto_log,
        "prompt": "\n".join(lines),
        "track": onboarding_store.get_track(),
    }


def reset_wizard() -> None:
    onboarding_store.merge_state({"wizard_step_index": 0, "wizard_mode": "beginner", "wizard_started": True})
