/**
 * One-shot: browser login (if needed) + create Teams meeting in same process.
 * Usage: node schedule_meeting_now.mjs '<json-payload>'
 */
console.log = (...args) => console.error(...args);
process.env.LOG_LEVEL = process.env.LOG_LEVEL || "error";

import { createMeeting } from "@shayanline/msteams-mcp/dist/api/calendar-api.js";
import { createBrowserContext, closeBrowser } from "@shayanline/msteams-mcp/dist/browser/context.js";
import { ensureAuthenticated } from "@shayanline/msteams-mcp/dist/browser/auth.js";
import { requireGraphAuth } from "@shayanline/msteams-mcp/dist/utils/auth-guards.js";

import fs from "node:fs";

let payload = {};
const arg = process.argv[2] || "";
if (arg && fs.existsSync(arg)) {
  payload = JSON.parse(fs.readFileSync(arg, "utf8"));
} else if (arg) {
  payload = JSON.parse(arg);
}

async function ensureLogin() {
  let auth = requireGraphAuth();
  if (auth.ok) {
    return;
  }
  console.error("[schedule] Opening Edge for Teams sign-in...");
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
}

async function main() {
  await ensureLogin();
  const auth = requireGraphAuth();
  if (!auth.ok) {
    process.stdout.write(
      `${JSON.stringify({ ok: false, error: auth.error?.message || "Graph auth failed after login" })}\n`,
    );
    process.exit(1);
  }
  const result = await createMeeting({
    subject: payload.subject,
    startTime: payload.startTime,
    endTime: payload.endTime,
    attendees: payload.attendees || [],
    body: payload.body || "",
    isOnlineMeeting: payload.isOnlineMeeting !== false,
    location: payload.location || "",
  });
  if (!result.ok) {
    process.stdout.write(
      `${JSON.stringify({ ok: false, error: result.error?.message, detail: result.error })}\n`,
    );
    process.exit(1);
  }
  process.stdout.write(
    `${JSON.stringify({
      ok: true,
      event_id: result.value.id,
      join_url: result.value.joinUrl,
      subject: result.value.subject,
      startTime: result.value.startTime,
      endTime: result.value.endTime,
    })}\n`,
  );
}

main().catch((err) => {
  process.stdout.write(`${JSON.stringify({ ok: false, error: String(err) })}\n`);
  process.exit(1);
});
