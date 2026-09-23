# Release Orchestrator scripts

Operational CLI and PowerShell helpers for the MCP package. Run from repo root:

```powershell
python orchestrator/ops/verify_integrations.py --check=all
python orchestrator/ops/complete_launch.py
.\orchestrator\ops\daily_review\setup.ps1
.\orchestrator\ops\setup_e2e.ps1
```

| Path | Purpose |
|------|---------|
| `daily_review/` | Teams bridge, npm deps, pilot sign-off, Task Scheduler |
| `verify_integrations.py` | Jira/Slack/SharePoint readiness checks |
| `complete_launch.py` | Final launch sign-off runner |
| `legacy/` | Archived one-off demos |

The top-level `scripts/` folder only contains a redirect README.
