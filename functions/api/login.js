/* Password login, for deployments without Cloudflare Access.
 *
 * This endpoint is reachable by anyone who finds the URL — that is the cost of
 * not putting Access in front — so it is throttled per IP and compares digests
 * rather than strings. The password itself is a deployment secret and is never
 * returned, logged, or echoed. */

import {
  json, passwordMatches, signSession, sessionCookie, sessionHours, clearedCookie, resolveSecret,
  throttleState, recordFailure, clearFailures, clientIp, MAX_FAILURES
} from "./_lib.js";

export async function onRequestPost({ request, env }) {
  const appPassword = await resolveSecret(env, "APP_PASSWORD");
  if (!appPassword) {
    return json({ error: { message: "Sign-in is unavailable." } }, 503);
  }
  /* Throttling needs somewhere to count. Refuse rather than run an
     unthrottled password endpoint on the open internet. */
  if (!env.PREPHERO) {
    return json({ error: { message: "Sign-in is unavailable." } }, 503);
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

  if (!(await passwordMatches(given, appPassword))) {
    await recordFailure(env, ip);
    return json({ error: { message: "Wrong password." } }, 401, { "set-cookie": clearedCookie() });
  }

  await clearFailures(env, ip);
  const hours = sessionHours(env);
  const token = await signSession(appPassword, {
    sub: "owner",
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + hours * 3600
  });
  return json({ ok: true, hours: hours }, 200, { "set-cookie": sessionCookie(token, hours * 3600) });
}

export async function onRequestGet() {
  return json({ error: { message: "POST a password here." } }, 405);
}
