# Release Orchestrator scripts

Operational CLI and PowerShell helpers for the MCP package. Run from repo root:

```powershell
python release_mcp/scripts/verify_integrations.py --check=all
python release_mcp/scripts/complete_launch.py
.\release_mcp\scripts\daily_review\setup.ps1
.\release_mcp\scripts\setup_e2e.ps1
```

| Path | Purpose |
|------|---------|
| `daily_review/` | Teams bridge, npm deps, pilot sign-off, Task Scheduler |
| `verify_integrations.py` | Jira/Slack/SharePoint readiness checks |
| `complete_launch.py` | Final launch sign-off runner |
| `legacy/` | Archived one-off demos |

The top-level `scripts/` folder only contains a redirect README.
