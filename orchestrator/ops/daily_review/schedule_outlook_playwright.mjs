/**
 * Playwright → Outlook web calendar (ABC tenant). One browser session, batch-safe.
 *
 * Usage:
 *   node schedule_outlook_playwright.mjs path/to/payload.json
 *
 * payload.json:
 * {
 *   "replacePattern": "Daily Review Agent — Mohan sync",  // optional — cancel matches first
 *   "verify": true,
 *   "meetings": [{
 *     "subject": "...",
 *     "startIso": "2026-09-17T20:00:00+05:30",
 *     "endIso": "2026-09-17T20:10:00+05:30",
 *     "attendees": [{ "email": "...", "name": "..." }]
 *   }]
 * }
 */
import fs from "node:fs";
import {
  calendarDayUrl,
  cancelAllMatching,
  createOneMeeting,
  emit,
  ensureLoggedIn,
  launchOutlookContext,
  verifyMeetings,
} from "./outlook_playwright_lib.mjs";

async function main() {
  const payloadPath = process.argv[2];
  if (!payloadPath || !fs.existsSync(payloadPath)) {
    emit({ ok: false, error: "Payload JSON path required" });
    process.exit(1);
  }
  const payload = JSON.parse(fs.readFileSync(payloadPath, "utf8"));
  const meetings = payload.meetings || [];
  if (!meetings.length) {
    emit({ ok: false, error: "No meetings in payload" });
    process.exit(1);
  }

  const timeZone = payload.timezone || "Asia/Kolkata";
  const dayUrl = calendarDayUrl(meetings[0].startIso, timeZone);
  const replacePattern = payload.replacePattern ? String(payload.replacePattern) : "";
  const titleRe = replacePattern
    ? new RegExp(replacePattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i")
    : null;

  let context;
  let page;
  try {
    ({ context, page } = await launchOutlookContext());
    const loginWaitMinutes = payload.loginWaitMinutes || 0;
    await ensureLoggedIn(page, dayUrl, {
      waitMinutes: loginWaitMinutes,
      interactive: loginWaitMinutes > 0,
    });

    let replaced = { cancelled: 0, errors: [] };
    if (replacePattern) {
      replaced = await cancelAllMatching(page, titleRe, dayUrl);
    }

    const results = [];
    for (let i = 0; i < meetings.length; i++) {
      try {
        if (i === 0 || !page.url().includes("/calendar/view/day")) {
          await ensureLoggedIn(page, dayUrl);
        }
        const r = await createOneMeeting(page, meetings[i], timeZone);
        results.push({ slot: i + 1, ...r });
      } catch (err) {
        results.push({ slot: i + 1, ok: false, error: String(err) });
        await page.goto(dayUrl).catch(() => {});
        await page.waitForTimeout(800);
      }
    }

    const scheduled = results.filter((r) => r.ok).length;
    let verification = null;
    if (payload.verify !== false && titleRe) {
      verification = await verifyMeetings(page, dayUrl, meetings, titleRe, timeZone);
    }

    const ok =
      scheduled === meetings.length && (!verification || verification.ok);

    emit({
      ok,
      status: ok ? "ok" : scheduled ? "partial" : "failed",
      scheduled,
      total: meetings.length,
      mode: "playwright_outlook",
      replaced,
      verification,
      results,
    });
    process.exit(ok ? 0 : 1);
  } catch (err) {
    emit({ ok: false, error: String(err), mode: "playwright_outlook" });
    process.exit(1);
  } finally {
    if (context) await context.close().catch(() => {});
  }
}

main();
