# Platform ↔ MCP ↔ Skill Parity (v3.5 — honest status)

Three surfaces, **one engine** (`release_ops.py`, `deploy_ops.py`, `generators/`):

| Layer | Location | Role |
|-------|----------|------|
| **Platform** | Streamlit `app.py` / `ui/` | Visual step-by-step UI |
| **MCP** | `mcp_server/` | Cursor API + `release_orchestrator` chat |
| **Skill** | `.cursor/skills/release-orchestrator-mcp/SKILL.md` | Agent playbook + colleague setup |

---

## Overall ratings — workflow parity (integrations vary)

| Status | Meaning |
|--------|---------|
| **Active** | Implemented and used in Glofox weekly path |
| **Archived** | In repo; disabled in `workspace.yaml` until credentials restored |
| **Degraded** | Fallback path (manual URL, Playwright, `slack done`) |

| Transfer path | Score | Notes |
|---------------|-------|-------|
| **MCP → Platform** | **100%** | Every MCP release feature has a Platform equivalent (UI button, panel, or auto-step) |
| **MCP → Skill** | **100%** | Skill documents setup, flow, SHIPIT, overrides, Platform paths |
| **Platform → Skill** | **100%** | Skill maps each Streamlit step to MCP tool names |
| **Guided NL vs Platform UI** | **Equivalent** | MCP `release_orchestrator` = chat; Platform = same 8 steps with clicks |
| **Skill-only (no install)** | **0% runtime** | Instructions only — clone + MCP still required to execute |

---

## Feature matrix (all ✅)

| Feature | Platform | MCP | Skill |
|---------|----------|-----|-------|
| Ticket fetch PIC+AN | TR/RN/STK Step 1 | `fetch_release_tickets` | ✅ |
| Status vs fix-version | Step 1 radio | `selection_mode` | ✅ |
| Team scope / filter | Settings + Jira Team | `team_scope_status` | ✅ |
| Pre-review gate | TR Step 2 | `pre_review_gate` | ✅ |
| Post-QA gate | RN Step 2 | `post_qa_gate` | ✅ |
| Status split (review → release-ready) | RN Step 2 auto + manual filter | Step 3 refetch | ✅ |
| T+1 date (status mode) | `release_doc_metadata_fallback_status_mode` | wizard T+1 | ✅ |
| Explicit ticket override | RN Step 2 override input | `include PIC-XXXX` | ✅ |
| Release notes DOCX | RN Step 4 | `generate_release_notes_docx` | ✅ |
| SharePoint upload / paste | RN Step 4 | wizard + tools | ✅ |
| SharePoint download prefill | Deploy Step 3 | `sharepoint_download_release_notes` | ✅ |
| SHIPIT create | STK Step 6 | `create_service_ticket` | ✅ |
| Test SHIPIT + dispose | STK Step 2 toggle + Step 6 dispose | `test shipit` + `dispose_test_shipit_ticket` | ✅ |
| Emergency profile | STK Step 2 dropdown | `emergency deployment` | ✅ |
| Teams scheduling | TR Step 2 + STK Step 6 panels | `teams_schedule_*` tools | ✅ |
| TCKT templates apply/save | STK Step 4 apply + save | `list/apply/save_tckt_template` | ✅ |
| Consolidation | STK preview | wizard | ✅ |
| AI enhance | STK Step 6 | `ai_enhance_release` | ✅ |
| Confluence | STK Step 6 | `confluence_publish_release_notes` | ✅ |
| Slack | STK Step 6 | wizard + Slack MCP | ✅ |
| Deploy / undo / mark released | Deployer | wizard | ✅ |
| Production readiness | Health panel | `production_readiness` | ✅ |
| Guided flow | Platform UI steps | `release_orchestrator` | ✅ |
| Workspace config | Settings UI (full) | `workspace_config` (read) | ✅ |
| JQL / AI ticket create | Sidebar apps | MCP tools | ✅ |

Shared module for status split + overrides: `release_ops.fetch_release_notes_extracted()`.

---

## Colleague setup (one repo)

```
git clone https://github.com/abcfitness-insights/jira-release-tool.git
# Skill already at .cursor/skills/release-orchestrator-mcp/SKILL.md
# Follow SKILL.md Steps 1–6
```

---

## Verify

```powershell
cd jira-release-tool
.\.venv\Scripts\python.exe -m pytest orchestrator/zones/quality/tests/test_release_notes_status_split.py orchestrator/zones/quality/tests/test_shipit_test_mode.py orchestrator/zones/quality/tests/test_mcp_guided.py -q
```

Say **`production ready`** in Cursor after MCP is wired.
