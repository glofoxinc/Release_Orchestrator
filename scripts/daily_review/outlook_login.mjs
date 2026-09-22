/**
 * One-time Outlook web sign-in for the agent Edge profile.
 * Usage: node outlook_login.mjs [waitMinutes=10]
 */
import fs from "node:fs";
import {
  calendarDayUrl,
  emit,
  ensureLoggedIn,
  launchOutlookContext,
  PROJECT_ROOT,
  USER_DATA,
} from "./outlook_playwright_lib.mjs";

async function main() {
  const waitMinutes = Math.max(1, parseInt(process.argv[2] || "10", 10) || 10);
  const dayUrl = calendarDayUrl(new Date().toISOString());

  let context;
  let page;
  try {
    ({ context, page } = await launchOutlookContext());
    await ensureLoggedIn(page, dayUrl, { waitMinutes, interactive: true });
    const marker = {
      ok: true,
      url: page.url(),
      profile: USER_DATA,
      message: "Outlook web session ready for Daily Review Agent",
    };
    fs.mkdirSync(USER_DATA, { recursive: true });
    fs.writeFileSync(
      `${USER_DATA}/.outlook_session_ok`,
      JSON.stringify({ ...marker, signed_in_at: new Date().toISOString() }, null, 2),
    );
    emit(marker);
    process.exit(0);
  } catch (err) {
    emit({
      ok: false,
      error: String(err),
      profile: USER_DATA,
      hint: `Sign in at ${dayUrl} with abcfitness.com in the opened Edge window`,
    });
    process.exit(1);
  } finally {
    if (context) await context.close().catch(() => {});
  }
}

main();
