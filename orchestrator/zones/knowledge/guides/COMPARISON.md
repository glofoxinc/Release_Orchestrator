# Orchestrator vs Deployment Bot (Glofox PIC+AN)

Updated after `orchestrator/` restructure + MCP-only path.

| Dimension | **Release Orchestrator** | Deployment Bot |
|-----------|--------------------------|----------------|
| **Using (weekly)** | **9/10** — `week release` + your status/comment gates | 6/10 — Fix Version model, wrong gate model |
| **Onboarding** | **8/10** — [MCP_ONLY_SETUP.md](./MCP_ONLY_SETUP.md) ~10 min | 9/10 — skill only, but wrong workflow |
| **Size** | **7/10** with MCP-only install* / 4/10 full | 10/10 |
| **Performance** | **8/10** MCP-only* / 6/10 full | 9/10 |
| **Workflow fit** | **10/10** | 5/10 |

\* Use `pip install -r orchestrator/zones/config/deps/requirements-mcp.txt` — skips Streamlit. Platform stays in `orchestrator/zones/product/ui/` — see [PLATFORM_SEPARATION.md](./PLATFORM_SEPARATION.md).

---

## Why Orchestrator wins for Glofox

1. **Correct release model** — review-ready + comment gates, not Fix Version only  
2. **PR gate + Jira assignee comments** on fetch  
3. **Ticket lock + drift detection**  
4. **Dual Slack channels** with squad/buddies CC rules  
5. **Deploy history + SHIPIT parity**  
6. **Optional Daily Review** (Deployment Bot has none)

---

## Where Deployment Bot is still smaller

- ~7 Python files vs Orchestrator’s MCP path (~200 product files)  
- One prompt per Fix Version  
- No MCP server process  

Orchestrator closes the gap with **`week release`** (one phrase start) and **MCP-only install** without removing features you rely on.

---

## Recommendation

**Production:** Orchestrator MCP chat ([GUIDE.md](./GUIDE.md))  
**Platform:** Separated in `orchestrator/zones/product/ui/` — not removed ([PLATFORM_SEPARATION.md](./PLATFORM_SEPARATION.md))
