/* Who am I, and what can this deployment do?
 *
 * The browser probes this on load, and it has to answer while signed out —
 * that is how the app knows to show a password prompt instead of falling back
 * to local profiles. So the signed-out answer is deliberately almost empty.
 *
 * Anyone can reach this. Telling them a server-held API key is sitting here,
 * or that the deployment is misconfigured, is free reconnaissance for the one
 * visitor who should not have it. The details only appear once you are in,
 * where they are the owner's own diagnostics. */

import { resolveSecret } from "./_lib.js";

export async function onRequestGet({ env, data }) {
  if (!data.email) {
    return json({ hosted: true, authed: false });
  }

  return json({
    hosted: true,
    authed: true,
    email: data.email,
    configured: !!data.configured,
    authMethod: data.accessConfigured ? "access" : data.passwordConfigured ? "password" : "none",
    hasServerKey: !!(await resolveSecret(env, "ANTHROPIC_API_KEY")),
    sync: !!env.PREPHERO
  });
}

function json(body) {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json", "cache-control": "no-store" }
  });
}
