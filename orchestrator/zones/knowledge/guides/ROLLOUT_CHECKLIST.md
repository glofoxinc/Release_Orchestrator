# Rollout checklist (you + colleagues)

After pulling the `orchestrator/` restructure:

## You (this week)

- [ ] `pip install -e .` in repo venv
- [ ] Cursor MCP still uses `args: ["-m", "release_mcp"]`
- [ ] Dry-run: **`week release`** → `yes` → `create release notes` → `sharepoint done` → `create shipit` → (skip or test) `send slack` → `slack done`
- [ ] Optional: `streamlit run orchestrator/entry/app.py` — confirm UI loads

## New colleague

- [ ] Share [MCP_ONLY_SETUP.md](./MCP_ONLY_SETUP.md)
- [ ] They run **`welcome onboard`** once
- [ ] Daily: [GUIDE.md § Daily release](./GUIDE.md#daily-release) — **`week release`**

## Platform users

- [ ] [SETUP.md](./SETUP.md) + `streamlit run orchestrator/entry/app.py`
- [ ] Platform code lives in `orchestrator/zones/product/ui/` — not removed ([PLATFORM_SEPARATION.md](./PLATFORM_SEPARATION.md))
