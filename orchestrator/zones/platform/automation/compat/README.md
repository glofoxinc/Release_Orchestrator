# Import aliases (`orchestrator/aliases/`)

Thin packages that keep existing commands working after the 4-folder layout.

| Alias | Maps to | Run |
|-------|---------|-----|
| `release_mcp` | `orchestrator/zones/product/mcp/` | `python -m release_mcp` |
| `release_platform` | `orchestrator/zones/product/ui/` | `streamlit run orchestrator/entry/app.py` |
| `daily_review_agent` | `orchestrator/zones/product/agents/review/` | `python -m daily_review_agent` |
| `mcp_server` | legacy → `release_mcp` | `python -m mcp_server` |
| `common` | `orchestrator/shared/common/` | `import common` |
| `generators` | `orchestrator/generators/` | `import generators` |
| `persistence` | `orchestrator/shared/persistence/` | `import persistence` |

After clone: run `tools\bin\setup.bat` (installs `pip install -e .` and wires aliases).
