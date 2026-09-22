# Legacy scripts (deprecated)

These scripts predate the Daily Review merge (v3.4). **Do not use for production.**

| Script | Replacement |
|--------|-------------|
| `graph_explorer_schedule_demo.py` | `daily_review_outlook_login` + `daily_review_run_live` |
| `schedule_demo_delegated.py` | `daily_review_demo_call` |
| `schedule_demo_device_code.py` | `daily_review_outlook_login` |
| `schedule_demo_outlook_com.py` | Playwright Outlook (`scripts/daily_review/*.mjs`) |
| `open_demo_teams_link.py` | `daily_review_demo_call` |
| `fetch_demo_teams_link.py` | Teams MCP |

Production path: `.\scripts\setup_e2e.ps1` → `daily_review_orchestrator(message="daily review welcome")`.
