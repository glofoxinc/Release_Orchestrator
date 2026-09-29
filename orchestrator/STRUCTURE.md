# orchestrator/ — zone map

Everything lives inside **`orchestrator/`** in nested zones. Repo root only has `.git`, `.github`, `README.md`, `pyproject.toml`.

```
orchestrator/
├── entry/                    # app.py, cli.py
├── zones/
│   ├── product/              # Runnable code
│   │   ├── engine/           # Jira, gates, Slack, SHIPIT
│   │   ├── mcp/              # MCP chat server
│   │   ├── ui/               # Streamlit
│   │   ├── agents/review/    # Daily Review
│   │   ├── generators/
│   │   └── lib/              # common + persistence
│   ├── config/
│   │   ├── profiles/         # workspace.yaml
│   │   ├── assets/templates/
│   │   ├── aliases/          # release_mcp, daily_review_agent, …
│   │   └── deps/             # orchestrator/zones/config/deps/requirements.txt
│   ├── platform/
│   │   ├── ops/              # verify, sign-off scripts
│   │   ├── automation/       # setup.bat, launchers
│   │   └── ci/               # gitleaks, pre-commit
│   ├── knowledge/
│   │   ├── guides/           # all .md docs
│   │   ├── skills/
│   │   └── examples/
│   ├── quality/tests/        # pytest
│   └── runtime/              # gitignored local only
│       ├── state/
│       ├── cache/
│       ├── local/.env        # secrets (never commit)
│       ├── launch/
│       └── streamlit/
├── .cursor/                  # MCP config (junction from repo root)
└── paths.py
```

## Why `.git` / `.github` stay outside

Git and GitHub **require** those folders at the repository root — they cannot move inside `orchestrator/`.

## Commands

| Task | Command |
|------|---------|
| Setup | `orchestrator\zones\platform\automation\bin\setup.bat` |
| MCP | `python -m release_mcp` |
| UI | `streamlit run orchestrator\entry\app.py` |
| Tests | `pytest orchestrator\zones\quality\tests\` |
