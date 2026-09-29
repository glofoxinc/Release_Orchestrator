# Release Orchestrator Runbook

Operator procedures for the single-user Streamlit + MCP release platform.
**Validation and preflight never create Jira issues or post Slack messages.**

Related docs: [INTEGRATIONS.md](INTEGRATIONS.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md) · [SETUP.md](SETUP.md) · [SECURITY.md](SECURITY.md) · [PUSH_SAFETY.md](PUSH_SAFETY.md)

---

## 1. Single-user threat model

| Assumption | Implication |
|---|---|
| One trusted operator on a desktop/laptop | No multi-tenant auth, RBAC, or shared session isolation |
| Secrets live in local `.env` | Protect the machine disk and backups; never commit `.env` |
| MCP runs in the operator’s Cursor session | Confirmation tokens bind to preview content; still treat the host as trusted |
| Jira/Slack credentials can write to production | Every write path requires an explicit confirm (UI click or MCP token) |
| History/drafts are local JSON | `.state/` (see [STATE.md](./STATE.md)) — audit/recovery aids, not a vault |

**Out of scope for this release gate:** remote attackers, XSS against Streamlit, concurrent multi-operator races, and public internet exposure. Prefer binding Streamlit to localhost.

**Residual risks:** stolen API tokens; operator confirming a wrong preview; audited `proceed_with_locked_snapshot` override after drift; residual duplicate TCKT if post-failure lookup fails.

---

## 2. Pre-release checklist (exact)

Run from the repo root with the project venv active. Do **not** claim readiness if any required live check is skipped for credentials/network.

### Offline / CI (required)

- [ ] `python -m pytest orchestrator/zones/quality/tests/ -q`
- [ ] `ruff check .`
- [ ] `ruff format --check` on hardened modules + quality-gate tests (scoped; full-repo format debt is tracked separately)
- [ ] `mypy --config-file=pyproject.toml mcp_server/wizard_store.py deploy_ops.py sharepoint_url.py slack_announce.py deployment_history.py`
- [ ] `bandit -r . -x ./tests,./venv,./.venv,./build,./dist -ll` (or CI Security workflow)
- [ ] Coverage gate: `python -m pytest orchestrator/zones/quality/tests/test_quality_gate.py orchestrator/zones/quality/tests/test_mcp_wizard.py orchestrator/zones/quality/tests/test_wizard_store.py orchestrator/zones/quality/tests/test_slack_announce.py orchestrator/zones/quality/tests/test_platform_ops.py orchestrator/zones/quality/tests/test_efficiency.py orchestrator/zones/quality/tests/test_headless_ops.py --cov=mcp_server --cov=deploy_ops --cov=slack_announce --cov=sharepoint_url --cov=deployment_history --cov-report=term-missing --cov-fail-under=70`

### Smoke (required)

- [ ] MCP import/tool smoke: `python -c "from mcp_server import server, wizard, wizard_store; print('mcp_ok')"`
- [ ] Streamlit health smoke: `python -c "import os; os.environ.setdefault('MOCK_MODE','1'); from ui.health import collect_setup_issues; print(len(collect_setup_issues()))"`
- [ ] Optional AppTest: `python -m pytest orchestrator/zones/quality/tests/test_e2e_smoke.py -q` (needs Streamlit testing)

### Live read-only preflight (required for “production-ready” claim)

- [ ] Credentials present: real `JIRA_EMAIL` / `JIRA_API_TOKEN` / `JIRA_BASE_URL` (not placeholders)
- [ ] `python orchestrator/zones/platform/ops/verify_integrations.py --check=readiness,service_desk,release_notes,team_scope`
- [ ] `python orchestrator/zones/platform/ops/test_release_notes_e2e.py`
- [ ] Confirm script exit code `0` for Jira auth/search (Slack/Teams/Graph checks SKIP when archived)
- [ ] No Jira creates occurred (script is read-only by design)

### Config sanity

- [ ] `workspace.yaml` service desk points to **SHIPIT** (desk 2046 / RT 2969)
- [ ] Service Desk IDs / field map complete if SHIPIT create is in scope
- [ ] Manual SharePoint document URL host/link shape validated (Graph upload archived)

### Re-enable archived integrations (optional)

1. Copy the desired block from `archive/slack_announce.yaml`, `archive/teams_schedule.yaml`, or `archive/sharepoint_upload.yaml` into `workspace.yaml`.
2. Set `enabled: true` and remove or set `archived: false`.
3. Provision credentials (`SLACK_BOT_TOKEN` and/or `MS_GRAPH_*`).
4. Re-run `python orchestrator/zones/platform/ops/verify_integrations.py --check=slack|teams|sharepoint`.

### Automated sign-off runner

```bash
python orchestrator/zones/platform/ops/release_signoff_checklist.py
python orchestrator/zones/platform/ops/release_signoff_checklist.py --live-jira
python orchestrator/zones/platform/ops/shipit_preflight.py
python orchestrator/zones/platform/ops/compare_release_notes_docx.py --generate-sample
```

### SHIPIT live validation (operator — before first production release)

1. Cancel test ticket **SHIPIT-16710** in the Jira portal if still open.
2. MCP `create_service_ticket` with `dry_run=true` on the next fix version — verify ADF description (Release Summary, Key Highlights, Reports/Dashboards Delivered).
3. One real SHIPIT create on a sandbox or small release — confirm Request Type, approver groups, and post-create batch edit (assignment group optional; blank if Jira group name differs).
4. Paste manual SharePoint link on Release Notes Step 4 and confirm it appears in the SHIPIT description.

---

## 3. Live read-only integration preflight

```bash
# Load .env, then:
python orchestrator/zones/platform/ops/verify_integrations.py --check=all

# Narrow checks:
python orchestrator/zones/platform/ops/verify_integrations.py --check=auth
python orchestrator/zones/platform/ops/verify_integrations.py --check=search --project=PIC
python orchestrator/zones/platform/ops/verify_integrations.py --check=create --dry-run
python orchestrator/zones/platform/ops/verify_integrations.py --check=slack
python orchestrator/zones/platform/ops/verify_integrations.py --check=service_desk
python orchestrator/zones/platform/ops/verify_integrations.py --check=sharepoint --sharepoint-url="https://....sharepoint.com/..."
python orchestrator/zones/platform/ops/verify_integrations.py --check=placeholders
python orchestrator/zones/platform/ops/verify_integrations.py --check=workspace

# Config-only (no network):
python orchestrator/zones/platform/ops/verify_integrations.py --no-live
python orchestrator/zones/platform/ops/verify_integrations.py --mock
```

| Exit | Meaning |
|---|---|
| 0 | Required checks passed |
| 1 | One or more required checks failed |
| 2 | Bad arguments |

**Caveat:** If credentials or network are unavailable, report preflight as **not proven** — do not equate mock/`SKIP` with a live pass.

---

## 4. MCP guided release (v3.1) + session recovery

**Primary tool:** `release_orchestrator(message="welcome")` — full platform E2E in
natural language. See **[MCP_GUIDED.md](MCP_GUIDED.md)**.

| User says | MCP call |
|---|---|
| welcome | `release_orchestrator(message="welcome")` |
| yes / confirm | `release_orchestrator(message="yes", workflow_id=...)` |
| use Ignite | `release_orchestrator(message="use Ignite")` |
| help | `release_orchestrator(message="help", workflow_id=...)` |

Show **`say_to_user`** from each response; pass **`workflow_id`** on follow-ups.
Confirmation tokens auto-resolve on **yes** for most steps.

Sessions live under `.state/mcp_wizard_sessions/` (or `.state/workspaces/<name>/mcp_wizard_sessions/`).

| Situation | Action |
|---|---|
| Cursor/MCP restarted mid-flow | `release_orchestrator(message="next", workflow_id=...)` or `release_wizard` `resume` |
| Lost workflow id | `release_wizard` `list` / inspect JSON files |
| Need to abandon | `release_wizard` `cancel` — terminal sessions reject further confirms |
| Corrupt session JSON | Delete that session file; start a new workflow (do not hand-edit fingerprints) |
| Confirmation token rejected | Re-`resume`/`update` to mint a fresh token bound to the latest preview |
| Write already applied | Status `already_applied` — do not force another create/deploy for the same fingerprint |

Confirmation tokens are **single-use** and bound to workflow + step + preview hash.

### Recovery contract (Platform + MCP)

Both surfaces persist restart-safe state for the same release-critical domains:
`snapshot`, `release_notes`, `sharepoint`, `service_ticket`, `slack`, `teams`,
`deploy`. The shared module `recovery_contract.py` defines this contract.

| Surface | Storage |
|---|---|
| Streamlit | `.deploy_draft.json` + `release_session` keys (workspace-scoped) |
| MCP wizard | `.state/mcp_wizard_sessions/<workflow_id>.json` |

Use MCP `release_recovery_status(platform_state=..., workflow_id=...)` to compare
domain readiness after a restart. Streamlit offers restore on launch when
`draft_has_restorable_content()` is true.

Wizard service-ticket and deploy previews include a structured `validation`
payload (`blockers`, `warnings`, `ready`) from the same core as the UI.

---

## 5. Partial Slack recovery

1. Inspect prior per-channel results in UI success panel, MCP `slack` artifact, or `.deployment_history.json`.
2. Retry **only failed channels** (`skip_channel_keys` / `pending_channel_messages`). Successful channels must not be re-posted.
3. If `slack_announce.enabled=false`, deployer is **not** blocked — skip announce and continue.
4. Edited message bodies cannot drop required CC mentions; trailing `CC:` is re-appended from config.
5. Legacy `SLACK_DEPLOY_WEBHOOK` / `notifier.py` is **deprecated** — use Bot API announce only.

Read-only membership/channel resolution: `python orchestrator/zones/platform/ops/verify_integrations.py --check=slack`.

---

## 6. Deploy procedures (Streamlit + MCP)

### Before deploy

1. Locked ticket snapshot matches intended release (or audited override after drift).
2. SharePoint URL validated; TCKT created (or stand-alone mode intentional).
3. Slack sent or skipped (or disabled).
4. Preview comments/transitions; confirm **Confirm & Deploy** (UI) or MCP confirmation token.

### Partial deploy

- Failed keys stay on the deploy step; mark-released is blocked until clean.
- Retry failed tickets only; successful comment/transition rows remain.
- Dual-project (PIC/AN) results are stored separately under `deployment_results`.

### After deploy

- History entry links SharePoint, TCKT, Slack outcomes, per-project results.
- Optional mark-released only after a clean deploy result.

---

## 7. Undo / recovery

| Goal | How |
|---|---|
| Undo deployment comments/transitions | Streamlit history undo, or MCP `undo` then confirm — covers **all** projects recorded in `deployment_results` |
| Ambiguous TCKT create | App/MCP runs read-only `find_tckt_by_summary`; if found → **do not retry**; adopt existing key |
| Streamlit restart mid Step 5 | Secret-free `.deploy_draft.json` restores draft; confirm click is still required |
| Wrong tickets deployed | Undo, fix selection / re-lock snapshot, redeploy only the intended keys |
| Drift vs Jira | Prefer `relock_snapshot`; use `proceed_with_locked_snapshot=true` only as an audited override |

Undo deletes deployment comments and reverses Done transitions when undo data is present. It does **not** delete TCKTs or Slack messages.

---

## 8. Desktop / local deploy of the app

```bash
pip install -e ".[dev]"
# Configure .env from .env.example — never commit secrets
streamlit run orchestrator/entry/app.py
# or Windows launcher: setup.bat / launch.vbs
```

MCP: run `python -m mcp_server` **inside the project venv** (`mcp>=2.0.0`). Point Cursor at that interpreter.

Docker: see repo `Dockerfile` / `docker-compose.yaml`. Prefer localhost-only publishing for this threat model.

---

## 9. Incident quick reference

| Symptom | First check |
|---|---|
| MCP `ModuleNotFoundError: mcp...` | Wrong interpreter — use `.venv` |
| TCKT HTTP 400 | Read field errors; run Service Desk schema preflight |
| Approvers missing after create | Team UUID / batched post-create edits (see CHANGELOG) |
| Wrong planned times for approvers | Schedule timezone picker + dual-clock preview |
| Slack retry double-posts | Ensure skip of already-sent channel keys |
| Deploy ran without click | Should be impossible — file bug if Step 5 executed on render |
| Step 2 shows wrong empty message (releases vs status) | Hard refresh; confirm build id `2026.09.08-audit-hardening`; re-run Step 1 Continue to lock source |
| Session not restored after restart | Use single **Restore session** prompt at startup; check scope mismatch warning |

---

## 10. End-to-end workflow sign-off checklist

Run after each platform stabilization release:

1. **Settings** — PIC + AN team scope configured (board/filter/JQL).
2. **Ticket Review** — By status → Step 2 loads → deselect stays on page → **Generate Review List →**.
3. **Ticket Review** — Fix version path still works.
4. **Release Notes (full)** — locked list → Step 2 → Step 3 → Step 4 DOCX download.
5. **Release Notes (quick)** — By status → tickets load → Next → Step 3 → Step 4.
6. **Restart** Streamlit mid-RN Step 2 → **Restore session** → same mode + tickets.
7. **SharePoint** — paste link on RN Step 4; STK gate passes.
8. **SHIPIT** — Step 2 → **Apply SHIPIT-16769 template** → paste SharePoint link → preview → create → verify Request Type in Jira portal.
9. **Deployer** — full path with snapshot filter; quick start without snapshot.
10. **Team switch** — progress saved to disk before workspace switch.

---

## 10b. Daily Review recovery (on-demand)

**Mode:** on-demand only — say **`daily review welcome`** when you want a run. No automatic 6 PM Task Scheduler.

**Config:** `daily_review.enabled: false` and `schedule_mode: on_demand` in `orchestrator/zones/product/agents/review/agent.yaml`.

| Situation | Action |
|---|---|
| Run blocked (`on_demand_only`) | Say **`daily review welcome`** and confirm each step, or `daily_review_run_live(force=true)` |
| Graph calendar blocked | Say **`daily review calendar playwright`** — Playwright Outlook handoff |
| Duplicate meeting same day | Agent returns `already_scheduled` — use `--force` only to reschedule |
| Teams summary missing | Verify Teams MCP login; re-run after schedule succeeds |
| Recovery audit | Inspect `orchestrator/zones/product/agents/review/.state/last_run.json` |

**Pilot sign-off (operator):**

```powershell
powershell -File orchestrator/zones/platform/ops/daily_review/pilot_signoff.ps1
```

---

## 11. SharePoint (Glofox Customize release notes)

**Target folder (configured in `workspace.yaml`):**

- Host: `abcfinancial.sharepoint.com`
- Site: `/sites/ABCFitnessSolutionsLLC-Glofox-Customize`
- Folder: `Release Notes/2026 - Q3`
- File name: `Release Notes YYYY.Q.MM.DD.docx` (generated by the platform)

**Credentials (`.env`, never commit):**

```env
MS_GRAPH_TENANT_ID=
MS_GRAPH_CLIENT_ID=
MS_GRAPH_CLIENT_SECRET=
```

Entra app needs **Sites.ReadWrite.All** (application permission) + admin consent.

**Verify (read-only):**

```bash
python orchestrator/zones/platform/ops/verify_integrations.py --check=sharepoint
python -c "from mcp_server import sharepoint_ops; print(sharepoint_ops.sharepoint_upload_status())"
```

**Without Graph credentials (works today):**

1. Generate DOCX in Release Notes Step 4.
2. Upload manually to the Q3 folder in SharePoint.
3. Copy the **document** link (not the folder link) into Step 4 / Service Ticket.

**Enable auto-upload:** set `sharepoint_upload.enabled: true` in `workspace.yaml` after credentials work, then use Release Notes Step 4 **Upload to SharePoint** or MCP wizard SharePoint step.

**MCP standalone modes:**

| Mode | Start input |
|---|---|
| Full workflow | `workflow_mode=full` (default) |
| Release notes only | `workflow_mode=release_notes_only` + `version_name` |
| Service ticket only | `workflow_mode=service_ticket_only` + `version_name` + `sharepoint_url` |
| Deployer only | `workflow_mode=deployer_only` + `version_name` |

Every MCP wizard response includes `operator_guide` with next steps.

---

## 11. v2 Tier-2 Features (wired in v3.0)

All v2 tier-2 modules are now wired to both Platform UI and MCP:

| Feature | Platform Location | MCP Tool |
|---|---|---|
| AI Enhancer | STK Step 5 Review → "AI-Enhanced Insights" expander | `ai_enhance_release(extracted, options)` |
| Confluence Publisher | STK post-create → "Publish to Confluence" section | `confluence_publish_release_notes(...)` |
| Template Library | STK Step 4 → "Apply Template" expander | `list_tckt_templates`, `apply_tckt_template`, `save_tckt_template` |
| Linked Ticket Verifier | Ticket Review Step 2 → "Ticket Pre-flight Verification" expander | `verify_linked_tickets(ticket_keys, ...)` |
| JQL Search | Sidebar → "🔍 JQL Search" button | `search_tickets(jql, ...)` (existing) |

**New MCP config/observability tools:**

| Tool | Purpose |
|---|---|
| `workspace_config(section)` | Read workspace.yaml sections |
| `tckt_history(limit, search, status)` | Query user's TCKT deployment tickets |
| `deployment_metrics(days)` | DORA-style metrics from local history |

### Feature configuration

**AI Enhancer:** Uses shared `common/ai` module. Configure LLM via environment variables or falls back to deterministic heuristics.

**Confluence Publisher:** Set `CONFLUENCE_SPACE` and optionally `CONFLUENCE_PARENT_ID` in `.env`. Falls back to `JIRA_BASE_URL` for Confluence URL if `CONFLUENCE_URL` is not set.

**Template Library:** Templates are stored in `~/.jira-release-tool/templates/`. Built-in templates (`standard-monthly-glofox`, `emergency-hotfix`, etc.) are always available.
