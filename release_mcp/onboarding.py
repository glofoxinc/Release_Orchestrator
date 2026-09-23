"""First-time setup guide for cloned repos — credentials, MCP config, next steps."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import config

from release_mcp import onboarding_guide
from release_mcp import onboarding_team_flow
from release_mcp import step_ux
import team_crew

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_EXAMPLE = _PROJECT_ROOT / ".env.example"
_ENV_FILE = _PROJECT_ROOT / ".env"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _env_file_exists() -> bool:
    return _ENV_FILE.is_file()


def _python_launcher() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        return str(exe).replace("\\", "/")
    venv_py = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return str(venv_py).replace("\\", "/")
    return "python"


# Ordered checklist — new clones walk top to bottom once.
SETUP_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "venv",
        "title": "Python virtual environment",
        "required": True,
        "phase": "install",
        "check": lambda: (_PROJECT_ROOT / ".venv" / "Scripts" / "python.exe").is_file(),
        "instructions": (
            "Open a terminal in the repo folder and run:\n"
            "```\n"
            "python -m venv .venv\n"
            ".venv\\Scripts\\pip install -r requirements.txt\n"
            "```"
        ),
        "where": "Local — no account needed.",
    },
    {
        "id": "env_file",
        "title": "Create `.env` from template",
        "required": True,
        "phase": "install",
        "check": _env_file_exists,
        "instructions": (
            "Copy the example file (never commit `.env` to git):\n"
            "```\n"
            "copy .env.example .env\n"
            "```\n"
            "On Mac/Linux: `cp .env.example .env`"
        ),
        "where": f"Template: `{_ENV_EXAMPLE.name}` in the repo root.",
    },
    {
        "id": "jira_base_url",
        "title": "Jira site URL",
        "required": True,
        "phase": "credentials",
        "env_var": "JIRA_BASE_URL",
        "check": lambda: bool(_env("JIRA_BASE_URL") and "atlassian.net" in _env("JIRA_BASE_URL")),
        "instructions": (
            "In `.env` set:\n"
            "`JIRA_BASE_URL=https://abcfinancial.atlassian.net`\n"
            "(no trailing slash — use your org's Atlassian cloud URL.)"
        ),
        "where": "Your Jira home page URL in the browser (without `/browse/...`).",
        "example": "JIRA_BASE_URL=https://abcfinancial.atlassian.net",
    },
    {
        "id": "jira_email",
        "title": "Jira account email",
        "required": True,
        "phase": "credentials",
        "env_var": "JIRA_EMAIL",
        "check": lambda: bool(_env("JIRA_EMAIL") and "@" in _env("JIRA_EMAIL")),
        "instructions": (
            "In `.env` set:\n"
            "`JIRA_EMAIL=you@abcfitness.com`\n"
            "Must match the Atlassian account that owns the API token."
        ),
        "where": "Same email you use to log in to Jira / Atlassian.",
        "example": "JIRA_EMAIL=you@abcfitness.com",
    },
    {
        "id": "jira_api_token",
        "title": "Jira API token",
        "required": True,
        "phase": "credentials",
        "env_var": "JIRA_API_TOKEN",
        "check": lambda: bool(_env("JIRA_API_TOKEN") and _env("JIRA_API_TOKEN") not in {
            "",
            "your-api-token-here",
            "changeme",
        }),
        "instructions": (
            "1. Open **Atlassian API tokens**: https://id.atlassian.com/manage-profile/security/api-tokens\n"
            "2. Click **Create API token**, name it (e.g. `release-orchestrator`).\n"
            "3. Copy the token once — it is shown only once.\n"
            "4. In `.env` set: `JIRA_API_TOKEN=<paste token>`"
        ),
        "where": "https://id.atlassian.com/manage-profile/security/api-tokens",
        "example": "JIRA_API_TOKEN=ATATT3x...",
    },
    {
        "id": "team_and_projects",
        "title": "Pick Jira team + projects (PIC / AN)",
        "required": True,
        "phase": "team",
        "check": lambda: bool(_env("DEFAULT_JIRA_TEAM") and _env("DEFAULT_PROJECTS")),
        "instructions": onboarding_team_flow.format_team_pick_prompt(),
        "where": "Say in chat: use glofox | use ignite | projects pic an",
    },
    {
        "id": "team_crew",
        "title": "Confirm team crew (review + release calls)",
        "required": True,
        "phase": "team",
        "check": lambda: bool(team_crew.team_crew_status().get("crew_in_env")),
        "instructions": (
            "One-time crew for review calls, release calls, QA, and leadership.\n"
            "**Glofox:** **`use glofox`** → **`crew done`** (auto-writes `.env`).\n"
            "**Other teams:** **`crew add Name <email> to leadership|qa|squad`** → **`crew done`**.\n\n"
            "**Daily Review meeting invites (from this crew):**\n"
            "- **Required:** leadership + QA pool + in-squad ticket assignees\n"
            "- **Optional:** review + release crew (TEAM_CREW_REVIEW / TEAM_CREW_RELEASE)\n"
            "- **Never invited:** TEAM_CREW_EXCLUDE + outside-squad assignees (e.g. Standard/AN-only — Gabriel, Erasmo)\n"
            "Outside-squad tickets (Gabriel/Erasmo) are not fetched by default.\n"
            "Preview: MCP **`daily_review_attendee_policy`**."
        ),
        "where": ".env — TEAM_CREW_REVIEW, TEAM_CREW_RELEASE, TEAM_CREW_QA, TEAM_CREW_LEADERSHIP, TEAM_CREW_EXCLUDE",
    },
    {
        "id": "cursor_mcp",
        "title": "Cursor MCP server config",
        "required": True,
        "phase": "cursor",
        "check": lambda: True,  # Cannot detect from repo; user confirms manually
        "manual_confirm": True,
        "instructions": (
            "Add to **Cursor → Settings → MCP** (or project `.cursor/mcp.json`):\n"
            "```json\n"
            "{\n"
            '  "mcpServers": {\n'
            '    "release-orchestrator": {\n'
            f'      "command": "{_python_launcher()}",\n'
            '      "args": ["-m", "release_mcp"],\n'
            f'      "cwd": "{str(_PROJECT_ROOT).replace(chr(92), "/")}"\n'
            "    }\n"
            "  }\n"
            "}\n"
            "```\n"
            "Then **reload MCP** in Cursor (or restart Cursor)."
        ),
        "where": "Cursor Settings → MCP, or `.cursor/mcp.json` in the project.",
    },
    {
        "id": "slack_plugin",
        "title": "Slack Step 6 — Playwright (Glofox private channels)",
        "required": True,
        "phase": "cursor",
        "manual_confirm": True,
        "check": lambda: True,
        "instructions": (
            "**Glofox path (configured):** Step 6 uses **Playwright MCP** — not Slack MCP.\n"
            "One-time per machine: sign in to Slack web in Playwright Edge (abcfitness.com).\n"
            "At Step 6: **send slack** → agent posts to #insights-customize-squad and #customize-bi-buddies → **slack done**.\n"
            "No `SLACK_BOT_TOKEN` or api.slack.com app needed.\n"
            "Slack MCP in Cursor is optional (public channels only)."
        ),
        "where": "Playwright MCP + one-time Slack web login.",
    },
    {
        "id": "playwright_plugin",
        "title": "Enable Playwright MCP (review calls + SharePoint + Slack fallback)",
        "required": True,
        "phase": "cursor",
        "manual_confirm": True,
        "check": lambda: True,
        "instructions": (
            "In **Cursor → Settings → MCP**, enable **Playwright** (your mcp.json server is usually named `playwright`). "
            "Sign in once to M365 in the Playwright browser.\n\n"
            "**Daily Review — Teams review call (primary):**\n"
            "- Say **`schedule review call`** or run daily review live\n"
            "- Agent drives Playwright MCP → Outlook web → Teams invite\n"
            "- Say **`calendar done`** when invite is sent\n\n"
            "**Release Step 4 — SharePoint:**\n"
            "- After DOCX: **`upload sharepoint`** → upload `.docx` → **`sharepoint done`**\n\n"
            "**Slack browser fallback:** **`send slack playwright`**"
        ),
        "where": "Cursor Settings → MCP → Playwright plugin.",
    },
    {
        "id": "deploy_window",
        "title": "Deployment window (IST → CST in Jira)",
        "required": False,
        "phase": "info",
        "check": lambda: True,
        "instructions": (
            "Normal releases: **10:30–11:30 AM IST** (your team clock).\n"
            "Jira planned start/end store the **same instant in US Central (CST/CDT)**.\n"
            "SHIPIT ticket text shows **both** clocks so approvers do not close early.\n"
            "Emergency profile: **6:00–8:00 PM IST** — say **emergency deployment** at Step 5."
        ),
        "where": "Automatic — no config needed.",
    },
    {
        "id": "production_readiness",
        "title": "Run production readiness check",
        "required": False,
        "phase": "verify",
        "check": lambda: True,
        "instructions": (
            "Say **production ready** (or call `production_readiness()`).\n"
            "Finish launch: `python release_mcp/scripts/complete_launch.py` (or mark sign-offs in MCP):\n"
            "- **shipit confirmed** after SHIPIT dry-run\n"
            "- **slack confirmed** after Step 6 Slack MCP post\n"
            "When both are recorded → **launch complete**."
        ),
        "where": "MCP chat or platform Home → Production readiness panel.",
    },
    {
        "id": "defaults_optional",
        "title": "Optional defaults (save typing each release)",
        "required": False,
        "phase": "optional",
        "check": lambda: bool(_env("DEFAULT_SELECTION_MODE")),
        "instructions": (
            "Optional line in `.env`:\n"
            "`DEFAULT_SELECTION_MODE=status`"
        ),
        "where": ".env.example comments",
    },
)


RELEASE_ROADMAP = [
    "Step 1 — Fetch review-ready tickets (PIC + AN)",
    "Step 2 — Lock selection & exclusions",
    "Step 3 — Generate release notes (Word DOCX) + upload to SharePoint",
    "Step 4 — Confirm SharePoint document link",
    "Step 5 — Create SHIPIT service ticket + Slack announce (10:30–11:30 AM IST → CST in Jira)",
    "Step 6 — Confirm Slack posted (squad + buddies)",
    "Step 7 — Deploy comments + Done transitions",
    "Step 8 — Mark fix version released (optional)",
]


def assess_setup(
    *,
    mcp_confirmed: bool = False,
    from_mcp: bool = True,
    team_inputs: dict[str, Any] | None = None,
    track: str | None = None,
    interactive: bool = False,
) -> dict[str, Any]:
    """Evaluate unified setup checklist (release, daily review, or both)."""
    from release_mcp import unified_onboarding as uo

    result = uo.assess_unified_setup(
        track=track,
        mcp_confirmed=mcp_confirmed,
        from_mcp=from_mcp,
        team_inputs=team_inputs,
        require_track=interactive,
    )
    result["release_roadmap"] = RELEASE_ROADMAP
    return result


def format_setup_guide(assessment: dict[str, Any], *, compact: bool = False) -> str:
    """Plain-English setup message for say_to_user."""
    from release_mcp import unified_onboarding as uo

    items = assessment.get("items") or []
    next_item = assessment.get("next_setup_step")
    lines: list[str] = []

    if assessment.get("needs_track_picker"):
        return uo.format_track_picker()

    if assessment.get("fully_ready"):
        return uo.completion_message(assessment.get("onboarding_track"))

    track_label = assessment.get("track_label") or uo.track_label(assessment.get("onboarding_track"))
    lines.append("**Welcome — first-time setup**")
    if assessment.get("onboarding_track"):
        lines.append(f"*Path:* **{track_label}**")
        lines.append("")
    lines.append("")
    lines.append("This repo needs a one-time `.env` + Cursor MCP config before releases work.")
    lines.append("")

    # Progress summary
    done_count = sum(1 for i in items if i.get("done"))
    lines.append(f"**Progress:** {done_count}/{len(items)} setup steps done")
    lines.append("")

    for item in items:
        mark = "✅" if item.get("done") else "⬜"
        req = " *(required)*" if item.get("required") else " *(optional)*"
        lines.append(f"{mark} **{item['title']}**{req}")

    lines.append("")

    if next_item:
        lines.append(f"**Do this next — {next_item['title']}**")
        if next_item.get("where"):
            lines.append(f"*Where:* {next_item['where']}")
        lines.append("")
        lines.append(next_item.get("instructions") or "")
        if next_item.get("example"):
            lines.append("")
            lines.append(f"*Example:* `{next_item['example']}`")

    lines.append("")
    lines.append("**After setup:** Reload MCP in Cursor, then say **start** to pick your first action.")
    lines.append("")
    lines.append(
        "*Slack:* Step 6 uses **Cursor Slack MCP** — no bot token needed. Say **skip slack** to skip announce."
    )

    if compact and next_item:
        return (
            f"Setup: {done_count}/{len(items)} done. "
            f"Next: **{next_item['title']}**. Say **setup status** anytime."
        )

    return "\n".join(lines)


def format_interactive_onboarding_prompt(
    assessment: dict[str, Any],
    *,
    show_intro: bool = False,
) -> str:
    """One setup item at a time for welcome-onboard flow."""
    from release_mcp import unified_onboarding as uo

    if assessment.get("needs_track_picker"):
        return uo.format_track_picker()

    items = assessment.get("items") or []
    done_count = sum(1 for i in items if i.get("done"))
    total = len(items)
    lines: list[str] = []

    if assessment.get("fully_ready"):
        return uo.completion_message(assessment.get("onboarding_track"))

    next_item = assessment.get("next_setup_step")
    if not next_item:
        return format_setup_guide(assessment)

    track_label = assessment.get("track_label") or uo.track_label(assessment.get("onboarding_track"))
    if track_label and track_label != "Not selected":
        lines.append(f"*Setup path:* **{track_label}**")
        lines.append("")

    if show_intro or done_count == 0:
        lines.append(onboarding_guide.format_welcome_onboard_intro(done_count=done_count, total=total))
        lines.append("")
        lines.append("---")
        lines.append("")

    # Team + crew steps get dedicated prompts when reached
    next_id = str((next_item or {}).get("id") or "")
    if next_id in {"team_and_projects", "team_crew"}:
        team_inputs = assessment.get("team_inputs") or {}
        if isinstance(team_inputs, dict):
            lines.append(onboarding_team_flow.format_team_onboard_step(team_inputs))
            lines.append("")
            lines.append("*Never paste tokens in chat — crew emails go in `.env` only.*")
            return "\n".join(lines)

    req = " *(required)*" if next_item.get("required") else " *(optional — say done to skip)*"
    lines.extend([
        f"**Setup {done_count + 1}/{total} — {next_item['title']}**{req}",
    ])
    if next_item.get("where"):
        lines.append(f"*{next_item['where']}*")
    lines.append("")
    instructions = str(next_item.get("instructions") or "").strip()
    if instructions:
        # Keep first actionable block only — avoids wall-of-text during onboard.
        short = instructions.split("```")[0].strip()
        short_lines = [ln for ln in short.splitlines() if ln.strip()][:6]
        lines.extend(short_lines)
    if next_item.get("example"):
        lines.append("")
        lines.append(f"Example: `{next_item['example']}`")
    elif next_item.get("env_var"):
        lines.append("")
        lines.append(f"`.env` → `{next_item['env_var']}=...`")

    if next_id.startswith("jira_") or next_id in {"team_and_projects", "env_file"}:
        from release_mcp import env_onboarding as env_ob

        lines.append("")
        lines.append(env_ob.format_env_checklist(compact=True))
        lines.append("")
        lines.append("*Say values in plain English — agent writes `.env` for you.*")

    lines.append("")
    lines.append(step_ux.compact_onboarding_footer(manual_confirm=bool(next_item.get("manual_confirm"))))
    lines.append("")
    lines.append("*Secrets in `.env` only — never in chat.* · **help** · **crew status**")
    return "\n".join(lines)


def full_onboarding_guide(*, assessment: dict[str, Any] | None = None) -> dict[str, Any]:
    """Complete onboarding payload — MCP catalog, phrases, setup checklist."""
    assessment = assessment or assess_setup(from_mcp=True)
    payload = onboarding_guide.onboarding_guide_payload(assessment=assessment)
    payload["setup_checklist"] = assessment.get("items") or []
    payload["release_roadmap"] = RELEASE_ROADMAP
    payload["next_setup_step"] = assessment.get("next_setup_step")
    payload["team_crew"] = onboarding_team_flow.team_onboard_payload()
    payload["team_profiles"] = team_crew.team_crew_status()
    return payload


def format_release_next_step(step: str, *, status: str = "") -> str:
    """Short 'what's next' hint after each workflow step."""
    hints = {
        "welcome": "Say **start** to pick fetch tickets, release notes, or SHIPIT.",
        "start_menu": "Pick one: **fetch review tickets**, **create release notes**, or **create shipit**.",
        "ticket_review": "Fetched review-ready tickets — reply **yes** to lock, or **exclude PIC-1234**.",
        "ticket_list": "Release-ready list only — say **fetch review tickets** to lock for release.",
        "exclusions": "Reply **yes** to continue, or **exclude PIC-1234**.",
        "release_date_confirm": (
            "Reply **yes** to confirm the proposed date, or send **`2026.3.09.18`** to override first."
        ),
        "release_notes": "Reply **create release notes** or **yes** — generates DOCX then starts SharePoint upload.",
        "sharepoint": "Complete Playwright upload, then **sharepoint done** or paste the document URL.",
        "service_ticket": "Reply **create shipit** or **yes** — creates SHIPIT then auto-starts Slack (10:30–11:30 AM IST → CST in Jira).",
        "slack": "Complete Playwright post to squad + buddies, then **slack done**.",
        "deploy": "Reply **yes** to post deployment comments and move tickets to Done.",
        "mark_released": "Reply **yes** to mark the fix version released, or **skip**.",
        "complete": "Say **welcome** to start a new release.",
    }
    base = hints.get(step, "Reply **yes** or **next** to continue.")
    if status == "blocked":
        return "Finish setup first — say **onboarding** for the checklist."
    return f"**What's next:** {base}"


def merge_env_readiness(base: dict[str, Any]) -> dict[str, Any]:
    """Extend welcome env_readiness with full onboarding assessment."""
    from release_mcp import onboarding_store

    mcp_confirmed = base.pop("mcp_confirmed", False) in {True, "yes", "true", "done", "1"}
    from_mcp = base.pop("from_mcp", True)
    interactive = base.pop("interactive_onboarding", False) in {True, "yes", "true", "1"}
    track = base.pop("onboarding_track", None) or onboarding_store.get_track()
    team_inputs = base.pop("team_inputs", None) or base.pop("team_crew_draft", None)
    if isinstance(team_inputs, dict) and "team_crew_draft" not in team_inputs:
        team_inputs = {"team_crew_draft": team_inputs}
    assessment = assess_setup(
        mcp_confirmed=mcp_confirmed,
        from_mcp=from_mcp,
        team_inputs=team_inputs if isinstance(team_inputs, dict) else None,
        track=track,
        interactive=interactive,
    )
    merged = dict(base)
    merged["onboarding"] = assessment
    merged["ready"] = assessment["jira_ready"]
    merged["fully_ready"] = assessment["fully_ready"]
    if not assessment["jira_ready"]:
        pending = [i["title"] for i in assessment["items"] if i["required"] and not i["done"]]
        merged["missing"] = pending or base.get("missing") or []
    else:
        merged["missing"] = []
    merged["setup_guide"] = format_setup_guide(assessment)
    return merged
