/* Password login, for deployments without Cloudflare Access.
 *
 * This endpoint is reachable by anyone who finds the URL — that is the cost of
 * not putting Access in front — so it is throttled per IP and compares digests
 * rather than strings. The password itself is a deployment secret and is never
 * returned, logged, or echoed. */

import {
  json, passwordMatches, signSession, sessionCookie, sessionHours, clearedCookie,
  throttleState, recordFailure, clearFailures, clientIp, MAX_FAILURES, WINDOW_SECONDS
} from "./_lib.js";

export async function onRequestPost({ request, env }) {
  if (!env.APP_PASSWORD) {
    return json({ error: { message: "This deployment has no APP_PASSWORD set, so password login is disabled." } }, 503);
  }
  /* Throttling needs somewhere to count. Refuse rather than run an
     unthrottled password endpoint on the open internet. */
  if (!env.PREPHERO) {
    return json({ error: { message: "No KV namespace bound as PREPHERO; login is disabled without it." } }, 503);
  }

  const ip = clientIp(request);
  const state = await throttleState(env, ip);
  if (state && state.failures >= MAX_FAILURES) {
    const retry = Math.max(1, (state.until || 0) - Math.floor(Date.now() / 1000));
    return json({ error: { message: "Too many failed attempts. Try again later." } }, 429,
      { "retry-after": String(retry) });
  }

  let body;
  try { body = await request.json(); } catch (e) { body = null; }
  const given = body && typeof body.password === "string" ? body.password : "";

  if (!(await passwordMatches(given, env.APP_PASSWORD))) {
    await recordFailure(env, ip);
    const left = Math.max(0, MAX_FAILURES - ((state ? state.failures : 0) + 1));
    return json({ error: { message: "Wrong password." }, attemptsLeft: left }, 401,
      { "set-cookie": clearedCookie() });
  }

  await clearFailures(env, ip);
  const hours = sessionHours(env);
  const token = await signSession(env.APP_PASSWORD, {
    sub: "owner",
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + hours * 3600
  });
  return json({ ok: true, hours: hours }, 200, { "set-cookie": sessionCookie(token, hours * 3600) });
}

export async function onRequestGet() {
  return json({ error: { message: "POST a password here." } }, 405);
}
