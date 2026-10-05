"""Auto-probes for welcome onboard — verify MCP/env before manual confirms."""

from __future__ import annotations

from typing import Any

from release_mcp import env_onboarding as env_ob
from release_mcp import onboarding_store
from release_mcp import unified_onboarding as uo

# Map wizard step ids → onboarding_store manual confirm keys
_STEP_CONFIRM_MAP: dict[str, str] = {
    "mcp_install": "cursor_mcp",
    "cursor_reload": "cursor_mcp",
    "playwright_signin": "playwright_plugin",
    "teams_login": "teams_mcp",
}


def _probe_mcp_install(*, track: str) -> dict[str, Any]:
    from release_mcp import mcp_installer

    status = mcp_installer.install_status(track=track)
    val: dict[str, Any] = {}
    try:
        from daily_review_agent.setup_mcp import validate_cursor_mcp_config

        val = validate_cursor_mcp_config()
    except Exception as exc:  # noqa: BLE001
        val = {"issues": [str(exc)]}

    ok = bool(status.get("ready")) and not val.get("parse_error")
    issues = list(val.get("issues") or [])
    if status.get("missing"):
        issues.append(f"Missing MCP servers: {', '.join(status['missing'])}")
    if status.get("parse_error"):
        issues.append(f"mcp.json parse error: {status['parse_error']}")

    return {
        "ok": ok,
        "step_id": "mcp_install",
        "detail": status.get("config_path") or "No mcp.json",
        "issues": issues,
        "fix": "Re-run welcome onboard (auto-merge) or daily_review_mcp_config for blocks.",
        "data": {"install_status": status, "validation": val},
    }


def _probe_cursor_reload(*, track: str) -> dict[str, Any]:
    from release_mcp import mcp_installer
    from release_mcp import onboarding_mcp_ping as ping

    status = mcp_installer.install_status(track=track)
    live = ping.live_mcp_ready(require_config=True)
    config_ok = bool(status.get("ready")) and not status.get("parse_error")
    module_ok = bool((live.get("ping") or {}).get("ok"))
    ack = onboarding_store.manual_confirmed("cursor_mcp")
    ok = config_ok and module_ok and ack
    if config_ok and module_ok and not ack:
        issues = ["Reload Cursor MCP once in Settings, then say **mcp configured** (or any message)."]
    elif not config_ok:
        issues = ["Fix .cursor/mcp.json — run onboarding_preflight(apply_fix=true)"]
    elif not module_ok:
        issues = ["release_mcp import failed — fix pip/venv first"]
    else:
        issues = []
    if ok:
        onboarding_store.record_manual_confirm("cursor_mcp")
    return {
        "ok": ok,
        "step_id": "cursor_reload",
        "detail": (
            f"MCP config={config_ok} module_smoke={module_ok} reload_ack={ack} "
            f"tools={(live.get('ping') or {}).get('tool_count')}"
        ),
        "issues": issues,
        "fix": "Cursor → Settings → MCP → Reload (once). Then **mcp configured** or any chat message.",
        "data": {"install_status": status, "live": live},
    }


def _probe_playwright() -> dict[str, Any]:
    import browser_automation

    ready = browser_automation.playwright_mcp_readiness()
    in_config = bool(ready.get("in_mcp_config"))
    confirmed = bool(ready.get("can_schedule"))
    ok = in_config and confirmed
    return {
        "ok": ok,
        "step_id": "playwright_signin",
        "detail": f"Playwright MCP: configured={in_config}, signed_in={confirmed}",
        "issues": list(ready.get("blockers") or []),
        "fix": "Enable Playwright in Cursor MCP, sign in to M365/Slack once, say **playwright confirmed**.",
        "data": ready,
    }


def _probe_teams() -> dict[str, Any]:
    ok = uo._teams_mcp_ok()
    return {
        "ok": ok,
        "step_id": "teams_login",
        "detail": "Teams MCP server in mcp.json",
        "issues": [] if ok else ["teams server missing or invalid in mcp.json"],
        "fix": "Add teams block from daily_review_mcp_config, then **teams_login** → **teams done**.",
        "data": {"teams_mcp_ok": ok},
    }


def _probe_jira_env() -> dict[str, Any]:
    params = env_ob.assess_env_params()
    ok = bool(params.get("credentials_ready"))
    live: dict[str, Any] | None = None
    if ok:
        live = env_ob.validate_jira_credentials_live()
        ok = bool(live.get("ok"))
    issues: list[str] = []
    if not params.get("credentials_ready"):
        issues.append("Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env")
    elif live and not live.get("ok") and not live.get("skipped"):
        issues.append(str(live.get("error") or "Jira API rejected credentials"))
    return {
        "ok": ok,
        "step_id": "jira_env",
        "detail": (
            f"Jira API OK ({live.get('display_name')})"
            if ok and live
            else "Jira .env credentials"
        ),
        "issues": issues,
        "fix": "Edit `.env` locally — never paste token in chat. Say **env checklist**.",
        "data": {"params": params, "live": live},
    }


def probe_step(step_id: str, *, track: str | None = None) -> dict[str, Any]:
    """Run probe for a wizard step; auto-record manual confirm when ok."""
    track = track or onboarding_store.get_track() or uo.TRACK_RELEASE
    sid = (step_id or "").strip()

    if sid in {"welcome", "install_venv", "create_env"}:
        return {"ok": True, "step_id": sid, "detail": "Auto step", "issues": [], "fix": "", "data": {}}
    if sid == "install_packages":
        from orchestrator.paths import venv_python

        ok = venv_python().is_file()
        return {
            "ok": ok,
            "step_id": sid,
            "detail": "Python venv",
            "issues": [] if ok else ["venv python not found"],
            "fix": "Send any message to retry automated pip install.",
            "data": {},
        }
    if sid == "jira_env":
        result = _probe_jira_env()
    elif sid == "pick_team":
        ok = bool(env_ob.assess_env_params().get("team_ready"))
        result = {
            "ok": ok,
            "step_id": sid,
            "detail": "Team + projects in .env",
            "issues": [] if ok else ["Say **use glofox** (or your team)"],
            "fix": "**use glofox** · **crew done**",
            "data": {},
        }
    elif sid == "crew_lock":
        from release_mcp import onboarding_team_flow as team_flow

        ok = team_flow.team_crew_env_configured()
        result = {
            "ok": ok,
            "step_id": sid,
            "detail": "TEAM_CREW_* in .env",
            "issues": [] if ok else ["Crew not saved"],
            "fix": "Say **crew done**",
            "data": {},
        }
    elif sid == "mcp_install":
        result = _probe_mcp_install(track=track)
    elif sid == "cursor_reload":
        result = _probe_cursor_reload(track=track)
    elif sid == "playwright_signin":
        result = _probe_playwright()
    elif sid == "teams_login":
        result = _probe_teams()
    elif sid == "dr_npm":
        ok = uo._dr_npm_ok()
        result = {
            "ok": ok,
            "step_id": sid,
            "detail": "Daily Review npm bridge",
            "issues": [] if ok else ["npm deps missing under orchestrator/zones/platform/ops/daily_review"],
            "fix": "Run **daily_review_setup(install=true)** or npm install in ops/daily_review",
            "data": {},
        }
    elif sid == "verify":
        result = {
            "ok": setup_complete(track=track),
            "step_id": sid,
            "detail": "Setup complete check",
            "issues": [] if setup_complete(track=track) else ["Required setup steps incomplete"],
            "fix": "Finish prior steps — wizard will auto-advance when ready.",
            "data": {},
        }
    elif sid == "complete":
        result = {"ok": True, "step_id": sid, "detail": "Done", "issues": [], "fix": "", "data": {}}
    else:
        result = {"ok": True, "step_id": sid, "detail": "", "issues": [], "fix": "", "data": {}}

    if result.get("ok") and sid in _STEP_CONFIRM_MAP:
        onboarding_store.record_manual_confirm(_STEP_CONFIRM_MAP[sid])

    return result


def run_all_probes(*, track: str | None = None) -> dict[str, Any]:
    track = track or onboarding_store.get_track() or uo.TRACK_RELEASE
    step_ids = [
        "jira_env",
        "pick_team",
        "crew_lock",
        "mcp_install",
        "cursor_reload",
        "playwright_signin",
    ]
    if track in {uo.TRACK_DAILY_REVIEW, uo.TRACK_BOTH}:
        step_ids.extend(["dr_npm", "teams_login"])
    probes = {sid: probe_step(sid, track=track) for sid in step_ids}
    return {
        "track": track,
        "setup_complete": setup_complete(track=track),
        "probes": probes,
    }


def setup_complete(*, track: str | None = None) -> bool:
    """True when required onboarding steps for the track are satisfied (probed or confirmed)."""
    track = track or onboarding_store.get_track() or uo.TRACK_RELEASE
    assessment = uo.assess_unified_setup(track=track, from_mcp=True)
    if assessment.get("needs_track_picker"):
        return False
    required_pending = list(assessment.get("required_pending") or [])
    # Playwright browser login cannot be fully probed — accept manual confirm for release track
    optional_manual = {"outlook_playwright", "slack_plugin", "cursor_plugins", "playwright_mcp_fallback"}
    blocking = [s for s in required_pending if s not in optional_manual]
    if blocking:
        return False
    if not env_ob.assess_env_params().get("credentials_ready"):
        return False
    from release_mcp import mcp_installer

    if not mcp_installer.install_status(track=track).get("ready"):
        return False
    import browser_automation

    pw = browser_automation.playwright_mcp_readiness()
    if not pw.get("in_mcp_config"):
        return False
    if track in {uo.TRACK_DAILY_REVIEW, uo.TRACK_BOTH}:
        if not uo._teams_mcp_ok() and not onboarding_store.manual_confirmed("teams_mcp"):
            return False
    return True


def format_probe_lines(probe: dict[str, Any]) -> str:
    if probe.get("ok"):
        return f"✅ {probe.get('detail') or probe.get('step_id')}"
    issues = probe.get("issues") or ["Not ready"]
    fix = probe.get("fix") or ""
    line = f"❌ {issues[0]}"
    if fix:
        line += f" — {fix}"
    return line
