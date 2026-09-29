# Repository layout

Modern **`orchestrator/`** package — no loose Python at repo root except entrypoints (`app.py`, `cli.py`).

**Weekly operator:** [docs/OPERATOR_GUIDE.md](docs/OPERATOR_GUIDE.md)  
**Doc index:** [docs/README.md](docs/README.md)

---

## Top level

```
release-orchestrator/
├── orchestrator/           # All product code
│   ├── core/               # Shared engine (Jira, gates, deploy, Slack, SHIPIT)
│   ├── server/             # MCP chat server (import alias: release_mcp)
│   ├── web/                # Streamlit UI (import alias: release_platform)
│   ├── agents/
│   │   └── review/         # 6 PM review agent (import alias: daily_review_agent)
│   ├── generators/         # DOCX release notes
│   ├── shared/
│   │   ├── common/
│   │   └── persistence/
│   ├── ops/                # Preflight / verify scripts (not MCP runtime)
│   └── tools/              # One-off maintenance scripts
├── profiles/
│   ├── workspace.yaml      # Team + integration settings
│   └── workspaces/         # Alternate workspace profiles
├── assets/
│   └── templates/          # Jinja2 (Slack, DOCX, onboarding)
├── docs/
├── tests/
├── skills/
├── release_mcp/            # Thin compat shim → orchestrator/server/
├── release_platform/       # Thin compat shim → orchestrator/web/
├── daily_review_agent/     # Thin compat shim → orchestrator/agents/review/
├── mcp_server/             # Legacy MCP entry (-m mcp_server)
├── app.py                  # Streamlit launcher
└── cli.py                  # CLI launcher
```

---

## Import aliases (unchanged for colleagues)

| Say / configure | Physical path |
|-----------------|---------------|
| `python -m release_mcp` | `orchestrator/server/` |
| `streamlit run app.py` | `orchestrator/web/` |
| `python -m daily_review_agent` | `orchestrator/agents/review/` |
| `import config`, `import jira_client` | `orchestrator/core/` |
| Ops scripts | `orchestrator/ops/` |

Cursor MCP config stays: `args: ["-m", "release_mcp"]` — no change required.

---

## Weekly path (code flow)

```
orchestrator/server/guided.py
  → orchestrator/core/ (jira_client, release_gates, slack_announce, …)
  → orchestrator/generators/
  → assets/templates/
```

---

## Folder sizes (~`.py` files)

| Path | ~Files | Role |
|------|--------|------|
| `orchestrator/core/` | 62 | Engine |
| `orchestrator/server/` | 36 | MCP |
| `orchestrator/web/` | 57 | Streamlit |
| `orchestrator/agents/review/` | 29 | Daily review |
| `orchestrator/ops/` | 13 + legacy | Manual ops |
| `tests/` | 166 | Offline pytest |

---

## Weekly release (chat)

`fetch review tickets` → `yes` → `create release notes` → `sharepoint done` → `create shipit` → `send slack` → `slack done`
