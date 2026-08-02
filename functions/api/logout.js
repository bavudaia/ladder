import { json, clearedCookie } from "./_lib.js";

export async function onRequestPost() {
  return json({ ok: true }, 200, { "set-cookie": clearedCookie() });
}
