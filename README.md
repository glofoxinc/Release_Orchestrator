# Release Orchestrator

**Version 3.5.0** — weekly Jira PIC/AN releases via Cursor MCP.

PyPI package name remains `jira-release-tool` (historical alias). Operator-facing name: **Release Orchestrator** (`release-orchestrator` MCP server and console script).

## Structure

| At repo root | Purpose |
|--------------|---------|
| **`orchestrator/`** | **Everything** — see [orchestrator/STRUCTURE.md](orchestrator/STRUCTURE.md) |
| `.github/` | CI only (GitHub requires this location) |
| `.git/` | Version control (cannot move) |
| `.cursor/` | Junction → `orchestrator/.cursor` (MCP for Cursor) |

**Start:** [orchestrator/zones/knowledge/guides/GUIDE.md](orchestrator/zones/knowledge/guides/GUIDE.md)

## Quick setup

```powershell
orchestrator\zones\platform\automation\bin\setup.bat
python -m release_mcp
```

Secrets: `orchestrator/zones/runtime/local/.env` (gitignored). Template: `orchestrator/zones/runtime/local/.env.example`.

Before push: `orchestrator\zones\platform\automation\check_push_safe.ps1`
