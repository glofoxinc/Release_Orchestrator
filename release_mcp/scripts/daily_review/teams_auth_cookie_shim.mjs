/**
 * ABC tenant / newer Teams web: session stores authtoken_asm, not authtoken.
 * @shayanline/msteams-mcp extractMessageAuth expects authtoken — alias before auth checks.
 */
import { readSessionState, writeSessionState } from "@shayanline/msteams-mcp/dist/auth/session-store.js";

function teamsDomain(cookie) {
  return (cookie?.domain || "").includes("teams.microsoft");
}

/** Persist authtoken alias when only authtoken_asm exists. Returns true if session patched. */
export function ensureAuthtokenCookieAlias() {
  const state = readSessionState();
  if (!state?.cookies?.length) {
    return false;
  }
  const cookies = state.cookies;
  const hasAuthtoken = cookies.some((c) => c.name === "authtoken" && teamsDomain(c) && c.value);
  if (hasAuthtoken) {
    return true;
  }
  const asm = cookies.find((c) => c.name === "authtoken_asm" && teamsDomain(c) && c.value);
  if (!asm) {
    return false;
  }
  writeSessionState({
    ...state,
    cookies: [...cookies, { ...asm, name: "authtoken" }],
  });
  return true;
}
