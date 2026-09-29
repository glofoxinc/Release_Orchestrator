# MCP-only setup (~10 minutes)

**For weekly PIC+AN releases in Cursor chat.** No Streamlit, no Daily Review.

Deployment Bot–simple install path, with full Orchestrator gates and workflow.

---

## Install

```powershell
git clone <repo-url> release-orchestrator
cd release-orchestrator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-mcp.txt
pip install -e .
```

## Configure

1. Copy `.env.example` → `.env`
2. Set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
3. Optional: `GITHUB_TOKEN` (PR merge check)

## Cursor MCP

```json
{
  "mcpServers": {
    "release-orchestrator": {
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "release_mcp"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

Enable **Playwright** MCP (SharePoint + Slack browser handoff).

## First chat

Say **`welcome onboard`** → pick **`release only`** → follow prompts → **`continue`** each step.

When setup completes, use **[OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md)** every week.

---

## Weekly (fast path)

| Say once | Then confirm at each step |
|----------|---------------------------|
| **`week release`** | `yes` → `create release notes` → `sharepoint done` → `create shipit` → `send slack` → `slack done` |

Same as **`full release`** — starts the standard PIC+AN flow.

---

## When you need more

| Need | Install |
|------|---------|
| Streamlit UI | `pip install streamlit pandas pywebview` → [SETUP.md](./SETUP.md) |
| Daily Review 6 PM | `pip install -r requirements.txt` → [COMPLETE_ONBOARDING.md](./COMPLETE_ONBOARDING.md) |
