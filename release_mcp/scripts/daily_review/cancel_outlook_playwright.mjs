/**
 * Cancel Outlook web meetings matching a title pattern (peek card → Cancel).
 * Usage: node cancel_outlook_playwright.mjs "Daily Review Agent — Mohan sync" 2026-09-17
 */
import {
  calendarDayUrl,
  cancelAllMatching,
  emit,
  ensureLoggedIn,
  launchOutlookContext,
  listMatchingEvents,
} from "./outlook_playwright_lib.mjs";

async function main() {
  const patternArg = process.argv[2] || "Daily Review Agent";
  const day = process.argv[3] || new Date().toISOString().slice(0, 10);
  const dayUrl = calendarDayUrl(day);
  const titlePattern = new RegExp(patternArg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");

  let context;
  let page;
  try {
    ({ context, page } = await launchOutlookContext());
    await ensureLoggedIn(page, dayUrl);
    const before = await listMatchingEvents(page, titlePattern);
    const result = await cancelAllMatching(page, titlePattern, dayUrl);
    await ensureLoggedIn(page, dayUrl);
    const after = await listMatchingEvents(page, titlePattern);
    emit({
      ok: true,
      mode: "cancel_outlook_playwright",
      day,
      pattern: patternArg,
      before_count: before.length,
      after_count: after.length,
      ...result,
    });
    process.exit(0);
  } catch (err) {
    emit({ ok: false, error: String(err), mode: "cancel_outlook_playwright" });
    process.exit(1);
  } finally {
    if (context) await context.close().catch(() => {});
  }
}

main();
