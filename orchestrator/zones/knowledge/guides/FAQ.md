# FAQ

### Q1. Why is "Request Type" showing as None on my SHIPIT ticket?

Standard Jira issue creation (`POST /rest/api/3/issue`) cannot set Service Desk Request Types — only the Service Desk API (`/rest/servicedeskapi/request/...`) can. The toolkit attempts this automatically **only if** `TCKT_SERVICE_DESK_ID` and `TCKT_REQUEST_TYPE_ID` are set in `config.py` (or environment variables of the same names).

**If it's missing after create:** open the ticket → Details panel → Request Type → **"Submit a normal or emergency change"**. This also fixes the field ordering on the Service Desk portal view.

### Q2. How do I configure approvers for my team?

Either:

1. **In-app**: Home → **Settings** → **Service Desk Defaults** → Add Approver (autocompletes by email; writes back to `workspace.yaml`).
2. **YAML directly**:
   ```yaml
   workspace:
     service_desk:
       default_approvers:
         - { name: "Jane Doe", account_id: "712020:xxx-xxx" }
       approver_groups: ["Command Center"]
       team_id: "your-team-uuid"
   ```

Restart Streamlit after editing YAML.

### Q3. Why am I getting "401 Unauthorized" from Jira?

Three causes in order of frequency:

1. **Wrong email** — must be the Atlassian account email (not an alias)
2. **Token regenerated** — old token invalidated when a new one was created
3. **Token not base64-encoded** — don't encode it yourself; the client does `HTTPBasicAuth(email, token)`

Test with curl:
```bash
curl -u "you@company.com:YOUR_TOKEN" "https://yourorg.atlassian.net/rest/api/3/myself"
```

### Q4. Does this support Jira Server / Data Center?

No. The toolkit uses Atlassian Document Format (ADF) and the `/rest/api/3/` endpoints, which are **Jira Cloud only**. Server uses wiki markup and a different API shape.

### Q5. Where are deployment history records stored?

`.deployment_history.json` in the project root. JSON array of records:

```json
[
  {
    "timestamp": "2026-04-14T15:00:00+00:00",
    "project": "PIC",
    "version": "2026.2.04.14",
    "clients": {
      "Jetts": {
        "deployment_id": "uuid-here",
        "deployment_date": "April 14 2026",
        "deployment_time": "10:39 AM IST",
        "tickets": ["PIC-5091", "PIC-5092"]
      }
    },
    "success": 2,
    "skipped": 0,
    "errors": 0,
    "reverted": false,
    "undo_data": [{"key": "PIC-5091", "comment_id": "123456", "prev_status": "In Progress", "transitioned": true}]
  }
]
```

Safe to commit or back up; no secrets included.

### Q6. How do I customize the deployment comment text?

Edit `templates/deployment_comment.j2` (or create `templates/<team>/deployment_comment.j2`). The template engine checks team-specific first, then `templates/default/`. Available variables: `release`, `client`, `tickets`, `deployed_at`, `deployed_by`.

### Q7. How do I configure multiple teams from one installation?

Create `workspaces/<team>/workspace.yaml` for each team. Switch between them from the **home page** team cards, or set `JIRA_TOOLKIT_WORKSPACE=analytics-team` in `.env` to default to one.

### Q8. Can I run this in Docker / Streamlit Cloud?

**Docker:** `docker-compose up -d` — the compose file mounts `.env`, `workspace.yaml`, `workspaces/`, and `templates/` so config persists outside the container.

**Streamlit Cloud:** push to GitHub, connect at [share.streamlit.io](https://share.streamlit.io), add the three secrets (`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`). No code changes needed.

### Q9. Why are some tickets skipped during deployment?

The deployer checks each ticket for an existing **verified** deployment comment block. If found, it skips re-posting to prevent duplicates. On the **Review** step, enable **Force post comments** to override partial or on-hold notes.

### Q10. Where are logs stored?

- **Streamlit logs**: terminal running `streamlit run orchestrator/entry/app.py`
- **Deployment actions**: `.deployment_history.json` (auditable)
- **Jira API errors**: terminal output with **secrets redacted** (tokens → `***`)
- **Tests**: `pytest orchestrator/zones/quality/tests/ -v` — all 381 tests run without network

### Q11. How do I see which DORA metrics are computed?

Open the **Deployment Dashboard** app. Metrics come from `.deployment_history.json`:
- **Deployment Frequency** — runs per week
- **Lead Time for Changes** — ticket creation → deployment
- **Change Volume** — tickets per deployment
- **Change Success Rate** — percentage without rollback

### Q12. Why is the Word document missing some tickets?

The generator filters by status by default — only tickets in **Done / Resolved / Ready for Deployment** appear. To include all: `workspace.yaml` → `release_notes.include_statuses: ["*"]`.

### Q13. How does the Ticket Preview / Diff mode work (new in 1.1)?

The new **Step 5 — Preview** tab renders the entire SHIPIT draft — summary, schedule, description ADF, plans, approvers, groups, team — exactly as it'll look in Jira. It also:

- Exposes **Copy as JSON** and **Copy as Markdown** download buttons for email sharing.
- Accepts a previous SHIPIT key (e.g. `SHIPIT-8346`). Paste it and the app calls `jira_client.get_issue()`, maps the custom fields via `config.TCKT_FIELDS`, and returns a `diff_engine.DiffResult`. Added / removed / changed fields are colour-coded; approver and dashboard lists show `+name` / `-name` deltas.

### Q14. The "Confluence Page" tab is disabled — why?

Set two env vars (or the equivalents in your secret store):

```
CONFLUENCE_URL=https://yourorg.atlassian.net
CONFLUENCE_TOKEN=your-token
# Optional:
CONFLUENCE_SPACE=REL
CONFLUENCE_PARENT_ID=123456
```

With those in place, the tab renders a live preview and exposes a **Publish** button that calls `jira_client.confluence_create_page()` (storage-format XHTML, with retries).

### Q15. What does "Approver validation failed" mean?

Before `POST /rest/api/3/issue`, the app calls `GET /user?accountId=...` and `GET /group?groupName=...` for each default approver and group. If any returns 404, ticket creation is blocked and a specific error is shown: `Approver Jane Doe (accountId: 712020:xxx-xxx) no longer exists. Remove or replace.`. Fix the `workspace.yaml` defaults (Settings page), click **Validate Approvers** to re-check, then retry. Results are cached for 30 minutes.

### Q16. Why is the same dashboard still listed twice in the Description?

It shouldn't be. As of 1.1, three layers enforce the dedup rule:

1. `consolidate_dashboards()` groups at build time.
2. `deduplicate_by_dashboard()` is the safety net — applied in Description bullets, Business Impact lines, and Test Plan items.
3. The **Auto-Consolidation Detector** surfaces cases to merge *before* you build the description.

If you still see a duplicate, report it with the exact ticket titles — it's likely a label-normalisation issue.

### Q17. How do I report a bug?

Open an issue at your repo's GitHub issues page. Include:

1. `python --version`
2. The app you were using (Ticket Review, Service Ticket, etc.)
3. Redacted `workspace.yaml` (remove `account_id` fields if you prefer)
4. Stack trace from the terminal (Streamlit prints full tracebacks)
5. Whether tests pass: `python -m pytest orchestrator/zones/quality/tests/ -v`
