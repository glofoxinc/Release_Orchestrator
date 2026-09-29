# Readiness model (v3.5)

Three tiers, scoped by onboarding **track** (`release`, `daily_review`, `both`):

| Tier | Meaning |
|------|---------|
| **release_capable** | Jira, SHIPIT metadata, team scope, schedule, Slack path configured |
| **integration_ready** | Tier 1 + MCP onboarding + verified Slack send path (or Playwright fallback) |
| **launch_evidence_complete** | Tier 2 + operator sign-offs + one successful **daily** golden-path run: Jira → PR gate → DOCX → SharePoint receipt → SHIPIT → both Slack channels (plus `daily_review_pilot` when track includes Daily Review — one **user-requested** live run, not scheduled) |

## Commands

```powershell
python -c "import production_readiness as pr; print(pr.assess_readiness_tiers(track='release'))"
python orchestrator/zones/platform/ops/capture_baseline.py
```

## Teams naming

| Name | Role |
|------|------|
| Graph `teams_schedule` | Archived release meeting scheduling |
| Playwright Outlook | Daily Review calendar invites |
| Teams MCP | Daily Review group-chat summary + alerts |

Daily PIC/AN release does **not** require Teams MCP or Graph Teams scheduling (those are for the separate Daily Review meeting track).
