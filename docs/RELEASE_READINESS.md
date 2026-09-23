# Release Readiness — Can we ship?

Quick go/no-go for **Glofox Customize BI** weekly releases via Cursor MCP.

---

## Go / no-go (operator view)

| Check | Required for live release? | How to verify |
|-------|---------------------------|---------------|
| Jira `.env` | **Yes** | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` set |
| `release-orchestrator` MCP | **Yes** | Cursor → MCP → green; or `setup status` |
| Playwright MCP + M365/Slack login | **Yes** | SharePoint + Slack Step 6; say **playwright confirmed** |
| Full test suite | **Recommended** | `pytest tests/ -q` → 0 failures |
| Operator sign-offs | **Recommended** | **shipit confirmed** · **slack confirmed** |
| `production_ready` gate | Informational | Say **production ready** in chat |
| Teams MCP | Daily Review only | Not blocking weekly PIC+AN release |
| Slack plugin MCP | **No** | Glofox uses Playwright for private channels |

---

## Blocking vs non-blocking

### Blocks a **live** weekly release if missing

1. **Jira credentials** — cannot fetch tickets or create SHIPIT  
2. **Playwright not signed in** — SharePoint upload + Slack Step 6 fail  
3. **Broken `mcp.json`** — MCP server won't start (fix JSON syntax first)

### Does **not** block weekly release (Glofox)

- `production_ready: false` when only `daily_review_mcp` is unverified  
- Slack MCP plugin disabled (Playwright is primary)  
- Graph/MS_GRAPH archived integrations  
- Colleague hasn't finished onboarding (you can still run if your machine is ready)

---

## Pre-release checklist (5 minutes)

```
welcome onboard          # once per clone
setup status             # MCP + .env
fetch review tickets     # Step 1 lock
create release notes     # DOCX + SharePoint
create shipit            # ticket + Slack handoff
test shipit              # dry-run optional but recommended
production ready         # automated report
```

**Phrase map:** `release_mcp/phrase_catalog.py` · tests: `pytest tests/test_guided_phrase_e2e.py -q`

---

## Automated gates

```powershell
cd jira-release-tool
.\.venv\Scripts\python.exe -m pytest tests/ -q
.\.venv\Scripts\python.exe -c "import production_readiness as pr; r=pr.assess_production_readiness(); print(r.get('production_ready'), r.get('launch_complete'))"
```

| Result | Meaning |
|--------|---------|
| `production_ready: True` | Automated checks green |
| `launch_complete: True` | Operator sign-offs recorded |
| Tests 0 failed | Safe to merge / tag release |

---

## Related docs

- [COMPLETE_ONBOARDING.md](./COMPLETE_ONBOARDING.md) — clone → ready flowchart  
- [RUNBOOK.md](./RUNBOOK.md) — recovery, partial Slack, undo  
- [skills/release-orchestrator/SKILL.md](../skills/release-orchestrator/SKILL.md) — weekly playbook
