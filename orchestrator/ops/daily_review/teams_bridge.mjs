/**
 * CLI bridge: Daily Review Agent → @shayanline/msteams-mcp (browser session tokens).
 * Usage: node teams_bridge.mjs <command> '<json-payload>'
 * Commands: status | create-meeting | send-message | send-self-message
 */
console.log = (...args) => {
  console.error(...args);
};
if (!process.env.LOG_LEVEL) {
  process.env.LOG_LEVEL = "error";
}

import { fileURLToPath } from "node:url";
import path from "node:path";
import { ensureAuthtokenCookieAlias } from "./teams_auth_cookie_shim.mjs";
import { createMeeting } from "@shayanline/msteams-mcp/dist/api/calendar-api.js";
import { refreshTokensViaBrowser } from "@shayanline/msteams-mcp/dist/auth/token-refresh.js";
import { ensureAuthenticated } from "@shayanline/msteams-mcp/dist/browser/auth.js";
import { closeBrowser, createBrowserContext } from "@shayanline/msteams-mcp/dist/browser/context.js";
import { sendMessage, sendNoteToSelf } from "@shayanline/msteams-mcp/dist/api/chatsvc-messaging.js";
import { requireGraphAuth, requireMessageAuth } from "@shayanline/msteams-mcp/dist/utils/auth-guards.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function emit(result) {
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

function prepareSession() {
  ensureAuthtokenCookieAlias();
}

/** Headless refresh then optional interactive login — shared by bridge CLI and Python subprocess. */
async function ensureBridgeAuth({ interactive = false } = {}) {
  prepareSession();
  await refreshTokensViaBrowser();
  let messaging = requireMessageAuth();
  if (messaging.ok) {
    return messaging;
  }
  if (!interactive) {
    return messaging;
  }
  console.error("[teams_bridge] Opening Edge for Teams sign-in (abcfitness.com)...");
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
  await refreshTokensViaBrowser();
  return requireMessageAuth();
}

async function cmdStatus() {
  prepareSession();
  await refreshTokensViaBrowser();
  const graph = requireGraphAuth();
  const messaging = requireMessageAuth();
  emit({
    ok: messaging.ok,
    authenticated: messaging.ok,
    graph_ready: graph.ok,
    calendar_ready: graph.ok,
    message: messaging.ok
      ? graph.ok
        ? "Teams session ready (messaging + calendar)"
        : "Messaging ready; calendar Graph token unavailable (summary chat OK)"
      : messaging.error?.message || graph.error?.message || "Run teams_bridge login or teams_login in Cursor.",
  });
}

async function cmdLogin() {
  const messaging = await ensureBridgeAuth({ interactive: true });
  const graph = requireGraphAuth();
  emit({
    ok: messaging.ok,
    authenticated: messaging.ok,
    graph_ready: graph.ok,
    message: messaging.ok
      ? "Teams bridge login complete — messaging ready"
      : messaging.error?.message || "Login finished but messaging auth missing — retry login",
  });
  if (!messaging.ok) {
    process.exit(1);
  }
}

async function cmdCreateMeeting(payload) {
  prepareSession();
  await refreshTokensViaBrowser();
  const auth = requireGraphAuth();
  if (!auth.ok) {
    emit({ ok: false, error: auth.error?.message || "AUTH_REQUIRED" });
    return;
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
    emit({ ok: false, error: result.error?.message || "create_meeting_failed", detail: result.error });
    return;
  }
  emit({
    ok: true,
    event_id: result.value.id,
    join_url: result.value.joinUrl,
    subject: result.value.subject,
    startTime: result.value.startTime,
    endTime: result.value.endTime,
  });
}

async function cmdSendMessage(payload) {
  prepareSession();
  await refreshTokensViaBrowser();
  const messaging = requireMessageAuth();
  if (!messaging.ok) {
    emit({ ok: false, error: messaging.error?.message || "AUTH_REQUIRED" });
    return;
  }
  const result = await sendMessage(payload.conversationId, payload.content || "", {});
  if (!result.ok) {
    emit({ ok: false, error: result.error?.message || "send_message_failed", detail: result.error });
    return;
  }
  emit({ ok: true, messageId: result.value?.messageId, conversationId: payload.conversationId });
}

async function cmdSendSelfMessage(payload) {
  prepareSession();
  await refreshTokensViaBrowser();
  const auth = requireMessageAuth();
  if (!auth.ok) {
    emit({ ok: false, error: auth.error?.message || "AUTH_REQUIRED" });
    return;
  }
  const result = await sendNoteToSelf(payload.content || "");
  if (!result.ok) {
    emit({ ok: false, error: result.error?.message || "send_self_message_failed", detail: result.error });
    return;
  }
  emit({ ok: true, messageId: result.value?.messageId, channel: "organizer_self_chat" });
}

async function main() {
  const command = (process.argv[2] || "").trim();
  let payload = {};
  const raw = process.argv[3];
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (err) {
      emit({ ok: false, error: `Invalid JSON payload: ${err.message}` });
      process.exit(1);
    }
  }
  try {
    if (command === "status") {
      await cmdStatus();
      return;
    }
    if (command === "login") {
      await cmdLogin();
      return;
    }
    if (command === "create-meeting") {
      await cmdCreateMeeting(payload);
      return;
    }
    if (command === "send-message") {
      await cmdSendMessage(payload);
      return;
    }
    if (command === "send-self-message") {
      await cmdSendSelfMessage(payload);
      return;
    }
    emit({ ok: false, error: `Unknown command: ${command}` });
    process.exit(1);
  } catch (err) {
    emit({ ok: false, error: err instanceof Error ? err.message : String(err) });
    process.exit(1);
  }
}

main();
