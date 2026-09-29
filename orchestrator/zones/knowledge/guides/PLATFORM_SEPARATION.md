# Platform separation policy

**Status:** Active. The Streamlit UI is **kept in the repo**, separated from MCP — **not removed**.

---

## Layout

| Surface | Physical path | How to run |
|---------|---------------|------------|
| **MCP chat (daily releases)** | `orchestrator/zones/product/mcp/` | `python -m release_mcp` in Cursor |
| **Streamlit platform (optional UI)** | `orchestrator/zones/product/ui/` | `streamlit run orchestrator/entry/app.py` |
| **Shared engine** | `orchestrator/zones/product/engine/` | Imported by both |

Compat import shims at repo root (`release_mcp/`, `release_platform/`) keep existing configs working.

---

## Install options

| Need | Install |
|------|---------|
| MCP daily releases only | `pip install -r orchestrator/zones/config/deps/requirements-mcp.txt && pip install -e .` — see [MCP_ONLY_SETUP.md](./MCP_ONLY_SETUP.md) |
| MCP + Streamlit UI | `pip install -r orchestrator/zones/config/deps/requirements.txt && pip install -e .` — see [SETUP.md](./SETUP.md) |

---

## Why separated

- **MCP** and **web** are different entry points — no shared startup cost
- MCP-only colleagues get a lighter install without losing platform for teams that use the browser UI
- One codebase, clear folders — see [REPO_LAYOUT.md](REPO_LAYOUT.md)

---

## Policy

- **Do not delete** `orchestrator/zones/product/ui/` — platform remains a first-class deliverable
- Daily PIC+AN production path is **MCP chat** ([GUIDE.md](./GUIDE.md))
- Streamlit is for ticket review tabs, deploy paste UI, DORA dashboard, and Settings when needed

---

## MCP vs platform feature map

| Task | MCP (primary) | Streamlit (optional) |
|------|---------------|----------------------|
| Fetch + lock tickets | `fetch review tickets` | Ticket Review app |
| Release notes DOCX | `create release notes` | Release Notes app |
| SHIPIT | `create shipit` | Service Ticket app |
| Deploy comments | Deploy step in chat | Release Deployer |
| Settings / workspace | `.env` + `orchestrator/zones/config/profiles/workspace.yaml` | Settings UI |

Both use the same `orchestrator/zones/product/engine/` engine — behavior stays aligned.
