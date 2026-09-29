"""First-time onboarding — MCP catalog, phrase cheat sheet, quick-start path.

New colleagues say **welcome onboard** once; this module drives zero-memorization
setup (~15 min) and documents every Cursor MCP + chat phrase for the release flow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from release_mcp.phrase_catalog import ONBOARDING_WORKFLOW_PHRASES

from orchestrator.paths import REPO_ROOT as _PROJECT_ROOT

ESTIMATED_SETUP_MINUTES = "15-20"

# Every MCP involved in the Release Orchestrator E2E path.
MCP_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "release-orchestrator",
        "name": "Release Orchestrator",
        "required": True,
        "role": "Main guided release workflow (PIC + AN → DOCX → SHIPIT → Slack → deploy)",
        "cursor_setup": (
            "Cursor → Settings → MCP → add server with your repo venv:\n"
            "command: .venv/Scripts/python.exe · args: [\"-m\", \"release_mcp\"] · cwd: repo root"
        ),
        "user_phrases": ["welcome", "welcome onboard", "start", "yes", "next", "help"],
        "mcp_tools": [
            "release_orchestrator",
            "slack_preview",
            "slack_mcp_e2e_handoff",
            "slack_reference",
            "production_readiness",
        ],
    },
    {
        "id": "playwright",
        "name": "Cursor Playwright MCP",
        "required": True,
        "role": (
            "Glofox primary path — Step 4 SharePoint upload, Step 6 Slack (private channels), "
            "Daily Review review-call calendar (Outlook web). One-time M365 + Slack web login."
        ),
        "cursor_setup": "Cursor → Settings → MCP → enable **Playwright** (mcp.json key: playwright)",
        "user_phrases": [
            "upload sharepoint",
            "sharepoint done",
            "send slack",
            "send slack playwright",
            "schedule review call",
            "calendar done",
        ],
        "mcp_tools": ["browser_navigate", "browser_run_code_unsafe", "browser_snapshot"],
        "notes": "Required for Glofox private Slack channels — Slack MCP alone cannot see them.",
        "verify": "Say playwright confirmed after one-time sign-in, or run browser_navigate to Slack.",
    },
    {
        "id": "slack",
        "name": "Cursor Slack plugin (optional for Glofox)",
        "required": False,
        "role": "Optional — public channels only. Glofox Step 6 uses Playwright, not Slack MCP.",
        "cursor_setup": "Cursor → Settings → MCP → enable **Slack** plugin (ABC Fitness workspace)",
        "user_phrases": ["send slack mcp"],
        "mcp_tools": ["slack_send_message", "slack_read_channel", "slack_search_users"],
        "notes": "Not required when browser_automation.slack.prefer_playwright is true (default for Glofox).",
    },
    {
        "id": "atlassian",
        "name": "Cursor Atlassian plugin (optional)",
        "required": False,
        "role": "Optional — browse Jira in chat; Release Orchestrator uses .env Jira token for writes",
        "cursor_setup": "Cursor → Settings → MCP → enable **Atlassian** if you want Jira in chat",
        "user_phrases": [],
        "mcp_tools": ["getJiraIssue", "searchJiraIssuesUsingJql"],
        "notes": "Jira API token in .env is still required for SHIPIT create and deploy.",
    },
    {
        "id": "teams",
        "name": "Microsoft Teams MCP",
        "required": True,
        "role": "Daily review — post summary to group chat; organizer alerts on schedule failure",
        "cursor_setup": "Add **teams** stdio server (see daily_review_mcp_config). First use: **teams_login**.",
        "user_phrases": ["teams_login", "teams done"],
        "mcp_tools": ["teams_login", "teams_send_message"],
        "notes": "Sibling teams-mcp project or bundled bridge under orchestrator/zones/platform/ops/daily_review/.",
    },
    {
        "id": "daily-review",
        "name": "Daily Review (same release-orchestrator MCP)",
        "required": False,
        "role": "6 PM PIC/AN ticket review — schedule Teams meeting, post summary, batch calendar",
        "cursor_setup": (
            "Same **release-orchestrator** server — no second MCP. "
            "Run daily_review_setup(install=true), then --outlook-login once."
        ),
        "user_phrases": [
            "daily review welcome",
            "daily review setup",
            "daily review preflight",
            "daily review live",
            "outlook login",
            "schedule daily review",
            "schedule daily review for 2 weeks",
        ],
        "mcp_tools": [
            "daily_review_orchestrator",
            "daily_review_setup",
            "daily_review_preflight",
            "daily_review_attendee_policy",
            "daily_review_run_dry",
            "daily_review_run_live",
            "daily_review_outlook_login",
            "daily_review_schedule_batch",
            "daily_review_calendar_playwright_handoff",
        ],
        "notes": (
            "Calendar primary: embedded Playwright → Outlook web. "
            "Fallback: Playwright MCP (daily review calendar playwright). "
            "Meeting invites: TEAM_CREW_* from welcome onboard — required = leadership + QA + in-squad assignees; "
            "optional = review/release crew; skip outside-squad + TEAM_CREW_EXCLUDE. "
            "SharePoint/Slack browser paths use Playwright plugin on release flow."
        ),
    },
)

QUICK_START: tuple[str, ...] = (
    "Read **`orchestrator/zones/knowledge/guides/GUIDE.md`** (or say **guide** in chat)",
    "Clone repo → venv → `pip install -r orchestrator/zones/config/deps/requirements-mcp.txt` → `pip install -e .`",
    "Copy `.env.example` → `.env` → JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN",
    "Cursor MCP: **release-orchestrator** → `python -m release_mcp` (see `.cursor/mcp.json`)",
    "Enable **Playwright** plugin → one-time M365 + Slack sign-in → **playwright confirmed**",
    "Say **welcome onboard** → **use glofox** → **crew done**",
    "Daily releases: **`week release`** — full steps in **`orchestrator/zones/knowledge/guides/GUIDE.md`**",
)

WORKFLOW_PHRASES = ONBOARDING_WORKFLOW_PHRASES

SLACK_REFERENCE_REMINDER = (
    "Step 6 messages match **SHIPIT-17191** reference: "
    "squad CC = Sushma, Sai Anirudh, Zeke, Eoin; buddies CC = Sushma only. "
    "Say **slack_reference** MCP tool to see exact copy."
)


def mcp_catalog_payload() -> list[dict[str, Any]]:
    return [dict(item) for item in MCP_CATALOG]


def workflow_phrases_payload() -> dict[str, Any]:
    return dict(WORKFLOW_PHRASES)


def format_welcome_onboard_intro(*, done_count: int = 0, total: int = 0) -> str:
    """Opening message for welcome onboard — sets expectations before step 1."""
    mcp_required = [m["name"] for m in MCP_CATALOG if m.get("required")]
    lines = [
        "**Welcome onboard — Release Orchestrator**",
        "",
        f"One-time setup takes about **{ESTIMATED_SETUP_MINUTES} minutes**. "
        "After that, daily releases are mostly **yes / send slack / done** — no step memorization.",
        "",
        "**You will enable these MCPs in Cursor:**",
    ]
    for name in mcp_required:
        lines.append(f"- **{name}** *(required)*")
    lines.append("- **Slack plugin** *(optional for Glofox — Step 6 uses Playwright)*")
    lines.append("- **Atlassian** *(optional — Jira browse in chat; .env token still required)*")
    lines.append("")
    lines.append(
        "Everything in one doc: **`orchestrator/zones/knowledge/guides/GUIDE.md`** (say **guide** in chat)"
    )
    lines.append("")
    lines.append("**Quick path:**")
    for idx, step in enumerate(QUICK_START, start=1):
        lines.append(f"{idx}. {step}")
    lines.append("")
    lines.append("**During setup:** complete one checklist item, then say **done** or **next**.")
    lines.append("**Never paste API tokens in chat** — secrets go only in your local `.env`.")
    lines.append("")
    lines.append(
        "**After setup:** say **week release** (see **`orchestrator/zones/knowledge/guides/GUIDE.md`**)."
    )
    lines.append("Anytime: **help** (phrase cheat sheet) · **production ready** (readiness check).")
    if total:
        lines.append("")
        lines.append(f"*Setup progress: {done_count}/{total} steps complete.*")
    return "\n".join(lines)


def format_phrase_cheat_sheet(*, compact: bool = False) -> str:
    """All user phrases by workflow step — for help and onboarding complete."""
    if compact:
        bits = []
        for key, block in WORKFLOW_PHRASES.items():
            phrases = ", ".join(f"**{p}**" for p in block.get("phrases") or [])
            bits.append(f"{block.get('title')}: {phrases}")
        return " · ".join(bits)

    lines = [
        "**Release Orchestrator — phrase cheat sheet**",
        "",
        "Say these in chat; the agent handles MCP calls. You do not call tools yourself.",
        "",
    ]
    for block in WORKFLOW_PHRASES.values():
        lines.append(f"**{block.get('title')}**")
        for phrase in block.get("phrases") or []:
            lines.append(f"- `{phrase}`")
        agent = str(block.get("agent_does") or "").strip()
        if agent:
            lines.append(f"  *Agent:* {agent}")
        lines.append("")

    lines.append(SLACK_REFERENCE_REMINDER)
    lines.append("")
    lines.append("**MCP servers (Cursor Settings → MCP):**")
    for mcp in MCP_CATALOG:
        req = "required" if mcp.get("required") else "optional"
        lines.append(f"- **{mcp['name']}** ({req}) — {mcp.get('role', '')}")
    return "\n".join(lines)


def format_help_guide(assessment: dict[str, Any] | None = None) -> str:
    """Full help text for `help` phrase."""
    assessment = assessment or {}
    ready = assessment.get("fully_ready")
    lines = [format_phrase_cheat_sheet()]
    lines.append("")
    if ready:
        lines.append(
            "**Status:** Setup complete — say **week release** or **fetch review tickets** "
            "(see **`orchestrator/zones/knowledge/guides/GUIDE.md`**)."
        )
    else:
        lines.append("**Status:** Setup incomplete. Say **welcome onboard** to continue setup.")
    lines.append("")
    lines.append("**8-step release roadmap:**")
    from release_mcp.onboarding import RELEASE_ROADMAP

    for step in RELEASE_ROADMAP:
        lines.append(f"- {step}")
    return "\n".join(lines)


def onboarding_guide_payload(*, assessment: dict[str, Any] | None = None) -> dict[str, Any]:
    """Structured onboarding guide for MCP tool and welcome responses."""
    assessment = assessment or {}
    items = assessment.get("items") or []
    done_count = sum(1 for i in items if i.get("done"))
    total = len(items)
    return {
        "estimated_setup_minutes": ESTIMATED_SETUP_MINUTES,
        "quick_start": list(QUICK_START),
        "mcp_catalog": mcp_catalog_payload(),
        "workflow_phrases": workflow_phrases_payload(),
        "slack_reference_reminder": SLACK_REFERENCE_REMINDER,
        "setup_progress": {"done": done_count, "total": total, "fully_ready": bool(assessment.get("fully_ready"))},
        "intro": format_welcome_onboard_intro(done_count=done_count, total=total),
        "phrase_cheat_sheet": format_phrase_cheat_sheet(),
        "help": format_help_guide(assessment),
        "project_root": str(_PROJECT_ROOT),
        "first_message_suggestion": "welcome onboard",
        "guide_doc": "orchestrator/zones/knowledge/guides/GUIDE.md",
        "onboarding_skill": "orchestrator/zones/knowledge/skills/release-orchestrator-onboarding/SKILL.md",
    }


__all__ = [
    "ESTIMATED_SETUP_MINUTES",
    "MCP_CATALOG",
    "QUICK_START",
    "WORKFLOW_PHRASES",
    "format_help_guide",
    "format_phrase_cheat_sheet",
    "format_welcome_onboard_intro",
    "mcp_catalog_payload",
    "onboarding_guide_payload",
    "workflow_phrases_payload",
]
