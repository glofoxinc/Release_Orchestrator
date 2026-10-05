"""Unified onboarding — release, daily review, or both in one checklist."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from orchestrator.paths import AGENT_YAML_FILE, DAILY_REVIEW_OPS_DIR, ENV_FILE, REPO_ROOT
from release_mcp import onboarding_store

TRACK_RELEASE = "release"
TRACK_DAILY_REVIEW = "daily_review"
TRACK_BOTH = "both"
VALID_TRACKS = frozenset({TRACK_RELEASE, TRACK_DAILY_REVIEW, TRACK_BOTH})

TRACK_PHRASES: tuple[tuple[str, str], ...] = (
    ("release and daily review", TRACK_BOTH),
    ("setup both", TRACK_BOTH),
    ("release + daily review", TRACK_BOTH),
    ("both paths", TRACK_BOTH),
    ("everything", TRACK_BOTH),
    ("both", TRACK_BOTH),
    ("release only", TRACK_RELEASE),
    ("weekly release only", TRACK_RELEASE),
    ("daily release only", TRACK_RELEASE),
    ("release orchestrator only", TRACK_RELEASE),
    ("daily review only", TRACK_DAILY_REVIEW),
    ("daily review setup", TRACK_DAILY_REVIEW),
)

# Which release SETUP_STEPS apply per track (default: release + both).
RELEASE_STEP_TRACKS: dict[str, frozenset[str]] = {
    "team_and_projects": frozenset({TRACK_RELEASE, TRACK_BOTH}),
    "team_crew": frozenset({TRACK_RELEASE, TRACK_BOTH}),
    "slack_plugin": frozenset({TRACK_RELEASE, TRACK_BOTH}),
    "deploy_window": frozenset({TRACK_RELEASE, TRACK_BOTH}),
    "defaults_optional": frozenset({TRACK_RELEASE, TRACK_BOTH}),
}

RELEASE_ONLY_SKIP_ON_DR: frozenset[str] = frozenset(
    {"team_and_projects", "slack_plugin", "deploy_window", "defaults_optional"}
)


def get_stored_track() -> str | None:
    raw = str(onboarding_store.load_state().get("onboarding_track") or "").strip().lower()
    return raw if raw in VALID_TRACKS else None


def set_track(track: str) -> dict[str, Any]:
    if track not in VALID_TRACKS:
        raise ValueError(f"Invalid track: {track}")
    return onboarding_store.merge_state({"onboarding_track": track})


def resolve_track_phrase(message: str) -> str | None:
    lowered = (message or "").lower().strip()
    for phrase, track in TRACK_PHRASES:
        if phrase in lowered:
            return track
    return None


def _project_root() -> Path:
    return REPO_ROOT


def _validate_mcp_config() -> dict[str, Any]:
    from daily_review_agent.setup_mcp import validate_cursor_mcp_config

    return validate_cursor_mcp_config()


def _release_mcp_ok() -> bool:
    val = _validate_mcp_config()
    present = val.get("servers_present") or {}
    if not present.get("release-orchestrator"):
        return False
    issues = [i for i in (val.get("issues") or []) if "release-orchestrator" in i.lower()]
    return not issues and not val.get("parse_error")


def _teams_mcp_ok() -> bool:
    val = _validate_mcp_config()
    present = val.get("servers_present") or {}
    if not present.get("teams"):
        return False
    issues = [i for i in (val.get("issues") or []) if i.startswith("teams:") or " teams" in i.lower()]
    return not issues


def _agent_yaml_ok() -> bool:
    try:
        from daily_review_agent.config_loader import load_agent_config

        cfg = load_agent_config()
        return bool(cfg.teams_summary_conversation_id and str(cfg.jira_team_id or "").strip())
    except Exception:  # noqa: BLE001
        return False


def _outlook_ok() -> bool:
    try:
        from daily_review_agent.playwright_outlook_auth import outlook_readiness

        return bool(outlook_readiness().get("can_schedule"))
    except Exception:  # noqa: BLE001
        return False


def _dr_npm_ok() -> bool:
    from daily_review_agent.paths import SCRIPTS_DIR, script

    bridge = script("teams_bridge.mjs")
    node_modules = SCRIPTS_DIR / "node_modules" / "@shayanline" / "msteams-mcp"
    return bridge.is_file() and node_modules.is_dir()


def _dr_enabled_ok() -> bool:
    try:
        from daily_review_agent.config_loader import load_agent_config

        return bool(load_agent_config().enabled)
    except Exception:  # noqa: BLE001
        return False


def _cursor_plugins_note() -> str:
    return (
        "Cursor → Settings → MCP → enable **Playwright** + **Slack** plugins (sign in once).\n\n"
        "**MCP roles (Release + Daily Review):**\n"
        "| MCP | Role |\n"
        "|-----|------|\n"
        "| **Playwright plugin** | **Primary** — review-call calendar (`schedule review call`), "
        "SharePoint upload (`upload sharepoint`), Slack browser fallback |\n"
        "| Embedded Playwright (Node) | Legacy unattended fallback (archived — on-demand only) |\n"
        "| Slack plugin | **Step 6** deployment announce |\n"
        "| Teams stdio | Daily Review chat summary + failure alerts |\n\n"
        "Review call: **`schedule review call`** → Playwright MCP → **`calendar done`**.\n"
        "SharePoint: **`upload sharepoint`** → **`sharepoint done`** or paste URL.\n"
        "Call `daily_review_mcp_config` for copy-paste JSON blocks."
    )


def _dr_preflight_ok() -> bool:
    try:
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.preflight import run_preflight

        cfg = load_agent_config()
        report = run_preflight(cfg, dry_run=False, force=True)
        return bool(report.get("ready"))
    except Exception:  # noqa: BLE001
        return False


DAILY_REVIEW_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "teams_mcp",
        "title": "Teams MCP server (Daily Review chat + alerts)",
        "required": True,
        "phase": "cursor",
        "tracks": frozenset({TRACK_DAILY_REVIEW, TRACK_BOTH}),
        "check": _teams_mcp_ok,
        "manual_confirm": False,
        "instructions": (
            "Add the **teams** stdio block from `daily_review_mcp_config` to `.cursor/mcp.json`, reload MCP.\n"
            "First use in chat: **teams_login** (abcfitness.com).\n"
            "Sibling repo `teams-mcp/` — run `npm install` once if missing."
        ),
        "where": "Cursor mcp.json — teams server (see daily_review_mcp_config MCP tool).",
    },
    {
        "id": "dr_npm_bridge",
        "title": "Daily Review npm bridge (teams-mcp)",
        "required": True,
        "phase": "install",
        "tracks": frozenset({TRACK_DAILY_REVIEW, TRACK_BOTH}),
        "check": _dr_npm_ok,
        "instructions": (
            "From repo root:\n"
            "```\n"
            f"cd {DAILY_REVIEW_OPS_DIR.relative_to(REPO_ROOT).as_posix()}\n"
            "npm install\n"
            "```\n"
            "Or run MCP tool: `daily_review_setup(install=true)`"
        ),
        "where": f"{DAILY_REVIEW_OPS_DIR.relative_to(REPO_ROOT).as_posix()}/ or sibling teams-mcp project.",
    },
    {
        "id": "agent_yaml",
        "title": "Daily Review `agent.yaml` (Teams chat + Jira team)",
        "required": True,
        "phase": "config",
        "tracks": frozenset({TRACK_DAILY_REVIEW, TRACK_BOTH}),
        "check": _agent_yaml_ok,
        "instructions": (
            f"Edit `{AGENT_YAML_FILE.relative_to(REPO_ROOT).as_posix()}`:\n"
            "- `jira_team.id` + `name` (Glofox Insights Customize)\n"
            "- `teams.summary_conversation_id` — Teams group chat ID for on-demand summary posts\n"
            "- `organizer_upn` — your abcfitness.com UPN\n"
            "Do **not** set `enabled: true` until pilot sign-off.\n\n"
            "Meeting invites use **TEAM_CREW_*** from welcome onboard (not a static list in yaml):\n"
            "required = leadership + QA + in-squad assignees · optional = review/release crew · "
            "skip = TEAM_CREW_EXCLUDE + outside squad (Gabriel/Erasmo for Glofox Customize BI)."
        ),
        "where": AGENT_YAML_FILE.relative_to(REPO_ROOT).as_posix(),
    },
    {
        "id": "outlook_playwright",
        "title": "Embedded Outlook login (optional — legacy unattended only)",
        "required": False,
        "phase": "cursor",
        "tracks": frozenset({TRACK_DAILY_REVIEW, TRACK_BOTH}),
        "check": _outlook_ok,
        "manual_confirm": True,
        "instructions": (
            "Only needed if you enable `embedded_playwright_fallback_enabled` for legacy unattended runs.\n"
            "MCP: `daily_review_outlook_login()` or `python -m daily_review_agent --outlook-login`.\n"
            "Cursor chat path uses **Playwright MCP** instead (`schedule review call`)."
        ),
        "where": "Local Playwright profile — skip for Cursor-first workflow.",
    },
    {
        "id": "playwright_mcp_fallback",
        "title": "Playwright MCP — review calls + SharePoint + Slack browser",
        "required": True,
        "phase": "cursor",
        "tracks": frozenset({TRACK_DAILY_REVIEW, TRACK_BOTH}),
        "check": lambda: onboarding_store.manual_confirmed("playwright_plugin")
        or onboarding_store.manual_confirmed("playwright_mcp_fallback"),
        "manual_confirm": True,
        "instructions": (
            "Enable **Playwright** in Cursor (`playwright` in mcp.json) — sign in to M365 once.\n\n"
            "**Review call (primary):** **`schedule review call`** → agent schedules Teams invite → **`calendar done`**.\n\n"
            "**SharePoint:** **`upload sharepoint`** → upload `.docx` → **`sharepoint done`**.\n\n"
            "**Slack browser:** **`send slack playwright`** if Slack MCP is blocked."
        ),
        "where": "Cursor Settings → MCP → playwright server.",
    },
    {
        "id": "cursor_plugins",
        "title": "Cursor Slack + Playwright plugins",
        "required": True,
        "phase": "cursor",
        "tracks": frozenset({TRACK_DAILY_REVIEW, TRACK_BOTH}),
        "check": lambda: onboarding_store.manual_confirmed("cursor_plugins")
        or onboarding_store.manual_confirmed("slack_plugin")
        or onboarding_store.manual_confirmed("playwright_plugin"),
        "manual_confirm": True,
        "instructions": _cursor_plugins_note(),
        "where": "Cursor Settings → MCP plugins.",
    },
    {
        "id": "daily_review_on_demand",
        "title": "Daily Review on-demand (user requests)",
        "required": False,
        "phase": "verify",
        "tracks": frozenset({TRACK_DAILY_REVIEW, TRACK_BOTH}),
        "check": lambda: onboarding_store.manual_confirmed("daily_review_on_demand"),
        "manual_confirm": True,
        "instructions": (
            "Daily Review is **on-demand only** — nothing runs at 6 PM automatically.\n"
            "When you want a review: say **`daily review welcome`** and confirm each step.\n"
            f"Optional pilot sign-off: `{DAILY_REVIEW_OPS_DIR.relative_to(REPO_ROOT).as_posix()}/pilot_signoff.ps1`.\n"
            "Keep `enabled: false` in agent.yaml unless you explicitly opt into auto-schedule later."
        ),
        "where": "MCP chat — daily_review_orchestrator / daily review welcome",
    },
    {
        "id": "daily_review_preflight",
        "title": "Daily Review live preflight",
        "required": False,
        "phase": "verify",
        "tracks": frozenset({TRACK_DAILY_REVIEW, TRACK_BOTH}),
        "check": _dr_preflight_ok,
        "instructions": (
            "Say **daily review preflight** or MCP: `daily_review_preflight(live=true)`.\n"
            "Fix all blockers before first live 6 PM run."
        ),
        "where": "MCP chat — daily_review_preflight.",
    },
)


def format_track_picker() -> str:
    return (
        "**Welcome onboard**\n\n"
        "Say **`both`** (recommended) · **`release only`** · **`daily review only`**\n\n"
        "**Glofox fast path:** `both` → `use glofox` → `crew done` → enable Playwright + Slack in Cursor → **`start`**"
    )


def steps_for_track(track: str) -> tuple[dict[str, Any], ...]:
    from release_mcp import onboarding as ob

    if track not in VALID_TRACKS:
        track = TRACK_BOTH

    merged: list[dict[str, Any]] = []
    for step in ob.SETUP_STEPS:
        sid = str(step["id"])
        if track == TRACK_DAILY_REVIEW and sid in RELEASE_ONLY_SKIP_ON_DR:
            continue
        row = dict(step)
        if sid == "cursor_mcp":
            row["check"] = _release_mcp_ok
            row["manual_confirm"] = False
            row["title"] = "Cursor MCP — release-orchestrator"
        merged.append(row)

    if track in {TRACK_DAILY_REVIEW, TRACK_BOTH}:
        _skip_dr = frozenset({"playwright_mcp_fallback", "cursor_plugins"})
        for step in DAILY_REVIEW_STEPS:
            if track in step["tracks"] and str(step["id"]) not in _skip_dr:
                merged.append(dict(step))

    return tuple(merged)


def track_label(track: str | None) -> str:
    return {
        TRACK_RELEASE: "Daily release (PIC + AN)",
        TRACK_DAILY_REVIEW: "Daily Review (on demand)",
        TRACK_BOTH: "Daily release + Daily Review",
    }.get(track or "", "Not selected")


def setup_complete(*, track: str | None = None) -> bool:
    """Delegate to onboarding_verify — single definition of setup done."""
    from release_mcp import onboarding_verify

    return onboarding_verify.setup_complete(track=track)


def assess_unified_setup(
    *,
    track: str | None = None,
    mcp_confirmed: bool = False,
    from_mcp: bool = True,
    team_inputs: dict[str, Any] | None = None,
    require_track: bool = False,
) -> dict[str, Any]:
    """Full checklist for the selected onboarding track."""
    track = track or get_stored_track()
    if not track and not require_track:
        track = TRACK_BOTH
    if not track:
        picker_step = {
            "id": "onboarding_track",
            "title": "Pick setup path",
            "instructions": format_track_picker(),
            "required": True,
            "phase": "setup",
            "done": False,
            "where": "Chat — say both, release only, or daily review only",
            "manual_confirm": False,
        }
        return {
            "items": [picker_step],
            "required_pending": ["onboarding_track"],
            "optional_pending": [],
            "jira_ready": False,
            "core_ready": False,
            "fully_ready": False,
            "needs_track_picker": True,
            "onboarding_track": None,
            "track_label": track_label(None),
            "next_setup_step": picker_step,
            "env_file_exists": ENV_FILE.is_file(),
            "project_root": str(_project_root()),
            "team_inputs": dict(team_inputs or {}),
        }

    steps = steps_for_track(track)
    items: list[dict[str, Any]] = []
    required_pending: list[str] = []
    optional_pending: list[str] = []

    for step in steps:
        sid = str(step["id"])
        manual = bool(step.get("manual_confirm"))
        if manual and sid in {"cursor_mcp", "slack_plugin", "playwright_plugin", "cursor_plugins", "outlook_playwright"}:
            done = onboarding_store.manual_confirmed(sid) or (from_mcp and sid == "cursor_mcp" and mcp_confirmed)
            if sid == "cursor_plugins":
                done = done or onboarding_store.manual_confirmed("slack_plugin")
        elif manual:
            done = onboarding_store.manual_confirmed(sid) or mcp_confirmed
        else:
            try:
                done = bool(step["check"]())
            except Exception:  # noqa: BLE001
                done = False

        entry = {
            "id": sid,
            "title": step["title"],
            "required": bool(step.get("required")),
            "phase": step.get("phase", ""),
            "done": done,
            "env_var": step.get("env_var"),
            "where": step.get("where", ""),
            "instructions": step.get("instructions", ""),
            "example": step.get("example", ""),
            "manual_confirm": manual,
        }
        items.append(entry)
        if not done:
            if entry["required"]:
                required_pending.append(sid)
            else:
                optional_pending.append(sid)

    jira_ids = {"jira_base_url", "jira_email", "jira_api_token", "env_file"}
    jira_ready = all(i["done"] for i in items if i["id"] in jira_ids)
    core_ready = jira_ready and not [s for s in required_pending if s not in jira_ids]
    fully_ready = core_ready and not required_pending

    next_step = next((i for i in items if not i["done"]), None)

    return {
        "items": items,
        "required_pending": required_pending,
        "optional_pending": optional_pending,
        "jira_ready": jira_ready,
        "core_ready": core_ready,
        "fully_ready": fully_ready,
        "needs_track_picker": False,
        "onboarding_track": track,
        "track_label": track_label(track),
        "next_setup_step": next_step,
        "env_file_exists": ENV_FILE.is_file(),
        "project_root": str(_project_root()),
        "team_inputs": dict(team_inputs or {}),
        "mcp_validation": _validate_mcp_config(),
    }


def apply_progress_from_message(
    message: str,
    *,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist track selection or manual step confirms from chat phrases."""
    lowered = (message or "").lower().strip()
    applied: dict[str, Any] = {}

    track = resolve_track_phrase(lowered)
    if track:
        set_track(track)
        applied["track"] = track

    if any(p in lowered for p in ("mcp configured", "mcp is configured")):
        onboarding_store.record_manual_confirm("cursor_mcp")
        applied["manual_confirm"] = "cursor_mcp"
    elif "outlook done" in lowered:
        onboarding_store.record_manual_confirm("outlook_playwright")
        applied["manual_confirm"] = "outlook_playwright"
    elif "teams done" in lowered:
        onboarding_store.record_manual_confirm("teams_mcp")
        applied["manual_confirm"] = "teams_mcp"
    elif lowered in {"done", "next", "next setup step", "setup done", "step done", "continue setup"}:
        next_step = (assessment or {}).get("next_setup_step") or {}
        sid = str(next_step.get("id") or "")
        if sid and next_step.get("manual_confirm"):
            onboarding_store.record_manual_confirm(sid)
            applied["manual_confirm"] = sid

    return applied


def completion_message(track: str | None) -> str:
    track = track or get_stored_track() or TRACK_BOTH
    lines = ["**Setup complete.**", ""]
    if track in {TRACK_RELEASE, TRACK_BOTH}:
        lines.append("**Release:** say **`yes`** or **`full release`** to start PIC + AN.")
    if track in {TRACK_DAILY_REVIEW, TRACK_BOTH}:
        lines.append("**Daily Review:** say **`daily review welcome`** → preflight → live run.")
    lines.extend(["", "**production ready** · **help** · **crew status**"])
    return "\n".join(lines)
