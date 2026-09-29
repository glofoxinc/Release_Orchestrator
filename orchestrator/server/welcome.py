"""Guided welcome flow for Release Orchestrator MCP — zero memorization E2E."""

from __future__ import annotations

import os
from typing import Any

import config
import jira_teams


from release_mcp import onboarding  # noqa: E402
from release_mcp.onboarding import RELEASE_ROADMAP as STEP_ROADMAP  # noqa: E402


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def default_projects() -> list[str]:
    raw = _env("DEFAULT_PROJECTS", "PIC,AN")
    return [p.strip().upper() for p in raw.split(",") if p.strip()] or ["PIC", "AN"]


def default_statuses_by_project(projects: list[str] | None = None) -> dict[str, list[str]]:
    keys = projects or default_projects()
    return {pk: list(config.ticket_review_default_checked_statuses(pk)) for pk in keys}


def release_notes_default_statuses_by_project(projects: list[str] | None = None) -> dict[str, list[str]]:
    """Release-ready statuses for Step 3 Release Notes (narrower than Ticket Review)."""
    keys = projects or default_projects()
    return {pk: list(config.release_notes_default_statuses(pk)) for pk in keys}


def _catalog_teams() -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for entry in config.KNOWN_JIRA_TEAMS:
        tid = str(entry.get("id") or "").strip()
        name = jira_teams.normalize_team_display_name(str(entry.get("name") or ""))
        if tid and name:
            seen[tid] = {"id": tid, "name": name, "projects": ", ".join(entry.get("projects") or [])}
    return sorted(seen.values(), key=lambda item: item["name"].lower())


def resolve_team(name_or_id: str | None = None) -> dict[str, Any]:
    """Resolve team by env default, explicit name/id, or Glofox-first fallback."""
    needle = (name_or_id or _env("DEFAULT_JIRA_TEAM")).strip()
    catalog = _catalog_teams()
    if not needle:
        for entry in catalog:
            if "glofox" in entry["name"].lower():
                return {"status": "ok", "team": entry, "source": "default_glofox"}
        if catalog:
            return {"status": "ok", "team": catalog[0], "source": "first_catalog_entry"}
        return {"status": "needs_input", "teams": catalog}

    lowered = needle.casefold()
    for entry in catalog:
        if entry["id"].casefold() == lowered or entry["name"].casefold() == lowered:
            return {"status": "ok", "team": entry, "source": "exact_match"}
    for entry in catalog:
        if lowered in entry["name"].casefold():
            return {"status": "ok", "team": entry, "source": "partial_match"}

    return {
        "status": "not_found",
        "query": needle,
        "teams": catalog,
        "hint": "Use team name (e.g. Glofox Insights Customize) or team UUID from workspace.yaml",
    }


def team_ids_map_for_projects(projects: list[str], inputs: dict[str, Any]) -> dict[str, list[str]]:
    """Build jira_team_ids_by_project from inputs or resolved default team."""
    explicit = inputs.get("jira_team_ids_by_project")
    if isinstance(explicit, dict) and explicit:
        return {str(k).upper(): [str(v) for v in (vals if isinstance(vals, list) else [vals]) if str(v).strip()]
                for k, vals in explicit.items()}

    team_id = str(inputs.get("jira_team_id") or "").strip()
    if not team_id:
        resolved = resolve_team(str(inputs.get("jira_team_name") or inputs.get("team_name") or ""))
        if resolved.get("status") == "ok":
            team_id = str((resolved.get("team") or {}).get("id") or "")
    if not team_id:
        return {}
    return {pk: [team_id] for pk in projects}


def env_readiness(
    *,
    mcp_confirmed: bool = False,
    team_inputs: dict[str, Any] | None = None,
    interactive_onboarding: bool = False,
) -> dict[str, Any]:
    from release_mcp import onboarding

    jira_ok = bool(config.JIRA_EMAIL and config.JIRA_API_TOKEN and config.JIRA_BASE_URL)
    configured = {
        "jira": jira_ok,
        "default_projects": default_projects(),
        "default_team_env": _env("DEFAULT_JIRA_TEAM") or None,
        "default_selection_mode": _env("DEFAULT_SELECTION_MODE", "status") or "status",
        "workspace": config.active_workspace_name() or config.WORKSPACE_NAME,
    }
    base = {
        "configured": configured,
        "missing": [],
        "ready": jira_ok,
        "env_hint": (
            "Copy .env.example → .env once. Jira token: "
            "https://id.atlassian.com/manage-profile/security/api-tokens"
        ),
    }
    merged_base: dict[str, Any] = {
        **base,
        "mcp_confirmed": mcp_confirmed,
        "from_mcp": True,
        "interactive_onboarding": interactive_onboarding,
    }
    if team_inputs:
        merged_base["team_inputs"] = team_inputs
    return onboarding.merge_env_readiness(merged_base)


START_MENU_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "fetch_review_tickets",
        "label": "Fetch review tickets",
        "description": "Step 1 — fetch review-ready tickets (PIC Review + AN Passed QA), lock, then continue full release.",
        "workflow_mode": "full",
        "user_phrase": "fetch review tickets",
    },
    {
        "id": "release_notes",
        "label": "Create release notes",
        "description": "Generate Release Notes DOCX and upload to SharePoint (Steps 3–4). Best after tickets are QA-ready.",
        "workflow_mode": "release_notes_only",
        "user_phrase": "create release notes",
    },
    {
        "id": "shipit",
        "label": "Create SHIPIT + Slack",
        "description": "Create SHIPIT service ticket and post Slack announce (Steps 5–6). Needs SharePoint URL + version.",
        "workflow_mode": "service_ticket_only",
        "user_phrase": "create shipit",
    },
)


def start_path_to_workflow_mode(start_path: str) -> str:
    for opt in START_MENU_OPTIONS:
        if opt["id"] == start_path:
            return opt["workflow_mode"]
    return "full"


def build_start_menu(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """After onboarding — ask user which release path to take."""
    payload = dict(payload or {})
    readiness = env_readiness(mcp_confirmed=payload.get("mcp_confirmed") in {True, "yes", "true", "done", "1"})
    projects = default_projects()
    team_resolved = resolve_team(
        str(payload.get("jira_team_name") or payload.get("team_name") or payload.get("team") or "")
    )
    team = (team_resolved.get("team") or {}) if team_resolved.get("status") == "ok" else {}
    team_label = team.get("name") or "Glofox Insights Customize"

    jira_ready = bool(readiness.get("jira_ready") or readiness.get("ready"))
    if not jira_ready:
        assessment = (readiness.get("onboarding") or {})
        interactive = payload.get("interactive_onboarding") in {True, "yes", "true", "1"}
        show_intro = "onboard" in str(payload.get("_trigger") or "").lower()
        prompt = (
            onboarding.format_interactive_onboarding_prompt(assessment, show_intro=show_intro)
            if interactive
            else str(readiness.get("setup_guide") or "")
        )
        return {
            "status": "setup",
            "step": "onboarding",
            "onboarding_mode": True,
            "interactive_onboarding": interactive,
            "prompt": prompt,
            "setup_checklist": assessment.get("items") or [],
            "setup_next": assessment.get("next_setup_step"),
            "env": readiness,
            "suggested_defaults": {"projects": projects, "jira_team": team or {"name": team_label}},
        }

    prompt = (
        f"Ready — **{' + '.join(projects)}** · **{team_label}**\n\n"
        "Standard weekly release: say **`yes`** or **`full release`** (Steps 1–8).\n\n"
        "Ticket commands:\n"
        "- **`fetch review tickets`** — review-ready fetch + lock (Step 1)\n"
        "- **`fetch release tickets`** — list release-ready tickets only (no lock)\n"
        "- **`schedule review call`** — Teams review-call calendar invite\n\n"
        "Other paths:\n"
        "- **`create release notes`** — DOCX + SharePoint upload\n"
        "- **`create shipit`** — SHIPIT ticket + Slack announce\n\n"
        "Switch team first: **`use ignite`** · **`use glofox`** · **`crew status`**"
    )

    next_actions: dict[str, Any] = {}
    for opt in START_MENU_OPTIONS:
        inputs = build_start_inputs({**payload, "workflow_mode": opt["workflow_mode"]})
        if opt["id"] == "fetch_review_tickets":
            inputs["confirm_defaults"] = "yes"
        next_actions[opt["id"]] = {
            "action": "start",
            "inputs": inputs,
            "description": opt["description"],
        }

    return {
        "status": "ok",
        "step": "start_menu",
        "prompt": prompt,
        "start_menu_options": list(START_MENU_OPTIONS),
        "suggested_defaults": {
            "projects": projects,
            "jira_team": team or {"name": team_label},
            "known_teams": _catalog_teams(),
            "statuses_by_project": default_statuses_by_project(projects),
            "release_notes_statuses_by_project": release_notes_default_statuses_by_project(projects),
        },
        "next_actions": next_actions,
        "env": readiness,
    }


def build_start_inputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge welcome answers into release_wizard start inputs."""
    payload = dict(payload or {})
    projects = [str(p).strip().upper() for p in (payload.get("projects") or default_projects()) if str(p).strip()]
    team_resolved = resolve_team(
        str(payload.get("jira_team_name") or payload.get("team_name") or payload.get("team") or "")
    )
    team = (team_resolved.get("team") or {}) if team_resolved.get("status") == "ok" else {}
    selection_mode = str(payload.get("selection_mode") or _env("DEFAULT_SELECTION_MODE", "status")).strip() or "status"

    inputs: dict[str, Any] = {
        "workflow_mode": str(payload.get("workflow_mode") or "full"),
        "projects": projects,
        "selection_mode": selection_mode,
        "guided": True,
    }
    if selection_mode == "status":
        statuses = payload.get("statuses_by_project")
        if not isinstance(statuses, dict) or not any(statuses.values()):
            statuses = default_statuses_by_project(projects)
        inputs["statuses_by_project"] = statuses
        if team.get("id"):
            inputs["jira_team_id"] = team["id"]
            inputs["jira_team_name"] = team.get("name") or ""
            inputs["jira_team_ids_by_project"] = {pk: [team["id"]] for pk in projects}
    else:
        version = str(payload.get("version_name") or "").strip()
        if version:
            inputs["version_name"] = version
    return inputs


def build_welcome(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return greeting, defaults, and the exact next MCP call — no session required."""
    payload = dict(payload or {})
    mcp_confirmed = payload.get("mcp_confirmed") in {True, "yes", "true", "done", "1"}
    onboarding_mode = payload.get("onboarding") in {True, "yes", "true", "1"} or payload.get(
        "setup_mode"
    ) in {True, "yes", "true", "1"}
    interactive_onboarding = payload.get("interactive_onboarding") in {True, "yes", "true", "1"} or (
        onboarding_mode and "onboard" in str(payload.get("_trigger") or "").lower()
    )
    show_start_menu = payload.get("show_start_menu") in {True, "yes", "true", "1"}
    start_path = str(payload.get("start_path") or "").strip()
    team_inputs = payload.get("team_inputs") if isinstance(payload.get("team_inputs"), dict) else {}
    readiness = env_readiness(
        mcp_confirmed=mcp_confirmed,
        team_inputs=team_inputs or None,
        interactive_onboarding=interactive_onboarding,
    )
    projects = default_projects()
    team_resolved = resolve_team(
        str(payload.get("jira_team_name") or payload.get("team_name") or payload.get("team") or "")
    )
    team = (team_resolved.get("team") or {}) if team_resolved.get("status") == "ok" else {}
    statuses = default_statuses_by_project(projects)
    release_statuses = release_notes_default_statuses_by_project(projects)
    start_inputs = build_start_inputs({**payload, "projects": projects})

    team_label = team.get("name") or "Glofox Insights Customize"
    status_summary = ", ".join(
        f"{pk}: {', '.join(statuses.get(pk, []))}" for pk in projects if statuses.get(pk)
    )
    release_status_summary = ", ".join(
        f"{pk}: {', '.join(release_statuses.get(pk, []))}" for pk in projects if release_statuses.get(pk)
    )

    greeting = (
        "Welcome to Release Orchestrator! "
        "I'll walk you through the full PIC + AN release — you don't need to remember the steps."
    )
    step1_prompt = (
        f"Let's start **Step 1 — Fetch review-ready tickets**.\n"
        f"Projects: **{' + '.join(projects)}**\n"
        f"Team: **{team_label}**\n"
        f"Statuses: {status_summary}\n"
        f"(Step 3 Release Notes re-fetches with: {release_status_summary})\n\n"
        f"Shall I fetch review-ready tickets with these defaults?"
    )

    questions: list[dict[str, Any]] = [
        {
            "field": "confirm_defaults",
            "prompt": f"Use {team_label} for {' + '.join(projects)} and fetch by review-ready status?",
            "required": True,
            "options": ["yes — start Step 1", "no — I'll specify a different team"],
        },
        {
            "field": "team_name",
            "prompt": "If not Glofox, which team? (e.g. Ignite Insights Customize)",
            "required": False,
        },
        {
            "field": "selection_mode",
            "prompt": "Ticket source: status-based (review-ready) or fix version?",
            "required": False,
            "options": ["status", "fix_version"],
            "default": "status",
        },
        {
            "field": "version_name",
            "prompt": "If fix_version mode: release version (e.g. 2026.3.08.12)",
            "required": False,
        },
    ]

    jira_ready = bool(readiness.get("ready") or readiness.get("jira_ready"))
    fully_ready = bool(readiness.get("fully_ready"))
    show_setup = onboarding_mode or not jira_ready

    if start_path and jira_ready:
        mode = start_path_to_workflow_mode(start_path)
        auto_inputs = build_start_inputs({**payload, "workflow_mode": mode})
        if start_path == "fetch_review_tickets":
            auto_inputs["confirm_defaults"] = "yes"
        return {
            "status": "ok",
            "step": "start_menu",
            "auto_start": True,
            "start_path": start_path,
            "recommended_call": {"action": "start", "inputs": auto_inputs},
            "prompt": f"Starting **{start_path.replace('_', ' ')}** with team **{team_label}**.",
            "suggested_defaults": {"projects": projects, "jira_team": team},
        }

    if onboarding_mode and fully_ready and not start_path:
        menu = build_start_menu(payload)
        menu["greeting"] = f"{greeting} Setup is complete."
        menu["step_roadmap"] = STEP_ROADMAP
        menu["workspace"] = readiness["configured"].get("workspace")
        if interactive_onboarding:
            menu["prompt"] = "**Setup complete.**\n\n" + str(menu.get("prompt") or "")
        return menu

    if (show_start_menu or (jira_ready and not onboarding_mode and not payload.get("confirm_defaults"))) and jira_ready:
        menu = build_start_menu(payload)
        if not show_start_menu and payload.get("confirm_defaults"):
            pass
        else:
            menu["greeting"] = greeting
            menu["step_roadmap"] = STEP_ROADMAP
            menu["workspace"] = readiness["configured"].get("workspace")
            return menu

    result: dict[str, Any] = {
        "status": "ok" if jira_ready and not onboarding_mode else ("setup" if show_setup else "ok"),
        "greeting": greeting,
        "prompt": step1_prompt if jira_ready and not onboarding_mode else str(readiness.get("setup_guide") or ""),
        "step": "welcome" if jira_ready and not onboarding_mode else "onboarding",
        "onboarding_mode": show_setup,
        "step_roadmap": STEP_ROADMAP,
        "current_step": STEP_ROADMAP[0],
        "workspace": readiness["configured"].get("workspace"),
        "env": readiness,
        "setup_checklist": (readiness.get("onboarding") or {}).get("items") or [],
        "setup_next": (readiness.get("onboarding") or {}).get("next_setup_step"),
        "suggested_defaults": {
            "projects": projects,
            "selection_mode": start_inputs.get("selection_mode"),
            "statuses_by_project": statuses,
            "release_notes_statuses_by_project": release_statuses,
            "jira_team": team or {"name": "Glofox Insights Customize", "hint": "confirm or override"},
            "known_teams": _catalog_teams(),
        },
        "questions": questions,
        "next_actions": {
            "confirm_and_start": {
                "action": "start",
                "inputs": start_inputs,
                "description": "Starts Step 1 — fetches tickets and shows lock preview",
            },
            "welcome_with_other_team": {
                "action": "welcome",
                "inputs": {"team_name": "<Ignite Insights Customize>"},
                "description": "Re-run welcome with a different team before starting",
            },
            "start_after_team_override": {
                "action": "start",
                "inputs": {"team_name": "<team>", "projects": projects, "selection_mode": "status"},
            },
        },
        "operator_hint": (
            "Prefer release_orchestrator(message='yes') — not release_wizard directly. "
            "Show say_to_user to the user; follow user_can_say for suggested replies."
        ),
        "agent_instructions": (
            "Use release_orchestrator only. First message='welcome'. "
            "Show say_to_user. On yes → message='yes' with workflow_id when present."
        ),
    }

    if payload.get("confirm_defaults") in {True, "yes", "yes — start Step 1", "true", "1"}:
        result["auto_start"] = True
        result["recommended_call"] = result["next_actions"]["confirm_and_start"]
    elif payload.get("start_now") in {True, "true", "yes"}:
        result["auto_start"] = True
        result["recommended_call"] = {"action": "start", "inputs": build_start_inputs(payload)}

    if show_setup:
        assessment = readiness.get("onboarding") or {}
        if interactive_onboarding:
            show_intro = "onboard" in str(payload.get("_trigger") or "").lower()
            result["prompt"] = onboarding.format_interactive_onboarding_prompt(
                assessment,
                show_intro=show_intro,
            )
            result["interactive_onboarding"] = True
            result["onboarding_guide"] = onboarding.full_onboarding_guide(assessment=assessment)
        else:
            result["prompt"] = str(readiness.get("setup_guide") or result["prompt"])
        result["next_actions"] = {
            "check_setup": {
                "action": "welcome",
                "inputs": {"onboarding": True, "interactive_onboarding": True, "mcp_confirmed": mcp_confirmed},
                "description": "Re-run setup checklist after editing .env",
            },
            "mcp_configured": {
                "action": "welcome",
                "inputs": {"mcp_confirmed": True, "onboarding": True, "interactive_onboarding": True},
                "description": "User finished Cursor MCP config — refresh checklist",
            },
            "after_setup_start": {
                "action": "welcome",
                "inputs": {"show_start_menu": True},
                "description": "After .env is complete, show start menu",
            },
        }

    return result
