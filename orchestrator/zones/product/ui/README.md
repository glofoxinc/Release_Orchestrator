# Platform (Streamlit UI)

Click-through daily release UI — same 8 steps as MCP.

| Item | Location |
|------|----------|
| Entry | `release_platform/app.py` (also `streamlit run orchestrator/entry/app.py` at repo root) |
| Pages | `release_platform/ui/` |
| Python package | `release_platform` (import: `from release_platform.ui import ...`) |
| Legacy tests | `ui.*` aliases to `release_platform.ui.*` via test bootstrap |

Shared engine (Jira, DOCX, SHIPIT, Slack) lives at repo root (`config.py`, `deploy_ops.py`, etc.).
