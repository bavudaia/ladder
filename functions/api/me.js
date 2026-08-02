/* Who am I, and what can this deployment do?
 * The browser probes this on load: a 200 means hosted mode (Access identity,
 * server-held key, synced season). Anything else and the app falls back to
 * running purely locally. */

export async function onRequestGet({ env, data }) {
  return new Response(JSON.stringify({
    hosted: true,
    email: data.email,
    hasServerKey: !!env.ANTHROPIC_API_KEY,
    sync: !!env.PREPHERO
  }), { headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
