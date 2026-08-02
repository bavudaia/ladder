"""Password-protected deployments (Option B: no Cloudflare Access).

What matters here is that the app fails closed. An unauthenticated visitor must
see a password prompt and nothing else — no season, no key, no API calls — and
a deployment with no password configured must refuse to pretend it is protected.
"""

import sys
from harness import HEAD_RAW, dom, run, report

# A deployment guarded by a password rather than Access. The stub models the
# server's view: /api/me answers while logged out, everything else needs the
# cookie, and the "cookie" here is just a flag the fake server flips on login.
PW_FETCH = r"""
globalThis.__password = "a-24-character-strong-pw";
globalThis.__signedIn = false;
globalThis.__configured = true;
globalThis.__remote = null;
globalThis.__calls = [];
globalThis.__failures = 0;
globalThis.__lockedOut = false;

function __res(status, obj, ok){
  return Promise.resolve({
    ok: ok !== undefined ? ok : (status >= 200 && status < 300), status: status,
    json: function(){ return Promise.resolve(obj); },
    text: function(){ return Promise.resolve(JSON.stringify(obj)); },
    headers: { get: function(){ return "application/json"; } },
    body: { getReader: function(){ var sent=false; return { read: function(){
      if (sent) return Promise.resolve({done:true});
      sent = true;
      var t = 'data: ' + JSON.stringify({type:"content_block_delta",delta:{type:"text_delta",text:globalThis.__reply||"{}"}}) +
              '\n\n' + 'data: ' + JSON.stringify({type:"message_delta",delta:{stop_reason:"end_turn"}}) + '\n\n';
      var codes=[]; for(var i=0;i<t.length;i++) codes.push(t.charCodeAt(i));
      return Promise.resolve({done:false, value:codes});
    } }; } }
  });
}

function fetch(url, opts){
  opts = opts || {};
  var body = opts.body ? JSON.parse(opts.body) : null;
  globalThis.__calls.push({ url:url, method:opts.method || "GET", body:body });

  if (url === "/api/me") {
    /* answers signed in or not — that is how the app knows to show a prompt */
    return __res(200, { hosted:true, authed:globalThis.__signedIn,
      email: globalThis.__signedIn ? "owner" : null,
      configured: globalThis.__configured, authMethod: globalThis.__configured ? "password" : "none",
      hasServerKey:true, sync:true });
  }
  if (url === "/api/login") {
    if (!globalThis.__configured) return __res(503, { error:{message:"This deployment has no APP_PASSWORD set, so password login is disabled."} });
    if (globalThis.__lockedOut) return __res(429, { error:{message:"Too many failed attempts. Try again later."} });
    if (body && body.password === globalThis.__password) { globalThis.__signedIn = true; globalThis.__failures = 0; return __res(200, { ok:true, hours:24 }); }
    globalThis.__failures++;
    if (globalThis.__failures >= 8) globalThis.__lockedOut = true;
    return __res(401, { error:{message:"Wrong password."}, attemptsLeft: Math.max(0, 8 - globalThis.__failures) });
  }
  if (url === "/api/logout") { globalThis.__signedIn = false; return __res(200, { ok:true }); }

  /* everything else is gated */
  if (!globalThis.__signedIn) return __res(401, { error:{message:"Not signed in."} });

  if (url === "/api/state") {
    if ((opts.method || "GET") === "GET") return __res(200, { state: globalThis.__remote });
    globalThis.__remote = body;
    return __res(200, { ok:true });
  }
  if (url === "/api/claude") return __res(200, {});
  return __res(404, {});
}
"""

LOGIN = HEAD_RAW + r"""
settle();

print("-- a locked-out visitor sees a password prompt, not the app --");
ok(T.SYNC.hosted === true, "hosted deployment detected even while signed out");
ok(T.SYNC.authed === false, "and it knows we are not signed in");
ok(T.state === null, "no season is loaded");
ok(__el("appShell")._c.hidden === 1, "the app shell is hidden");
ok(__el("authTitle").textContent === "Unlock", "the prompt says Unlock, got " + __el("authTitle").textContent);
ok(__el("authUserWrap")._c.hidden === 1, "no profile-name field — there is one deployment password");
ok(__el("authConfirmWrap")._c.hidden === 1, "and no signup confirm field");
ok(__el("authSwitch")._c.hidden === 1, "no 'create another profile' link");
ok(__el("authLede").textContent.indexOf("password protected") >= 0, "it explains the deployment is protected");

print("-- a wrong password is refused and changes nothing --");
__el("authPass").value = "not-the-password";
T.submitAuth(); settle();
ok(__el("authErr").textContent.indexOf("Wrong password") >= 0, "the error is shown, got " + __el("authErr").textContent);
ok(__el("authErr").textContent.indexOf("attempts left") >= 0, "with the attempts remaining: " + __el("authErr").textContent);
ok(T.state === null, "still no season");
ok(T.SYNC.authed === false, "still signed out");

print("-- the right password unlocks everything --");
__el("authPass").value = globalThis.__password;
T.submitAuth(); settle();
ok(T.SYNC.authed === true, "signed in");
ok(T.state !== null, "the season loaded");
ok(__el("appShell")._c.hidden === undefined, "the app is showing");
ok(__el("authPass").value === "", "the password field is cleared");
ok(T.hasKey() === true, "the server's key is available");
ok(T.getKey() === "", "but this browser still holds no key");
ok(__el("whoName").textContent === "owner", "identity comes from the session");
ok(__el("lockBtn")._c.hidden === undefined, "a Sign out button is offered");
ok(__el("lockBtn").textContent === "Sign out", "labelled for a session, not a local lock");

print("-- the password is never persisted --");
ok(JSON.stringify(__store).indexOf(globalThis.__password) < 0, "not in localStorage");
ok(T.auth.apiKey === "", "and no key was cached in memory");

print("-- signing out --");
T.lockApp(); settle();
ok(globalThis.__signedIn === false, "the server was told to end the session");
ok(T.state === null, "the season is unloaded");
ok(T.SYNC.authed === false, "and the app knows it");
ok(__el("authTitle").textContent === "Unlock", "back to the prompt");
ok(__el("appShell")._c.hidden === 1, "app hidden again");

print("-- a session that expires mid-use returns you to the prompt --");
__el("authPass").value = globalThis.__password;
T.submitAuth(); settle();
ok(T.state !== null, "signed back in");
globalThis.__signedIn = false;            /* the cookie expires server-side */
T.state.user.points = 42;
T.pushRemote(); settle();
ok(T.SYNC.authed === false, "a 401 on sync marks us signed out");
ok(__el("appShell")._c.hidden === 1, "and the app is hidden again rather than silently failing");
done();
"""

LOCKOUT = HEAD_RAW + r"""
settle();

print("-- repeated failures lock the login out --");
for (var i = 0; i < 8; i++) {
  __el("authPass").value = "wrong-" + i;
  T.submitAuth(); settle();
}
ok(globalThis.__lockedOut === true, "the server locked out after 8 failures");
__el("authPass").value = globalThis.__password;
T.submitAuth(); settle();
ok(T.state === null, "even the correct password is refused while locked out");
ok(__el("authErr").textContent.indexOf("Too many failed attempts") >= 0,
   "and the message says why, got " + __el("authErr").textContent);
done();
"""

UNCONFIGURED = HEAD_RAW + r"""
settle();

print("-- a deployment with no password configured --");
ok(T.SYNC.hosted === true, "still detected as hosted");
ok(T.SYNC.configured === false, "but reports itself unconfigured");
ok(T.state === null, "nothing boots");
ok(__el("authLede").textContent.indexOf("APP_PASSWORD") >= 0,
   "the screen names the variable to set, got " + __el("authLede").textContent);
ok(__el("authSubmit").disabled === true, "and there is nothing to submit");
var before = globalThis.__calls.length;
__el("authPass").value = "anything";
T.submitAuth(); settle();
ok(T.state === null, "submitting cannot get in");
done();
"""


def main():
    hosted = dom(speech_support=True).replace("function TextDecoder", PW_FETCH + "\nfunction TextDecoder")
    unconfigured = dom(speech_support=True).replace(
        "function TextDecoder", PW_FETCH + "\nglobalThis.__configured = false;\nfunction TextDecoder")
    return {
        "login":    run("login", hosted, LOGIN),
        "lockout":  run("lockout", hosted, LOCKOUT),
        "unconfig": run("unconfig", unconfigured, UNCONFIGURED),
    }


if __name__ == "__main__":
    sys.exit(report(main()))
