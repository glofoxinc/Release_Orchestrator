# Runtime state map

All operator/runtime artifacts live under **`.state/`** at the repo root (gitignored). Config stays in **`profiles/`** and **`.env`**.

| Path | Purpose |
|------|---------|
| `.state/mcp_wizard_sessions/` | MCP wizard workflow JSON sessions |
| `.state/mcp_wizard_sessions/.confirmation_secret` | HMAC secret for confirm tokens |
| `.state/mcp_onboarding_state.json` | Welcome-onboard / MCP setup progress |
| `.state/deploy_draft.json` | Streamlit deployer draft (desktop recovery) |
| `.state/deploy_draft.rn_docx.bin` | Large DOCX sidecar for deploy draft |
| `.state/operator_signoff.json` | SHIPIT dry-run + Slack live sign-offs |
| `.state/deployment_history.json` | Local deployment history |
| `.state/workspaces/{name}/…` | Same files scoped per multi-workspace |
| `.launch/baseline_evidence.json` | Sanitized CI/readiness baseline (no secrets) |
| `orchestrator/zones/product/agents/review/.state/` | Daily Review agent runtime (meetings, schedule) |

## Migrate legacy paths

If sessions were created before v3.5 structure rework:

```powershell
python orchestrator/zones/platform/ops/migrate_state.py --dry-run
python orchestrator/zones/platform/ops/migrate_state.py --apply
```

Legacy locations merged: repo-root `.mcp_wizard_sessions/`, `orchestrator/.mcp_wizard_sessions/`, and root/orchestrator/core dotfiles.
