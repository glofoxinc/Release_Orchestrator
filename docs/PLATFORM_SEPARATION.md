# Platform separation policy

**Status:** Active. The Streamlit UI is **kept in the repo**, separated from MCP — **not removed**.

---

## Layout

| Surface | Physical path | How to run |
|---------|---------------|------------|
| **MCP chat (weekly releases)** | `orchestrator/server/` | `python -m release_mcp` in Cursor |
| **Streamlit platform (optional UI)** | `orchestrator/web/` | `streamlit run app.py` |
| **Shared engine** | `orchestrator/core/` | Imported by both |

Compat import shims at repo root (`release_mcp/`, `release_platform/`) keep existing configs working.

---

## Install options

| Need | Install |
|------|---------|
| MCP weekly releases only | `pip install -r requirements-mcp.txt && pip install -e .` — see [MCP_ONLY_SETUP.md](./MCP_ONLY_SETUP.md) |
| MCP + Streamlit UI | `pip install -r requirements.txt && pip install -e .` — see [SETUP.md](./SETUP.md) |

---

## Why separated

- **MCP** and **web** are different entry points — no shared startup cost
- MCP-only colleagues get a lighter install without losing platform for teams that use the browser UI
- One codebase, clear folders — see [REPO_LAYOUT.md](../REPO_LAYOUT.md)

---

## Policy

- **Do not delete** `orchestrator/web/` — platform remains a first-class deliverable
- Weekly PIC+AN production path is **MCP chat** ([OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md))
- Streamlit is for ticket review tabs, deploy paste UI, DORA dashboard, and Settings when needed

---

## MCP vs platform feature map

| Task | MCP (primary) | Streamlit (optional) |
|------|---------------|----------------------|
| Fetch + lock tickets | `fetch review tickets` | Ticket Review app |
| Release notes DOCX | `create release notes` | Release Notes app |
| SHIPIT | `create shipit` | Service Ticket app |
| Deploy comments | Deploy step in chat | Release Deployer |
| Settings / workspace | `.env` + `profiles/workspace.yaml` | Settings UI |

Both use the same `orchestrator/core/` engine — behavior stays aligned.
