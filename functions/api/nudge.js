/* The daily nudge endpoint.
 *
 * Pages Functions have no scheduler, so the clock lives outside: a GitHub
 * Actions cron POSTs here once a day. That means this route is publicly
 * reachable and has to carry its own authentication — it is deliberately not
 * behind the session cookie, because a cron job has no session.
 *
 * It fails closed. With no NUDGE_SECRET set, nothing here answers, so a
 * half-configured deployment cannot be used to make your mail provider send
 * whatever a stranger asks it to.
 *
 * POST ?dry=1 renders the mail and returns it without sending — which is how
 * you check the copy without waiting for tomorrow.
 */

import { json, resolveSecret, passwordMatches } from "./_lib.js";
import { buildNudge } from "./_nudge.js";

/* The season stores local dates, so "today" has to be the owner's today. A
 * London cron firing at 07:00 must not tell someone in California their streak
 * broke because UTC has already rolled over. */
function localToday(tz) {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: tz || "UTC" }).format(new Date());
  } catch (e) {
    return new Date().toISOString().slice(0, 10);
  }
}

async function send(env, to, mail) {
  const key = await resolveSecret(env, "RESEND_API_KEY");
  if (!key) return { sent: false, error: "No RESEND_API_KEY set." };

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: JSON.stringify({
      from: env.NUDGE_FROM || "PrepHero <onboarding@resend.dev>",
      to: [to],
      subject: mail.subject,
      html: mail.html,
      text: mail.text
    })
  });

  const body = await res.text();
  if (!res.ok) return { sent: false, error: `Mail provider refused (${res.status}): ${body.slice(0, 300)}` };
  return { sent: true, id: (() => { try { return JSON.parse(body).id || null; } catch (e) { return null; } })() };
}

export async function onRequestPost({ request, env }) {
  const secret = await resolveSecret(env, "NUDGE_SECRET");
  if (!secret) return json({ error: { message: "Nudges are not configured." } }, 503);

  const given = request.headers.get("x-nudge-key");
  if (!(await passwordMatches(given, secret))) {
    return json({ error: { message: "Not authorised." } }, 401);
  }
  if (!env.PREPHERO) return json({ error: { message: "No KV namespace bound as PREPHERO." } }, 503);

  const to = env.NUDGE_TO;
  if (!to) return json({ error: { message: "No NUDGE_TO set." } }, 503);

  const identity = env.NUDGE_IDENTITY || "owner";
  const raw = await env.PREPHERO.get(`season:${identity}`);
  if (!raw) {
    return json({ error: { message: `No season stored for "${identity}". Open the app once so it syncs.` } }, 404);
  }

  let state;
  try { state = JSON.parse(raw); }
  catch (e) { return json({ error: { message: "Stored season is not readable." } }, 500); }

  const today = localToday(env.NUDGE_TZ);
  const appUrl = env.APP_URL || new URL(request.url).origin;
  const nudge = buildNudge(state, today, appUrl);

  /* A quiet day is still worth reporting, so the caller can see the copy that
     would have gone out without a message landing in the inbox. */
  const dry = new URL(request.url).searchParams.get("dry") === "1";
  if (dry) {
    return json({ dry: true, today, to, hook: nudge.hook, signals: nudge.signals,
      subject: nudge.subject, text: nudge.text, html: nudge.html });
  }

  const result = await send(env, to, nudge);
  if (!result.sent) return json({ error: { message: result.error }, hook: nudge.hook.id }, 502);

  return json({ sent: true, today, hook: nudge.hook.id, subject: nudge.subject, id: result.id });
}
