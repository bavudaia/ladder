/* Guards every /api/* route.
 *
 * Cloudflare Access sits in front of this deployment and puts a signed JWT on
 * each request. We verify that signature ourselves rather than trusting the
 * header's presence, because a header is trivially forged if a request ever
 * reaches the origin without passing through Access.
 *
 * This fails closed on purpose. If ACCESS_TEAM_DOMAIN or ACCESS_AUD is missing,
 * every API call is refused — a misconfigured deployment must not become an
 * open relay to your Anthropic key.
 */

const CERT_TTL_MS = 60 * 60 * 1000;
let certCache = { at: 0, domain: "", keys: null };

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" }
  });
}

function b64urlToBytes(s) {
  const pad = s.replace(/-/g, "+").replace(/_/g, "/");
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
  const okSig = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5", key, b64urlToBytes(parts[2]), signed);
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

export async function onRequest(context) {
  const { request, env, next, data } = context;

  if (!env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD) {
    return json({ error: {
      message: "This deployment is not protected. Set ACCESS_TEAM_DOMAIN and ACCESS_AUD, " +
        "and put a Cloudflare Access policy in front of this hostname, before the API will answer."
    } }, 503);
  }

  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) return json({ error: { message: "No Cloudflare Access identity on this request." } }, 401);

  try {
    data.email = await verifyAccessJwt(token, env.ACCESS_TEAM_DOMAIN, env.ACCESS_AUD);
  } catch (e) {
    return json({ error: { message: e.message || "Access verification failed." } }, 403);
  }

  return next();
}
