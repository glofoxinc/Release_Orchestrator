/**
 * Browser login once + schedule N Teams meetings (visible in Outlook/Teams web).
 * Usage: node schedule_batch_browser.mjs path/to/payload.json
 *
 * payload.json: { "meetings": [ { subject, startTime, endTime, attendees, body? }, ... ] }
 */
console.log = (...args) => console.error(...args);
process.env.LOG_LEVEL = process.env.LOG_LEVEL || "error";

import fs from "node:fs";
import { createMeeting } from "@shayanline/msteams-mcp/dist/api/calendar-api.js";
import { createBrowserContext, closeBrowser } from "@shayanline/msteams-mcp/dist/browser/context.js";
import { ensureAuthenticated } from "@shayanline/msteams-mcp/dist/browser/auth.js";
import { requireGraphAuth } from "@shayanline/msteams-mcp/dist/utils/auth-guards.js";

async function ensureLogin() {
  let auth = requireGraphAuth();
  if (auth.ok) {
    console.error("[batch] Graph token already available");
    return true;
  }
  console.error("[batch] Opening Edge — sign in with abcfitness.com...");
  const manager = await createBrowserContext({ headless: false });
  try {
    await ensureAuthenticated(
      manager.page,
      manager.context,
      (msg) => console.error(`[login] ${msg}`),
      false,
      false,
    );
  } finally {
    await closeBrowser(manager, true);
  }
  auth = requireGraphAuth();
  return auth.ok;
}

async function main() {
  const path = process.argv[2];
  if (!path || !fs.existsSync(path)) {
    process.stdout.write(JSON.stringify({ ok: false, error: "Payload file required" }) + "\n");
    process.exit(1);
  }
  const payload = JSON.parse(fs.readFileSync(path, "utf8"));
  const meetings = payload.meetings || [];
  if (!meetings.length) {
    process.stdout.write(JSON.stringify({ ok: false, error: "No meetings in payload" }) + "\n");
    process.exit(1);
  }

  const loggedIn = await ensureLogin();
  if (!loggedIn) {
    process.stdout.write(
      JSON.stringify({ ok: false, error: "Graph auth failed — complete Edge sign-in (abcfitness.com)" }) + "\n",
    );
    process.exit(1);
  }

  const results = [];
  for (let i = 0; i < meetings.length; i++) {
    const m = meetings[i];
    console.error(`[batch] Scheduling ${i + 1}/${meetings.length}: ${m.subject}`);
    const result = await createMeeting({
      subject: m.subject,
      startTime: m.startTime,
      endTime: m.endTime,
      attendees: m.attendees || [],
      body: m.body || "",
      isOnlineMeeting: m.isOnlineMeeting !== false,
      location: m.location || "Microsoft Teams Meeting",
    });
    if (!result.ok) {
      results.push({
        slot: i + 1,
        ok: false,
        error: result.error?.message || "create_meeting_failed",
        subject: m.subject,
      });
      continue;
    }
    results.push({
      slot: i + 1,
      ok: true,
      backend: "teams_browser",
      event_id: result.value.id,
      join_url: result.value.joinUrl,
      subject: result.value.subject,
      startTime: result.value.startTime,
      endTime: result.value.endTime,
    });
  }

  const scheduled = results.filter((r) => r.ok).length;
  process.stdout.write(
    JSON.stringify({
      ok: scheduled === meetings.length,
      status: scheduled === meetings.length ? "ok" : scheduled ? "partial" : "failed",
      scheduled,
      total: meetings.length,
      results,
    }) + "\n",
  );
  process.exit(scheduled === meetings.length ? 0 : 1);
}

main().catch((err) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(err) }) + "\n");
  process.exit(1);
});
