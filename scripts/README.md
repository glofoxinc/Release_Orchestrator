# Scripts moved

All operational scripts live under **`release_mcp/scripts/`** (part of the Release Orchestrator MCP package).

Examples:

```powershell
python release_mcp/scripts/verify_integrations.py --check=all
python release_mcp/scripts/complete_launch.py --dry-run-version VERSION --sharepoint-url URL
.\release_mcp\scripts\daily_review\setup.ps1
.\release_mcp\scripts\daily_review\pilot_signoff.ps1
```

Do not add new top-level scripts here — add them under `release_mcp/scripts/`.
