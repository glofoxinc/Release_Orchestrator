<!-- GENERATED â€” edit skills/release-orchestrator-mcp/SKILL.md then re-run orchestrator/zones/platform/ops/sync_cursor_skill.ps1 -->
---
name: release-orchestrator-mcp
description: >-
  Release Orchestrator MCP v3.5.0 — portable colleague guide (no local path assumptions). Full PIC + AN
  release workflow: one-time MCP setup, Jira .env, Cursor config, guided flow with
  Jira-first release date confirmation, release notes DOCX, SHIPIT, Slack, deploy.
  Triggers: welcome, start release, production ready, include PIC-XXXX for release notes.
  NOT Daily Review or Release Review app.
---

# Release Orchestrator MCP — Complete Skill (v3.5.0)

> **Portable guide** — no `ZABC/` paths, no author-specific folders. Colleagues clone the repo anywhere and use `${workspaceFolder}` for MCP.

## START HERE — read this first

**New clone?** One doc: **`orchestrator/zones/knowledge/guides/GUIDE.md`** (or say **`guide`** in chat). Then **`welcome onboard`**. Onboarding skill: **`skills/release-orchestrator-onboarding/SKILL.md`**.

**Share this `SKILL.md` file with colleagues.** It is the **daily** release playbook (Jira → PR gate → DOCX → SharePoint receipt → SHIPIT → both Slack channels) — no private folder paths, no assumption about where they keep code on their laptop.

| Question | Answer |
|----------|--------|
| **What is this file?** | Instructions for Cursor’s agent — workflow, rules, what to say. **Not** the app itself. |
| **Can they run releases with only this file?** | **No.** Each person also installs the **MCP server** once (clone repo → venv → `.env` → Cursor MCP). |
| **Do colleagues need your folder layout?** | **No.** They clone the repo to **any folder they choose** (Desktop, Documents, `dev`, etc.). |
| **Ready to go?** | After onboarding → say **`production ready`** in Cursor chat. |

---

## The three layers (Platform + MCP + Skill — one repo)

| Layer | Location | Role |
|-------|----------|------|
| **Platform** | `release_platform/` | Streamlit UI (`streamlit run orchestrator/entry/app.py`) |
| **MCP** | `release_mcp/` (see `mcp/README.md`) | Cursor API — `python -m release_mcp` |
| **Skill** | `skills/release-orchestrator-mcp/SKILL.md` | This file — agent rules + colleague setup |

All three use the **same engine** (`release_ops.py`, `deploy_ops.py`, generators). Parity matrix: `orchestrator/zones/knowledge/guides/PLATFORM_MCP_SKILL_PARITY.md`.

### Parity ratings (v3.5 — 100%)

| Path | Score |
|------|-------|
| MCP → Platform | **100%** |
| MCP → Skill | **100%** |
| Platform → Skill | **100%** |
| Guided chat vs Platform UI | **Equivalent** (same 8 steps) |
| Skill alone (no MCP install) | **0% runtime** — instructions only |

Full matrix: `orchestrator/zones/knowledge/guides/PLATFORM_MCP_SKILL_PARITY.md`

**The skill does not call Jira by itself.** The agent reads this skill, then calls the MCP server you install below.

---

## What you send vs what colleagues install

| You share | Colleague installs (once) |
|-----------|---------------------------|
| This **`SKILL.md`** (or `release-orchestrator-mcp/` folder) | Git repo **`jira-release-tool`** — any path on their machine |
| — | Python 3.10+ venv inside that repo |
| — | Personal **`.env`** (Jira token — never share) |
| — | Cursor **MCP** entry pointing at their venv |

**Repo URL:** https://github.com/abcfitness-insights/jira-release-tool  
No GitHub access? Ask **CC171 Insights & Reporting** for a zip of the repo.

---

## One-time setup — complete checklist (~30 min)

Do these **once per machine**. Use **your own** folder — examples below use `~/dev` / `%USERPROFILE%\dev`; change to whatever you prefer.

### Step 1 — Clone the repo (any location)

Pick a folder you use for work tools, then clone:

**Windows (PowerShell):**
```powershell
mkdir $env:USERPROFILE\dev -ErrorAction SilentlyContinue
cd $env:USERPROFILE\dev
git clone https://github.com/abcfitness-insights/jira-release-tool.git
cd jira-release-tool
```

**Mac / Linux:**
```bash
mkdir -p ~/dev && cd ~/dev
git clone https://github.com/abcfitness-insights/jira-release-tool.git
cd jira-release-tool
```

Remember this path — you will open **`jira-release-tool`** as your Cursor workspace (recommended).

### Step 2 — Python venv + dependencies

Run **inside the cloned repo** (same folder that contains `release_mcp/`):

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
```

**Mac / Linux:**
```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

**Quick sanity check** (from repo root):
```powershell
# Windows
.\.venv\Scripts\python.exe -c "from release_mcp import server; print('MCP import OK')"

# Mac/Linux
./.venv/bin/python -c "from release_mcp import server; print('MCP import OK')"
```

### Step 3 — Create your `.env` (required)

In the repo root, copy the template and fill in **your** Jira credentials:

```powershell
copy .env.example .env   # Windows
# cp .env.example .env   # Mac/Linux
```

**Minimum required (edit `.env`):**
```env
JIRA_BASE_URL=https://abcfinancial.atlassian.net
JIRA_EMAIL=you@abcfitness.com
JIRA_API_TOKEN=your-token-here

# Recommended defaults for Glofox daily releases (every business day)
DEFAULT_JIRA_TEAM=Glofox Insights Customize
DEFAULT_PROJECTS=PIC,AN
DEFAULT_SELECTION_MODE=status
```

**Jira API token:** https://id.atlassian.com/manage-profile/security/api-tokens → Create token → paste into `JIRA_API_TOKEN`.

**Never commit `.env`** — it stays on your machine only.

### Step 4 — Wire Cursor MCP (required)

**Recommended:** Open the cloned **`jira-release-tool`** folder in Cursor (File → Open Folder), then add MCP config.

**Option A — project config** (best; no hard-coded paths): create or edit **`.cursor/mcp.json`** inside the repo:

**Windows:**
```json
{
  "mcpServers": {
    "release-orchestrator": {
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "release_mcp"]
    }
  }
}
```

**Mac / Linux:**
```json
{
  "mcpServers": {
    "release-orchestrator": {
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "release_mcp"]
    }
  }
}
```

**Option B — user config** (`~/.cursor/mcp.json`): only if you cannot open the repo as workspace — use the **full absolute path** to your venv Python from Step 2 (your path will differ from everyone else’s).

**Restart Cursor.** MCP panel should list **`release-orchestrator`** with tool **`release_orchestrator`**.

### Step 5 — Install this skill in Cursor

Copy the shared **`SKILL.md`** into **one** of:

| Location | Scope |
|----------|-------|
| `~/.cursor/skills/release-orchestrator-mcp/SKILL.md` | Personal — works in any project |
| `jira-release-tool/.cursor/skills/release-orchestrator-mcp/SKILL.md` | Inside the repo you cloned |

Folder name must be **`release-orchestrator-mcp`**. Only **`SKILL.md`** is required.

### Step 6 — Verify (say this in Cursor chat)

```
production ready
```

The agent should call `mcp_production_readiness()` and report **VERIFIED** / **UNVERIFIED** items. Fix anything marked UNVERIFIED before a live release.

**Manual verify (optional)** — from repo root, after venv is active:
```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest orchestrator/zones/quality/tests/test_mcp_wizard.py orchestrator/zones/quality/tests/test_mcp_welcome.py -q

# Mac/Linux
./.venv/bin/python -m pytest orchestrator/zones/quality/tests/test_mcp_wizard.py orchestrator/zones/quality/tests/test_mcp_welcome.py -q
```

---

## Optional integrations (not required for core flow)

| Integration | Required? | What works without it |
|-------------|-----------|------------------------|
| **Jira** (`.env`) | **Yes** | Nothing works without this |
| **Playwright MCP** (`user-playwright`) | **Recommended** | SharePoint DOCX upload when Graph is archived — say **upload sharepoint** |
| **Slack MCP** (`plugin-slack-slack`) | **Recommended** | Step 6 dual-channel post — say **send slack** (no bot token) |
| **SharePoint Graph** (`MS_GRAPH_*`) | No | Optional when IT provisions Entra app |
| **Slack bot** (`SLACK_BOT_TOKEN`) | No | Optional Streamlit auto-send only |
| **Confluence** | No | Optional wiki publish only |
| **OpenAI** | No | Falls back to deterministic summaries |

---

## First release — beginner walkthrough

### First time on this machine (unified onboarding)
1. Say **`welcome onboard`** → pick path: **`both`** · **`release only`** · **`daily review only`**
2. **Release path:** **`use glofox`** / **`projects pic an`** → **`crew done`** → paste `.env` snippet → **`mcp configured`**
3. **Daily Review path (same MCP):** enable **Teams MCP** → **`daily_review_setup(install=true)`** → edit `agent.yaml` → **`daily_review_outlook_login()`** → **`outlook done`** → enable **Playwright plugin** (calendar fallback)
4. Edit `.env` locally — **never paste tokens in chat**
5. Optional: **`crew status`** · **`production ready`** · MCP **`team_crew_status`**
6. When ready: **`yes`** or **`full release`** (release) · **`daily review welcome`** (6 PM review — **one** meeting per run)

### MCP role matrix (Daily Review + Release)

| MCP | Daily Review | Release |
|-----|--------------|---------|
| **release-orchestrator** | Orchestration | Orchestration |
| **Embedded Playwright (Node)** | Primary calendar (1 meeting/run) | — |
| **Teams stdio** | Summary + failure alerts | — |
| **Playwright plugin** | Fallback calendar | SharePoint + Slack fallback |
| **Slack plugin** | Optional | Primary Step 6 |
| **Jira (.env REST)** | Ticket fetch | Ticket fetch + SHIPIT |

**Calendar fallback:** if embedded scheduling fails → **`daily review calendar playwright`** → execute Playwright MCP steps → **`calendar done`**

### Daily Review meeting invites (from welcome onboard crew)

During **`welcome onboard`**, **`crew done`** writes `TEAM_CREW_*` into `.env`. The 6 PM agent uses that for Outlook/Teams meeting invites — **not** a static list in `agent.yaml`.

| Invite type | Who |
|-------------|-----|
| **Required** | Leadership (`TEAM_CREW_LEADERSHIP`) + QA pool (`TEAM_CREW_QA`) + **in-squad** ticket assignees |
| **Optional** | Review crew (`TEAM_CREW_REVIEW`) + release crew (`TEAM_CREW_RELEASE`) |
| **Never invited** | `TEAM_CREW_EXCLUDE` emails + assignees **outside** the Customize BI squad roster (e.g. Standard/AN-only — Gabriel, Erasmo) |

**Ticket fetch:** outside-squad assignees (Gabriel, Erasmo) are **not fetched** by default — they won't appear in the summary or meeting body. Opt-in only: `ticket_scope.include_outside_squad_assignees: true` in `agent.yaml`.

**Preview before live run:** MCP **`daily_review_attendee_policy`** or **`daily_review_run_dry`** (includes `skipped_outside_squad` + `invite_policy`).

**Exclude someone permanently:** **`crew exclude email@abcfitness.com`** during onboarding.

### Every release (minimal phrases)
| Step | Say |
|------|-----|
| 1–2 | **`yes`** / **`full release`** |
| 3 | **`yes`** (DOCX) |
| 4 | **`upload sharepoint`** |
| 5 | **`yes`** (SHIPIT) |
| 6 | **`send slack`** |
| 7–8 | **`yes deploy`** → **`yes`** |

Per-step MCP helpers: **`release_step_status`** (full map), **`release_step_slack`**, **`release_step_deploy`**, etc.

### Every release (menu path)
1. Say **`start`** → menu (fetch review tickets / **create release notes** / SHIPIT)
2. Or **`welcome`** when Jira is configured
3. Pick a path, then follow confirmations step by step

### Full E2E path (after choosing fetch review tickets)
1. Agent calls `release_orchestrator(message="fetch review tickets")` → Step 1 fetch
2. Say **`yes`** → lock ticket list
4. Say **`yes`** again → lock ticket list
5. Step 2 exclusions → **`yes`** to skip, or **`exclude PIC-1234`**
6. **Step 2b — Release date confirm** → MCP reads Jira **fixVersions** on locked tickets; shows per-ticket list. Reply **`yes`** to confirm, or send **`2026.3.09.18`** to override, then **`yes`**. If no fix version in Jira, MCP suggests **T+1** — never applies silently.
7. Step 3 release notes → agent shows **Ready for Release** ticket list → **`create release notes`** or **`yes`** — generates DOCX **and auto-starts SharePoint upload** (Playwright)
8. Step 4 SharePoint → complete browser upload → **`sharepoint done`** + paste URL (or agent captures link)
9. Step 5 SHIPIT → review dry-run + `cab_quality` → **`create shipit`** or **`yes`** — creates live ticket **and auto-starts Slack**
10. Step 6 Slack → complete Playwright post to squad + buddies → **`slack done`**
11. Step 7 deploy → **`yes`** after preview
12. Step 8 mark released → **`yes`** or skip

**Save `workflow_id`** from every MCP response — required on all follow-up messages.

---

## How to invoke (user phrases)

- `welcome` / `start release` / `let's go`
- `release notes` / `create SHIPIT` / `SHIPIT`
- `production ready` / `mcp status` / `onboarding`
- `deploy` / `mark released`
- `test shipit` / `dispose test shipit SHIPIT-12345`

**NOT for:** Daily Review Agent, gf-insights-fitnessbi ticket implementation, Release Review paginated app.

---

## Primary tool — agent always starts here

```
CallMcpTool → server: release-orchestrator (or user-release-orchestrator)
             tool:   release_orchestrator
             args:   { "message": "<user text>", "workflow_id": "<from prior response>" }
```

| Parameter | Rule |
|-----------|------|
| `message` | User's words: `welcome`, `yes`, SharePoint URL, `exclude PIC-1234`, `include PIC-5966 for release notes`, `use Ignite`, `send slack`, `version 2026.3.09.16` |
| `workflow_id` | **Required on every follow-up** after first response |
| `confirmation_token` | Pass when response includes one (usually auto on `yes`) |

**Always show the user:** `say_to_user`, `user_can_say`, and save `workflow_id`.

**Do NOT** use `release_wizard` for normal chat — only debugging or explicit `workflow_mode` overrides.

---

## 8-step guided flow

```
0. Welcome        → team + mode defaults (PIC + AN, Glofox, status)
1. Ticket Review  → fetch review-ready tickets, lock set
2. Exclusions     → drop tickets from release
2b. Release date  → Jira fixVersions first → user confirms (T+1 only if missing)
3. Release Notes  → re-fetch release-ready only → confirm → generate DOCX
4. SharePoint     → paste uploaded .docx URL (or MCP upload if Graph configured)
5. Service Ticket → SHIPIT dry-run → cab_quality → user confirms → create
6. Slack          → Cursor Slack MCP OR user posts manually → slack done
7. Deploy         → post deployment comments + Done transitions
8. Mark Released  → optional Jira fix-version release
```

### Status split (CRITICAL)

| Step | PIC statuses | AN statuses |
|------|--------------|-------------|
| **Step 1 — Ticket Review** | Review, In Review, Ready for Review | Passed QA, QA Passed |
| **Step 3 — Release Notes / SHIPIT** | Ready for Release | QA(migrated) |

Step 3 **re-fetches Jira** with release-ready statuses. Tickets still in review are excluded until moved in Jira — unless user uses explicit override (below).

### Team options

| User says | Team |
|-----------|------|
| `use Glofox` (default) | Glofox Insights Customize |
| `use Ignite` | Ignite Insights Customize |
| `use ETL` | Insights Customize (ETL) |

---

## Quick reference — message → intent

| User says | Message / action |
|-----------|------------------|
| Start | `welcome` |
| Proceed | `yes` |
| Different team | `use Ignite Insights Customize` / `use Glofox` / `use ETL` |
| Fix version mode | `version 2026.3.09.16` |
| SharePoint link | paste full `https://abcfinancial.sharepoint.com/...` URL |
| Exclude ticket | `exclude PIC-1234` |
| Include not-yet-release-ready ticket | `include PIC-5966 for release notes` |
| Upload SharePoint (Playwright) | `upload sharepoint` |
| SharePoint upload complete | `sharepoint done` + paste URL |
| Post Slack (Slack MCP) | `send slack` |
| Post Slack (Playwright fallback) | `send slack playwright` |
| Skip Slack | `skip slack` |
| Slack posted externally | `slack done` |
| Emergency deploy | `emergency deployment` |
| Test SHIPIT (no prod) | `test shipit` |
| Cleanup test ticket | `dispose test shipit SHIPIT-17076` |
| Operator sign-off | `shipit confirmed` / `slack confirmed` |
| Resume after restart | `next` + saved `workflow_id` |
| Help | `help` |
| Production check | `production ready` / `mcp status` |
| Onboarding | `onboarding` / `setup` |

---

## Defaults

| Setting | Value |
|---------|-------|
| Projects | PIC + AN |
| Team | Glofox Insights Customize |
| Mode | `status` (review-ready for Step 1) |
| Deploy window | 10:30–11:30 AM IST → stored as US Central |
| Version format | `YYYY.Q.MM.DD` (quarter 1–4) — **not** `YYYY.M.DD.DD` |
| **Release date** | **Jira fixVersions first** on locked tickets; user must **confirm**. T+1 is only a **suggestion** when Jira has no fix version — never applied silently |

---

## Release notes quality (agent MUST enforce)

| Rule | Behavior |
|------|----------|
| Confirm before DOCX | Show ticket list + preview; wait for **yes** / **proceed** |
| Status split | Step 3 uses release-ready statuses only |
| Testing Evidence clients | Only clients backed by selected tickets |
| Analyze (Standard) | Include **only** when AN tickets are in the release |
| Release date confirm | Step 2b: show Jira fixVersions per ticket; user confirms or sends `version 2026.3.09.18` |
| GitHub PR check | Step 3: open/unapproved PRs per ticket; Jira comment @ assignee when blocking PRs found |
| No auto-regenerate | Do not regenerate DOCX unless user explicitly asks |

### Testing Evidence — wrong vs right

| Wrong | Right |
|-------|-------|
| PIC-only release lists Jazzercise + **Analyze (Standard)** | Jazzercise only (no Analyze without AN tickets) |
| Auto-generate DOCX after fetch | Show list → user confirms → generate |

### Explicit ticket override

If user says *"include PIC-XXXX for release notes"* (or *include PIC-XXXX* while on Step 3):

1. Guided MCP sets `release_notes_include_ticket_keys` on the workflow
2. Step 3 re-fetch merges release-ready tickets **plus** override keys fetched directly from Jira
3. Preview shows `explicit_override_keys` — **disclose in chat** before user confirms DOCX
4. Still wait for **yes** before generating `.docx`

---

## SHIPIT — complete guide (TCKT project)

Gold standards:
- [SHIPIT-17036](https://abcfinancial.atlassian.net/browse/SHIPIT-17036) — Analyze-only (AN-5516 Unique Visits)
- [SHIPIT-17191](https://abcfinancial.atlassian.net/browse/SHIPIT-17191) — multi-custom PIC (Jazzercise + Xtreme Fitness)

### Evidence enrichment (automatic in MCP)

Before SHIPIT draft, MCP fetches each release ticket's Jira description + comments and extracts QA evidence, dashboard rules, test cases, deploy workspace — feeds Description, Business Impact, Verification, Risks, QA Test Plan (ADF).

### SHIPIT workflow in guided flow

```
Step 5 → create_service_ticket(dry_run=true)  → review cab_quality + post_create_plan
      → user confirms                          → create_service_ticket(dry_run=false)
      → post-create (17036 parity)               → Review Ready + assign creator + link PIC/AN
```

**CAB quality gate:** dry-run returns `cab_quality` with score + checklist. Target `ready_for_cab` when ≥90%.

### SHIPIT post-create (SHIPIT-17036 parity)

After `dry_run=false` create, MCP automatically:

| Step | Behavior |
|------|----------|
| Request type | **Manual Change** via Service Desk create (`workspace.yaml`) |
| Approver groups | **Insights Customize Approvers** (verify/repair via `assignment_ops`) |
| Assignee | Set to **creator** (Jira API user, or `shipit_owner_account_id` / `SHIPIT_OWNER_ACCOUNT_ID`) |
| Status | Transition to **Review Ready** |
| Links | Link each release PIC/AN ticket with **Discovery - Connected** (SHIPIT outward → release inward) |

Dry-run preview includes `post_create_plan` with the planned steps and ticket keys.

**Flexible overrides** (wizard chat or `create_service_ticket` args):

- `skip shipit link` / `skip link tickets` → no issue links
- `skip review ready` → no status transition
- `post_create_overrides`: `{ "link_release_tickets": false, "transition_status": "Review Ready", ... }`
- `shipit_owner_account_id`: explicit Atlassian accountId for assignee

### Test SHIPIT cleanup

```
dispose test shipit SHIPIT-17076
```

Only works on summaries containing `TEST SHIPIT` / `DO NOT DEPLOY`.

---

## Standalone workflow modes

Set `inputs.workflow_mode` on `release_wizard(action="start", ...)`:

| Mode | Starts at | Use when |
|------|-----------|----------|
| `full` (default) | Ticket Review | Normal daily release |
| `release_notes_only` | Release Notes | DOCX + SharePoint only |
| `service_ticket_only` | SHIPIT | Version + SharePoint URL already known |
| `deployer_only` | Deploy | Post-deploy comments only |

---

## All MCP tools (catalog)

### Guided (use 99% of the time)

| Tool | Purpose |
|------|---------|
| `release_orchestrator` | **START HERE** — conversational E2E |
| `release_wizard` | Advanced / standalone modes / resume / cancel |

### Release core

| Tool | Purpose |
|------|---------|
| `fetch_release_tickets` | PIC + AN by fix version or status + team |
| `generate_release_notes_docx` | Word .docx (platform parity) |
| `create_service_ticket` | SHIPIT create/preview + `cab_quality` |
| `dispose_test_shipit_ticket` | Delete TEST SHIPIT tickets |
| `validate_service_ticket` | Draft validation |
| `team_scope_status` | Team JQL scope preflight |
| `browser_automation_status` | Playwright + Slack MCP setup readiness |
| `sharepoint_playwright_handoff` | Step-by-step Playwright upload playbook |
| `slack_playwright_handoff` | Playwright post to both Slack channels (fallback) |

### Gates / recovery

| Tool | Purpose |
|------|---------|
| `pre_review_gate` / `post_qa_gate` | Ticket / QA gates |
| `production_readiness` / `mcp_production_readiness` | Install verification |
| `release_recovery_status` | Platform vs wizard session recovery |

Full tool list: enable MCP in Cursor → expand `release-orchestrator` server.

---

## Recovery

| Situation | Action |
|-----------|--------|
| Cursor restarted | `release_orchestrator(message="next", workflow_id="...")` |
| Lost workflow_id | `release_wizard(action="list")` |
| Abandon | `release_wizard(action="cancel", workflow_id="...")` |

Sessions stored in: `jira-release-tool/.mcp_wizard_sessions/`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| MCP server not listed in Cursor | Re-check Step 4 paths; restart Cursor; use absolute path to `python.exe` |
| `JIRA_API_TOKEN` / auth errors | Regenerate token; confirm `JIRA_EMAIL` matches Atlassian account |
| No tickets fetched | Confirm team name; check ticket statuses match Step 1 table |
| Step 3 blocked — not release-ready | Move ticket in Jira **or** say `include PIC-XXXX for release notes` |
| DOCX not generated | User must say **yes** after ticket list preview — never auto-generate |
| SHIPIT missing request type | Set Request Type manually in Jira portal: "Submit a normal or emergency change" |
| Wrong release date | At Step 2b send `version 2026.3.09.18` then **yes**; MCP reads Jira fixVersions first |
| Open PR blocking release | Step 3 lists PRs; assignee gets Jira comment — set `GITHUB_TOKEN` in `.env` |
| Skip PR Jira comments | Say `skip github pr comments` or set `skip_github_pr_comments=true` on workflow update |
| `production ready` shows UNVERIFIED | Complete missing items from readiness report (usually `.env` or MCP path) |

**Support:** CC171 Insights & Reporting / Glofox Analytics team.

---

## Anti-patterns

- ❌ Share skill only and skip MCP install — agent cannot call Jira
- ❌ Use `release_wizard` directly for normal chat — use `release_orchestrator`
- ❌ Auto-generate DOCX without user confirmation
- ❌ Add Analyze (Standard) to Testing Evidence when no AN tickets
- ❌ Use today's date for status-mode deploy (use **T+1**)
- ❌ Create SHIPIT with `dry_run=false` before user sees `cab_quality`
- ❌ Use version format `YYYY.M.DD.DD` — must be `YYYY.Q.MM.DD`

---

## Agent checklist (before marking step complete)

1. Step 3 fetched **release-ready** statuses (not review statuses)
2. Ticket list shown; user confirmed before DOCX
3. Version/date = **T+1** for status mode unless override
4. Testing Evidence clients match tickets only
5. SHIPIT dry-run reviewed; `cab_quality` shown when available
6. Explicit overrides disclosed in chat
7. `workflow_id` passed on every follow-up call

---

## Companion: Release Review (paginated validation)

Separate app — **not** part of `release_orchestrator`. Use when QA needs paginated report validation before release (ask CC171 for access if your team uses it).

---

## Share checklist for team leads

**Send colleagues:**
1. This **`SKILL.md`** file (or the `release-orchestrator-mcp` folder)
2. Repo link: https://github.com/abcfitness-insights/jira-release-tool (or a zip if no GitHub)

**Tell them:**
1. Clone repo to **any folder they choose** — not your machine’s paths
2. Complete setup **Steps 1–5** in this file
3. Say **`production ready`**, then **`welcome`**
4. Create their own **Jira API token** — never share `.env`

**Do not include:** your local paths, `.env`, tokens, or screenshots with credentials.

**Skill version:** v3.5.0 — portable colleague guide
