# Release Orchestrator MCP — Guided E2E (v3.4)

Platform-parity release workflow **and Daily Review Agent** in one MCP server (`python -m release_mcp`).

## Quick start

1. **One-time `.env`** in repo root (copy from `.env.example`):

   ```env
   JIRA_BASE_URL=https://abcfinancial.atlassian.net
   JIRA_EMAIL=you@abcfitness.com
   JIRA_API_TOKEN=...

   # Optional — defaults so you never repeat them
   DEFAULT_JIRA_TEAM=Glofox Insights Customize
   DEFAULT_PROJECTS=PIC,AN
   DEFAULT_SELECTION_MODE=status

   # Slack: use Cursor Slack MCP at Step 6 — no token needed
   # Optional SLACK_BOT_TOKEN only for platform UI auto-send
   ```

2. **Cursor MCP** — add to project or user config:

   ```json
   {
     "mcpServers": {
       "release-orchestrator": {
         "command": "C:/Users/YOU/ZABC/projects/done/small/jira-release-tool/.venv/Scripts/python.exe",
         "args": ["-m", "release_mcp"]
       }
     }
   }
   ```

3. Reload MCP. In chat say:
   - **onboarding** — first clone setup
   - **production ready** — readiness (releases + daily review)
   - **week release** — start weekly PIC+AN (see [OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md))
   - **daily review welcome** — guided 6 PM review setup

## Full E2E setup (one script)

```powershell
.\orchestrator\ops\setup_e2e.ps1
```

Installs Python extras, npm + Playwright Edge for calendar, prints MCP config reminder.

## MCP stack

| Server / plugin | Role |
|---|---|
| **release-orchestrator** | Releases + all `daily_review_*` tools |
| **teams** | Daily review chat summary + failure alerts |
| **Playwright plugin** | SharePoint upload + Slack browser fallback (release Step 4/6) |
| **Slack plugin** | Release Step 6 announce (preferred over browser) |

Calendar scheduling uses **Playwright scripts** (Outlook web profile) — not the Playwright MCP session — so Task Scheduler works headless.

## Production readiness

Say **production ready** or call `mcp_production_readiness()`:

- **VERIFIED** — automated checks passed (Jira creds, IST→CST schedule, SHIPIT metadata, tests)
- **UNVERIFIED** — fix before prod
- **OPERATOR REQUIRED** — live SHIPIT dry-run + Slack post (you confirm once)

**Deploy window:** **10:30–11:30 AM IST** → Jira stores **US Central (CST/CDT)** — ticket text shows both.
**Emergency:** at Step 5 say **emergency deployment** (6:00–8:00 PM IST profile).

## First-time clone (no `.env` yet)

Say **onboarding** — the MCP walks through:

1. Create `.venv` + `pip install -r requirements.txt`
2. Copy `.env.example` → `.env`
3. **JIRA_BASE_URL** — your Atlassian cloud URL
4. **JIRA_EMAIL** — your login email
5. **JIRA_API_TOKEN** — create at https://id.atlassian.com/manage-profile/security/api-tokens
6. Cursor MCP config (snippet provided)
7. **Slack** — Cursor Slack MCP at Step 6 (no bot token)

After each step, say **setup status** to refresh. When Jira credentials are set, say **welcome** → **yes** to start Step 1.

Every response includes **What's next** so you never guess the next step.

## Primary tool

### `release_orchestrator`

| Parameter | Use |
|---|---|
| `message` | Natural language: `welcome`, `yes`, `help`, `use Ignite`, SharePoint URL, `exclude PIC-1234` |
| `workflow_id` | From previous response — pass on every follow-up |
| `confirmation_token` | Usually auto on **yes**; pass only if MCP returns one explicitly |

Every response includes:

- **`say_to_user`** — show this to the operator (plain English)
- **`user_can_say`** — suggested replies
- **`step_number` / `step_title` / `roadmap`**
- **`workflow_id`** — required for follow-ups

## Conversation flow

```
You: welcome
MCP: Step 1 — fetch PIC + AN for Glofox? (PIC Review + AN Passed QA)
You: yes
MCP: Found N tickets — yes to lock?
You: yes
MCP: Step 2 exclusions — yes to skip?
You: yes
MCP: Step 3 release notes — re-fetches release-ready only
     (PIC Ready for Release + AN QA(migrated)), shows ticket list — yes to generate DOCX?
... SharePoint URL → SHIPIT → send slack → deploy → mark released ...
```

At **Step 6 (Slack)**, paste the SharePoint URL earlier if needed, review the preview, then say **send slack** or **skip slack**. Posts to `#insights-customize-squad` (CC: Sushma + Trent).

**Release notes:** Development Team is always **Customize BI Team**. Release version is included whether you fetch by fix version or by status (status mode derives `vYYYY.Q.MM.DD` from the planned deploy date).

### Status split (Ticket Review vs Release Notes)

| Step | PIC | AN |
|---|---|---|
| **Step 1 — Ticket Review** | Review, In Review, Ready for Review | Passed QA, QA Passed |
| **Step 3 — Release Notes** | Ready for Release | QA(migrated) |

Step 3 **re-fetches** Jira with the release-ready statuses. If you locked tickets in Step 1 that are still in review, they are listed as **not release-ready** and excluded from the DOCX until moved in Jira. You can skip Ticket Review entirely with `workflow_mode=release_notes_only` and `selection_mode=status` to fetch release-ready tickets directly.

**Explicit override (one-off):** If a ticket is locked but not yet release-ready, say:

```
release_orchestrator(message="include PIC-5966 for release notes", workflow_id="<id>")
```

The MCP fetches that ticket directly from Jira and adds it to the Step 3 list. Overrides are shown in the preview as `explicit_override_keys` — disclose them in chat before confirming DOCX generation.

Team override anytime before first fetch:

```
release_orchestrator(message="use Ignite Insights Customize")
```

Fix-version mode instead of status:

```
release_orchestrator(message="welcome")
# then update via release_wizard with selection_mode=fix_version and version_name
```

Or set `DEFAULT_SELECTION_MODE=fix_version` in `.env`.

## Platform parity map

| Platform UI | MCP step | Guided message hints |
|---|---|---|
| Ticket Review Step 2 lock | `ticket_review` | yes to lock |
| Exclusions | `exclusions` | exclude PIC-xxx or yes |
| Release Notes | `release_notes` | yes to generate DOCX; `include PIC-xxx for release notes` for override |
| SharePoint Step 4 | `sharepoint` | paste URL |
| Service Ticket SHIPIT | `service_ticket` | yes to create |
| Slack announce | `slack` | send slack / skip slack |
| Release Deployer | `deploy` | yes after preview |
| Mark released | `mark_released` | yes or skip |

Shared modules: `release_critical.py`, `recovery_contract.py`, same generators and validators as Streamlit.

## Recovery

Sessions: `.mcp_wizard_sessions/` (workspace-scoped when using multi-workspace).

| Situation | Action |
|---|---|
| Cursor restarted | `release_orchestrator(message="next", workflow_id=...)` |
| Lost ID | `release_wizard(action="list")` or inspect session JSON |
| Abandon | `release_wizard(action="cancel", workflow_id=...)` |

See [RUNBOOK.md](RUNBOOK.md) §4 for full recovery contract.

## Advanced / atomic tools

Use when debugging — not for normal releases:

- `release_wizard` — explicit `start` / `update` / `confirm` / `resume`
- `fetch_release_tickets` — status or fix-version fetch
- `generate_release_notes_docx` — standalone DOCX
- `create_service_ticket` — standalone SHIPIT (`test_mode`, `draft_overrides`, `extracted_override`)
- `dispose_test_shipit_ticket` — comment → cancel → delete TEST tickets only
- `validate_service_ticket`, `release_recovery_status`, `deployment_metrics`

### SHIPIT parity (prod vs test)

| | **Production** (SHIPIT-17036 / SHIPIT-17191) | **Test / demo** |
|---|---|---|
| Summary | `Glofox Insights Customize BI - Prod Deployment - Release Version YYYY.Q.MM.DD` | `TEST SHIPIT … DO NOT DEPLOY` |
| Content | Evidence-based description, plans, risks from Jira description + comments (Analyze single-ticket or multi-custom PIC) | Minimal / placeholder |
| Approver groups | `Insights Customize Approvers` | None |
| Team | None | None |
| Version format | `2026.3.09.11` (YYYY.Q.MM.DD — quarter 1–4) | Same, or `test_mode=true` |
| SharePoint | Real uploaded `.docx` URL | Placeholder OK for migration tests |

Guided phrases: **test shipit** (sets test mode), **dispose test shipit SHIPIT-12345** (cleanup).

## Cursor skill

Install: `~/.cursor/skills/release-orchestrator-mcp/SKILL.md`

Triggers when you say welcome, start release, fetch review-ready tickets, release notes, SHIPIT, deploy.

## Verify install

```powershell
cd C:\Users\LYal01\ZABC\projects\done\small\jira-release-tool
python -c "from mcp_server import server, guided; print('ok', server.release_orchestrator)"
python -m pytest tests/test_mcp_guided.py tests/test_mcp_welcome.py tests/test_mcp_wizard.py -q
```
