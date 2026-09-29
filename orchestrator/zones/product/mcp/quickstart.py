"""Operator guide summary — mirrors orchestrator/zones/knowledge/guides/GUIDE.md."""

from __future__ import annotations

from typing import Any

from orchestrator.paths import REPO_ROOT

DOCS = {
    "guide": "orchestrator/zones/knowledge/guides/GUIDE.md",
    "runbook": "orchestrator/zones/knowledge/guides/RUNBOOK.md",
    "state": "orchestrator/zones/knowledge/guides/STATE.md",
    "layout": "REPO_LAYOUT.md",
}

INSTALL_STEPS = (
    "git clone <repo> && cd jira-release-tool",
    "python -m venv .venv",
    ".venv\\Scripts\\activate  (Windows)  ·  source .venv/bin/activate  (Mac/Linux)",
    "pip install -r orchestrator/zones/config/deps/requirements-mcp.txt && pip install -e .",
    "copy .env.example → .env  →  JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN",
)

MCP_JSON = {
    "mcpServers": {
        "release-orchestrator": {
            "command": "${workspaceFolder}/.venv/Scripts/python.exe",
            "args": ["-m", "release_mcp"],
            "cwd": "${workspaceFolder}",
        }
    }
}

SETUP_PHRASES = (
    "welcome onboard",
    "setup status",
    "production ready",
)

DAILY_RELEASE_PHRASES = (
    ("week release", "Start full daily flow (same as full release)"),
    ("yes", "Confirm current step"),
    ("create release notes", "Generate DOCX + SharePoint handoff"),
    ("sharepoint done", "Paste SharePoint URL after upload"),
    ("create shipit", "Create SHIPIT change ticket"),
    ("send slack", "Post to both Slack channels"),
    ("slack done", "Continue after Slack posted"),
)

OPTIONAL_PHRASES = (
    ("fetch review tickets", "Fetch + lock review-ready tickets"),
    ("fetch release tickets", "List release-ready tickets (no lock)"),
    ("daily review welcome", "On-demand Daily Review setup + run"),
    ("help", "Phrase cheat sheet"),
)


def quickstart_payload() -> dict[str, Any]:
    """Structured quickstart for MCP tool and guided chat."""
    return {
        "repo_root": str(REPO_ROOT),
        "docs": dict(DOCS),
        "install_steps": list(INSTALL_STEPS),
        "mcp_json": MCP_JSON,
        "cursor_plugins": ["Playwright (SharePoint + Slack)", "Slack (optional primary for Step 6)"],
        "setup_phrases": list(SETUP_PHRASES),
        "daily_release": [{"phrase": p, "does": d} for p, d in DAILY_RELEASE_PHRASES],
        "optional_phrases": [{"phrase": p, "does": d} for p, d in OPTIONAL_PHRASES],
        "golden_path": "Jira → PR gate → DOCX → SharePoint receipt → SHIPIT → both Slack channels",
        "runtime_state": ".state/ (wizard sessions, sign-offs)",
        "config_files": {
            "secrets": ".env",
            "team": "orchestrator/config/orchestrator/zones/config/profiles/workspace.yaml",
            "mcp": ".cursor/mcp.json",
            "daily_review": "orchestrator/zones/product/agents/review/agent.yaml",
        },
        "first_time": "Say **welcome onboard** once in Cursor chat",
        "every_day": "Say **week release** → confirm each step",
        "forgot_phrases": "Say **guide** or **help**",
        "migrate_legacy_state": "python orchestrator/zones/platform/ops/migrate_state.py --apply",
    }


def quickstart_markdown() -> str:
    """Plain-text quickstart for chat responses."""
    p = quickstart_payload()
    lines = [
        "# Release Orchestrator — Guide (summary)",
        "",
        f"Full doc: **`{DOCS['guide']}`** — say **guide** in chat anytime.",
        "",
        f"**Golden path (every business day):** {p['golden_path']}",
        "",
        "## 1. Install (once)",
    ]
    for idx, step in enumerate(p["install_steps"], 1):
        lines.append(f"{idx}. `{step}`")
    lines.extend(
        [
            "",
            "## 2. Cursor MCP (once)",
            "Project file: `.cursor/mcp.json` — server **`release-orchestrator`**, args `[-m`, `release_mcp]`.",
            "Enable **Playwright** plugin → sign in to M365 + Slack once.",
            "",
            "## 3. Setup in chat (once)",
        ]
    )
    for phrase in p["setup_phrases"]:
        lines.append(f"- **`{phrase}`**")
    lines.extend(["", "## 4. Daily release", ""])
    for item in p["daily_release"]:
        lines.append(f"- **`{item['phrase']}`** — {item['does']}")
    lines.extend(["", "## Optional", ""])
    for item in p["optional_phrases"]:
        lines.append(f"- **`{item['phrase']}`** — {item['does']}")
    lines.extend(
        [
            "",
            "## Config you edit",
            "- **`.env`** — Jira secrets only",
            "- **`orchestrator/config/orchestrator/zones/config/profiles/workspace.yaml`** — team, channels, SHIPIT",
            "- **`.state/`** — runtime (gitignored) — see orchestrator/zones/knowledge/guides/STATE.md",
            "",
            f"Full doc: **`{DOCS['guide']}`**",
        ]
    )
    return "\n".join(lines)
