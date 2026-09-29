# Rollout checklist (you + colleagues)

After pulling the `orchestrator/` restructure:

## You (this week)

- [ ] `pip install -e .` in repo venv
- [ ] Cursor MCP still uses `args: ["-m", "release_mcp"]`
- [ ] Dry-run: **`week release`** → `yes` → `create release notes` → `sharepoint done` → `create shipit` → (skip or test) `send slack` → `slack done`
- [ ] Optional: `streamlit run app.py` — confirm UI loads

## New colleague

- [ ] Share [MCP_ONLY_SETUP.md](./MCP_ONLY_SETUP.md)
- [ ] They run **`welcome onboard`** once
- [ ] Weekly: [OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md) only

## Platform users

- [ ] [SETUP.md](./SETUP.md) + `streamlit run app.py`
- [ ] Platform code lives in `orchestrator/web/` — not removed ([PLATFORM_SEPARATION.md](./PLATFORM_SEPARATION.md))
