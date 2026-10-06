"""Beginner onboarding — auto-runs setup burst; stops only for human gates."""

from __future__ import annotations

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from orchestrator.paths import (
    DAILY_REVIEW_SETUP_PS1,
    ENV_FILE as _ENV_FILE,
    REPO_ROOT as _PROJECT_ROOT,
    REQUIREMENTS_MCP_FILE,
    is_windows,
    venv_pip_argv,
    venv_python,
)
from release_mcp import env_onboarding as env_ob
from release_mcp import onboarding_store
from release_mcp import onboarding_team_flow as team_flow
from release_mcp import onboarding_verify as ob_verify
from release_mcp import unified_onboarding as uo

_VENV_PY = venv_python()


def _packages_ready() -> bool:
    if not _VENV_PY.is_file():
        return False
    try:
        subprocess.run(
            [str(_VENV_PY), "-c", "import release_mcp"],
            cwd=str(_PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        return True
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return False


_CONTINUE_PHRASES = frozenset({
    "continue",
    "next",
    "next step",
    "next setup step",
    "done",
    "step done",
    "setup done",
    "setup status",
    "ok",
})
_WELCOME_PHRASES = frozenset({
    "welcome onboard",
    "welcome onboarding",
    "onboard me",
    "first time setup",
    "onboarding",
    "setup status",
    "check setup",
    "setup",
})

_RESET_WIZARD_PHRASES = frozenset({
    "welcome onboard",
    "welcome onboarding",
    "onboard me",
    "first time setup",
})

# Steps that need a person (credentials, reload, browser login) — no "continue" spam elsewhere.
_HUMAN_GATE_IDS = frozenset({
    "jira_env",
    "pick_team",
    "crew_lock",
    "cursor_reload",
    "playwright_signin",
    "teams_login",
})


def _step(
    step_id: str,
    title: str,
    *,
    auto: Callable[[], dict[str, Any]] | None = None,
    check: Callable[[], bool] | None = None,
    prompt: str,
    say_next: str = "",
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
        return {"ok": False, "detail": "venv created but python not found."}
    return {"ok": True, "detail": "Created .venv"}


def _playwright_signin_handoff() -> dict[str, Any]:
    return {
        "agent_must": "Invoke Playwright MCP now (do not ask user to open browser manually).",
        "urls": [
            "https://outlook.office.com/mail/",
            "https://abcfinancial.slack.com/",
        ],
        "playwright_actions": [
            "browser_navigate → Outlook → user completes M365 login if prompted",
            "browser_navigate → Slack web → user completes login if prompted",
        ],
        "user_phrase_after": "playwright confirmed",
    }


def _auto_pip() -> dict[str, Any]:
    if not _VENV_PY.is_file():
        return {"ok": False, "detail": "Run venv step first."}
    try:
        pip = venv_pip_argv()
        req = str(REQUIREMENTS_MCP_FILE)
        subprocess.run(
            pip + ["install", "-r", req, "-q"],
            cwd=str(_PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        subprocess.run(
            pip + ["install", "-e", ".", "-q"],
            cwd=str(_PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail": f"pip install failed: {exc}"}
    return {"ok": True, "detail": "Python packages installed."}


def _auto_install_parallel() -> dict[str, Any]:
    """pip + optional Daily Review npm in parallel (both/daily_review tracks)."""
    track = onboarding_store.get_track() or uo.TRACK_RELEASE
    results: dict[str, Any] = {}

    def _run_pip() -> dict[str, Any]:
        return _auto_pip()

    def _run_npm() -> dict[str, Any]:
        return _auto_dr_npm()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_pip = pool.submit(_run_pip)
        f_npm = None
        if track in {uo.TRACK_BOTH, uo.TRACK_DAILY_REVIEW}:
            f_npm = pool.submit(_run_npm)
        results["pip"] = f_pip.result()
        if f_npm is not None:
            results["npm"] = f_npm.result()

    if not results["pip"].get("ok"):
        return {"ok": False, "detail": results["pip"].get("detail"), "parallel": results}
    if results.get("npm") and not results["npm"].get("ok") and not results["npm"].get("skipped"):
        return {"ok": False, "detail": results["npm"].get("detail"), "parallel": results}
    parts = ["Python packages installed."]
    if results.get("npm") and results["npm"].get("ok"):
        parts.append("Daily Review npm installed.")
    return {"ok": True, "detail": " ".join(parts), "parallel": results}


def _auto_env_file() -> dict[str, Any]:
    env_ob.ensure_env_file_from_example()
    return {"ok": True, "detail": "`.env` ready (from .env.example)."}


def _auto_mcp_merge() -> dict[str, Any]:
    from release_mcp import mcp_installer

    track = onboarding_store.get_track() or uo.TRACK_RELEASE
    return mcp_installer.merge_starter_servers(track=track, backup=True)


def _auto_dr_npm() -> dict[str, Any]:
    if not is_windows():
        return {
            "ok": True,
            "skipped": True,
            "detail": "Non-Windows: run **daily_review_setup(install=true)** in chat for npm deps.",
        }
    script = DAILY_REVIEW_SETUP_PS1
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


def _playwright_step_done() -> bool:
    import browser_automation

    ready = browser_automation.playwright_mcp_readiness()
    return bool(ready.get("in_mcp_config")) and (
        bool(ready.get("can_schedule")) or onboarding_store.manual_confirmed("playwright_plugin")
    )


def wizard_steps(*, track: str | None = None) -> list[dict[str, Any]]:
    track = track or onboarding_store.get_track() or uo.TRACK_RELEASE
    all_steps = [
        _step(
            "welcome",
            "Welcome — pick your path",
            check=lambda: bool(onboarding_store.get_track()),
            prompt=(
                "**Welcome aboard.** I'll run automated setup first, then pause only where you must act.\n\n"
                "Default: **daily release** (PIC+AN). Optional: **`both`** · **`daily review only`**"
            ),
            say_next="both · daily review only",
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
            auto=_auto_install_parallel,
            check=_packages_ready,
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
            "Install Cursor MCP (auto → `.cursor/mcp.json`)",
            auto=_auto_mcp_merge,
            check=_mcp_ready,
            prompt="Merging MCP blocks into project `.cursor/mcp.json`…",
        ),
        _step(
            "cursor_reload",
            "Reload Cursor MCP",
            check=lambda: bool(_mcp_ready())
            and onboarding_store.manual_confirmed("cursor_mcp"),
            prompt=(
                "**One action:** Cursor → **Settings** → **MCP** → **Reload** (once).\n"
                "File: **`.cursor/mcp.json`**. I'll run a live MCP smoke test when you send any message."
            ),
            say_next="mcp configured",
        ),
        _step(
            "playwright_signin",
            "Playwright sign-in",
            check=_playwright_step_done,
            prompt=(
                "**Human step:** Sign in to **M365** + **Slack web** in the Playwright browser.\n"
                "The agent should open browsers for you. Say **`playwright confirmed`** when both work."
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
            check=lambda: uo._teams_mcp_ok() or onboarding_store.manual_confirmed("teams_mcp"),
            prompt="Say **`teams_login`** in chat once, then **`teams done`** or **`continue`**.",
            say_next="teams done · continue",
            tracks=frozenset({uo.TRACK_DAILY_REVIEW, uo.TRACK_BOTH}),
        ),
        _step(
            "verify",
            "Final check",
            check=lambda: ob_verify.setup_complete(track=onboarding_store.get_track() or uo.TRACK_RELEASE),
            prompt="Final checks running…",
            say_next="week release",
        ),
        _step(
            "complete",
            "Ready to release",
            check=lambda: True,
            prompt=(
                "**Setup complete.** Ready for **`week release`**.\n"
                "- Daily release: **`week release`** or **`fetch review tickets`**\n"
                "- Daily Review (when you want it): **`daily review welcome`** — on demand only\n\n"
                "Run **`production ready`** anytime for launch evidence tier (informational)."
            ),
            say_next="week release · daily review welcome",
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


def _is_welcome_message(message: str) -> bool:
    lowered = (message or "").lower().strip()
    return any(p in lowered for p in _WELCOME_PHRASES)


def _should_reset_wizard(message: str) -> bool:
    lowered = (message or "").lower().strip()
    return any(p in lowered for p in _RESET_WIZARD_PHRASES)


def _reconcile_wizard_index(steps: list[dict[str, Any]]) -> int:
    """Jump index to the first incomplete step (fixes stale index after auto work)."""
    for i, step in enumerate(steps):
        if not _step_done(step):
            return i
    return max(0, len(steps) - 1)


def _is_human_gate(step: dict[str, Any]) -> bool:
    return str(step.get("id") or "") in _HUMAN_GATE_IDS


def _run_preflight_onboarding(*, track: str, force_fix: bool = False) -> dict[str, Any]:
    from release_mcp import onboarding_preflight as opf

    report = opf.run_preflight(track=track, include_tool_scan=False)
    if force_fix or report.get("status") == "blocked":
        fixed = opf.apply_safe_fixes(track=track)
        report = fixed.get("preflight") or report
    return report


def _automation_burst(
    steps: list[dict[str, Any]],
    start_idx: int,
    *,
    track: str,
    max_passes: int | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Run auto installers and skip completed steps until a human gate or failure."""
    limit = max_passes if max_passes is not None else len(steps) * 3
    idx = start_idx
    logs: list[dict[str, Any]] = []

    for _ in range(limit):
        if idx >= len(steps):
            idx = len(steps) - 1
            break
        step = steps[idx]
        sid = str(step.get("id") or "")

        if sid == "verify" and ob_verify.setup_complete(track=track):
            if idx < len(steps) - 1:
                idx += 1
                _set_wizard_index(idx)
                continue
            break

        if step.get("auto") and not _step_done(step):
            result = _run_auto(step)
            logs.append({
                "step_id": sid,
                "title": step.get("title"),
                **result,
            })
            ob_verify.probe_step(sid, track=track)
            if not result.get("ok"):
                break

        if not _step_done(step):
            break

        if idx >= len(steps) - 1:
            break
        nxt = steps[idx + 1]
        if _is_human_gate(nxt) and not _step_done(nxt):
            idx += 1
            _set_wizard_index(idx)
            break
        idx += 1
        _set_wizard_index(idx)

    return idx, logs


def process_message(message: str) -> dict[str, Any]:
    """Drive linear beginner onboarding from chat."""
    started = time.perf_counter()
    raw = (message or "").strip()
    lowered = raw.lower()

    if _should_reset_wizard(raw):
        reset_wizard()
        uo.set_track(uo.TRACK_RELEASE)
        onboarding_store.merge_state({"wizard_started": True, "preflight_ran": False})
    elif _is_welcome_message(raw) and not onboarding_store.load_state().get("wizard_started"):
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

    track_name = onboarding_store.get_track() or uo.TRACK_RELEASE
    steps = wizard_steps(track=track_name)
    idx = _reconcile_wizard_index(steps)
    _set_wizard_index(idx)

    preflight_report: dict[str, Any] | None = None
    state = onboarding_store.load_state()
    if not state.get("preflight_ran") or _should_reset_wizard(raw):
        preflight_report = _run_preflight_onboarding(
            track=track_name,
            force_fix=_should_reset_wizard(raw),
        )
        onboarding_store.merge_state({
            "preflight_ran": True,
            "last_preflight_status": preflight_report.get("status"),
        })

    idx, auto_batch = _automation_burst(steps, idx, track=track_name)
    steps = wizard_steps(track=track_name)
    step = steps[min(idx, len(steps) - 1)]
    if step.get("id") == "cursor_reload" and raw.strip():
        from release_mcp import mcp_installer as _mi
        from release_mcp import onboarding_mcp_ping as _ping

        st = _mi.install_status(track=track_name)
        live = _ping.live_mcp_ready(require_config=True)
        module_ok = bool((live.get("ping") or {}).get("ok"))
        if st.get("ready") and module_ok:
            onboarding_store.record_manual_confirm("cursor_mcp")
            idx, extra = _automation_burst(steps, idx, track=track_name)
            auto_batch.extend(extra)
            step = steps[min(idx, len(steps) - 1)]
    probe = ob_verify.probe_step(str(step["id"]), track=track_name)

    # After auth phrases, try another burst without requiring "continue".
    if lowered in {"mcp configured", "playwright confirmed", "teams done", "crew done"} or lowered in _CONTINUE_PHRASES:
        idx, extra = _automation_burst(steps, idx, track=track_name)
        auto_batch.extend(extra)
        step = steps[min(idx, len(steps) - 1)]
        probe = ob_verify.probe_step(str(step["id"]), track=track_name)

    total = len(steps)
    lines: list[str] = []
    if preflight_report and preflight_report.get("status") != "ready":
        from release_mcp import onboarding_preflight as opf

        lines.append(opf.format_preflight_markdown(preflight_report))
        lines.append("")

    if auto_batch:
        lines.append("**Automated setup**")
        for entry in auto_batch:
            mark = "✅" if entry.get("ok") else "❌"
            title = entry.get("title") or entry.get("step_id")
            detail = entry.get("detail") or entry.get("message") or entry.get("error") or ""
            line = f"{mark} {title}"
            if detail and detail not in (title, ""):
                line += f" — {detail}"
            lines.append(line)
        lines.append("")

    lines.append(f"**Onboarding {idx + 1}/{total} — {step['title']}**")
    lines.append("")

    probe_line = ob_verify.format_probe_lines(probe)
    if probe_line:
        lines.append(probe_line)
        lines.append("")

    if step["id"] == "jira_env":
        lines.append(env_ob.format_env_checklist(compact=True))
        if not env_ob.assess_env_params()["credentials_ready"]:
            lines.append("")
            lines.append(env_ob.format_next_env_question())
    elif step["id"] == "verify":
        import production_readiness as pr

        report = pr.assess_production_readiness(surface="mcp", track="release")
        lines.append(step["prompt"])
        lines.append("")
        lines.append(f"*Informational:* production_ready={report.get('production_ready')} "
                     f"(launch evidence may still be pending)")
    else:
        lines.append(step["prompt"])

    done = _step_done(step)
    setup_complete = ob_verify.setup_complete(track=track_name)

    if done and step["id"] == "complete":
        try:
            import operator_signoff as osign

            osign.record_signoff("onboarding_complete", detail="welcome onboard wizard finished")
        except Exception:  # noqa: BLE001
            pass

    if done and step["id"] == "complete":
        lines.append("*You're ready — say **`week release`** to start.*")
    elif _is_human_gate(step) and not done:
        need = step.get("say_next") or "done"
        lines.extend(["", f"**Your turn:** {need.split(' · ')[0] if need else 'complete the step above'}"])
        lines.append("*No need to say `continue` — I'll pick up automatically when this is done.*")
    elif not done:
        fix = probe.get("fix") or step.get("say_next") or ""
        if fix:
            lines.extend(["", f"**Fix:** {fix}"])

    user_can_say = ["env checklist", "help", "use glofox", "crew done"]
    if _is_human_gate(step):
        user_can_say.extend((step.get("say_next") or "").replace(" · ", " ").split())

    playwright_handoff = None
    if step.get("id") == "playwright_signin" and not done:
        playwright_handoff = _playwright_signin_handoff()

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    try:
        from release_mcp import onboarding_telemetry as tele

        tele.log_event(
            "wizard_turn",
            step_id=step.get("id"),
            index=idx,
            done=done,
            human_gate=_is_human_gate(step) and not done,
            elapsed_ms=elapsed_ms,
            track=track_name,
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "wizard_step": step["id"],
        "wizard_index": idx,
        "wizard_total": total,
        "step_done": done,
        "setup_complete": setup_complete,
        "auto": auto_batch[-1] if auto_batch else None,
        "auto_batch": auto_batch,
        "preflight": preflight_report,
        "probes": probe,
        "prompt": "\n".join(lines),
        "track": track_name,
        "user_can_say": [p for p in user_can_say if p.strip()],
        "human_gate": _is_human_gate(step) and not done,
        "playwright_handoff": playwright_handoff,
        "complete_setup_hint": (
            "Daily Review is optional — say **`daily review welcome`** after release setup."
            if track_name == uo.TRACK_RELEASE
            else None
        ),
    }


def reset_wizard() -> None:
    onboarding_store.merge_state({"wizard_step_index": 0, "wizard_mode": "beginner", "wizard_started": True})
