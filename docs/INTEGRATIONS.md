# Integrations — Release Orchestrator

## Active vs archived (v3.1.5)

| Integration | Status | Active path |
|---|---|---|
| Jira Cloud REST + Service Desk | **Active** | Ticket fetch, SHIPIT create, deploy transitions |
| Release Notes DOCX v4 | **Active** | Built-in generator + readiness gate |
| Manual SharePoint URL | **Active** | Paste link on Release Notes Step 4 → SHIPIT description |
| Release gates (Jira status) | **Active** | Pre-review / post-QA filters (Slack DMs off by default) |
| Slack deployment announce | **Active** | Step 6 — **Cursor Slack MCP** `slack_send_message` (no bot token). Optional `SLACK_BOT_TOKEN` for platform auto-send. |
| MCP guided E2E | **Active** | `release_orchestrator` — say **welcome** → **yes** |
| Confluence publish | Optional | Post-create companion page |
| Teams scheduling | **Archived** | `archive/teams_schedule.yaml` — restore when `MS_GRAPH_*` ready |
| SharePoint Graph upload | **Archived** | `archive/sharepoint_upload.yaml` — manual URL is primary |

**Deployment window:** team agrees **10:30–11:30 AM IST**; Jira planned start/end store the same instant in **US Central (CST/CDT)**. Ticket text states both clocks.

Check MCP readiness: `mcp_production_readiness()` or say **production ready** in chat.

This tool talks to the Atlassian Jira Cloud REST API to read releases,
search issues, and create deployment (**SHIPIT**) tickets.

Verify with (never posts to Slack or creates Jira issues):

```bash
python orchestrator/ops/verify_integrations.py --check=all
python orchestrator/ops/verify_integrations.py --check=auth
python orchestrator/ops/verify_integrations.py --check=search --project=AN
python orchestrator/ops/verify_integrations.py --check=create --dry-run
python orchestrator/ops/verify_integrations.py --check=slack
python orchestrator/ops/verify_integrations.py --check=service_desk
python orchestrator/ops/verify_integrations.py --check=sharepoint --sharepoint-url=URL
python orchestrator/ops/verify_integrations.py --check=placeholders
python orchestrator/ops/verify_integrations.py --check=workspace
python orchestrator/ops/verify_integrations.py --no-live   # config-only Slack/SD
python orchestrator/ops/verify_integrations.py --mock
```

| Check | What it validates |
|---|---|
| `auth` / `search` / `create` | Jira REST auth, JQL, createmeta (dry-run) |
| `slack` | SKIP when archived; bot token + channel checks when enabled |
| `teams` | SKIP when archived; organizer + Graph readiness when enabled |
| `service_desk` | SHIPIT desk/request-type/issue-type metadata; optional live GET |
| `sharepoint` | Graph upload SKIP when archived; URL shape check for manual links |
| `placeholders` | Example `.env` tokens that would block real integrations |
| `workspace` | `slack_announce` channels/cc schema warnings |

---

## 1. Jira Cloud REST API

| Attribute | Value |
|---|---|
| Status | **Required** — the app does nothing without this |
| Env vars | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` |
| Optional efficiency | `JIRA_RATE_LIMIT_PAUSE` (inter-call pause, default `0`), `JIRA_VERSION_CACHE_TTL` (version list cache, default `300`), `JIRA_READONLY_CONCURRENCY` (read-only preflight fan-out, default `1`; writes stay sequential) |
| Auth | HTTP Basic: `email:api_token`, base64 encoded |
| API version | v3 (REST API) + Service Desk API |

### How to get credentials
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**, name it (e.g. `jira-release-tool`), copy it.
3. Paste it into `.env` as `JIRA_API_TOKEN`.
4. Set `JIRA_EMAIL` to the **same email** as your Atlassian account.
5. Set `JIRA_BASE_URL` to your instance URL (no trailing slash),
   e.g. `https://abcfinancial.atlassian.net`.

### What the app does with it
- Lists Fix Versions per project.
- Reads issues in `fixVersion = "vX.Y.Z"`.
- Creates `[System] Change` tickets under the **SHIPIT** project (legacy TCKT archived in `archive/service_desk_tckt.yaml`).
- Optionally sets Service Desk Request Type.
- Transitions issues through workflow states on deployment.

### Verification
```bash
python orchestrator/ops/verify_integrations.py --check=auth
```
Expected: `[PASS] authenticated as <Your Name> (<email>)`.

### Common errors
| Status | Meaning | Fix |
|---|---|---|
| 401 | Token invalid / expired | Regenerate at id.atlassian.com/manage-profile/security/api-tokens. |
| 403 | Account exists but lacks permission | Ask Jira admin to grant Jira Software (and Service Desk, for TCKT) access. |
| 404 | Project key not found | Check `project` arg; verify project exists and you can browse it. |
| 429 | Rate limited | Back off; the app auto-retries with exponential backoff. |

### Required Jira permissions
| Action | Jira permission |
|---|---|
| Read releases | Browse Projects on source project (PIC / AN / etc.) |
| Search issues | Browse Projects on target project |
| Create TCKT | Create Issues on TCKT project |
| Edit TCKT | Edit Issues on TCKT project |
| Transition release tickets | Transition Issues on source project |

---

## 2. Service Desk (optional, for SHIPIT request type)

| Attribute | Value |
|---|---|
| Status | Optional — enables proper Service Desk portal experience |
| Configured in | `profiles/workspace.yaml` (`service_desk` block) |
| Key fields | `TCKT_SERVICE_DESK_ID`, `TCKT_REQUEST_TYPE_ID` |

If Service Desk fields are missing, the ticket is still created via
standard Jira API but **no Request Type is set**, which produces the
"Request Type: None" / wrong portal layout issue.

Fix: after ticket creation, manually set **Request Type → "Submit a
normal or emergency change"** in the Details panel.

---

## Mock mode

Run without any Jira credentials:

```bash
python orchestrator/ops/verify_integrations.py --mock
MOCK_MODE=true streamlit run app.py   # UI stub data
```

In mock mode the verifier returns `[MOCK]` pass for every check, and the
app should show a warning banner "Mock mode enabled — no real Jira
calls" (when wired in the UI).

---

## Secrets policy

- `.env` is gitignored; `.env.example` contains placeholders only.
- Verifier prints only `JIRA_API_TOKEN[:4] + '*' * …` when debugging.
- `jira_client.py::_redact_auth` masks `Authorization` headers in all logs.
- `.gitleaks.toml` blocks tokens being committed.
