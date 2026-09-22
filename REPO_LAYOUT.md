# Repository layout (Platform · MCP · Skill)

Three deliverables, one repo. Shared Jira/DOCX/SHIPIT engine stays at repo root until a future `core/` extraction.

```
jira-release-tool/
├── release_platform/      # Streamlit UI (import: release_platform; legacy: ui.*)
│   ├── app.py
│   └── ui/
├── release_mcp/           # Release Orchestrator MCP (python -m release_mcp)
│   ├── server.py          # MCP tool registry
│   ├── guided.py          # release_orchestrator chat
│   ├── onboarding*.py     # welcome onboard flow
│   └── steps/             # Per-step catalog + release_step_status
├── mcp/                   # Pointer README only (package is release_mcp)
├── skills/
│   └── release-orchestrator/
│       └── SKILL.md       # Colleague playbook (share this folder)
├── mcp_server/            # Legacy shim (-m mcp_server still works)
├── templates/             # DOCX, Slack, onboarding YAML
├── config.py, jira_client.py, deploy_ops.py, …  # shared engine
└── archive/               # Retired configs (e.g. teams_schedule)
```

## Colleague quick start

1. Clone → venv → `.env` from `.env.example`
2. Cursor MCP: `args: ["-m", "release_mcp"]`
3. Chat: **`welcome onboard!`** → team + crew → **`full release`**

## Weekly release (chat)

`yes` → `yes` → SharePoint → `yes` → `send slack` → `yes deploy`

MCP step tools: **`release_step_status`** (empty = full map), **`release_step_catalog`**, **`release_step_<id>`** (onboarding, ticket_review, slack, deploy, …).
