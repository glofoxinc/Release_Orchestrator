# Troubleshooting

## Installation

### `pip install` fails on `python-docx`

Usually an outdated pip. Upgrade first:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'streamlit'`

Virtual environment not activated:

```powershell
.venv\Scripts\activate          # Windows
source .venv/bin/activate        # macOS/Linux
pip install -r requirements.txt
```

### Setup.bat fails on Windows

Re-run as administrator once (needed only for the first run if Python was installed system-wide). Subsequent runs don't need elevation.

## Authentication / Credentials

### 401 Unauthorized

Verify with curl:
```bash
curl -u "you@company.com:YOUR_TOKEN" "https://yourorg.atlassian.net/rest/api/3/myself" -o - | head
```

If this fails, the creds are wrong — fix `.env`. If this succeeds but the app still 401s, your `.env` isn't being loaded — confirm the file is in the project root, not `.env.example`.

### 403 Forbidden on ticket create

Your account lacks **Create Issue** permission on the target project. Ask the Jira admin to grant it in **Project settings → Permissions**.

### "Request Type could not be auto-set"

The toolkit tried the Service Desk API and it returned an error. Causes:

1. `TCKT_SERVICE_DESK_ID` / `TCKT_REQUEST_TYPE_ID` not configured in `config.py`
2. Your account isn't a **customer** of that Service Desk (some tenants require explicit customer add)
3. Service Desk endpoint is different (e.g. JSM on-prem syntax)

**Manual fix always works:** set Request Type via the portal after creation.

### Approver groups / Team not set on create

Some Jira instances reject these fields in the create call. The toolkit handles this by calling `PUT /issue/{key}` separately after create. If the separate call also fails, check the `field_ids` in `workspace.yaml` → `service_desk.fields` — they differ per tenant.

## Runtime Errors

### `ConnectionError: HTTPSConnectionPool(...)`

Network issue. Common causes:
- Corporate proxy — set `HTTPS_PROXY=http://proxy:8080` in `.env`
- TLS inspection — add corporate root CA to Python's trust store:
  ```powershell
  pip install pip-system-certs
  ```

### `429 Too Many Requests`

Jira is rate-limiting. The client auto-retries with exponential backoff (up to
`_MAX_RETRIES` attempts) and honors `Retry-After` on 429. If you see this
persistently:

- Reduce bulk operations (smaller ticket batches)
- Set `JIRA_RATE_LIMIT_PAUSE` in `.env` to a small inter-call pause in seconds
  (default `0` / off; `0.5` is a common starting point under pressure)
- Keep `JIRA_READONLY_CONCURRENCY` at `1` (or low) while throttling — that knob
  only fans out **read-only** preflight checks; all Jira writes stay sequential

### "Cannot find Agile board for project"

Rare — some configs reference boards that require additional scopes. Remove the board lookup from your flow or request the `read:board-scope.admin:jira-software` permission.

### Streamlit session state lost between steps

Happens when the browser tab is duplicated. Streamlit session state is per-tab; open a single tab and complete the flow end-to-end. To persist across sessions, save/load via the **Save Draft** button on each step (adds to `workspaces/<team>/drafts/`).

## Docker / Deployment

### Container starts but UI is blank

CORS or reverse-proxy issue. Ensure these are set (already in compose):
```yaml
STREAMLIT_SERVER_ENABLE_CORS: "false"
STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION: "false"
```

### "Permission denied" writing to `workspaces/`

```bash
docker-compose down
sudo chown -R 1000:1000 workspaces templates
docker-compose up -d
```

The container runs as UID 1000.

### Streamlit Cloud deployment fails with secrets

In Streamlit Cloud settings, add secrets in **TOML** format (not INI):
```toml
JIRA_BASE_URL = "https://yourorg.atlassian.net"
JIRA_EMAIL = "you@company.com"
JIRA_API_TOKEN = "..."
```

## Platform-specific

### Windows — launcher.pyw closes immediately

`pywebview` requires a GUI backend. Install:

```powershell
pip install pywebview[edgechromium]
```

### macOS — `launch.vbs` doesn't open

`.vbs` is Windows-only. On macOS use:

```bash
streamlit run app.py
# or create an Automator .app calling the same
```

### Linux container — time zone wrong in deployment comments

Set TZ in compose or env:
```yaml
environment:
  TZ: America/Chicago
```

## Collecting logs for support

```powershell
# 1. Version info
python --version
pip show streamlit python-docx requests jinja2 | Select-String Version

# 2. Test basic Jira connectivity
python -c "from jira_client import JiraClient; import os; c = JiraClient(os.getenv('JIRA_BASE_URL'), os.getenv('JIRA_EMAIL'), os.getenv('JIRA_API_TOKEN')); print(c.get_current_user())"

# 3. Run the test suite
python -m pytest tests/ -v --tb=short | Tee-Object -FilePath tests.log

# 4. Sanitized workspace.yaml
Get-Content workspace.yaml | Out-File workspace.sanitized.yaml   # then manually remove any account_id fields
```

Attach `tests.log` and `workspace.sanitized.yaml`. Mention which app (Ticket Review / Service Ticket / Release Notes / Release Deployer) was active when the bug appeared.
