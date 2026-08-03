"""The session helpers in functions/api/_lib.js.

WebCrypto is stubbed, so this does not verify that HMAC-SHA256 is correct —
that is WebCrypto's job. What it verifies is the control flow around it, which
is where session bugs actually live: expired tokens, tampered signatures,
tokens signed with a different password, and malformed cookies must all be
rejected rather than accepted or thrown on.
"""

import os
import re
import subprocess
import sys

from harness import BUILD, JSC, ROOT, report

LIB = os.path.join(ROOT, "functions", "api", "_lib.js")

# Deterministic stand-ins with the shapes the library expects. sign() is a hash
# of key-material plus data, so a different secret or altered payload produces a
# different signature -- which is the property under test.
STUB = r"""
var __B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
function btoa(s){
  var out="", i=0;
  while(i<s.length){
    var c1=s.charCodeAt(i++), c2=s.charCodeAt(i++), c3=s.charCodeAt(i++);
    var e1=c1>>2, e2=((c1&3)<<4)|((isNaN(c2)?0:c2)>>4);
    var e3=isNaN(c2)?64:(((c2&15)<<2)|((isNaN(c3)?0:c3)>>6));
    var e4=isNaN(c3)?64:(c3&63);
    out += __B64.charAt(e1)+__B64.charAt(e2)+(e3===64?"=":__B64.charAt(e3))+(e4===64?"=":__B64.charAt(e4));
  }
  return out;
}
function atob(s){
  s = String(s).replace(/[^A-Za-z0-9+/]/g, "");
  var out="", bits=0, acc=0;
  for (var i=0;i<s.length;i++){ acc=(acc<<6)|__B64.indexOf(s.charAt(i)); bits+=6;
    if(bits>=8){ bits-=8; out += String.fromCharCode((acc>>bits)&0xff); } }
  return out;
}
function TextEncoder(){ this.encode=function(s){ s=String(s); var a=new Uint8Array(s.length);
  for(var i=0;i<s.length;i++) a[i]=s.charCodeAt(i)&0xff; return a; }; }
function TextDecoder(){ this.decode=function(b){ var a=new Uint8Array(b), s="";
  for(var i=0;i<a.length;i++) s+=String.fromCharCode(a[i]); return s; }; }

function __bytesToStr(b){ var a=new Uint8Array(b), s=""; for(var i=0;i<a.length;i++) s+=String.fromCharCode(a[i]); return s; }
function __hash32(str){
  var out = new Uint8Array(32), h = 2166136261;
  for (var i=0;i<str.length;i++){ h ^= str.charCodeAt(i); h = (h * 16777619) >>> 0; }
  for (var j=0;j<32;j++){ h = (h * 16777619 + j) >>> 0; out[j] = h & 0xff; }
  return out;
}
var crypto = {
  subtle: {
    digest: function(alg, data){ return Promise.resolve(__hash32(__bytesToStr(data))); },
    importKey: function(fmt, raw){ return Promise.resolve({ __k: __bytesToStr(raw) }); },
    sign: function(alg, key, data){ return Promise.resolve(__hash32(key.__k + "|" + __bytesToStr(data))); },
    verify: function(alg, key, sig, data){
      var want = __hash32(key.__k + "|" + __bytesToStr(data)), got = new Uint8Array(sig);
      if (got.length !== want.length) return Promise.resolve(false);
      for (var i=0;i<want.length;i++) if (got[i] !== want[i]) return Promise.resolve(false);
      return Promise.resolve(true);
    }
  }
};
function Response(body, init){ this.body = body; this.status = (init && init.status) || 200;
  this.headers = (init && init.headers) || {}; }

var fails=0, checks=0;
function ok(c,m){ checks++; if(!c){ fails++; print("  FAIL: "+m); } }
function settle(n){ for (var i=0;i<(n||30);i++) if (typeof drainMicrotasks === "function") drainMicrotasks(); }
function done(){ print(""); print(fails===0 ? ("ALL "+checks+" CHECKS PASSED") : (fails+" FAILURES of "+checks)); }
"""

TESTS = r"""
var PW = "a-24-character-strong-pw";

print("-- base64url round trip --");
var bytes = new TextEncoder().encode('{"sub":"owner"}');
var round = new TextDecoder().decode(b64urlDecode(b64urlEncode(bytes)));
ok(round === '{"sub":"owner"}', "survives a round trip, got " + round);
ok(b64urlEncode(bytes).indexOf("=") < 0, "no padding");
ok(b64urlEncode(bytes).indexOf("+") < 0 && b64urlEncode(bytes).indexOf("/") < 0, "url-safe alphabet");

print("-- secrets arrive as strings or as Secrets Store bindings --");
var sec = {};
resolveSecret({ A: "plain-value" }, "A").then(function(v){ sec.str = v; });
resolveSecret({ A: { get: function(){ return Promise.resolve("store-value"); } } }, "A").then(function(v){ sec.store = v; });
resolveSecret({}, "MISSING").then(function(v){ sec.missing = v; });
resolveSecret(null, "A").then(function(v){ sec.noEnv = v; });
resolveSecret({ A: "" }, "A").then(function(v){ sec.empty = v; });
resolveSecret({ A: { get: function(){ return Promise.reject(new Error("boom")); } } }, "A").then(function(v){ sec.throws = v; });
resolveSecret({ A: { notGet: 1 } }, "A").then(function(v){ sec.wrongShape = v; });
settle();
ok(sec.str === "plain-value", "a project-level secret reads as a string, got " + sec.str);
ok(sec.store === "store-value", "a Secrets Store binding is unwrapped via get(), got " + sec.store);
ok(sec.missing === "", "an unset name is empty, not undefined");
ok(sec.noEnv === "", "a missing env is empty");
ok(sec.empty === "", "an empty string stays empty");
ok(sec.throws === "", "a failing binding degrades to empty rather than throwing");
ok(sec.wrongShape === "", "an unrecognised shape is empty");

print("-- season ordering --");
/* Revisions restart at 1 after a reset, so they are only comparable inside one
   season. Getting this wrong refuses a reset for ever. */
ok(compareSeasons("2026-08-02#3", "2026-08-01#2") === 1, "a later date is newer");
ok(compareSeasons("2026-08-01#2", "2026-08-02#3") === -1, "an earlier one is older");
ok(compareSeasons("2026-08-02#3", "2026-08-02#3") === 0, "the same season is the same season");
ok(compareSeasons("2026-08-02#3", "2026-08-02#2") === 1, "a re-armed serial on the same date is newer");
ok(compareSeasons("2026-08-02#10", "2026-08-02#2") === 1, "serials compare as numbers, not strings");
ok(compareSeasons("2026-08-02#2", "2026-08-02#10") === -1, "in both directions");
ok(compareSeasons("2026-08-02", "2026-08-02#1") === -1, "a missing serial is older than serial 1");
ok(compareSeasons("", "2026-08-02#1") === -1, "an absent epoch is older than any season");
ok(compareSeasons(null, undefined) === 0, "and two absent epochs are equal rather than throwing");

print("-- password comparison --");
var r = {};
passwordMatches(PW, PW).then(function(v){ r.same = v; });
passwordMatches("wrong", PW).then(function(v){ r.diff = v; });
passwordMatches(PW, "").then(function(v){ r.noneSet = v; });
passwordMatches(null, PW).then(function(v){ r.nullGiven = v; });
passwordMatches(PW + "x", PW).then(function(v){ r.longer = v; });
settle();
ok(r.same === true, "the right password matches");
ok(r.diff === false, "a wrong one does not");
ok(r.noneSet === false, "an unset deployment password never matches");
ok(r.nullGiven === false, "a non-string is refused");
ok(r.longer === false, "a prefix-plus-extra is refused");

print("-- session signing --");
var now = Math.floor(Date.now()/1000);
var t = {};
signSession(PW, { sub:"owner", iat:now, exp:now+3600 }).then(function(tok){ t.good = tok; });
settle();
ok(!!t.good && t.good.indexOf(".") > 0, "produces a two-part token");

var v = {};
verifySession(PW, t.good).then(function(p){ v.good = p; });
settle();
ok(v.good && v.good.sub === "owner", "verifies under the same password");

verifySession("a-different-password", t.good).then(function(p){ v.other = p; });
settle();
ok(v.other === null, "a token signed with another password is rejected");

print("-- tampering --");
var parts = t.good.split(".");
verifySession(PW, parts[0] + ".AAAA").then(function(p){ v.badSig = p; });
var forged = b64urlEncode(new TextEncoder().encode(JSON.stringify({sub:"attacker", exp:now+3600})));
verifySession(PW, forged + "." + parts[1]).then(function(p){ v.swapped = p; });
verifySession(PW, "").then(function(p){ v.empty = p; });
verifySession(PW, "only-one-part").then(function(p){ v.onePart = p; });
verifySession(PW, "a.b.c").then(function(p){ v.threeParts = p; });
verifySession(PW, null).then(function(p){ v.nullTok = p; });
settle();
ok(v.badSig === null, "a bad signature is rejected");
ok(v.swapped === null, "a swapped payload is rejected");
ok(v.empty === null, "an empty token is rejected");
ok(v.onePart === null, "a malformed token is rejected, not thrown on");
ok(v.threeParts === null, "so is one with too many parts");
ok(v.nullTok === null, "and null");

print("-- expiry --");
var e = {};
signSession(PW, { sub:"owner", iat:now-7200, exp:now-3600 }).then(function(tok){ e.tok = tok; });
settle();
verifySession(PW, e.tok).then(function(p){ e.result = p; });
settle();
ok(e.result === null, "an expired session is rejected even though the signature is valid");

signSession(PW, { sub:"owner", iat:now }).then(function(tok){ e.noExp = tok; });
settle();
verifySession(PW, e.noExp).then(function(p){ e.noExpResult = p; });
settle();
ok(e.noExpResult === null, "a session with no expiry is rejected, not treated as forever");

print("-- cookies --");
function req(cookie){ return { headers: { get: function(n){ return n === "Cookie" ? cookie : null; } } }; }
ok(readCookie(req("ph_session=abc123"), "ph_session") === "abc123", "reads a lone cookie");
ok(readCookie(req("other=1; ph_session=abc123; third=2"), "ph_session") === "abc123", "picks it out of several");
ok(readCookie(req("other=1"), "ph_session") === null, "absent means null");
ok(readCookie(req(""), "ph_session") === null, "empty header means null");
ok(readCookie(req(null), "ph_session") === null, "no header means null");
ok(readCookie(req("ph_session_other=nope"), "ph_session") === null, "does not match a longer name");

var c = sessionCookie("tok", 3600);
ok(c.indexOf("HttpOnly") >= 0, "cookie is HttpOnly, so scripts cannot read the session");
ok(c.indexOf("Secure") >= 0, "and Secure");
ok(c.indexOf("SameSite=Strict") >= 0, "and SameSite=Strict");
ok(c.indexOf("Max-Age=3600") >= 0, "with the requested lifetime");
ok(clearedCookie().indexOf("Max-Age=0") >= 0, "logout expires it immediately");

print("-- session length --");
ok(sessionHours({}) === 24, "defaults to 24 hours");
ok(sessionHours({SESSION_HOURS:"1"}) === 1, "honours a shorter setting");
ok(sessionHours({SESSION_HOURS:"0"}) === 24, "ignores zero");
ok(sessionHours({SESSION_HOURS:"-5"}) === 24, "ignores negatives");
ok(sessionHours({SESSION_HOURS:"99999"}) === 24, "clamps an absurd one back to the default");
ok(sessionHours({SESSION_HOURS:"abc"}) === 24, "ignores nonsense");
done();
"""


def main():
    src = re.sub(r"^export ", "", open(LIB, encoding="utf-8").read(), flags=re.M)
    if not os.path.isdir(BUILD):
        os.makedirs(BUILD)
    path = os.path.join(BUILD, "run_server.js")
    open(path, "w", encoding="utf-8").write(STUB + src + TESTS)
    r = subprocess.run([JSC, path], capture_output=True, text=True)
    out = r.stdout.strip()
    print("=== server ===")
    print(out if out else "(no output)")
    if r.stderr.strip():
        print("STDERR:", r.stderr.strip()[:1200])
    m = re.search(r"(?:ALL (\d+) CHECKS PASSED|(\d+) FAILURES of (\d+))", out)
    checks = int(m.group(1) or m.group(3)) if m else 0
    return {"server": (("PASSED" in out and "FAIL" not in out), checks)}


if __name__ == "__main__":
    sys.exit(report(main()))
