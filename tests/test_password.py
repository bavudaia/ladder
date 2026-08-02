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
    if (!globalThis.__signedIn) return __res(200, { hosted:true, authed:false });
    return __res(200, { hosted:true, authed:true, email:"owner",
      configured: globalThis.__configured, authMethod:"password", hasServerKey:true, sync:true });
  }
  if (url === "/api/login") {
    if (!globalThis.__configured) return __res(503, { error:{message:"Sign-in is unavailable."} });
    if (globalThis.__lockedOut) return __res(429, { error:{message:"Too many failed attempts. Try again later."} });
    if (body && body.password === globalThis.__password) { globalThis.__signedIn = true; globalThis.__failures = 0; return __res(200, { ok:true, hours:24 }); }
    globalThis.__failures++;
    if (globalThis.__failures >= 8) globalThis.__lockedOut = true;
    return __res(401, { error:{message:"Wrong password."} });
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
ok(__el("authTitle").textContent === "Sign in", "the prompt says Sign in, got " + __el("authTitle").textContent);
ok(__el("authUserWrap")._c.hidden === 1, "no profile-name field — there is one deployment password");
ok(__el("authConfirmWrap")._c.hidden === 1, "and no signup confirm field");
ok(__el("authSwitch")._c.hidden === 1, "no 'create another profile' link");

print("-- and it tells a stranger nothing --");
var screen = __el("authTitle").textContent + " " + __el("authLede").textContent + " " + __el("authFoot").textContent;
ok(screen.toLowerCase().indexOf("api key") < 0, "does not mention an API key: " + screen);
ok(screen.toLowerCase().indexOf("server") < 0, "does not say anything is held on a server");
ok(screen.toLowerCase().indexOf("anthropic") < 0, "does not name the upstream provider");
ok(screen.toLowerCase().indexOf("app_password") < 0, "does not name the deployment variable");
ok(screen.toLowerCase().indexOf("season") < 0, "does not describe what is behind it");
ok(T.SYNC.serverKey === false && T.SYNC.kv === false,
   "the probe told us nothing about the key or the store while signed out");

print("-- a wrong password is refused and changes nothing --");
__el("authPass").value = "not-the-password";
T.submitAuth(); settle();
ok(__el("authErr").textContent.indexOf("Wrong password") >= 0, "the error is shown, got " + __el("authErr").textContent);
ok(__el("authErr").textContent.indexOf("attempt") < 0, "and no countdown to the lockout: " + __el("authErr").textContent);
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
ok(T.SYNC.serverKey === true && T.SYNC.kv === true, "once in, the app learns what the deployment can do");

print("-- the password is never persisted --");
ok(JSON.stringify(__store).indexOf(globalThis.__password) < 0, "not in localStorage");
ok(T.auth.apiKey === "", "and no key was cached in memory");

print("-- signing out --");
T.lockApp(); settle();
ok(globalThis.__signedIn === false, "the server was told to end the session");
ok(T.state === null, "the season is unloaded");
ok(T.SYNC.authed === false, "and the app knows it");
ok(__el("authTitle").textContent === "Sign in", "back to the prompt");
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

print("-- a misconfigured deployment looks the same from outside --");
ok(T.SYNC.hosted === true, "still detected as hosted");
ok(T.state === null, "nothing boots");
ok(__el("authTitle").textContent === "Sign in", "same prompt as a working deployment");
ok(__el("authLede").textContent === "Enter your password to continue.", "same wording, got " + __el("authLede").textContent);
ok(__el("authLede").textContent.indexOf("APP_PASSWORD") < 0, "the variable is not named to a stranger");
ok(__el("authSubmit").disabled === false, "the button is not disabled, which would itself be a tell");
__el("authPass").value = "anything";
T.submitAuth(); settle();
ok(T.state === null, "submitting cannot get in");
ok(__el("authErr").textContent === "Sign-in is unavailable.",
   "and the failure is generic, got " + __el("authErr").textContent);
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
