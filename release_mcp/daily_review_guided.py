"""Guided Daily Review E2E — conversational setup + live run (same MCP as releases)."""

from __future__ import annotations

import json
import uuid
from typing import Any

YES = frozenset({"yes", "y", "ok", "okay", "done", "next", "continue", "proceed", "go"})
WELCOME = frozenset(
    {
        "daily review",
        "daily review welcome",
        "daily review setup",
        "daily review onboard",
        "start daily review",
        "setup daily review",
    }
)

STEP_GUIDE: dict[str, dict[str, str]] = {
    "welcome": {"number": "0", "title": "Welcome", "goal": "Daily Review Agent — 6 PM PIC/AN review path."},
    "setup": {"number": "1", "title": "Setup", "goal": "Install deps (npm + pip) and validate checklist."},
    "mcp": {"number": "2", "title": "MCP config", "goal": "release-orchestrator + teams + Playwright/Slack plugins."},
    "teams": {"number": "3", "title": "Teams login", "goal": "One-time abcfitness.com sign-in via Teams MCP."},
    "playwright": {"number": "4", "title": "Playwright MCP", "goal": "Enable Playwright MCP + one-time M365 sign-in for review-call scheduling."},
    "preflight": {"number": "5", "title": "Pre-flight", "goal": "Live readiness gate — must be green before production."},
    "dry_run": {"number": "6", "title": "Dry run", "goal": "Preview tickets + meeting draft (no side effects)."},
    "live": {"number": "7", "title": "Live run", "goal": "Schedule meeting + post Teams summary."},
    "schedule": {"number": "8", "title": "Schedule window", "goal": "Enable 2-week Task Scheduler window."},
    "complete": {"number": "done", "title": "Complete", "goal": "Production path ready — register Task Scheduler after pilot sign-off."},
}

_ORDER = list(STEP_GUIDE.keys())
_SESSIONS: dict[str, dict[str, Any]] = {}


def _roadmap(current: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key in _ORDER:
        if key == "welcome":
            continue
        info = STEP_GUIDE[key]
        out.append(
            {
                "step": info["number"],
                "title": info["title"],
                "status": "current" if key == current else ("done" if _ORDER.index(key) < _ORDER.index(current) else "pending"),
            }
        )
    return out


def _say(step: str, body: str, *, workflow_id: str, user_can_say: list[str] | None = None) -> dict[str, Any]:
    info = STEP_GUIDE.get(step, STEP_GUIDE["welcome"])
    return {
        "workflow_id": workflow_id,
        "step": step,
        "step_number": info["number"],
        "step_title": info["title"],
        "goal": info["goal"],
        "say_to_user": body,
        "user_can_say": user_can_say or ["yes", "next", "help", "status"],
        "roadmap": _roadmap(step),
    }


def _advance(session: dict[str, Any], *, delta: int = 1) -> str:
    step = str(session.get("step") or "welcome")
    idx = _ORDER.index(step) if step in _ORDER else 0
    nxt = min(len(_ORDER) - 1, idx + delta)
    session["step"] = _ORDER[nxt]
    return session["step"]


def run_daily_review_guided(message: str = "daily review welcome", workflow_id: str | None = None) -> dict[str, Any]:
    """Guided Daily Review E2E — say **daily review welcome**, then **yes** step by step."""
    raw = (message or "").strip().lower()
    wid = workflow_id or str(uuid.uuid4())
    session = _SESSIONS.setdefault(wid, {"step": "welcome", "history": []})

    if raw in WELCOME or (not workflow_id and raw in {"", "help"}):
        session["step"] = "welcome"
        return _say(
            "welcome",
            (
                "**Daily Review Agent** (merged into Release Orchestrator)\n\n"
                "This walks you through production setup:\n"
                "1. Install deps → 2. MCP (release-orchestrator + teams + Playwright/Slack plugins) → "
                "3. Teams login → 4. Playwright MCP → 5. Pre-flight → 6. Dry run → 7. Live run → 8. Schedule\n\n"
                "Review calls + SharePoint + Slack browser paths all use **Playwright MCP** in Cursor.\n\n"
                "Reply **yes** to start Step 1 (setup checklist)."
            ),
            workflow_id=wid,
            user_can_say=["yes", "daily review setup", "help"],
        )

    if raw in {"help", "status"}:
        step = str(session.get("step") or "welcome")
        return _say(
            step,
            f"Current step: **{STEP_GUIDE.get(step, {}).get('title', step)}**. Reply **yes** or **next** to continue.",
            workflow_id=wid,
        )

    step = str(session.get("step") or "welcome")

    if step == "welcome" and raw in YES:
        session["step"] = "setup"
        step = "setup"

    if step == "setup":
        from daily_review_agent.setup_mcp import format_setup_text, run_setup

        report = run_setup(install="install" in raw)
        text = format_setup_text(report)
        ready = bool(report.get("ready_for_dry_run"))
        if raw in YES and ready:
            _advance(session)
            return run_daily_review_guided("yes", workflow_id=wid)
        return {
            **_say(
                "setup",
                text + "\n\nReply **yes** when checklist is green enough to continue.",
                workflow_id=wid,
                user_can_say=["yes", "daily review setup install=true", "help"],
            ),
            "setup_report": report,
        }

    if step == "mcp":
        from daily_review_agent.setup_mcp import generate_mcp_snippets, validate_cursor_mcp_config

        val = validate_cursor_mcp_config()
        snippets = generate_mcp_snippets()
        body = (
            "**MCP stack for full E2E:**\n"
            "- **release-orchestrator** (this repo — releases + daily_review_* tools)\n"
            "- **teams** (stdio — chat summary + alerts)\n"
            "- **Playwright plugin** — review-call calendar + SharePoint upload + Slack browser fallback\n"
            "- **Slack plugin** — release Step 6 announce\n\n"
            f"Config: `{val.get('config_path')}`\n"
        )
        if val.get("issues"):
            body += "Issues:\n" + "\n".join(f"- {i}" for i in val["issues"][:8])
            body += "\n\nCall **daily_review_mcp_config** for copy-paste blocks. Reply **yes** when fixed."
        else:
            body += "MCP config looks good. Reply **yes** to continue."
            if raw in YES:
                _advance(session)
                return run_daily_review_guided("yes", workflow_id=wid)
        return {**_say("mcp", body, workflow_id=wid), "mcp_validation": val, "mcp_snippets": snippets}

    if step == "teams":
        body = (
            "**Teams login (Cursor Teams MCP):**\n"
            "In chat run **teams_login** and sign in with abcfitness.com.\n\n"
            "Reply **teams done** or **yes** when Teams MCP shows logged in."
        )
        if raw in YES or "teams done" in raw:
            step = _advance(session)
        return _say(step, body, workflow_id=wid, user_can_say=["teams done", "yes", "help"])

    if step == "playwright":
        import browser_automation

        ready = browser_automation.playwright_mcp_readiness()
        mcp = ready.get("mcp_server") or "playwright"
        body = (
            f"**Playwright MCP (primary for review calls + SharePoint):**\n"
            f"1. Cursor → Settings → MCP → enable **`{mcp}`**\n"
            "2. Say **schedule review call** — agent opens Outlook web and creates the Teams invite\n"
            "3. Sign in with abcfitness.com once in the Playwright browser if prompted\n\n"
            f"MCP ready: **{ready.get('can_schedule')}**\n"
            "Reply **playwright confirmed** or **yes** when enabled."
        )
        if raw in YES or "playwright confirmed" in raw or "playwright done" in raw or ready.get("can_schedule"):
            step = _advance(session)
        return _say(
            step,
            body,
            workflow_id=wid,
            user_can_say=["playwright confirmed", "schedule review call", "yes"],
        )

    if step == "preflight":
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.preflight import run_preflight

        cfg = load_agent_config()
        pf = run_preflight(cfg, dry_run=False, force=True)
        body = json.dumps(pf, indent=2, default=str)
        if pf.get("ready") and raw in YES:
            step = _advance(session)
        elif pf.get("ready"):
            body = f"Pre-flight **ready**. Reply **yes** to dry run.\n\n{body}"
        else:
            body = f"Pre-flight **not ready** — fix blockers first.\n\n{body}"
        return {**_say(step, body, workflow_id=wid), "preflight": pf}

    if step == "dry_run":
        from daily_review_agent.runner import run_daily_agent

        if raw in YES or "run" in raw:
            result = run_daily_agent(dry_run=True, force=True)
            body = json.dumps(result, indent=2, default=str)
            if result.get("status") not in {"disabled", "preflight_failed"}:
                step = _advance(session)
            return {**_say(step, body, workflow_id=wid), "dry_run_result": result}
        return _say(
            step,
            "Reply **yes** to run **daily_review_run_dry** (preview tickets + meeting draft).\n"
            "Optional first: **daily_review_attendee_policy** — required vs optional vs skipped "
            "(crew from welcome onboard; outside-squad assignees like Gabriel/Erasmo are never invited).",
            workflow_id=wid,
        )

    if step == "live":
        from daily_review_agent.runner import run_daily_agent

        if raw in YES or "live" in raw:
            result = run_daily_agent(dry_run=False, force=True)
            body = json.dumps(result, indent=2, default=str)
            if result.get("status") == "ok":
                step = _advance(session)
            return {**_say(step, body, workflow_id=wid), "live_result": result}
        return _say(
            step,
            "Reply **yes** for **live run** — returns Playwright MCP steps to schedule the review call, "
            "then posts Teams summary after you say **calendar done**.",
            workflow_id=wid,
            user_can_say=["yes", "skip", "help"],
        )

    if step == "schedule":
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.schedule_registry import schedule_for_weeks

        if raw in YES or "schedule" in raw:
            cfg = load_agent_config()
            reg = schedule_for_weeks(weeks=2, timezone=cfg.timezone, run_at=cfg.run_at)
            session["step"] = "complete"
            return {
                **_say(
                    "complete",
                    (
                        f"Scheduled until **{reg.get('active_until')}** at {cfg.run_at} {cfg.timezone}.\n\n"
                        "Run `.\\scripts\\daily_review\\pilot_signoff.ps1` then register Task Scheduler.\n"
                        "Release flow: say **welcome onboard** on the same MCP."
                    ),
                    workflow_id=wid,
                ),
                "schedule": reg,
            }
        return _say(
            step,
            "Reply **yes** to enable a **2-week** daily review window (18:00 IST).",
            workflow_id=wid,
        )

    if step == "complete":
        return _say(
            "complete",
            "Daily Review E2E complete. Say **daily review welcome** to rerun setup checks.",
            workflow_id=wid,
            user_can_say=["daily review welcome", "welcome onboard"],
        )

    # Default: advance on yes from any intermediate step
    if raw in YES:
        step = _advance(session)
        if step == "setup":
            return run_daily_review_guided("yes", workflow_id=wid)
        if step == "mcp":
            return run_daily_review_guided("yes", workflow_id=wid)
        return _say(step, f"Advanced to **{STEP_GUIDE[step]['title']}**. Reply **yes** or **help**.", workflow_id=wid)

    return _say(step, "Reply **yes**, **next**, or **help**.", workflow_id=wid)
