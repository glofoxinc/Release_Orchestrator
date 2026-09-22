# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [3.0.2] - 2026-09-08

### Added

- **`shipit_preflight.py`** — SHIPIT metadata, assignment group (Jira group API), and dry-run create preflight.
- **`release_notes_compare.py`** — DOCX v4 section + fingerprint compare vs reference fixture.
- **CLI scripts:** `scripts/shipit_preflight.py`, `scripts/compare_release_notes_docx.py`, `scripts/release_signoff_checklist.py` (automated sign-off runner with VERIFIED / OPERATOR REQUIRED table).

### Changed

- User-facing copy: remaining Lean v3 / TCKT strings → DOCX v4 / SHIPIT in readiness, health, FAQ, TUTORIALS, MCP docstrings.
- **`assignment_group_name` cleared** in `workspace.yaml` — live Jira group lookup returned HTTP 400 for `Insights Analyze/Customize`; field remains optional on SHIPIT.

## [3.0.1] - 2026-09-08

### Added

- **Archived integration configs:** `archive/slack_announce.yaml`, `archive/teams_schedule.yaml`, `archive/sharepoint_upload.yaml` — restore to `workspace.yaml` and set `enabled: true` when IT provisions tokens.
- **Reference fixture:** `tests/fixtures/Release Notes 2026.3.09.09.docx` for DOCX v4 parity tests.

### Changed

- **Active release path:** Ticket Review → Release Notes DOCX v4 → manual SharePoint URL → SHIPIT create → Deployer. Slack announce, Teams scheduling, and SharePoint Graph auto-upload are archived (`enabled: false`, `archived: true`).
- **Release gates:** `slack_notify: false` on pre-review and post-QA (assignee DMs archived with Slack).
- **UI/MCP:** Archived integrations hidden or stubbed with `{archived: true, restore: "archive/..."}`; operator guide and home dashboard reflect active path only.
- **SHIPIT defaults:** `assignment_group_name: "Insights Analyze/Customize"` (optional; blank if Jira group name differs).
- **User-facing labels:** SHIPIT replaces TCKT in workflow copy, sidebar, and docs (internal `TCKT_*` config aliases unchanged).

### Fixed

- Integration readiness and `verify_integrations.py` report archived Slack/Teams/Graph as SKIP, not FAIL.
- Settings Integrations tab no longer renders Teams editor when archived.

## [Unreleased]

## [3.2.0] - 2026-09-11

### Added

- **Operator sign-off tracking** — `operator_signoff.py`, `record_operator_signoff()`
  MCP tool, platform Home buttons, phrases **shipit confirmed** / **slack confirmed**.
- **`scripts/complete_launch.py`** — final launch runner (pytest + readiness + optional
  SHIPIT dry-run sign-off). **`launch_complete`** when all operator checks recorded.

## [3.1.6] - 2026-09-11

### Added

- **Slack via Cursor Slack MCP** — Step 6 posts with `slack_send_message`; **no
  `SLACK_BOT_TOKEN`** required when releasing from Cursor. Say **send slack** →
  agent posts → **slack done**.
- **`production_readiness()`** — shared MCP + platform report (VERIFIED /
  UNVERIFIED / OPERATOR REQUIRED). Home dashboard + Settings show the same panel.

### Changed

- Onboarding no longer pushes bot token setup — Slack MCP is the default path.
- `SLACK_BOT_TOKEN` optional (platform UI auto-send only).

## [3.1.5] - 2026-09-11

### Added

- **`mcp_production_readiness()`** — honest VERIFIED / UNVERIFIED / OPERATOR REQUIRED
  report; say **production ready** in `release_orchestrator` for the same check.
- **Emergency deployment profile** — MCP phrase **emergency deployment** at Step 5;
  platform profile picker applies IST window + Emergency change type.

### Fixed

- **Deployment window timezone intelligence** — team agrees **10:30–11:30 AM IST**;
  Jira planned start/end fields store the **same instant in US Central (CST/CDT)**.
  Ticket text, MCP wizard, platform UI, and `create_service_ticket` all use
  `resolve_jira_schedule()` so approvers see both clocks and the change is not
  closed early. Corrects v3.1.3 treating 10:30 as CST clock time instead of IST.
- **Docs** — `INTEGRATIONS.md` Slack active (not archived); signoff script footer updated.

## [3.1.4] - 2026-09-11

### Added

- **Onboarding flow** — `onboarding` / `setup status` shows a step-by-step checklist for
  new clones: venv, `.env`, Jira credentials (with Atlassian token URL), Cursor MCP JSON,
  optional Slack token.
- **What's next** — every guided response includes `whats_next` + hints in `say_to_user`.

## [3.1.3] - 2026-09-11

### Changed

- **Deployment window standardized to CST** — Normal profile **10:30–11:30 AM
  America/Chicago** everywhere (workspace, platform UI, MCP wizard, `create_service_ticket`).
- **`default_deployment_schedule()`** — single source for profile times + timezone.
- **Schedule defaults** — `DEFAULT_SCHEDULE_TZ` / `TCKT_SCHEDULE_TZ` fallback is
  `America/Chicago` (not IST).

## [3.1.2] - 2026-09-11

### Added

- **Slack deployment announce re-enabled** — `workspace.yaml` → `slack_announce.enabled: true`;
  posts to `#insights-customize-squad` and `#customize-bi-buddies` via `SLACK_BOT_TOKEN`.
- **Guided MCP Slack phrases** — `send slack` / `skip slack` at Step 6.
- **Onboarding phrases** — `onboarding`, `let's go`, `start release`, `deploy` all trigger welcome.

### Changed

- **Slack message format** — short deploy notice (SharePoint label + SHIPIT key, CC Sushma + Trent on squad).
- **Release notes Development Team** — default **Customize BI Team** (platform + MCP).
- **Release version in status mode** — always included; derives `vYYYY.Q.MM.DD` from planned deploy date when no fix version.
- **Welcome message** — shows full defaults (projects, team, statuses) with override instructions.

### Verified

- **SHIPIT service ticket creation** — 44 dedicated tests pass (preflight, reference, schedule, service desk create).
- **Full test suite** — 1,307 tests pass (100% verification before launch).

## [3.1.0] - 2026-09-11

### Added

- **`release_orchestrator` MCP tool** — primary guided E2E entry: `message="welcome"` → `yes`
  through ticket review, exclusions, release notes, SharePoint, SHIPIT, deploy, mark released.
- **`mcp_server/guided.py`** — natural-language router with `say_to_user`, `user_can_say`,
  auto confirmation-token resolve on **yes**, team aliases (Glofox / Ignite / ETL).
- **`mcp_server/welcome.py`** — status-first fetch defaults (PIC Review + AN Passed QA).
- **Cursor skill** `release-orchestrator-mcp` and **docs/MCP_GUIDED.md**.
- **Tests:** `tests/test_mcp_guided.py`, `tests/test_mcp_welcome.py` (12+ cases).

### Changed

- **`release_wizard`** remains for advanced `start` / `update` / `confirm`; docs steer operators
  to `release_orchestrator` first.
- **`.env.example`** — optional `DEFAULT_JIRA_TEAM`, `DEFAULT_PROJECTS`, `DEFAULT_SELECTION_MODE`.
- **README / RUNBOOK / SETUP** — v3.1 guided MCP as the main release surface.
- **`operator_guide.enrich_tool_response`** — includes `tool` id on every atomic response.

### Fixed

- MCP ops tests patch archived integrations at module import sites (teams/sharepoint/slack).
- SharePoint wizard parity test respects `sharepoint_upload_archived()` gate.

## [3.0.3] - 2026-09-10

### Added

- **Platform hardening (Phases 1–6):** Status-safe snapshot fetch, status-aware drift/relock, SHIPIT status-only metadata, unified session persist, fail-closed scope restore gate, MCP status-only RN + team filter parity, deploy/Confluence MCP tools, `persistence/schema.py`, reference DOCX fixtures, parity matrix in operator guide.
- **`tests/test_drift_gate.py`**, **`tests/test_mcp_release_ops_extended.py`**, golden recovery round-trip tests.
- **`ui/release_picker.py`**, **`batch_app_prerequisites()`**, **`navigate_step()`**, Ticket Review `@st.fragment` checkbox panel.

### Changed

- Home page computes workflow prerequisites once per render (not per app card).
- `list_all_teams()` cached by workspace YAML mtime; invalidated on workspace create.
- Sidebar Quick Stats deferred until operator clicks **Load SHIPIT stats**.
- Release Notes Step 3 readiness panel renders after field editors (accurate score).
- Coverage gate expanded to `jira_client` / `confluence_publisher` (60% floor; suite at ~72%).

### Fixed

- Windows flaky MCP wizard session writes (`wizard_store._replace_with_retry`).
- Confluence upsert test mocks `confluence_find_page_by_title`.
- DOCX parity tests use legacy fixture path when sample data aligns with `2026.3.07.15`.

## [Unreleased prior]

### Added

- **SharePoint upload backend (Graph):** `sharepoint_upload.py` + `ms_graph.py`
  client-credentials helper. Dry-run by default; live PUT to drive folder when
  `sharepoint_upload.enabled` + `MS_GRAPH_*` are set. MCP tools:
  `sharepoint_upload_status`, `sharepoint_upload_release_notes`, and
  `sharepoint_download_release_notes`. Release Notes Step 4 now persists the
  generated bytes and offers preview/live SharePoint upload with manual-link fallback.
- **Teams schedule backend (Graph):** `teams_schedule.py` creates calendar
  events with Teams online meeting (`review` / `deployment`). Dry-run by
  default. MCP tools: `teams_schedule_status`, `teams_schedule_meeting`.
  Ticket Review and Service Ticket now include preview/live Teams scheduling panels.
  Same `MS_GRAPH_*` credentials; targets in `workspace.yaml` → `teams_schedule`.
- **SharePoint deployment-table reader:** Graph sharing-link download plus DOCX
  table extraction supplies deployment IDs, dates, and times to post-deploy comments.

### Changed

- **Service ticket target:** Production deployment changes now create **SHIPIT** Manual Change tickets (desk 2046 / RT 2969). Legacy TCKT config is archived in `archive/service_desk_tckt.yaml`; `config.py` aliases keep `TCKT_*` env var names for compatibility.
- **Release notes format (v4):** Category summary tables, single **Reports / Dashboards Delivered** table, **Ticket Details** 4-column layout, **Testing Evidence** section (replaces Screenshots), sanity checklist removed from generated DOCX. Service ticket ADF description uses Release Summary + Key Highlights + Delivered table. Generator build id: `2026.09.07-rn-format-v4-shipit`.
- **UI labels:** User-facing workflow strings reference SHIPIT where tickets are created; Confluence companion pages follow the new release layout.
- **Home health:** Slack bot-token / channel-ID gaps no longer show as setup
  warnings (optional; configure when you enable announce send).
- **Product rename:** user-facing Jira Toolkit / ReleaseOps branding is now
  **Release Orchestrator**. Package/CLI paths remain `jira-release-tool`.
- **Home Upcoming:** cards now report SharePoint, Teams, and SharePoint Deployer
  integration as UI-wired with Graph credentials pending; Slack remains bot-token pending.
- **Deployer Deployment Info:** auto-prefills IDs/times from Release Notes rows
  + generated DOCX + SharePoint DOCX + deployment history; **Detect from paste** /
  **Fill from Release Notes / SharePoint / History** buttons show the source used.

### Added (Quality gate)

- **Focused acceptance tests:** `tests/test_quality_gate.py` covers write-fingerprint
  replay, drift/re-lock override, UI deploy confirm safety, Slack channel/CC mapping,
  and critical Streamlit/MCP import surfaces.
- **CI gates (proportionate):** Ruff format check, mypy on hardened modules only,
  coverage fail-under for MCP/deploy/Slack/SharePoint/history modules (not brittle
  whole-repo strictness), full pytest suite.
- **Operator runbook:** `docs/RUNBOOK.md` — recovery/undo, MCP sessions, partial
  Slack, deploy procedures, single-user threat model, exact pre-release checklist,
  and live read-only integration preflight instructions.
- **Preflight JQL safety:** `scripts/verify_integrations.py` always scopes search
  and createmeta to a project key (workspace default or `--project`) so Cloud
  unbounded-JQL rejection and createmeta timeouts no longer fail `--check=all`.

### Added (Efficiency / shared deploy executor)

- **Shared executor:** Streamlit Step 5 and MCP/headless deploy both call
  `deploy_ops.execute_deploy` / `undo_deploy` with injectable progress callbacks;
  history and undo behavior stay identical.
- **Safer Jira reads:** shared JQL pagination helper; recent-comments-first
  duplicate-marker check with full-scan fallback; TTL cache for project versions
  (`JIRA_VERSION_CACHE_TTL`, default 300s); optional bounded concurrency for
  read-only preflight only (`JIRA_READONLY_CONCURRENCY`, default 1).
- **Rate limiting:** configurable inter-call pause via `JIRA_RATE_LIMIT_PAUSE`
  (default 0). All Jira **writes** remain sequential and ordered.
- **Tests:** `tests/test_efficiency.py` covers parity, call-count, pause, and
  429 retry regressions.

### Added (Platform operations hardening)

- **Diagnostics:** `ui/health.py` and `scripts/verify_integrations.py` now cover Slack
  bot token presence, read-only Slack channel resolution/membership, Jira Service Desk
  metadata (optional live request-type GET), workspace `slack_announce` schema,
  placeholder credentials, and SharePoint URL host/link-shape checks.
- **Logging:** Streamlit (`app.py`) and MCP (`mcp_server/server.py`) call
  `common.logger.setup_logging` with secret redaction and safe workflow/release
  context (no tokens in context).
- **History:** `.deployment_history.json` records SharePoint URL, TCKT key/URL,
  per-channel Slack outcomes, per-project deploy results, mark-released, and undo
  while remaining backward compatible with legacy entries.
- **Deploy confirm + draft:** Release Deployer Step 5 requires an explicit
  **Confirm & Deploy** click (no execute-on-render). Single-user desktop mode
  persists a secret-free `.deploy_draft.json` for restart recovery.

### Fixed (Slack announce hardening)

- **Partial sends retry only failed channels** in both the Service Ticket UI and
  Release Orchestrator MCP (`skip_channel_keys` / `pending_channel_messages`); already-sent
  channels are not posted again.
- **`slack_announce.enabled=false` no longer blocks Release Deployer** (UI gate
  and MCP auto-skip).
- **MCP `slack_messages` edits preserve the body but cannot drop required CC
  user mentions** — trailing `CC:` is stripped and reappended from config before
  preview/send.
- **Offline validation** of exact channel names and CC mappings
  (`insights-customize-squad` + Sushma/Soumyakant/Trent;
  `customize-bi-buddies` + Sushma/Soumyakant).
- **Legacy webhook notifier** (`SLACK_DEPLOY_WEBHOOK` / `notifier.py`) is
  explicitly documented as deprecated so operators do not confuse it with the
  Bot API announce path.

### Added (Release Orchestrator MCP full workflow parity)

- Added a durable `release_wizard` MCP tool that mirrors the complete PIC + AN
  Streamlit workflow: ticket lock/exclusions, editable Word release notes,
  SharePoint handoff, TCKT preflight/create/assignment verification, Slack,
  deployment, history, undo, and optional mark-released.
- Wizard drafts survive Cursor/MCP restarts and every Jira/Slack write requires
  a content-bound confirmation token from the latest preview.
- Extracted headless service-ticket plans, deployment execution/history, and
  fix-version exclusion operations while preserving existing Streamlit entry
  points. Generic MCP ticket creation now defaults to dry-run.

### Fixed (planned start/end showed the wrong clock time to approvers)

- **A 10:00 AM window was landing on the ticket as `Aug 04, 11:30 PM → Aug 05, 2:30 AM`.** `_format_iso` stamped the offset of whatever machine ran the app (`dt.astimezone().strftime("%z")` → `+0530`), so the instant depended on the developer's laptop, and Jira then rendered it in each viewer's profile timezone — US Central for Command Center and the approvers. A normal morning deployment therefore read as an overnight change (same pattern on the Jul 29 release: `Jul 28, 11:30 PM → Jul 29, 2:30 AM`).
- **The schedule timezone is now explicit.** New `schedule_time.py` derives the offset from a named zone on that date (DST-aware: `-0500` in August, `-0600` in January for `America/Chicago`) instead of the host offset.
- **Step 2 has a "Times are in" picker** (default `Asia/Kolkata`, configurable via `service_desk.defaults.schedule_timezone`) and shows both the entered window and **what Jira will show approvers**, warning when the converted window spans midnight.
- **Step 5 review shows both renderings** plus the exact ISO values sent to Jira, so the mismatch is visible before create rather than after.
- **The ticket text now states both clocks.** On TCKT-112175 another team read the Central rendering and closed the change at 9 PM IST on Aug 4, before the Aug 5 morning window had started. The planned start/end fields can only ever render in the viewer's timezone, so the window is now spelled out in words where it cannot be misread:
  - **Description** gains a **Deployment Window** section: `Aug 05, 2026, 10:00 AM – 1:00 PM IST (Aug 04, 2026, 11:30 PM – Aug 05, 2026, 2:30 AM CDT)` plus an explicit *"Do not close or action this change before the agreed window has ended."*
  - **Implementation Plan** opens with the same window line and note.
  - **A Jira comment is posted on create** with the same clarification (title: *Deployment window (timezone clarification)*), so it stays visible in the activity feed even if someone only skims the fields.
  - **Slack announce is left unchanged** — historical wording only; timezone clarity belongs on the service ticket.
- Plans and description regenerate when the schedule or its timezone changes, so the stated window can never drift from the fields.

### Added (Slack announce before Release Deployer)

- **After a TCKT is created**, the success screen now has a **Send Slack message** section before Release Deployer.
- Builds the standard two-channel posts for **#insights-customize-squad** (CC: Sushma, Soumyakant, Trent) and **#customize-bi-buddies** (CC: Sushma, Soumyakant), matching prior release wording (date, version, SharePoint link, service desk ticket).
- **Preview both messages with CC tags** before send; editable deployment date / version / SharePoint URL.
- Send uses `SLACK_BOT_TOKEN` + `chat.postMessage` (optional `slack_announce.channel_ids` in `workspace.yaml`). Skip is available if you prefer to paste manually.
- Release Deployer stays locked until you **send or skip**.
- **Confluence Release-Notes Companion removed** from the success screen (not part of the release flow).
- **Assignment verification** auto-retries Approvers / Groups / Team once when mismatches are shown, with manual **Fix assignments** / **Re-check from Jira** buttons (covers tickets created before the Team UUID fix).

### Fixed (approvers missing after successful TCKT create)

- **Root cause on TCKT-112175:** post-create REST edit sent Team as `{\"id\": \"uuid\"}`, which abcfinancial's `atlassian-team` field rejects (`Team id 'JsonData{data={id=...}}' is not valid`). That single failure aborted the whole PUT, so Approvers, Approver Groups, Change Type, and Team were never applied — Jira kept request-type defaults (wrong people / wrong groups / Emergency / empty Team).
- **Team value is now a plain UUID string** (`_normalize_team_value`).
- **Post-create edits are split into isolated batches** (approvers/groups/change type, team, reasserted form fields, priority, ADF plans). A bad Team value can no longer wipe Approvers.
- **TCKT-112175 corrected in Jira:** Eoin George, Jose Ruiz, Srinivas Veerabomma, Sushma Bhamidipati; groups Command Center + Insights Analyze / Customize; Team Insights Customize Approvers; Change Type Normal.

### Added (TCKT create preflight against live form)

- **Create now validates the payload against the live Service Desk request-type schema before calling Jira.** Missing required fields, wrong string types, and option ids that are not on the form are reported immediately as a blocked preflight — no more guessing from HTTP 400 after the fact. Empty ADF/plain-text values are treated as absent.

### Added (post-failure "was it created?" check)

- **A failed create left it ambiguous whether the TCKT had been raised**, which invites a retry that quietly produces a duplicate change ticket. On failure the app now queries Jira for a TCKT with the same summary reported by the current user in the last hour (`find_tckt_by_summary` / `find_recent_tckt_issues`, read-only) and states the outcome: either the matching key with a link and a do-not-retry warning, or an explicit confirmation that nothing was created and retrying is safe. Matching ignores case and padding; the check is best-effort and can never mask the original error.

### Fixed (platform-wide error sweep)

- **`python -m mcp_server` crashed with a bare `ModuleNotFoundError: No module named 'mcp.server.mcpserver'`** on any interpreter without `mcp>=2.0.0` (the module resolves only inside the project virtualenv). The import is now guarded and explains which interpreter to use and how to install the pinned dependencies.
- **The MCP server had no test coverage at all**, so a broken tool signature or pagination bug would ship unnoticed. Added `tests/test_mcp_server.py` — 9 tests covering tool registration, stdio startup, `search_tickets` pagination and `max_results` cutoff, missing assignee/priority handling, release-notes grouping and case-insensitive version matching, unknown-version reporting, and `create_ticket` override precedence. Skips cleanly when `mcp` is absent.
- **Three `except Exception: pass` blocks silently swallowed unrelated bugs** in `extract_ticket_info`, `get_test_by_pool`, and the change-table link builder. Each now catches only the import/attribute errors it is actually guarding against, and the ticket-info path logs at debug instead of discarding the reason.
- Verified with an import sweep over all 82 project modules: zero import failures, zero Python warnings. `ruff` clean; 885 tests pass under the virtualenv, 876 with 2 skips on the system interpreter.

### Fixed (TCKT create rejected Business Impact — HTTP 400)

- **`Field with id 'customfield_14549' named 'Business Impact' has these errors : []`.** The Service Desk create sent `isAdfRequest: true` — declaring that rich text would arrive as ADF — while `_build_service_desk_request_field_values` flattened those same fields to plain strings with `adf_to_plain_text`. The flag is gone; the payload is now plain strings throughout, matching the schema.
- **Field routing is now derived from the live schema instead of assumption.** Verified against `GET /servicedeskapi/servicedesk/15/requesttype/1223/field` and `GET /api/3/issue/createmeta/TCKT/issuetypes/10502`: the request form requires 15 fields and declares every text field — description, Implementation plan, Test plan, Backout plan, Business Impact — as `type: string`. Only Approvers, Approver Groups, Team, Change Type, and Priority are absent from the form. `_POST_CREATE_TCKT_FIELDS`, `_RICH_TEXT_TCKT_FIELDS`, and `_REASSERTED_TCKT_FIELDS` now encode exactly that split.
- **Rich-text plans were being stored permanently as flattened text.** The Service Desk API only takes strings for them, and nothing put the formatting back, so every TCKT contradicted the ADF requirement in `jira-release-ticket-creation.mdc`. The post-create REST edit now re-applies description and all four plans as ADF, where API v3 accepts it.
- **The automatic retry never fired for this error.** Recovery keyed off Jira's `errors` map, but the Service Desk API names the offending field in prose instead. `_field_ids_in_message` recovers ids from both `Field with id '...'` phrasing and bare `customfield_nnnnn` mentions. Retries now skip fields Jira reports as *required* (dropping one only trades one 400 for another) and re-raise the original error if the retry also fails, since the first message describes the real problem.

### Fixed (TCKT creation failures were unreadable and unrecoverable)

- **"Failed to create ticket: Jira API request failed (HTTP 400). Check your connection and try again."** — `_friendly_raise` threw away the response body, so Jira's own explanation (`errorMessages`, `errorMessage`, and the `errors` map naming the offending field) never reached the user, and the advice was wrong: a 400 is a rejected payload, not a connection problem. Jira's detail is now parsed, logged, attached to `JiraApiError.field_errors`, and shown in the message. Custom field ids are labelled from `service_desk.fields` (`customfield_11763 (planned start)`).
- **Fields set after create were also sent on create.** `_build_supplemental_tckt_fields` applied Assignment Group, Affects PF, and Outage Required via REST edit, but `_build_service_desk_request_field_values` still put them in `requestFieldValues`. JSM returns HTTP 400 for any field that is not on the request-type form. Both now share `_POST_CREATE_TCKT_FIELDS`, so each field is sent exactly once, in the call that accepts it.
- **A field rejection killed the whole create.** When a 400 names specific fields, the Service Desk create is now retried once without them and those values are applied by the post-create edit instead.
- **A failed follow-up edit was reported as "create failed"**, inviting a duplicate TCKT. The post-create edit is now best-effort: the ticket key is always returned, with the problem surfaced as `supplementalWarning`.
- **The error vanished on the next rerun** and named no field. Review & Create now renders a persistent panel with the HTTP status, Jira's message, a per-field rejection list, remediation guidance, and a Dismiss button.

### Added (TCKT creation success feedback)

- Success state shows an explicit confirmation (`Ticket TCKT-nnnnn was created successfully in Jira`), the clickable ticket link, and the full browse URL in a copyable block alongside the existing banner, balloons, and toast.

### Fixed (release notes Test by + ETL status)

- **Test by was uneven** (random pick clustered on Mona/Chanti). Assignment is now least-loaded across the full QA pool so 5–20 tickets spread properly. Hard rule unchanged: Test by ≠ Jira assignee.
- **Testing Status auto-fill**: Mona-owned (ETL) tickets → `ETL Done`; all other tickets → `Done`. Wired into Change Details defaults and Rebuild.

### Fixed (release notes quality — local refs, no SharePoint)

- **Change Details rows skipped the quality pipeline.** Highlights/Dashboards were repaired, but the Change Details table still shipped stubs (`Report=E`, `Client=XtremeFitness`, FWBC report titles as clients). Added `prepare_change_table_entries`; defaults and **Rebuild Change Details** / **Rebuild Highlights & Dashboards** now apply the same repairs. Ticket extract (Step 2) also runs `improve_extracted` once so downstream sections start clean. Deployment owner labels use canonical client names.

### Fixed (Exclude Tickets select-and-proceed)

- **Exclude Tickets could not see Ticket Review exclusions.** Step 2 filtered `wiz_issues` to the snapshot before Step 3, so deselected tickets never appeared in the exclude UI and their fix version was never removed. Step 3 now lists **all tickets on the fix version**, pre-selects Ticket Review exclusions, and uses **Exclude selected & continue** (remove fix version → Deployment Info). **Continue without excluding** is available when nothing is checked, with a warning if review exclusions still carry the fix version. Step 2 fingerprints exclude selection against the raw list.

### Fixed (reference cross-check vs `Release Notes 2026.3.08.05`)

- **Dashboards / Reports bullets rendered without bullet glyphs.** The section built each line with `doc.add_paragraph()` while Key Highlights passed `style=LIST_STYLE`, so the two lists looked different in Word — Dashboards came out as plain body text. Now uses `LIST_STYLE`, matching Key Highlights and the `2026.2.04.14` reference. `test_dashboard_lines_bold_client_prefix` selected paragraphs by `style.name == "Normal"`, which encoded the defect; it now locates the section positionally and asserts the bulleted style.
- **Client names were published in non-display spellings.** `XtremeFitness` and `Jett's` reached the document verbatim, contradicting the naming table in `abc-bi-core.mdc` and splitting one client across two spellings. Added `canonical_client_name` plus `CLIENT_DISPLAY_NAMES` to `release_notes_quality.py`, applied in `improve_extracted_entry` and `build_custom_clients_list`. Comparison ignores spaces, case, and punctuation, so `XtremeFitness` → `Xtreme Fitness` and `Jett's` → `Jetts`; unrecognized names pass through untouched.
- Removed a no-op `if`/`pass` block in `build_dashboard_lines` whose comment described behavior it did not implement.

### Fixed (audit)

- **Release Notes Key Highlights / Dashboards quality** — auto-generated sections matched the weak output in recent SharePoint docs (e.g. `Analyze- E`, `Analyze- Analyze`, `Montly`, empty-looking Affected Clients). Added `generators/release_notes_quality.py` with typo cleanup, Analyze-prefix repair, known-client splitting (FWBC), consolidated Dashboards (`Analyze - Report` with spaces), and default Analyze Clients bullet `All Analyze-based (Standard) clients`. Edit step now shows quality warnings and a **Rebuild Highlights & Dashboards** button.
- **Custom Clients Summary intro** was collected in session state but never written into the `.docx` — now rendered under the heading before client bullets.
- **`mcp` was missing from `requirements.txt`** while being a hard `pyproject.toml` dependency, so `pip install -r requirements.txt` produced an install that could not run the MCP server.
- **Removed `generators/release_notes_docx_patch.py`** — it imported `generators.release_notes_docx_numbering`, a module that does not exist, so the file raised `ImportError` on any import. Nothing referenced it; the live path calls `patch_docx_grid_table4_accent1_style` directly.
- **`st.components.v1.html` is past its removal date** (scheduled for removal after 2026-06-01). Migrated `ui/theme.py` to `st.iframe`.
- **CI was red.** `ruff check .` reported 173 errors; the lint step could never pass. All are now resolved and `ruff check .` exits clean.
- Two retry tests (`test_502_retries_then_succeeds`, `test_503_retries_then_succeeds`) discarded their result and only asserted the sleep count — they would have passed even if the retry returned wrong data. They now assert the returned payload and call count.
- `scripts/_ref_title_gap.py` executed on import (no `__main__` guard) and hardcoded a personal `~/Downloads` path; it now takes the document path as an argument and exits cleanly when missing.
- Removed a duplicate import block and dead locals in `ui/step1_release.py`, `ui/step3_deploy_info.py`, `ui/ticket_review/`, and `request_type_setter.py`.
- **Deployment history date filter returned wrong rows.** A timestamp that failed to parse was swallowed and the entry appended anyway, so undated records showed up regardless of the selected range. Unparseable entries are now excluded and logged.
- **A corrupt deployment history file looked like "no deployments yet."** `load_history()` caught read/JSON errors and returned `[]` with no signal. It now logs and surfaces a UI error making clear the records are still on disk.
- **TCKT description could silently drop a ticket.** `ui/service_ticket/step3_description.py` carried its own `_consolidate_dashboards` that had drifted from `consolidation.py`: a Custom ticket with neither client nor report produced an empty label and vanished from the description entirely, and partial ticket dicts raised `KeyError`. It now uses the canonical `consolidate_dashboards`. Output is identical for normal input.
- `security.yml` ended both scan steps with `|| true`, so the job could never fail; `bandit` also excluded `venv/` rather than `.venv/`. Both corrected.
- README version badge still advertised 2.0.0.

### Changed (audit)

- `ui/step4_review.py`: `_render_quick_review_summary` and `_render_full_review_details` had byte-identical bodies; extracted `_render_deployment_cards` / `_deployment_card_html` and removed ~35 duplicated lines.
- Moved module-level imports above executable statements across `jira_client.py`, `ui/helpers.py`, `ui/history.py`, `ui/step1_release.py`, `ui/ticket_review/step3_format.py`, and `generators/release_notes_generator.py`.
- Hoisted inline `import requests` out of `ui/settings.py` and `from typing import Any` out of `mcp_server/server.py`.
- Ruff now excludes `build/`, `dist/`, and `*.egg-info/` so regenerated artifacts cannot fail the lint step.
- Deleted stale local build output (`build/`, `dist/` containing 1.1.0 and 2.0.0 wheels, `jira_release_tool.egg-info/`) that no longer matched the 3.0.0 source.

### Added
- **Setup health panel** on home page — actionable checklist for new users (credentials, projects, TCKT IDs).
- **`docs/SETUP.md`** — complete new-user E2E setup guide with troubleshooting.
- **Light / Dark / Auto theme** toggle and redesigned UI (build `2026.07.01-e2e`).
- **Release dropdown pickers** — select, switch, or deselect (`— None —`) per project; Clear all button.
- **Optional features** expander on home — AI Ticket Creator hidden by default.
- **Settings → Fetch from Jira** — auto-discover Service Desk ID and Request Type ID for TCKT.
- **Release Deployer step: Exclude Tickets** — remove fix version from deselected/excluded tickets before post-deploy.
- **Release Notes — Key Highlights dedup** (`build_key_highlight_lines`) — no repeated report/description text when Jira summary parsing falls back to the same value.
- **Release Notes — Change Details hyperlinks** (generator build `2026.07.27-change-table-hyperlinks-v2`) — Ticket#, Parent, and Link columns are clickable Jira links in the downloaded `.docx`; Step 4 verifies hyperlink count after generate.
- **Release Deployer — Quick start** — streamlined 5-step post-deploy flow (Release → Select Tickets → Deployment Info → Review → Deploy); skip Ticket Review / Release Notes / Service Ticket; uncheck failed-in-prod tickets on step 2; cleaner release picker (dropdown).
- **Release Notes — Change Details Test by** — auto-assigns **Test by** from the QA pool (Rekha, Mona, Navya, Chanti, Narasimha, Nikhath, Bharathi, Soumya, Sushma); never matches the ticket owner (Jira assignee); **Rebuild Test by column** on Edit step.

### Fixed
- Release Deployer **Review** crash (`StopIteration`) when deployment info was missing — now redirects to Deployment Info instead of crashing.
- Stale deployer session after the new **Exclude Tickets** step — wizard auto-resets when step flow changes.
- **False "already deployed" skips** — only full verified deployment comments (with Deployment ID) block re-post; on-hold/partial notes no longer count.
- **Release Workflow sidebar** — fixed stuck unchecked boxes; shows correct step order and live progress.
- **Wrong ticket deployed per client** — deploy now respects Ticket Review snapshot, shows fix-version mismatches (e.g. PIC-5634 vs PIC-5638), and requires ticket confirmation on Review before posting comments.
- Request Type sidebar warning scoped to Service Ticket / Settings only (not every page).
- `render_sidebar_promo` import error in theme module.
- Outdated install paths in `GETTING_STARTED.md` and `setup.bat`.

## [3.0.0] - 2026-05-05

### Added

- **AI Ticket Triage (`ai_triage.py`)** — rule-based + optional LLM classification of incoming tickets by component, priority, and suggested assignee. Uses keyword matching as primary engine; enhances with OpenAI/Azure OpenAI when API key is set.
- **AI Ticket Creator (`ai_ticket_creator.py`)** — parse natural-language descriptions into structured Jira tickets (summary, description, type, priority, component) and create them via the existing `jira_client`. Includes dry-run/preview mode.
- **MCP Server (`mcp_server/`)** — Python MCP server exposing four tools: `create_ticket`, `triage_ticket`, `search_tickets`, `generate_release_notes`. Run via `python -m mcp_server` for agent integration.
- **AI Ticket Creator UI page** — new Streamlit app page with NL text area, project selector, live preview of parsed fields + triage analysis, and one-click Jira creation with result link.
- `mcp>=1.0.0` added to dependencies.

### Changed

- Version bumped to 3.0.0.
- `pyproject.toml` registers `ai_triage`, `ai_ticket_creator` modules and `mcp_server` package.
- App registry (`ui/app_registry.py`) includes "AI Ticket Creator" as a new built-in app.
- Sidebar and router updated to support the new `ai_ticket_creator` app.
- CI now installs the package via `pip install -e ".[dev]"` so dependency resolution and tooling stay aligned with `pyproject.toml`.
- Ruff in CI now runs as `ruff check .` to enforce the same rule selection configured under `[tool.ruff.lint]`, including import-order checks.

## [2.0.0] - 2026-04-20

### Added

- **Shared `common/` library** — ADF builders (`common/adf`), injectable Atlassian REST client (`common/atlassian`), exponential-backoff retry (`common/retry`), Slack/Teams webhook helpers (`common/notify`), AI enhancer with OpenAI / Azure OpenAI + offline fallback (`common/ai`), and CLI scaffolding (`common/cli`). Shared verbatim with `weekly-update-tool`.
- **Template library (`template_library.py`)** — five built-in ticket templates (`standard-monthly-glofox`, `emergency-hotfix`, `major-feature-release`, `custom-client-deployment`, `semantic-model-refactor`), load/save/delete/apply, and capture-from-draft. Templates live at `~/.jira-release-tool/templates/` as YAML and override built-ins by name.
- **AI-enhanced ticket summaries (`ai_enhancer.py`)** — 3-sentence executive brief, acceptance-criteria generation, release-risk rating (low/medium/high with scope + keyword signals). Works offline by default; uses `OPENAI_API_KEY` or `AZURE_OPENAI_API_KEY` automatically when available.
- **Linked ticket verification (`linked_ticket_verifier.py`)** — pre-flight check for source PIC/AN tickets: expected state, non-empty summary, acceptance-criteria field, with optional release-label auto-application.
- **Slack / Teams deployment notifier (`notifier.py`)** — incoming-webhook announcement after TCKT creation. Configurable via `SLACK_DEPLOY_WEBHOOK` / `TEAMS_DEPLOY_WEBHOOK`.
- **Hardened request-type setter (`request_type_setter.py`)** — exponential-backoff retries with audit log persisted to `~/.jira-release-tool/audit/request-type.log`, clear diagnostics on permanent failure.
- **CLI (`cli.py`)** — headless `create`, `validate-config`, and `list-recent` subcommands with `--dry-run` and `--json` output. Registered as console script `jira-release-tool`.
- 270+ new tests covering shared library, template library, AI enhancer, linked verifier, notifier, request-type setter and CLI. Test suite now ≥ 650 passing.

### Changed

- `pyproject.toml` now exposes `[project.scripts] jira-release-tool = "cli:main"` — the tool is installable as a headless command.
- New top-level modules registered under `[tool.setuptools].py-modules`.

## [1.1.0] - 2026-04-20

### Added

- **Ticket Preview tab** — render the TCKT draft exactly as it will appear in Jira (summary, schedule, description, plans, approvers) before clicking Create. Includes Copy-as-JSON and Copy-as-Markdown exports. (`ui/preview.py`)
- **Diff Mode** — paste a previous TCKT key in the preview step to see a field-by-field diff (added / removed / changed). Highlights approver, group, team, and dashboard drift. (`diff_engine.py`)
- **Auto-Consolidation Detector** — groups selected release tickets by dashboard/report, and suggests a single merged bullet in the rule-mandated `**Label** – summary (AN-X, AN-Y)` format. Also detects shared client and semantic-similarity clusters. (`consolidation_detector.py`)
- **Approver Validation (pre-flight)** — validates every `accountId` via `/user` and every approver group via `/group` before ticket creation; caches results for 30 minutes. (`approver_validator.py`)
- **Confluence Release-Notes Companion** — optional publish-to-Confluence tab after ticket creation. Generates a storage-format XHTML page with affected clients, dashboards, plans, and source tickets. (`confluence_publisher.py`)
- **Release Timeline / TCKT History** — new sidebar entry that queries `reporter = currentUser() AND project = TCKT` and shows a filterable, exportable timeline. (`ui/tckt_history.py`)
- **Quick Stats sidebar** — total TCKTs / quarter / month, avg draft-to-create lead time, last release date, most-used approver. Cached for 1 hour. (`release_stats.py`)
- **Test Plan Coverage Check** — non-blocking warnings with auto-fix suggestions when a dashboard is in the Description but missing from the Test Plan or Business Impact. (`ticket_validator.py`)
- 143 new tests; total suite now at 381 passing.

### Changed

- `jira_client.set_request_type` now returns a structured `RequestTypeStatus` (via `set_request_type_detailed`). UI shows a red banner with manual instructions when the Service Desk request type cannot be auto-set.
- Sidebar displays a warning banner on startup when `TCKT_SERVICE_DESK_ID` or `TCKT_REQUEST_TYPE_ID` are missing.
- Description bullets, Business Impact lines, and Test Plan items now run through `consolidation.deduplicate_by_dashboard()` to enforce the "never list the same dashboard twice" rule in three places at once.

### Added (env vars)

- `TCKT_SERVICE_DESK_ID`, `TCKT_REQUEST_TYPE_ID` — request-type auto-set IDs.
- `CONFLUENCE_URL`, `CONFLUENCE_TOKEN`, `CONFLUENCE_SPACE`, `CONFLUENCE_PARENT_ID` — Confluence companion page publishing.

## [Unreleased-1.0.1]

### Changed

- Complete README rewrite with badges, feature checklist, tech stack table, project structure, and full configuration guide.
- Enhanced `.gitignore` with Docker, Streamlit, and generated document patterns.
- Expanded `.env.example` with all environment variables documented.
- CI pipeline now fails on lint errors (removed `continue-on-error`).
- Docker healthcheck uses Python stdlib instead of curl.

### Fixed

- Added missing `help=` tooltips on Streamlit inputs across all UI modules.
- Added missing error handling in service ticket and release notes steps.
- Added export/download buttons on data display views.

## [1.0.0] - 2026-04-14

### Added

- Initial release of Release Orchestrator.
- **Ticket Review** workflow with multi-project release selection, owner grouping, select/deselect, and formatted review lists with Jinja2 templates.
- **Release Notes** generator producing styled Word (.docx) documents from Jira tickets.
- **Service Ticket** creator for deployment/change tickets with ADF descriptions, implementation plans, test plans, backout plans, business impact, and approver assignment.
- **Release Deployer** with paste-to-parse deployment info, deployment comments, Done-transition, undo support, and duplicate comment detection.
- **Deployment Dashboard** with DORA-style metrics: frequency, lead time, change volume, success rate trends, and CSV export.
- Multi-workspace support via `workspace.yaml` — run multiple team configurations from a single installation.
- Configurable Jinja2 template engine with per-workspace overrides (`templates/` → `templates/default/` fallback).
- Home page with team selector cards and app launcher grid.
- Sidebar navigation with workspace switcher, history access, and release context.
- Settings page for in-app workspace configuration with export/import.
- Docker deployment with `Dockerfile` and `docker-compose.yaml`.
- Desktop launchers (`launcher.pyw`, `launch.vbs`).
- 105 passing tests with pytest.
- CI pipeline with GitHub Actions (Ruff lint + pytest).
- Pre-commit hooks configuration.
