"""Compact user-facing copy — one action + one phrase per release/onboard step."""

from __future__ import annotations

from typing import Any

# Ordered release steps (8 user-visible steps; release_date_confirm is 2b)
RELEASE_PROGRESS: tuple[tuple[str, str, str], ...] = (
    ("ticket_review", "1", "Lock review tickets"),
    ("exclusions", "2", "Confirm exclusions"),
    ("release_date_confirm", "2b", "Confirm release date"),
    ("release_notes", "3", "Release notes + SharePoint"),
    ("sharepoint", "4", "SharePoint upload"),
    ("service_ticket", "5", "SHIPIT + Slack"),
    ("slack", "6", "Slack confirm"),
    ("deploy", "7", "Deploy comments"),
    ("mark_released", "8", "Mark released"),
)

_STEP_INDEX: dict[str, tuple[str, str]] = {
    key: (num, title) for key, num, title in RELEASE_PROGRESS
}

STEP_UX: dict[str, dict[str, Any]] = {
    "welcome": {
        "say": ["start", "full release"],
        "hint": "Say **start** to pick a path, or **full release** to run the standard PIC + AN flow.",
    },
    "start_menu": {
        "say": ["yes", "full release"],
        "hint": "Most releases: say **yes** or **full release**. Or pick release notes / SHIPIT only.",
    },
    "onboarding": {
        "say": ["done", "next"],
        "hint": "Finish the step in `.env` or Cursor, then say **done**.",
    },
    "ticket_review": {
        "say": ["yes", "exclude PIC-1234"],
        "hint": "Review-ready fetch — **yes** = lock · **exclude AN-1234** = drop · **fetch release tickets** = list-only elsewhere.",
    },
    "ticket_list": {
        "say": ["fetch review tickets", "schedule review call"],
        "hint": "List only — **fetch review tickets** to lock · **schedule review call** for calendar invite.",
    },
    "exclusions": {
        "say": ["yes", "exclude PIC-1234"],
        "hint": "**yes** to continue · **exclude** a key if something should not ship.",
    },
    "release_date_confirm": {
        "say": ["yes", "2026.3.09.18"],
        "hint": "**yes** to accept the proposed date · or paste **YYYY.M.DD.DD** to override.",
    },
    "release_notes": {
        "say": ["create release notes", "yes"],
        "hint": "**create release notes** or **yes** — generates DOCX then uploads to SharePoint · **include PIC-1234** to add a ticket.",
    },
    "sharepoint": {
        "say": ["sharepoint done", "upload sharepoint"],
        "hint": "Agent uploads via Playwright — then **sharepoint done** (or paste the doc URL).",
    },
    "service_ticket": {
        "say": ["create shipit", "yes"],
        "hint": "**create shipit** or **yes** — creates SHIPIT then auto-starts Slack announce · **emergency deployment** for evening window.",
    },
    "slack": {
        "say": ["slack done", "send slack"],
        "hint": "Agent posts via Playwright — then **slack done** when both channels show the message.",
    },
    "deploy": {
        "say": ["yes", "yes deploy"],
        "hint": "**yes** to post deployment comments and move tickets to Done.",
    },
    "mark_released": {
        "say": ["yes", "skip"],
        "hint": "**yes** to mark fix version released · **skip** to finish without it.",
    },
    "complete": {
        "say": ["welcome", "full release"],
        "hint": "Release finished. Say **welcome** for a new run.",
    },
}


def progress_header(step: str) -> str:
    """Short progress line, e.g. Step 3/8 — Release notes DOCX."""
    meta = _STEP_INDEX.get(step)
    if not meta:
        if step in {"welcome", "start_menu", "onboarding"}:
            return ""
        return f"**{step.replace('_', ' ').title()}**"
    num, title = meta
    total = len(RELEASE_PROGRESS)
    display_num = num if num != "2b" else "2"
    return f"**Step {display_num}/{total} — {title}**"


def primary_phrases(step: str, limit: int = 3) -> list[str]:
    ux = STEP_UX.get(step) or {}
    phrases = list(ux.get("say") or [])
    return phrases[:limit]


def step_hint(step: str) -> str:
    ux = STEP_UX.get(step) or {}
    return str(ux.get("hint") or "").strip()


def wrap_user_message(
    step: str,
    body: str,
    *,
    status: str = "",
    include_progress: bool = True,
) -> str:
    """Prepend progress + append one-line hint; keep body in the middle."""
    parts: list[str] = []
    header = progress_header(step) if include_progress and step not in {"onboarding", "welcome"} else ""
    if header:
        parts.append(header)
        parts.append("")
    core = (body or "").strip()
    if core:
        parts.append(core)
    hint = step_hint(step)
    if hint and status in {"", "ok", "awaiting_confirmation", "needs_input"}:
        parts.append("")
        parts.append(hint)
    say = primary_phrases(step, limit=2)
    if say:
        parts.append("")
        parts.append("**Say:** " + " · ".join(f"`{p}`" for p in say))
    return "\n".join(parts).strip()


def compact_onboarding_footer(*, manual_confirm: bool = False) -> str:
    if manual_confirm:
        return "When done, say **`done`** or **`mcp configured`**."
    return "Update `.env`, reload MCP if needed, then say **`done`**."
