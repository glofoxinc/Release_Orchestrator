# Release Orchestrator — complete guide

**One document.** Install once → **`welcome onboard`** once → **`week release`** every business day.

**In Cursor chat:** say **`guide`** or **`quickstart`** for this page · **`help`** for phrase cheat sheet

---

## Contents

1. [Three phrases](#three-phrases)
2. [Pick your path](#pick-your-path)
3. [Install & MCP](#install--mcp)
4. [First-time setup](#first-time-setup)
5. [Daily release](#daily-release)
6. [Daily Review (optional)](#daily-review-optional)
7. [Config & repo](#config--repo)
8. [Troubleshooting](#troubleshooting)
9. [More (only if needed)](#more-only-if-needed)

---

## Three phrases

| When | Say |
|------|-----|
| First time on this machine | **`welcome onboard`** |
| Every business day | **`week release`** |
| Forgot what to say | **`guide`** or **`help`** |

**Golden path:** Jira → PR gate → DOCX → SharePoint receipt → SHIPIT → both Slack channels

---

## Pick your path

| Path | Who | What |
|------|-----|------|
| **A — Daily release** | Most operators | Sections 3–5 below · chat only |
| **B — + Daily Review** | Pilot users | Path A + **`daily review welcome`** when you want a run (on demand, not scheduled) |
| **C — Streamlit UI** | Optional | `pip install streamlit` → `streamlit run orchestrator/entry/app.py` — same engine, click-through UI |

---

## Install & MCP

### Install (5 min)

```powershell
git clone <repo-url> jira-release-tool
cd jira-release-tool
python -m venv .venv
.venv\Scripts\activate
pip install -r orchestrator/zones/config/deps/requirements-mcp.txt
pip install -e .
copy .env.example .env
```

Or: `.\orchestrator\zones\platform\ops\setup_e2e.ps1`

### `.env` (secrets — never commit)

```env
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your-token
```

Optional: `GITHUB_TOKEN` (PR merge gate on release fetch)

### Cursor MCP

Project **`.cursor/mcp.json`** (preferred over user-global):

```json
{
  "mcpServers": {
    "release-orchestrator": {
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "release_mcp"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

Mac/Linux: `.venv/bin/python` in `command`.

**Enable Playwright plugin** in Cursor → Settings → MCP. Sign in to M365 + Slack once in the browser.

Legacy wizard sessions (after upgrade):

```powershell
python orchestrator/zones/platform/ops/migrate_state.py --apply
```

---

## First-time setup

Say **`welcome onboard`** once — linear wizard, one step at a time. After each step: **`continue`**.

- **Default path:** daily release (`release only`) — say **`both`** to add Daily Review
- **Resume anytime:** **`setup status`** or **`continue`**
- **Auto-probes:** MCP JSON, Jira `.env`, crew — green checks without typing `mcp configured` when probes pass
- **Manual fallback:** **`mcp configured`**, **`playwright confirmed`**, **`teams done`** if a probe cannot run headless
- **MCP config:** written to **`.cursor/mcp.json`** in this repo (project-first)

### MCP checklist

| MCP | Required | Verify |
|-----|----------|--------|
| **release-orchestrator** | Always | `setup status` or green in Cursor MCP list |
| **Playwright** | Glofox release + calendar | Sign in via browser → **`playwright confirmed`** |
| **teams** | Daily Review only | **`teams_login`** → **`teams done`** |
| **Slack plugin** | Optional | Glofox Step 6 uses Playwright for private channels |
| **Jira `.env`** | Always | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` |

Paste MCP blocks: tool **`daily_review_mcp_config`** or ask agent in chat.

### Setup steps (chat)

| Step | Say |
|------|-----|
| Team | **`use glofox`** |
| Crew | **`crew done`** |
| MCP added | **`mcp configured`** |
| Browser auth | **`playwright confirmed`** |
| Teams (DR only) | **`teams done`** |
| Readiness | **`production ready`** |
| Dry run | **`test shipit`** |

**Never paste API tokens in chat** — only in local `.env`.

Agent skill (for Cursor agents): `skills/release-orchestrator-onboarding/SKILL.md`

---

## Daily release

### Fast path

Say **`week release`** or **`full release`** → then **`yes`** at each step.

Nothing auto-posts to Slack or SharePoint — you confirm **`sharepoint done`** and **`send slack`**.

### Step-by-step

| # | Say | What happens |
|---|-----|--------------|
| 1 | **`fetch review tickets`** | PIC + AN fetch + **GitHub PR gate** (merged PR required) |
| 2 | **`yes`** | Lock ticket list |
| 3 | **`create release notes`** | Word DOCX → SharePoint upload handoff |
| 4 | **`sharepoint done`** + URL | Save link + receipt (idempotent on retry) |
| 5 | **`create shipit`** | SHIPIT ticket (blocked if PR gate fails) |
| 6 | **`send slack`** | Both channels (see below) |
| 7 | **`slack done`** | Continue |
| 8 | Deploy | Paste deployment info or use Streamlit Deployer |

**Shortcuts:** **`fetch release tickets`** (list only, no lock) · **`skip slack`** · **`help`**

### Jira rules

| When | Ticket needs |
|------|--------------|
| Review fetch | Comment: **ready for review** |
| Release / notes | Comment: **ready for release** |
| Release fetch | GitHub PR **merged** |

Status alone is not enough.

### Slack (when you say `send slack`)

Channels: **`#insights-customize-squad`** + **`#customize-bi-buddies`**

Includes SharePoint download + folder links, SHIPIT link. Squad CC: Sushma, Sai Anirudh, Zeke, Eoin · Buddies CC: Sushma only.

### Quick fixes

| Problem | Fix |
|---------|-----|
| Ticket missing | Add **ready for review/release** comment on Jira |
| PR blocked | Merge on GitHub → **`fetch release tickets`** |
| SharePoint | **`upload sharepoint`** → upload → **`sharepoint done`** + URL |
| Slack failed | **`send slack`** (Playwright) or manual → **`slack done`** |
| Start over | **`welcome`** |

---

## Daily Review (optional)

**On demand only** — nothing runs at 6 PM or on a timer.

| Say | Purpose |
|-----|---------|
| **`daily review welcome`** | Guided setup + dry run + live (you confirm each step) |
| **`schedule review call`** | Calendar handoff only (Playwright Outlook) |

Setup once: Teams MCP + `orchestrator/zones/platform/ops/daily_review` npm deps. Edit `orchestrator/zones/product/agents/review/agent.yaml` — keep **`enabled: false`** until pilot sign-off.

Pilot checklist: `.\orchestrator\zones\platform\ops\daily_review\pilot_signoff.ps1`

---

## Config & repo

### Files you edit

| File | Purpose |
|------|---------|
| `.env` | Secrets (Jira, GitHub) |
| `orchestrator/zones/config/profiles/workspace.yaml` | Team, Slack channels, SHIPIT |
| `.cursor/mcp.json` | MCP servers for this repo |
| `.state/` | Runtime sessions, sign-offs (gitignored) |
| `orchestrator/zones/product/agents/review/agent.yaml` | Daily Review (optional) |

### Naming

| Name | What |
|------|------|
| **Release Orchestrator** | Product |
| **jira-release-tool** | This repo |
| **`release_mcp`** | MCP module — `python -m release_mcp` |

Folder map: [REPO_LAYOUT.md](REPO_LAYOUT.md) · State detail: [STATE.md](STATE.md) · Push safety: [PUSH_SAFETY.md](PUSH_SAFETY.md)

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Invalid `mcp.json` | Fix JSON syntax; reload Cursor MCP |
| No tickets | Check `.env`; **`use glofox`** |
| Slack `channel_not_found` | Use Playwright path — **`send slack`** |
| SharePoint fails | Sign in M365 in Playwright browser |
| Teams fails | **`teams_login`** again |

Say **`help`** in chat for full phrase cheat sheet.

More: [RUNBOOK.md](./RUNBOOK.md) (undo/recovery) · [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

---

## More (only if needed)

These are **optional** deep-dives — you do not need them for daily work.

| Topic | Doc |
|-------|-----|
| Incidents / undo | [RUNBOOK.md](./RUNBOOK.md) |
| Go/no-go checks | [RELEASE_READINESS.md](./RELEASE_READINESS.md) |
| Readiness tiers | [READINESS_MODEL.md](./READINESS_MODEL.md) |
| Streamlit UI install | [SETUP.md](./SETUP.md) |
| MCP tool catalog | [MCP_GUIDED.md](./MCP_GUIDED.md) |
| Integrations | [INTEGRATIONS.md](./INTEGRATIONS.md) |
