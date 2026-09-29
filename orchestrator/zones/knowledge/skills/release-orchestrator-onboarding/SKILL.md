---
name: release-orchestrator-onboarding
description: >-
  Clone-to-ready onboarding for Release Orchestrator — verify every MCP (release-orchestrator,
  playwright, teams, optional slack/atlassian), guide .env + crew setup, one-time browser auth.
  Use when user clones repo, says welcome onboard, onboarding, setup status, mcp configured,
  or asks how to set up Cursor MCPs from scratch.
---

# Release Orchestrator — Onboarding & MCP Verification Skill

Use this skill **before** the first real release or daily review. The agent must **verify**, not assume.

Human-readable guide: **`orchestrator/zones/knowledge/guides/GUIDE.md`**

---

## When to activate

- User cloned the repo / fresh machine / new colleague
- User says: **welcome onboard**, **onboarding**, **setup status**, **mcp configured**, **help setup**
- User asks which MCPs are needed or why something failed (Slack, Teams, calendar, Jira)

---

## Agent protocol (mandatory order)

### 1. Detect path

Ask once if unclear (or infer from message):

| Path | Say |
|------|-----|
| Weekly release only | **release only** |
| Daily Review only | **daily review only** |
| Both | **both** |

Persist via chat: user’s phrase maps to `onboarding_track` in MCP state.

### 2. Single wizard entry (all setup phrases)

| User says | Route |
|-----------|-------|
| **`welcome onboard`** | `beginner_wizard` (fresh start) |
| **`onboarding`**, **`setup status`**, **`check setup`** | `beginner_wizard` (resume step) |
| **`continue`** | `beginner_wizard` (next step when probe/check passes) |

1. User says **`welcome onboard`** → call **`onboarding_wizard(message="welcome onboard")`**
2. **Default track:** daily release (`release only`) — user may say **`both`** or **`daily review only`**
3. After each step, user says **`continue`** — re-call wizard with their message
4. Auto steps (venv, pip, `.env`, **`install_mcp_config`**) run inside the wizard — agent reports ✅/❌
5. **`onboarding_verify.probe_step`** runs per step — auto-confirms MCP when probes pass (no honor-system)

### 3. Run automated checks (do not skip)

Execute in order:

1. **`release_orchestrator(message="setup status")`** — wizard progress + **`onboarding_verify.run_all_probes()`**
2. **`install_mcp_config`** or **`daily_review_mcp_config`** if MCP merge failed (writes **`.cursor/mcp.json`** in repo)
3. **`daily_review_setup(install=true)`** — if Daily Review track and npm bridge missing
4. Read **`validate_cursor_mcp_config`** output if parse errors (fix JSON before continuing)
5. **`setup_complete`** gates wizard finish — **`production ready`** is informational only (launch evidence tier)

Report a table:

| MCP / dependency | Required? | Status | Fix |
|------------------|-----------|--------|-----|
| release-orchestrator | Yes | ✅/❌ | paste JSON block |
| playwright | Yes (Glofox) | ✅/❌ | enable + sign in |
| teams | Daily Review | ✅/❌ | npm + teams_login |
| slack plugin | Optional | ✅/❌ | skip for Glofox Step 6 |
| Jira .env | Yes | ✅/❌ | user provides token |

### 3. Install what is missing (agent drives)

| Gap | Agent action |
|-----|----------------|
| No venv | Run `.\scripts\setup_e2e.ps1` (or `python -m venv .venv` + pip install) |
| No `.env` | Call **`onboarding_env`** or let user say values in plain English (`org is abcfinancial`, `email you@…`, `use glofox`) — agent writes `.env`. Token: paste in `.env` only (recommended) |
| No MCP JSON | Show blocks from `daily_review_mcp_config`; merge to **`.cursor/mcp.json`** in repo → **reload Cursor** |
| No team crew | **use glofox** → **crew done** (writes TEAM_CREW_* to `.env`) |
| Playwright not signed in | Open Slack/M365 once via Playwright MCP; user signs in → **playwright confirmed** |
| Teams not logged in | User runs **teams_login** in chat when prompted |

**Never ask user to paste secrets in chat** except when they choose to (prefer `.env` file edit).

### 4. Manual confirmations (user phrases)

After each one-time step, record via chat:

| User says | Meaning |
|-----------|---------|
| **mcp configured** | release-orchestrator + teams blocks added, MCP reloaded |
| **playwright confirmed** | M365 + Slack web login done in Playwright browser |
| **teams done** | teams_login succeeded |
| **crew done** | TEAM_CREW_* written to `.env` |

### 5. Verify ready

- **`production ready`** — automated + operator sign-offs
- First release dry-run: **`test shipit`** → **`fetch review tickets`** → Steps 1–6

---

## MCP catalog (Glofox Customize BI — default)

| ID | Required | Role | Auth (one-time per machine) |
|----|----------|------|----------------------------|
| **release-orchestrator** | Yes | Guided PIC+AN release, SHIPIT, Slack handoffs | Repo venv; Jira via `.env` |
| **playwright** | Yes | SharePoint upload, Slack Step 6 (private channels), review-call calendar | User signs in M365 + Slack in browser |
| **teams** | Daily Review | 6 PM summary chat + alerts | **teams_login** (abcfitness.com) |
| **slack** plugin | No | Public channels only; not used for Glofox Step 6 | Optional Slack OAuth in Cursor |
| **atlassian** plugin | No | Browse Jira in chat | Optional; writes still need `.env` |

Jira is **not** an MCP server — it uses **`JIRA_BASE_URL`**, **`JIRA_EMAIL`**, **`JIRA_API_TOKEN`** in `.env`.

---

## Rules for the agent

1. **Verify every MCP** in the catalog for the user’s track before saying “ready”.
2. **Auto-generate setup** — show exact `mcp.json` snippets from `daily_review_mcp_config`, not generic advice.
3. **Ask the user only for auth** they must provide (Jira API token, browser login, teams_login).
4. **Do not start Step 1 fetch** until Jira `.env` validates and required MCPs are present.
5. Point humans to **`orchestrator/zones/knowledge/guides/GUIDE.md`** for install, setup, and daily release.
6. After onboarding, hand off to **`skills/release-orchestrator-mcp/SKILL.md`** for daily releases.

---

## Troubleshooting quick map

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `channel_not_found` Slack MCP | Private Glofox channels | Use **send slack** (Playwright), not Slack MCP |
| Invalid mcp.json JSON | Syntax error in Cursor config | Fix JSON; remove duplicate `daily-review-agent` |
| No tickets fetched | Missing Jira token or team scope | Check `.env`; say **use glofox** |
| Calendar fails | Playwright not logged into Outlook | **schedule review call** → sign in → **calendar done** |
| Teams message fails | teams_login expired | **teams_login** again |

---

## Phrase E2E map (after onboarding)

| Say | E2E outcome |
|-----|-------------|
| **fetch review tickets** | Review-ready fetch + lock (Step 1) |
| **fetch release tickets** | Release-ready list only — no lock |
| **schedule review call** | Playwright → Outlook → Teams invite |
| **create release notes** | DOCX + auto SharePoint upload |
| **create shipit** | SHIPIT create + auto Slack announce |

Source of truth: `release_mcp/phrase_catalog.py` · tests: `orchestrator/zones/quality/tests/test_guided_phrase_e2e.py`

---

## Release go / no-go

Read **`orchestrator/zones/knowledge/guides/RELEASE_READINESS.md`** before first live release.

| Blocks live release | Does not block |
|--------------------|----------------|
| Missing Jira `.env` | `daily_review_mcp` unverified (release-only track) |
| Playwright not signed in | Slack MCP plugin missing |
| Invalid `mcp.json` JSON | `production_ready: false` if only Daily Review gaps |

After onboarding: **`test shipit`** dry-run → **`production ready`**.

---

## Related MCP tools

- `release_orchestrator(message="welcome onboard")`
- `daily_review_mcp_config`
- `daily_review_setup(install=true)`
- `production_readiness(surface="both")`
- `mcp_catalog` / onboarding help in `release_orchestrator(message="help")`
