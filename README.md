# Release Orchestrator

**Version 3.5.0** — weekly Jira PIC/AN releases via Cursor MCP.

PyPI package name remains `jira-release-tool` (historical alias). Operator-facing name: **Release Orchestrator** (`release-orchestrator` MCP server and console script).

## Team guide (HTML)

| Link | Use when |
|------|----------|
| [DOCUMENTATION.html on GitHub Pages](https://glofoxinc.github.io/Release_Orchestrator/DOCUMENTATION.html) | Default share link after [Pages is enabled](https://github.com/glofoxinc/Release_Orchestrator/settings/pages) (**Deploy from branch** → `gh-pages` → `/`) |
| [CDN mirror (same file)](https://cdn.jsdelivr.net/gh/glofoxinc/Release_Orchestrator@gh-pages/DOCUMENTATION.html) | Works immediately if Pages is not live yet |

Source: [`DOCUMENTATION.html`](DOCUMENTATION.html) on `main`; static site branch: `gh-pages`.

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
