/* Shared helpers for the API routes.
 *
 * Files prefixed with _ are not routed by Pages, so this is import-only.
 *
 * The session scheme: a cookie holding base64url(payload).base64url(HMAC),
 * where the HMAC key is derived from APP_PASSWORD itself. That has a property
 * worth having — changing the password invalidates every existing session, so
 * rotating it is also a "log out everywhere" button — and it means one secret
 * to configure instead of two.
 */

export const SESSION_COOKIE = "ph_session";
export const DEFAULT_SESSION_HOURS = 24;

/* Failed logins allowed per window, per IP. The login endpoint faces the open
   internet in this mode, unlike the Access-protected one. */
export const MAX_FAILURES = 8;
export const WINDOW_SECONDS = 15 * 60;

/* A secret can arrive two ways, and the dashboard makes it easy to pick either:
 *
 *   - a project-level secret in Settings -> Variables and Secrets, which lands
 *     on env as a plain string, or
 *   - a binding to the account-level Secrets Store, which lands as an object
 *     whose get() resolves to the value.
 *
 * Accept both, so a working deployment does not depend on guessing which one
 * the person configuring it happened to use. */
export async function resolveSecret(env, name) {
  const v = env ? env[name] : null;
  if (!v) return "";
  if (typeof v === "string") return v;
  if (typeof v.get === "function") {
    try { return (await v.get()) || ""; } catch (e) { return ""; }
  }
  return "";
}

export function json(body, status, extraHeaders) {
  const headers = { "content-type": "application/json", "cache-control": "no-store" };
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: Object.assign(headers, extraHeaders || {})
  });
}

export function b64urlEncode(bytes) {
  let bin = "";
  const a = new Uint8Array(bytes);
  for (let i = 0; i < a.length; i++) bin += String.fromCharCode(a[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function b64urlDecode(s) {
  const pad = String(s).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(pad + "=".repeat((4 - (pad.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

const enc = new TextEncoder();

async function sha256(text) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(text)));
}

/* Compare digests, not the strings: equal length, and no early exit. */
export async function passwordMatches(given, expected) {
  if (typeof given !== "string" || typeof expected !== "string" || !expected) return false;
  const [a, b] = await Promise.all([sha256(given), sha256(expected)]);
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

async function hmacKey(secret) {
  return crypto.subtle.importKey(
    "raw", enc.encode("prephero-session:" + secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

export async function signSession(secret, payload) {
  const body = b64urlEncode(enc.encode(JSON.stringify(payload)));
  const key = await hmacKey(secret);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(body));
  return body + "." + b64urlEncode(sig);
}

export async function verifySession(secret, token) {
  const parts = String(token || "").split(".");
  if (parts.length !== 2) return null;
  const key = await hmacKey(secret);
  let ok = false;
  try {
    ok = await crypto.subtle.verify("HMAC", key, b64urlDecode(parts[1]), enc.encode(parts[0]));
  } catch (e) { return null; }
  if (!ok) return null;

  let payload;
  try { payload = JSON.parse(new TextDecoder().decode(b64urlDecode(parts[0]))); }
  catch (e) { return null; }
  if (!payload || !payload.exp || payload.exp < Math.floor(Date.now() / 1000)) return null;
  return payload;
}

export function readCookie(request, name) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    if (part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

export function sessionCookie(token, maxAgeSeconds) {
  return `${SESSION_COOKIE}=${token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${maxAgeSeconds}`;
}

export function clearedCookie() {
  return `${SESSION_COOKIE}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0`;
}

export function sessionHours(env) {
  const n = Number(env.SESSION_HOURS);
  return n > 0 && n <= 24 * 30 ? n : DEFAULT_SESSION_HOURS;
}

/* --- login throttling, KV backed --- */

function rlKey(ip) { return "rl:" + (ip || "unknown"); }

export async function throttleState(env, ip) {
  if (!env.PREPHERO) return null;
  const raw = await env.PREPHERO.get(rlKey(ip));
  if (!raw) return { failures: 0, until: 0 };
  try {
    const v = JSON.parse(raw);
    if (v.until && v.until < Math.floor(Date.now() / 1000)) return { failures: 0, until: 0 };
    return v;
  } catch (e) { return { failures: 0, until: 0 }; }
}

export async function recordFailure(env, ip) {
  if (!env.PREPHERO) return;
  const now = Math.floor(Date.now() / 1000);
  const state = (await throttleState(env, ip)) || { failures: 0, until: 0 };
  const next = { failures: state.failures + 1, until: state.until || now + WINDOW_SECONDS };
  await env.PREPHERO.put(rlKey(ip), JSON.stringify(next), { expirationTtl: WINDOW_SECONDS });
}

export async function clearFailures(env, ip) {
  if (!env.PREPHERO) return;
  await env.PREPHERO.delete(rlKey(ip));
}

export function clientIp(request) {
  return request.headers.get("CF-Connecting-IP") || "unknown";
}
