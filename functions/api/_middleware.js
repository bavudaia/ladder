/* Guards every /api/* route.
 *
 * Two ways to prove who you are, and the deployment can use either:
 *
 *   1. Cloudflare Access — a signed JWT verified against your team's public
 *      keys. Strongest option: an unauthenticated request never reaches this
 *      code at all, and there is no password to guess. Needs Zero Trust.
 *
 *   2. A password session cookie — signed with an HMAC key derived from
 *      APP_PASSWORD. Weaker: this endpoint is publicly reachable and the
 *      security is entirely the strength of that password. Needs no Zero Trust.
 *
 * If Access is configured it is preferred, and the password path still works,
 * so a deployment can move from 2 to 1 by setting two variables.
 *
 * This fails closed. With neither mechanism configured every route is refused —
 * a half-configured deployment must not become an open relay to your API key.
 *
 * /api/me is the exception: it answers unauthenticated so the browser can find
 * out that this is a PrepHero deployment and show the right login. It returns
 * booleans about configuration only, never a secret.
 */

import { json, verifySession, readCookie, resolveSecret, SESSION_COOKIE } from "./_lib.js";

const CERT_TTL_MS = 60 * 60 * 1000;
let certCache = { at: 0, domain: "", keys: null };

function b64urlToBytes(s) {
  const pad = String(s).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(pad + "=".repeat((4 - (pad.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function b64urlToText(s) {
  return new TextDecoder().decode(b64urlToBytes(s));
}

async function accessKeys(teamDomain) {
  const fresh = certCache.keys && certCache.domain === teamDomain && Date.now() - certCache.at < CERT_TTL_MS;
  if (fresh) return certCache.keys;

  const res = await fetch(`https://${teamDomain}/cdn-cgi/access/certs`);
  if (!res.ok) throw new Error(`Could not fetch Access certs (${res.status}).`);
  const body = await res.json();
  const keys = {};
  for (const jwk of body.keys || []) {
    keys[jwk.kid] = await crypto.subtle.importKey(
      "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  }
  certCache = { at: Date.now(), domain: teamDomain, keys };
  return keys;
}

async function verifyAccessJwt(token, teamDomain, aud) {
  const parts = String(token || "").split(".");
  if (parts.length !== 3) throw new Error("Malformed Access token.");

  const header = JSON.parse(b64urlToText(parts[0]));
  const payload = JSON.parse(b64urlToText(parts[1]));
  const keys = await accessKeys(teamDomain);
  const key = keys[header.kid];
  if (!key) throw new Error("Access token was signed by an unknown key.");

  const signed = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const okSig = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64urlToBytes(parts[2]), signed);
  if (!okSig) throw new Error("Access token signature did not verify.");

  const now = Math.floor(Date.now() / 1000);
  if (payload.exp && payload.exp < now) throw new Error("Access token has expired.");
  if (payload.nbf && payload.nbf > now + 60) throw new Error("Access token is not valid yet.");

  const audience = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!audience.includes(aud)) throw new Error("Access token is for a different application.");
  if (payload.iss !== `https://${teamDomain}`) throw new Error("Access token has the wrong issuer.");

  const email = payload.email || payload.common_name;
  if (!email) throw new Error("Access token carries no identity.");
  return String(email).toLowerCase();
}

async function identify(request, env, appPassword) {
  const accessConfigured = !!(env.ACCESS_TEAM_DOMAIN && env.ACCESS_AUD);

  if (accessConfigured) {
    const token = request.headers.get("Cf-Access-Jwt-Assertion");
    if (token) {
      const email = await verifyAccessJwt(token, env.ACCESS_TEAM_DOMAIN, env.ACCESS_AUD);
      return { email, via: "access" };
    }
  }

  if (appPassword) {
    const payload = await verifySession(appPassword, readCookie(request, SESSION_COOKIE));
    if (payload) return { email: payload.sub || "owner", via: "password" };
  }

  return null;
}

export async function onRequest(context) {
  const { request, env, next, data } = context;
  const path = new URL(request.url).pathname;

  const appPassword = await resolveSecret(env, "APP_PASSWORD");
  const accessConfigured = !!(env.ACCESS_TEAM_DOMAIN && env.ACCESS_AUD);
  const passwordConfigured = !!appPassword;
  const configured = accessConfigured || passwordConfigured;

  let who = null, failure = null;
  if (configured) {
    try { who = await identify(request, env, appPassword); }
    catch (e) { failure = e.message || "Verification failed."; }
  }

  data.email = who ? who.email : null;
  data.authedVia = who ? who.via : null;
  data.configured = configured;
  data.accessConfigured = accessConfigured;
  data.passwordConfigured = passwordConfigured;

  /* The probe and the login endpoint have to be reachable while logged out. */
  if (path === "/api/me" || path === "/api/login" || path === "/api/logout") return next();

  if (!configured) {
    return json({ error: {
      message: "This deployment is not protected. Set APP_PASSWORD (or ACCESS_TEAM_DOMAIN and ACCESS_AUD) " +
        "before the API will answer — otherwise it would be an open relay to your Anthropic key."
    } }, 503);
  }
  if (failure) return json({ error: { message: failure } }, 403);
  if (!who) return json({ error: { message: "Not signed in." } }, 401);

  return next();
}
