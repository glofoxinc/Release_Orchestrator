# Tutorials

Three end-to-end workflows for the most common release tasks.

---

## Tutorial 1 — Create a production-ready SHIPIT change ticket

**Goal:** Generate a Service Desk change ticket (**SHIPIT** Manual Change) with correct custom fields (Change Type, Risk, Approvers, Affected Services), ADF-formatted plans, and Request Type set automatically when configured.

**Prerequisites:**
- Jira credentials working (see [`GETTING_STARTED.md`](./GETTING_STARTED.md))
- `workspace.yaml` populated with your team's `service_desk` section (project, field IDs, default approvers)

**Steps:**

1. Open the **Service Ticket** app from the home screen.
2. **Step 1 — Select releases.** Pick one or more (e.g. `PIC 2026.2.04.14` + `AN 2026.2.04.14`). The toolkit fetches tickets from all selected releases.
3. **Step 2 — Fill details.** Summary auto-generates from the version: `Production Deployment – Insights Customize BI - Glofox - Report Updates (v2026.2.04.14)`. Schedule defaults to the release date at **10:00–13:00** local time.
4. **Step 3 — Review description.** The toolkit builds an ADF description with:
   - Opening paragraph
   - **Affected Clients** section (auto-extracted from ticket metadata)
   - **Dashboards / Reports** bullets — **consolidated** so each dashboard appears once
   - **Release Notes** link to SharePoint
5. **Step 4 — Edit plans.** Implementation / Test / Backout / Business Impact plans are pre-filled dynamically from ticket descriptions. Edit freely; all output is ADF.
6. **Step 5 — Preview (new in 1.1).** The new Preview tab renders the ticket exactly as it'll appear in Jira with full ADF-to-HTML preview, and includes:
   - **Copy as JSON** / **Copy as Markdown** for Slack / email
   - **Compare to Previous SHIPIT** — paste `SHIPIT-8346` (or any key) to see a field-by-field diff against a previous release.
   - Non-blocking **Test Plan Coverage Check** warnings — each one has a one-click *Auto-fix* to append the missing dashboard to the Test Plan or Business Impact.
7. **Step 6 — Create.** Click **Create ticket**. The toolkit:
   - `POST /rest/api/3/issue` with all custom fields
   - Separately `PUT` to set Approver Groups and Team (some Jira Cloud instances reject these in the create call)
   - **Validates every approver `accountId` + approver group** before the POST (`/rest/api/3/user`, `/rest/api/3/group`). Blocks creation with a specific error if any fail — results cached for 30 minutes.
   - Calls the Service Desk API to set **Request Type** to "Submit a normal or emergency change". Returns a structured `RequestTypeStatus`: if it fails, the UI shows a red banner with manual-fix instructions and a "Copy Jira URL" button.
8. **After create — Confluence Companion (optional, new in 1.1).** A new **Confluence Page** tab appears alongside the success message. It:
   - Generates a Confluence storage-format XHTML body (affected clients, dashboards, collapsible plan sections, source tickets table)
   - Lets you preview the body, set space/parent/title, and publish with one click when `CONFLUENCE_URL` + `CONFLUENCE_TOKEN` are configured.

**Expected Result:** A SHIPIT ticket URL (e.g. `SHIPIT-8346`) with:
- Change type: Normal, Risk: Medium, Impact: Moderate, Urgency: Medium
- Approvers filled in
- Request Type visible on the portal
- All four ADF plans rendered with proper formatting (bold, bullets, spacers)

**Tip:** If Request Type shows as "None" after creation, the Service Desk API call failed. The UI will warn you — manually set in **Details panel → Request Type → "Submit a normal or emergency change"**. See `.cursor/rules/jira-release-ticket-creation.mdc` in this workspace for full field reference.

---

## Tutorial 2 — Generate a Word release-notes document

**Goal:** Produce a styled `.docx` with the release summary, per-client tables, and SharePoint-ready formatting.

**Prerequisites:**
- Release(s) selected (single or multi-project)
- `generators/release_notes_generator.py` accessible

**Steps:**

1. Open the **Release Notes** app → **Step 1: Pick Release(s)**. Pick the same release as your SHIPIT ticket for consistency.
2. **Step 2: Choose Template.** Two options:
   - **Built-in DOCX generator** (default) — uses `generators/release_notes_generator.py`
   - **Custom Jinja2 template** — select a file under `templates/` if your team has one
3. **Step 3: Preview.** The app renders the document in-browser. Every section is editable:
   - Title (version)
   - Per-client table (Client, Tickets, Summary of Changes)
   - Detailed ticket breakdown grouped by dashboard
   - Footer with generation timestamp and author (from `JIRA_EMAIL`)
4. **Step 4: Download.** Click **Download `.docx`**. Filename pattern: `Release Notes 2026.2.04.14.docx`.
5. Upload to SharePoint manually, copy the sharing link, and paste into the SHIPIT ticket description (Graph auto-upload is archived in v3.0.1).

**Expected Result:** A formatted Word document (example: `Release Notes 2026.2.04.14 (1).docx` in the repo root). Opens in Word/Google Docs with:
- Calibri 11 body, Calibri Bold 14 for headings
- ABC Fitness brand colors for table headers (hex `#1F4E79`)
- Bulleted ticket lists (`•` character), not numbered
- Page breaks between major sections

**Tip:** To change branding, edit `generators/release_notes_generator.py` — look for `DOCX_FONT`, `DOCX_HEADING_COLOR`, `DOCX_TABLE_COLOR`. Or follow the ABC-specific template rules in `.cursor/rules/release-notes.mdc`.

---

## Tutorial 3 — Configure approvers and deploy a release

**Goal:** Post deployment comments on every ticket in a release, transition them to Done, with full undo support — while using the correct approvers for your team.

**Prerequisites:**
- Approvers configured in `workspace.yaml`:
  ```yaml
  workspace:
    service_desk:
      defaults:
        approvers:
          - { accountId: "6414e24faf3b93d8ecf27b3d" }  # e.g. Eoin George
          - { accountId: "641390cc9796ea0a87174587" }  # update via Settings UI
      approver_groups:
        - "Command Center"
        - "Insights Analyze / Customize"
      team_id: "3b374af6-6998-440a-a5e5-9af5f70493dc"
  ```
- Build output or CI log with deployment timestamps and client UUIDs

**Steps:**

1. **Configure approvers** (one-time):
   - Home → **Settings** → **Service Desk Defaults**
   - Add each approver via the in-app "Find user by email" search — it writes the correct `accountId`
   - Save. The app writes back to `workspace.yaml`.
2. Open the **Release Deployer** app → **Step 1**: pick the release.
3. **Step 2 — Review tickets.** You'll see status validation warnings. Fix any stragglers (move to Ready for Deployment, etc.).
4. **Step 3 — Paste deployment info.** Paste your CI/CD output. The parser auto-detects:
   - UUIDs (client identifiers)
   - Dates (ISO 8601 and common variations)
   - Client names from `workspace.yaml` → `clients` mapping
   - Start / end timestamps
5. **Step 4 — Review & Confirm.** Per-client deployment block + comment preview. Toggle individual tickets off if needed.
6. **Step 5 — Deploy.** The tool:
   - Checks each ticket for an existing comment matching the fingerprint (deduplication)
   - Posts the deployment comment (ADF)
   - Transitions the ticket to **Done** via its `transitions` API
   - Records the action in `.deployment_history.json` with an undo token
7. **Undo** (if needed): Home → **History** → find the run → **Undo**. The tool deletes the posted comments and transitions tickets back to their prior status.

**Expected Result:**
- Each ticket has exactly one deployment comment
- Tickets are in **Done** status
- `history` page shows the run with count, success rate, and per-ticket status
- DORA Dashboard updates with the new deployment data point

**Tip:** Run in dry-run mode first — toggle **"Preview only, don't post"** on Step 4. Useful before your first production run to confirm the comment body looks right.

---

---

## Tutorial 4 — Use the Auto-Consolidation Detector (new in 1.1)

**Goal:** Spot when two or more tickets touch the same dashboard and merge them into a single bullet automatically.

**Steps:**

1. Open **Service Ticket** → Step 2 (after picking the release).
2. The app runs `consolidation_detector.detect_consolidation_opportunities()` over the selected ticket list and surfaces any group with 2+ tickets sharing:
   - The same dashboard label (primary rule)
   - The same custom client
   - The same report name across client boundaries
   - A description Jaccard similarity ≥ 0.6 ("semantic" cluster)
3. For each suggestion, the UI shows the rule-mandated format: `**Label** – merged summary (AN-XXXX, AN-YYYY)`.
4. Click **Apply** to collapse the tickets into one entry for Description / Business Impact / Test Plan.

---

## Tutorial 5 — Browse your TCKT history (new in 1.1)

**Goal:** Quickly find a past TCKT ticket, export the list to CSV, or verify how many releases you've shipped this quarter.

**Steps:**

1. Sidebar (inside the Service Ticket app) → **Your TCKT History**.
2. The page queries `reporter = currentUser() AND project = TCKT ORDER BY created DESC`.
3. Filter by free-text, status, date range, or approver.
4. Click **Export CSV** for offline analysis.
5. The sidebar **Quick Stats** panel (cached for 1 hour) shows totals, this quarter / this month, last release date, avg draft-to-create lead time, and most-used approver.

---

## Link map

| Feature | Code |
|---|---|
| Service Ticket wizard | [`ui/service_ticket/`](../ui/service_ticket/) |
| Ticket Preview + diff | [`ui/preview.py`](../ui/preview.py), [`diff_engine.py`](../diff_engine.py) |
| Consolidation detector | [`consolidation.py`](../consolidation.py), [`consolidation_detector.py`](../consolidation_detector.py) |
| Approver validation | [`approver_validator.py`](../approver_validator.py) |
| Confluence publisher | [`confluence_publisher.py`](../confluence_publisher.py) |
| Test plan coverage check | [`ticket_validator.py`](../ticket_validator.py) |
| TCKT history | [`ui/tckt_history.py`](../ui/tckt_history.py) |
| Quick stats | [`release_stats.py`](../release_stats.py) |
| Release Notes wizard | [`ui/release_notes/`](../ui/release_notes/) |
| Release Deployer | [`ui/step1_release.py`](../ui/step1_release.py) … [`step5_execute.py`](../ui/step5_execute.py) |
| ADF builder | [`adf_builder.py`](../adf_builder.py) |
| Jira client | [`jira_client.py`](../jira_client.py) |
| DOCX generator | [`generators/release_notes_generator.py`](../generators/release_notes_generator.py) |
| Deployment history | [`ui/history.py`](../ui/history.py) + `.deployment_history.json` |
