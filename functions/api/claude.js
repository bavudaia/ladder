/* Anthropic proxy.
 *
 * The key is a deployment secret and never reaches a browser, which is what
 * makes multi-device work without pasting it onto every device — and what
 * makes a stolen laptop a non-event.
 *
 * The request is not passed through blindly: it is re-assembled from fields we
 * recognise, with the model checked against an allowlist and token counts
 * bounded, so that anyone who does get past Access still cannot turn this into
 * a general-purpose key for arbitrary work. */

const UPSTREAM = "https://api.anthropic.com/v1/messages";
const API_VERSION = "2023-06-01";
const MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"];
const MAX_TOKENS = 16000;
const MAX_BODY = 6 * 1024 * 1024;   /* diagrams travel as base64 */

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" }
  });
}

export async function onRequestPost({ request, env }) {
  if (!env.ANTHROPIC_API_KEY) {
    return json({ error: { message: "ANTHROPIC_API_KEY is not set on this deployment." } }, 503);
  }

  const raw = await request.text();
  if (raw.length > MAX_BODY) return json({ error: { message: "Request too large." } }, 413);

  let body;
  try { body = JSON.parse(raw); } catch (e) { return json({ error: { message: "Body was not JSON." } }, 400); }

  if (MODELS.indexOf(body.model) < 0) {
    return json({ error: { message: `Model ${body.model} is not allowed on this deployment.` } }, 400);
  }
  if (!Array.isArray(body.messages) || !body.messages.length) {
    return json({ error: { message: "No messages." } }, 400);
  }

  const forward = {
    model: body.model,
    max_tokens: Math.min(Number(body.max_tokens) || 4000, MAX_TOKENS),
    messages: body.messages,
    stream: body.stream !== false
  };
  if (typeof body.system === "string") forward.system = body.system;
  if (body.output_config && typeof body.output_config === "object") forward.output_config = body.output_config;

  let upstream;
  try {
    upstream = await fetch(UPSTREAM, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": API_VERSION
      },
      body: JSON.stringify(forward)
    });
  } catch (e) {
    return json({ error: { message: "Could not reach api.anthropic.com." } }, 502);
  }

  /* Stream straight through so the interviewer still types in real time. */
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": "no-store"
    }
  });
}
