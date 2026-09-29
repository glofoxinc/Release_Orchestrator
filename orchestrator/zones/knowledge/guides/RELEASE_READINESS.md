# Release Readiness — Can we ship?

Quick go/no-go for **Glofox Customize BI daily releases** via Cursor MCP (same golden path each business day).

---

## Go / no-go (operator view)

| Check | Required for live release? | How to verify |
|-------|---------------------------|---------------|
| Jira `.env` | **Yes** | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` set |
| `release-orchestrator` MCP | **Yes** | Cursor → MCP → green; or `setup status` |
| Playwright MCP + M365 login | **Yes** | SharePoint Step 4 + Slack Step 6 (Playwright first); say **playwright confirmed** |
| Full test suite | **Recommended** | `pytest orchestrator/zones/quality/tests/ -q` → 0 failures |
| Operator sign-offs | **Recommended** | **shipit confirmed** · **slack confirmed** |
| `production_ready` gate | Informational | Say **production ready** — tiers in [READINESS_MODEL.md](./READINESS_MODEL.md) |
| Teams MCP | Daily Review meeting only | Not blocking daily PIC+AN release |
| Slack send cascade | **Yes** (both channels) | **Playwright** → **Slack MCP** → bot token; record both permalinks before **slack done** |

---

## Blocking vs non-blocking

### Blocks a **live** daily release if missing

1. **Jira credentials** — cannot fetch tickets or create SHIPIT  
2. **Playwright not signed in** — SharePoint upload + Slack Step 6 fail  
3. **Broken `mcp.json`** — MCP server won't start (fix JSON syntax first)

### Does **not** block daily release (Glofox)

- `production_ready: false` when only `daily_review_mcp` is unverified  
- Slack MCP plugin disabled when Playwright succeeds on both channels  
- Graph/MS_GRAPH archived integrations  
- Colleague hasn't finished onboarding (you can still run if your machine is ready)

---

## Pre-release checklist (5 minutes — repeat each business day)

```
welcome onboard          # once per clone
setup status             # MCP + .env
fetch review tickets     # Jira lock + PR gate
create release notes     # DOCX
sharepoint done + URL    # receipt recorded
create shipit            # SHIPIT + schedule
send slack               # both channels
slack done               # receipt
production ready         # automated report (informational)
```

**Launch evidence (10/10):** one full live day completing  
Jira → PR gate → DOCX → SharePoint receipt → SHIPIT → both Slack receipts, with restart/retry and no duplicate writes.

**Phrase map:** `release_mcp/phrase_catalog.py` · tests: `pytest orchestrator/zones/quality/tests/test_guided_phrase_e2e.py -q`

---

## Automated gates

```powershell
cd jira-release-tool
.\.venv\Scripts\python.exe -m pytest orchestrator/zones/quality/tests/ -q
.\.venv\Scripts\python.exe -c "import production_readiness as pr; r=pr.assess_production_readiness(); print(r.get('production_ready'), r.get('launch_complete'))"
```

| Result | Meaning |
|--------|---------|
| `production_ready: True` | Automated checks green |
| `launch_complete: True` | Operator sign-offs recorded |
| Tests 0 failed | Safe to merge / tag release |

---

## Readiness tiers (summary)

Full detail: [READINESS_MODEL.md](./READINESS_MODEL.md)

| Tier | Meaning |
|------|---------|
| **release_capable** | Jira, SHIPIT, team scope, schedule, Slack path configured |
| **integration_ready** | Above + MCP onboarding + verified Slack send (or Playwright fallback) |
| **launch_evidence_complete** | Above + sign-offs + one live daily golden path (Jira → PR gate → DOCX → SharePoint → SHIPIT → both Slack channels) |

```powershell
python -c "import production_readiness as pr; print(pr.assess_readiness_tiers(track='release'))"
python orchestrator/zones/platform/ops/capture_baseline.py --quick
```

---

## Rollout (summary)

Full checklist: [ROLLOUT_CHECKLIST.md](./ROLLOUT_CHECKLIST.md)

| Audience | Action |
|----------|--------|
| **You** | Dry-run **`week release`** end-to-end; optional Streamlit smoke |
| **New colleague** | Share [GUIDE.md](./GUIDE.md) → **`welcome onboard`** once |
| **Daily ops** | **`week release`** each business day ([GUIDE.md § Daily release](./GUIDE.md#daily-release)) |

---

## Related docs

- [GUIDE.md](./GUIDE.md) — install, setup, daily release  
- [RUNBOOK.md](./RUNBOOK.md) — recovery, partial Slack, undo  
- [skills/release-orchestrator-mcp/SKILL.md](../skills/release-orchestrator-mcp/SKILL.md) — daily release playbook
