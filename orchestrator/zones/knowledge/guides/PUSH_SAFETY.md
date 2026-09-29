# Push safety

Never commit secrets. Before `git push`:

```powershell
orchestrator\zones\platform\automation\check_push_safe.ps1
```

## Safe to commit

| Path | Notes |
|------|-------|
| `orchestrator/zones/runtime/local/.env.example` | Placeholders only |
| `orchestrator/zones/config/orchestrator/zones/config/profiles/workspace.yaml` | Team settings — no API tokens |

## Never commit

| Path | Why |
|------|-----|
| `orchestrator/zones/runtime/local/.env` | API tokens |
| `.cursor/mcp.json` / `orchestrator/.cursor/mcp.json` | May contain tokens |
| `orchestrator/zones/runtime/state/` | Local runtime |
