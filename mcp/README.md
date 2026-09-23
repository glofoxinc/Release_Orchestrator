# MCP (Release Orchestrator)

Cursor MCP server for guided PIC + AN releases.

| Item | Location |
|------|----------|
| **Python package** | `orchestrator/server/` (import: `release_mcp`) |
| **Run** | `python -m release_mcp` |
| **Legacy shim** | `python -m mcp_server` (same server) |
| **Per-step tools** | `release_mcp/steps/` + `release_step_status` MCP tool |
| **Onboarding** | `release_mcp/onboarding*.py`, `team_crew.py` at repo root |

**Cursor MCP config** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "release-orchestrator": {
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "release_mcp"]
    }
  }
}
```

| **Weekly operator page** | `docs/OPERATOR_GUIDE.md` |
| **First-time setup** | `docs/COMPLETE_ONBOARDING.md` — say **`welcome onboard!`** |
