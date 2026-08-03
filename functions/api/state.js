/* The season, stored per Access identity.
 *
 * One blob per user in KV. The client merges rather than overwrites, so this
 * only has to be a dumb store — but it does reject a write that is older than
 * what it already holds, which stops a stale tab from rolling back a season
 * you advanced on another device. */

import { compareSeasons } from "./_lib.js";

const MAX_BYTES = 900 * 1024;   /* KV's value ceiling is 25 MB; this is a sanity bound */

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" }
  });
}

function keyFor(email) { return `season:${email}`; }

export async function onRequestGet({ env, data }) {
  if (!env.PREPHERO) return json({ error: { message: "No KV namespace bound as PREPHERO." } }, 503);
  const raw = await env.PREPHERO.get(keyFor(data.email));
  return json({ state: raw ? JSON.parse(raw) : null });
}

export async function onRequestPut({ request, env, data }) {
  if (!env.PREPHERO) return json({ error: { message: "No KV namespace bound as PREPHERO." } }, 503);

  const body = await request.text();
  if (body.length > MAX_BYTES) {
    return json({ error: { message: `Season is ${Math.round(body.length / 1024)} KB, over the ${Math.round(MAX_BYTES / 1024)} KB limit.` } }, 413);
  }

  let incoming;
  try { incoming = JSON.parse(body); } catch (e) { return json({ error: { message: "Body was not JSON." } }, 400); }
  if (!incoming || !incoming.user) return json({ error: { message: "That is not a season." } }, 400);

  const existingRaw = await env.PREPHERO.get(keyFor(data.email));
  if (existingRaw) {
    try {
      const existing = JSON.parse(existingRaw);
      const order = compareSeasons(incoming.epoch, existing.epoch);

      if (order < 0) {
        /* An older season than the one stored. This is a device running a build
           from before a reset — it must not be allowed to put the old season
           back, and there is nothing for it to merge, so say so plainly rather
           than sending it round the retry loop. */
        return json({ error: { message: "That season is older than the one already stored. This device is running an out-of-date build — reload it." },
          reason: "old-season", rev: Number(existing.rev || 0), state: existing }, 409);
      }

      /* order > 0 is a reset: the new season replaces the old outright, and its
         revision counter starting again at 1 is expected rather than stale. */
      if (order === 0) {
        const theirs = Number(incoming.rev || 0), ours = Number(existing.rev || 0);
        if (theirs < ours) {
          return json({ error: { message: "Stale write refused." },
            reason: "stale", rev: ours, state: existing }, 409);
        }
      }
    } catch (e) { /* unparseable stored blob: let the write through */ }
  }

  await env.PREPHERO.put(keyFor(data.email), JSON.stringify(incoming));
  return json({ ok: true, rev: incoming.rev || 0, updatedAt: incoming.updatedAt || null });
}
