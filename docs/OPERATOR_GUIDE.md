# Release Orchestrator — Operator Guide

**One page for weekly releases.** Say these phrases in Cursor chat (`release_orchestrator` MCP).

For first-time machine setup: **[MCP_ONLY_SETUP.md](./MCP_ONLY_SETUP.md)** (~10 min) or [COMPLETE_ONBOARDING.md](./COMPLETE_ONBOARDING.md) (full).

---

## Fast path (one phrase to start)

Say **`week release`** (same as **`full release`**) → then **`yes`** at each step.

You still control Slack (`send slack`) and SharePoint (`sharepoint done`) — nothing auto-posts.

---

## One-time setup (5 minutes)

1. Copy `.env.example` → `.env` and set:
   - `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
   - `GITHUB_TOKEN` or `GH_TOKEN` (PR merge check on release fetch)
2. Cursor MCP → `release-orchestrator` server pointed at this repo.
3. Say **`welcome onboard`** once if a colleague set up the repo for you.

---

## Weekly release — say this in order

| # | Say in chat | What happens |
|---|-------------|--------------|
| 1 | **`fetch review tickets`** | Fetches PIC + AN review-ready tickets and locks them for release |
| 2 | **`yes`** | Confirms the locked list |
| 3 | **`create release notes`** | Builds Word doc → SharePoint upload handoff |
| 4 | **`sharepoint done`** + paste URL | Saves SharePoint link (after upload) |
| 5 | **`create shipit`** | Creates SHIPIT change ticket |
| 6 | **`send slack`** | Posts to both Slack channels (preview first) |
| 7 | **`slack done`** | Continues after you posted |
| 8 | Deploy step | Paste deployment info when prompted, or use Streamlit Deployer |

**Optional (any time):**

| Say | Does |
|-----|------|
| **`fetch release tickets`** | List release-ready tickets only (no lock) + PR check |
| **`skip slack`** | Skip Slack and continue |
| **`help`** | Current step hints |

---

## Jira rules (must know)

| When | Ticket needs |
|------|----------------|
| Review fetch | Jira comment: **ready for review** |
| Release fetch / notes | Jira comment: **ready for release** |
| Release fetch | GitHub PR **merged** (open PR → bot comments assignee on Jira) |

Status alone is **not** enough for fetch.

---

## Slack message (automatic)

Posted to **`#insights-customize-squad`** and **`#customize-bi-buddies`** when you say **`send slack`**:

- SharePoint **download** link + **folder** link  
- Service Desk (SHIPIT) link  
- **Squad CC:** Sushma, Sai Anirudh, Zeke, Eoin  
- **Buddies CC:** Sushma only  

Slack is **never auto-posted** — you must say **`send slack`**.

---

## Quick fixes

| Problem | Fix |
|---------|-----|
| Ticket not in fetch list | Add **ready for review** or **ready for release** comment on Jira |
| PR blocked | Merge PR on GitHub; re-run **`fetch release tickets`** |
| SharePoint | Say **`upload sharepoint`**, upload in browser, then **`sharepoint done`** + URL |
| Slack failed | Say **`send slack playwright`** or post manually, then **`slack done`** |
| Start over | Say **`welcome`** |

---

## Streamlit UI (optional)

Same flows in the browser: **Ticket Review** → **Release Notes** → **Service Ticket** → **Release Deployer**.

```powershell
streamlit run app.py
```

Most teams use **MCP chat only** for weekly releases.

---

## More detail (only if needed)

| Topic | Doc |
|-------|-----|
| First clone + MCP install | [COMPLETE_ONBOARDING.md](./COMPLETE_ONBOARDING.md) |
| Incidents / undo | [RUNBOOK.md](./RUNBOOK.md) |
| Pre-release checks | [RELEASE_READINESS.md](./RELEASE_READINESS.md) |
