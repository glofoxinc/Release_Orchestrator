# Getting Started with Release Orchestrator

A 5-minute quickstart to deploy your first Jira release automation.

## What this does

Release Orchestrator is a Streamlit-based platform that automates four error-prone release tasks against Jira Cloud: **creating SHIPIT change tickets** (with ADF-formatted Implementation/Test/Backout plans), **generating Word release-note documents**, **posting deployment comments and auto-transitioning tickets to Done**, and **producing DORA-style deployment dashboards**. One `workspace.yaml` configures everything — no code changes for new teams.

## Prerequisites

| Requirement | Version / Source |
|---|---|
| Python | 3.10+ |
| Jira Cloud | Any plan with REST API access |
| Atlassian API token | [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |

## Install in 3 commands

```powershell
cd C:\Users\LYal01\ZABC\projects\done\small\jira-release-tool
python -m venv .venv ; .venv\Scripts\activate ; pip install -r requirements.txt
Copy-Item .env.example .env   # then edit JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN
streamlit run app.py
```

See **[SETUP.md](./SETUP.md)** for the full new-user guide.

Open [http://localhost:8501](http://localhost:8501).

**Windows shortcut:** double-click `setup.bat` to create the venv, install deps, and launch. Or use `launcher.pyw` for a native desktop window (pywebview).

## First success — generate a ticket review list

1. Edit `.env` with your three credentials.
2. `streamlit run app.py` → home page loads with team cards.
3. Click your workspace (or the default). Pick **Ticket Review** from the app grid.
4. **Step 1**: Select a project (e.g. `AN`) and an unreleased version.
5. **Step 2**: Tickets fetch in ~5s (paginated via `/search/jql`). You'll see a table with status validation warnings (e.g., "Ticket AN-5192 is still In Progress").
6. **Step 3**: Click **Copy Formatted Review**. The toolkit outputs:

   ```
   AN-5192 – New Members – Add Join Type filter in Advanced Filters
   AN-5194 – New Members – Fix incorrect currency display per location
   AN-5139 – New Members – Standardize visibility excluding continuing members
   ```

   Paste into Slack / Teams / your review ticket.

You've completed your first end-to-end flow in under a minute.

## What to try next

| Try this | App in UI | Why |
|---|---|---|
| Create a SHIPIT change ticket | **Service Ticket** (5 steps) | Auto-builds ADF Implementation/Test/Backout plans and Business Impact |
| Generate a Word release notes doc | **Release Notes** (4 steps) | Produces `.docx` with per-client tables and branding |
| Post deployment comments + transition | **Release Deployer** (6 steps) | Select release → tickets → exclude → deployment info → review → deploy |
| See a DORA dashboard | Home → **Deployment Dashboard** | Frequency, lead time, change volume, success rate |
| Add another team | Edit `workspaces/<team>/workspace.yaml` | Switch from home page without restart |

## Where things live

- `app.py` — Streamlit router & session state
- `config.py` — YAML loader with workspace fallback (~12k lines)
- `jira_client.py` — REST client with retry, rate-limit handling, redacted errors
- `adf_builder.py` — Atlassian Document Format helpers
- `generators/release_notes_generator.py` — python-docx generator
- `templates/default/` — Jinja2 templates for all text outputs
- `workspace.yaml` — root workspace config
- `workspaces/<team>/workspace.yaml` — per-team overrides

## Troubleshooting the first run

- **"401 Unauthorized"** — your email or token is wrong. Regenerate the token; emails are lowercase.
- **"No unreleased versions found"** — the project has no open versions in Jira. Ask your PM to create one.
- **Port 8501 busy** — `streamlit run app.py --server.port 8502`.
- **Workspace not visible** — you set `JIRA_TOOLKIT_WORKSPACE=foo` but `workspaces/foo/workspace.yaml` doesn't exist. Unset the variable or create the file.

See [`TROUBLESHOOTING.md`](./TROUBLESHOOTING.md) for more.
