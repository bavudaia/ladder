/* Who am I, and what can this deployment do?
 *
 * The browser probes this on load. It answers whether authenticated or not —
 * that is how the app knows to show a password prompt rather than falling back
 * to purely local mode — so it returns configuration booleans only, never a
 * secret and never the reason a login failed. */

import { resolveSecret } from "./_lib.js";

export async function onRequestGet({ env, data }) {
  const hasServerKey = !!(await resolveSecret(env, "ANTHROPIC_API_KEY"));
  return new Response(JSON.stringify({
    hosted: true,
    authed: !!data.email,
    email: data.email || null,
    configured: !!data.configured,
    authMethod: data.accessConfigured ? "access" : data.passwordConfigured ? "password" : "none",
    hasServerKey: hasServerKey,
    sync: !!env.PREPHERO
  }), { headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
