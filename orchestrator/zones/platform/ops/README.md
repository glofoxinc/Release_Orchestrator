# Release Orchestrator scripts

Operational CLI and PowerShell helpers for the MCP package. Run from repo root:

```powershell
python orchestrator/zones/platform/ops/verify_integrations.py --check=all
python orchestrator/zones/platform/ops/complete_launch.py
.\orchestrator\zones\platform\ops\daily_review\setup.ps1
.\orchestrator\zones\platform\ops\setup_e2e.ps1
```

| Path | Purpose |
|------|---------|
| `daily_review/` | Teams bridge, npm deps, pilot sign-off (on-demand runs) |
| `verify_integrations.py` | Jira/Slack/SharePoint readiness checks |
| `complete_launch.py` | Final launch sign-off runner |
| `legacy/` | Archived one-off demos (incl. Task Scheduler register script) |
| `sync_cursor_skill.ps1` | Copy `skills/release-orchestrator-mcp/SKILL.md` → `.cursor/skills/` |

The top-level `scripts/` folder only contains a redirect README.
