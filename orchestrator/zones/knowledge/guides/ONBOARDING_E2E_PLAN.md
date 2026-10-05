# Onboarding E2E plan (implemented baseline)

## Goal

Reduce first-time **12/12** onboarding from **60+ minutes** of debugging to a **preflight-gated, auto-repair** flow. Stretch: **core ready in 3–5 minutes** when Jira token exists; full Playwright sign-in remains MFA-bound.

## E2E flow (operator)

```text
1. Clone → open repo root in Cursor
2. python orchestrator/zones/platform/ops/onboarding_preflight.py [--fix]
3. Reload Cursor MCP once (if --fix or merge ran)
4. Chat: welcome onboard → continue through wizard
5. production ready (informational) → week release
```

## E2E flow (automated regression)

| Test file | Covers |
|-----------|--------|
| `test_onboarding_preflight.py` | Paths, pinned Playwright MCP, preflight shape, pip requirements |
| `test_onboarding_e2e.py` | MCP merge, deprecated server detection, wizard advance |
| `test_beginner_wizard.py` | Routing, starter keys |
| `test_setup_mcp.py` | Deprecated daily-review-agent validation |
| `test_mcp_daily_review_registration.py` | DR tools on unified server |

Run:

```powershell
python -m pytest orchestrator/zones/quality/tests/test_onboarding_preflight.py orchestrator/zones/quality/tests/test_onboarding_e2e.py -q
```

## Implemented fixes (Sprint A)

- Wizard pip → canonical `requirements-mcp.txt`
- Wizard npm → `orchestrator/zones/platform/ops/daily_review/setup.ps1`
- Package step checks `import release_mcp`
- Playwright MCP: pinned `@playwright/mcp@0.0.39`, PATH injection for Node
- Removed hardcoded developer Node path in teams bridge
- Unified `.env` path via `orchestrator/zones/runtime/local/.env`
- `onboarding_preflight` module + MCP tool + CLI
- Short MCP tool alias `dr_cal_handoff`
- Preflight on wizard welcome step

## Next (Sprint B)

- MCP live ping after reload (not file-only)
- CI grep gate for `orchestrator/ops/` strings
- Telemetry `.state/onboarding_telemetry.jsonl`
- Optional: shorten more MCP tool names >40 chars
