/**
 * Shared Outlook web automation — matches the Playwright MCP flow proven on ABC tenant.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const PROJECT_ROOT = path.resolve(__dirname, "../..");
export const USER_DATA = path.join(PROJECT_ROOT, "daily_review_agent", ".state", "playwright-outlook-profile");
export const SESSION_MARKER = path.join(USER_DATA, ".outlook_session_ok");
export const CALENDAR_DAY_BASE = "https://outlook.cloud.microsoft/calendar/view/day";
const DEFAULT_TZ = "Asia/Kolkata";

export function emit(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

export function formatTime12(iso, timeZone = DEFAULT_TZ) {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone,
  });
}

export function calendarDayUrl(isoOrDay, timeZone = DEFAULT_TZ) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(isoOrDay))) {
    return `${CALENDAR_DAY_BASE}/${isoOrDay}`;
  }
  const d = new Date(isoOrDay);
  const day = d.toLocaleDateString("en-CA", { timeZone });
  return `${CALENDAR_DAY_BASE}/${day}`;
}

export async function launchOutlookContext() {
  fs.mkdirSync(USER_DATA, { recursive: true });
  const context = await chromium.launchPersistentContext(USER_DATA, {
    channel: "msedge",
    headless: false,
    viewport: { width: 1400, height: 900 },
  });
  const page = context.pages()[0] || (await context.newPage());
  return { context, page };
}

export async function ensureLoggedIn(page, dayUrl, options = {}) {
  const waitMinutes = options.waitMinutes ?? 0;
  const interactive = options.interactive ?? false;
  const deadline = Date.now() + waitMinutes * 60 * 1000;

  while (true) {
    await page.goto(dayUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForTimeout(1000);

    if (!page.url().includes("login.microsoftonline.com")) {
      try {
        await page.getByRole("button", { name: /New event/i }).first().waitFor({ timeout: 8000 });
        writeSessionMarker(page.url());
        return;
      } catch {
        /* calendar not ready yet */
      }
    }

    if (!interactive || Date.now() >= deadline) {
      throw new Error(
        interactive
          ? `Outlook sign-in not completed within ${waitMinutes} minutes. Sign in with abcfitness.com in Edge, then retry.`
          : "Outlook web is not signed in. Run: python -m daily_review_agent --outlook-login",
      );
    }
    await page.waitForTimeout(3000);
  }
}

function writeSessionMarker(url) {
  try {
    fs.writeFileSync(
      SESSION_MARKER,
      JSON.stringify({ ok: true, url, signed_in_at: new Date().toISOString() }, null, 2),
    );
  } catch {
    /* non-fatal */
  }
}

function composeDialog(page) {
  return page.locator('[role="document"]').filter({ hasText: /New event|Edit event|Daily Review/i }).first();
}

async function openTimeEditor(page, dialog) {
  const dtBtn = dialog.getByRole("button", { name: /\d{1,2}:\d{2}.*-/i }).first();
  if (await dtBtn.count()) {
    await dtBtn.click();
    await page.waitForTimeout(600);
    return;
  }
  throw new Error("Date/time button not found in compose dialog");
}

async function setTimeCombobox(page, label, value12) {
  const td = page.locator('[role="dialog"]').filter({ hasText: "Start time" }).last();
  await td.getByRole("combobox", { name: label }).fill(value12);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
}

async function closeTimePicker(page) {
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
  }
  const timeDialog = page.locator('[role="dialog"]').filter({ hasText: /Start time|End time/i });
  if (await timeDialog.count()) {
    await timeDialog.last().waitFor({ state: "hidden", timeout: 8000 }).catch(() => {});
  }
  const backdrop = page.locator(".fui-DialogSurface__backdrop");
  if (await backdrop.count()) {
    await backdrop.first().waitFor({ state: "hidden", timeout: 8000 }).catch(() => {});
  }
  await page.waitForTimeout(400);
}

async function addAttendee(page, dialog, email) {
  if (!email) return;
  await closeTimePicker(page);
  const field = dialog.getByLabel(/Invite required attendees/i);
  await field.click({ force: true, timeout: 15000 });
  await page.keyboard.type(email, { delay: 20 });
  await page.waitForTimeout(1200);
  const opt = page.getByRole("option", { name: new RegExp(email.split("@")[0], "i") }).first();
  if (await opt.count()) {
    await opt.click();
  } else {
    await page.keyboard.press("Enter");
  }
  await page.waitForTimeout(400);
}

export async function createOneMeeting(page, meeting, timeZone = DEFAULT_TZ) {
  const start12 = formatTime12(meeting.startIso, timeZone);
  const end12 = formatTime12(meeting.endIso, timeZone);
  const attendees = (meeting.attendees || []).map((a) => a.email).filter(Boolean);

  await page.getByRole("button", { name: /New event/i }).first().click({ timeout: 30000 });
  const dialog = composeDialog(page);
  await dialog.waitFor({ state: "visible", timeout: 20000 });

  await dialog.getByRole("textbox", { name: /Add title/i }).fill(meeting.subject || "Daily Review Agent meeting");

  await openTimeEditor(page, dialog);
  await setTimeCombobox(page, "Start time", start12);
  await setTimeCombobox(page, "End time", end12);
  await closeTimePicker(page);

  for (const email of attendees) {
    await addAttendee(page, dialog, email);
  }

  const teamsSwitch = dialog.getByRole("switch").first();
  if (await teamsSwitch.count() && (await teamsSwitch.getAttribute("aria-checked")) !== "true") {
    await teamsSwitch.click();
  }

  let joinUrl = "";
  const joinLink = dialog.locator('a[href*="teams.microsoft.com"]').first();
  if (await joinLink.count()) {
    joinUrl = (await joinLink.getAttribute("href")) || "";
  }

  await dialog.getByRole("button", { name: "Send" }).first().click({ timeout: 20000 });
  await dialog.waitFor({ state: "hidden", timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(600);

  return {
    ok: true,
    sent: true,
    backend: "playwright_outlook",
    subject: meeting.subject,
    start: meeting.startIso,
    end: meeting.endIso,
    join_url: joinUrl,
    attendees,
  };
}

export async function cancelEventViaPeek(page, titlePattern) {
  const event = page.getByRole("button", { name: titlePattern }).first();
  if (!(await event.count())) {
    return { cancelled: false, reason: "not_found" };
  }
  await event.click();
  await page.waitForTimeout(900);

  const more = page.getByRole("button", { name: "More options" }).last();
  if (!(await more.count())) {
    await page.keyboard.press("Escape");
    return { cancelled: false, reason: "no_more_options" };
  }
  await more.click();
  await page.waitForTimeout(500);
  await page.getByRole("menuitem", { name: "Cancel" }).first().click();
  await page.waitForTimeout(500);
  await page
    .getByRole("menu", { name: "Cancel" })
    .getByRole("menuitem", { name: "Cancel", exact: true })
    .click();
  await page.waitForTimeout(1500);
  return { cancelled: true };
}

export async function cancelAllMatching(page, titlePattern, dayUrl, max = 30) {
  let cancelled = 0;
  const errors = [];
  for (let i = 0; i < max; i++) {
    await page.goto(dayUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForTimeout(1000);
    const result = await cancelEventViaPeek(page, titlePattern);
    if (!result.cancelled) {
      if (result.reason !== "not_found") {
        errors.push(result.reason || "cancel_failed");
      }
      break;
    }
    cancelled += 1;
  }
  return { cancelled, errors };
}

export async function listMatchingEvents(page, titlePattern) {
  const labels = [];
  for (const e of await page.locator('[role="button"][aria-label*="PM"], [role="button"][aria-label*="AM"]').all()) {
    const lbl = await e.getAttribute("aria-label");
    if (lbl && titlePattern.test(lbl)) {
      labels.push(lbl);
    }
  }
  return labels;
}

export async function verifyMeetings(page, dayUrl, meetings, titlePattern, timeZone = DEFAULT_TZ) {
  await page.goto(dayUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.waitForTimeout(1200);
  const onCalendar = await listMatchingEvents(page, titlePattern);
  const missing = [];
  for (const m of meetings) {
    const start12 = formatTime12(m.startIso, timeZone);
    const re = new RegExp(m.subject.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
    const timeOk = onCalendar.some((lbl) => re.test(lbl) && lbl.includes(start12));
    if (!timeOk) {
      missing.push({ subject: m.subject, expectedStart: start12, onCalendar });
    }
  }
  return { ok: missing.length === 0, onCalendar, missing };
}
