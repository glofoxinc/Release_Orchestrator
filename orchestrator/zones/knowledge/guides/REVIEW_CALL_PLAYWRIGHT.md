# Glofox review call — Playwright / Outlook path

Graph `teams_schedule` is archived. Use **Playwright MCP** + Release Orchestrator handoff tools.

## Tool order (ad-hoc ticket review)

1. **`review_call_prepare`** — pass `ticket_keys` (`AN-xxxx`), `start`, optional `end` (default 30 min from `glofox.yaml`).
2. Execute **`playwright_handoff.steps`** in order via Playwright MCP.
3. Say **calendar done** after the invite is on the calendar.

Alternatives:

- **`build_review_call_attendees`** — roster only (then call `teams_playwright_handoff` with explicit `attendees`).
- **`teams_schedule_status`** — check `playwright_handoff_meta.handoff_version` after code changes; **restart MCP** if version mismatch.

**Not for ad-hoc Glofox review:** `daily_review_run_live`, `dr_attendee_policy` (Daily Review 6 PM pipeline).

## Pre-send gate (one send)

Before **Send**:

- Outlook **Start date** matches subject `Review call MM/DD/YYYY`.
- All **required** leadership + QA + ticket assignees in compose.
- All **optional** squad (five emails) via **Response options → Add optional attendees**.
- Body: ticket lines only (no Required/Optional boilerplate).

Never send required-only then patch optional in a second update.

## Playwright tips

- Open **`calendar/view/day/{YYYY-MM-DD}`** for the meeting day.
- If handoff steps are stale, restart **release-orchestrator** MCP and re-call `review_call_prepare`.

## Fail-closed

`teams_playwright_handoff` with `kind=review` **without** `attendees` returns an error. Always use `review_call_prepare` or pass full roster with `type` on each row.
