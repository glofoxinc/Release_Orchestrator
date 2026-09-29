# New User Setup Guide

Complete end-to-end setup for **Release Orchestrator** on a fresh machine.

> **Cursor + MCP operators:** prefer **[GUIDE.md](./GUIDE.md)** (install + MCP + daily release).  
> **Release go/no-go:** **[RELEASE_READINESS.md](./RELEASE_READINESS.md)**.

## Project location

Clone to any folder you choose, for example:

```
C:\dev\jira-release-tool
# or ~/projects/jira-release-tool
```

All MCP `cwd` paths in `~/.cursor/mcp.json` must point to **your** clone location.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | 3.11 recommended on Windows |
| Jira Cloud | Server/Data Center not supported |
| API token | [Create here](https://id.atlassian.com/manage-profile/security/api-tokens) |
| Permissions | Browse + create issues on your release projects (PIC, AN, TCKT) |

## One-time install (Windows)

```powershell
cd path\to\jira-release-tool
python -m venv .venv
.\.venv\Scripts\activate
pip install -r orchestrator/zones/config/deps/requirements.txt
Copy-Item .env.example .env
notepad .env
# Or one shot: .\orchestrator\zones\platform\ops\setup_e2e.ps1
```

Set in `.env`:

```ini
JIRA_BASE_URL=https://abcfinancial.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your-token-here
```

**Or** double-click `setup.bat` — it creates the venv, installs deps, and copies `.env.example`.

## Launch the app

```powershell
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501
```

Open **http://localhost:8501** and hard-refresh once (`Ctrl+Shift+R`).

Confirm sidebar promo shows build **`2026.07.01-e2e`**.

## First-run checklist (in the app)

The home page shows a **Setup status** panel. Fix items in this order:

1. **Jira credentials** — `.env` must have email + token
2. **Projects** — Settings → Projects → add PIC, AN (or your keys)
3. **Service Desk** (only if using Service Ticket):
   - Issue Type ID for `[System] Change`
   - Service Desk ID + Request Type ID (removes Request Type warning)
4. **Pick your team** on the home page
5. Start with **Ticket Review** (simplest workflow)

## Recommended workflow (E2E)

### Streamlit (platform)

```
Ticket Review  →  Release Notes  →  Service Ticket  →  Release Deployer
     │                  │                  │                    │
  Pick releases    Generate .docx     Create SHIPIT        Post deploy comments
  Group by owner   from locked list   with ADF plans      Transition to Done
```

Selections carry across apps — pick releases once in Ticket Review.

### Cursor MCP (v3.1 — same flow, conversational)

1. Register MCP (project `.cursor/mcp.json` or user `~/.cursor/mcp.json`):

   ```json
   "release-orchestrator": {
     "command": "C:/Users/LYal01/ZABC/projects/done/small/jira-release-tool/.venv/Scripts/python.exe",
     "args": ["-m", "release_mcp"],
     "cwd": "C:/Users/LYal01/ZABC/projects/done/small/jira-release-tool"
   }
   ```

2. Reload MCP in Cursor. Say **welcome** in chat.

3. Tool: **`release_orchestrator`** — not `release_wizard` for day-to-day use.

Full guide: **[MCP_GUIDED.md](./MCP_GUIDED.md)**.

Optional `.env` (one-time, avoids repeating team/projects):

```ini
DEFAULT_JIRA_TEAM=Glofox Insights Customize
DEFAULT_PROJECTS=PIC,AN
DEFAULT_SELECTION_MODE=status
```

## Configuration reference

| Setting | Where | Purpose |
|---|---|---|
| Jira URL / email / token | `.env` | Authentication |
| Projects, service desk, apps | `orchestrator/zones/config/profiles/workspace.yaml` or Settings UI | Team-specific config |
| Active team folder | `.env` `JIRA_TOOLKIT_WORKSPACE` or home page switcher | Multi-team |
| TCKT desk/type IDs | Settings → Service Desk **or** `.env` | Auto-set Request Type |

### TCKT Request Type IDs

Set **either**:

- **Settings → Service Desk → Service Desk ID + Request Type ID** (saved to `orchestrator/zones/config/profiles/workspace.yaml`), **or**
- `.env`:
  ```ini
  TCKT_SERVICE_DESK_ID=123
  TCKT_REQUEST_TYPE_ID=456
  ```

Env values override YAML when both are set.

## UI features (this release)

- **Light / Dark / Auto** theme toggle (top-right on every page)
- **Optional features** expander — AI Ticket Creator hidden by default
- **Release dropdowns** — select, switch, or choose `— None —` to deselect
- **Setup health panel** on home — actionable warnings for new users

## Common issues

| Symptom | Fix |
|---|---|
| Old UI / missing features | Kill Streamlit on 8501–8505; restart; hard refresh |
| 401 Unauthorized | Regenerate API token; check email matches Atlassian account |
| Request Type warning | Expected until desk/type IDs configured; only matters for Service Ticket |
| No unreleased versions | Create a fix version in Jira for PIC/AN |
| Session lost mid-wizard | Use one browser tab; click Start Over if stuck |
| Port busy | `streamlit run orchestrator/entry/app.py --server.port 8502` |

See also [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) and [FAQ.md](./FAQ.md).

## Verify installation

```powershell
.\.venv\Scripts\python.exe -m pytest orchestrator/zones/quality/tests/ -q --tb=no
.\.venv\Scripts\python.exe -m py_compile app.py ui\*.py
```

## Optional: CLI headless mode

```powershell
.\.venv\Scripts\jira-release-tool.exe validate-config orchestrator/zones/config/profiles/workspace.yaml
```
