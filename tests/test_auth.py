"""Profiles: the lock screen, password-derived encryption of the API key, and
per-profile season isolation.

The point of these is narrow and worth stating: a client-side password is not
access control, and the deployed file never held a secret anyway. What is being
verified here is that the API key is unreadable at rest without the password,
that a wrong password fails closed, and that one profile cannot see another's
season.
"""

import sys
from harness import HEAD_RAW, dom, run, report

AUTH = HEAD_RAW + r"""
settle();   /* boot probes for a hosted deployment before showing the lock screen */

print("-- the app boots locked --");
ok(T.state === null, "no season is loaded before unlock");
ok(T.auth.user === null && T.getKey() === "", "no profile, no key");
ok(__el("appShell")._c.hidden === 1, "the app shell is hidden");
ok(__el("authView")._c.hidden === undefined, "the lock screen is showing");
ok(__el("authTitle").textContent === "Create your profile", "first run offers signup, got " + __el("authTitle").textContent);
ok(__el("authLede").textContent.indexOf("encrypted") >= 0, "and says what the password does");
ok(T.saveState() === false, "a locked app cannot write a season");

print("-- password rules --");
var errs = [];
function trySignUp(n, p){ var e=null; T.signUp(n,p).then(function(){}, function(x){ e=x; }); settle(); return e; }
var short = trySignUp("me", "short");
ok(short && short.message.indexOf(String(T.MIN_PASSWORD)) >= 0, "a short password is refused with the minimum: " + (short&&short.message));
ok(trySignUp("", "password-1234") !== null, "an empty profile name is refused");
ok(trySignUp("no spaces here", "password-1234") !== null, "an invalid profile name is refused");
ok(T.accountNames().length === 0, "none of those created anything");

print("-- signing up --");
var made = null;
T.signUp("Tester", "password-1234").then(function(u){ made = u; }, function(e){ print("  FAIL: signup: "+e.message); });
settle();
ok(made === "tester", "profile names are normalised, got " + made);
ok(T.auth.user === "tester" && T.auth.cryptoKey, "unlocked into the new profile");
T.bootApp();
ok(T.state !== null && T.state.user.points === 0, "a fresh season loaded");
ok(__el("whoName").textContent === "tester", "the topbar names the profile");

var rec = T.readAccounts().users["tester"];
ok(!!rec.salt && !!rec.verifier && !!rec.verifier.iv && !!rec.verifier.ct, "salt and verifier persisted");
ok(rec.keyBlob === null, "no key stored yet");
ok(globalThis.__lastDerive.iterations === 310000, "PBKDF2 iteration count, got " + globalThis.__lastDerive.iterations);
ok(globalThis.__lastDerive.hash === "SHA-256", "PBKDF2 hash");
ok(JSON.stringify(__store).indexOf("password-1234") < 0, "the password itself is never stored");

ok(trySignUp("tester", "password-1234") !== null, "the same profile cannot be created twice");

print("-- the API key is encrypted at rest --");
T.setKey("sk-ant-secret-value"); settle();
ok(T.getKey() === "sk-ant-secret-value", "readable in memory while unlocked");
ok(T.hasKey() === true, "and the app knows it has a key");
var dump = JSON.stringify(__store);
ok(dump.indexOf("sk-ant-secret-value") < 0, "the key is nowhere in localStorage in plaintext");
ok(dump.indexOf("sk-ant") < 0, "not even the prefix leaks");
var blob = T.readAccounts().users["tester"].keyBlob;
ok(!!blob && !!blob.iv && !!blob.ct, "it is stored as an iv + ciphertext blob");
T.renderSettings();
ok(__el("keyStatus").textContent.indexOf("tester") >= 0, "settings says which profile the key belongs to");

print("-- locking --");
T.lockApp();
ok(T.auth.user === null && T.auth.cryptoKey === null, "identity cleared");
ok(T.getKey() === "" && T.hasKey() === false, "the plaintext key is gone from memory");
ok(T.state === null, "the season is unloaded");
ok(__el("authTitle").textContent === "Unlock", "the lock screen asks to unlock, not to sign up");
ok(__el("authFoot").textContent.indexOf("tester") >= 0, "and lists the profile on this browser");

print("-- unlocking --");
var bad = null;
T.logIn("tester", "wrong-password-9").then(function(){ bad = "resolved"; }, function(e){ bad = e.message; });
settle();
ok(bad === "Wrong password.", "a wrong password fails closed, got " + bad);
ok(T.auth.user === null && T.getKey() === "", "and changes nothing");

var good = null;
T.logIn("tester", "password-1234").then(function(u){ good = u; }, function(e){ good = "ERR " + e.message; });
settle();
ok(good === "tester", "the right password unlocks, got " + good);
ok(T.getKey() === "sk-ant-secret-value", "and decrypts the stored key");
T.bootApp();
ok(T.state !== null, "the season is back");

var missing = null;
T.logIn("nobody", "password-1234").then(function(){}, function(e){ missing = e.message; });
settle();
ok(missing && missing.indexOf("nobody") >= 0, "an unknown profile says so: " + missing);

print("-- the form drives the same paths --");
T.lockApp();
__el("authUser").value = "tester"; __el("authPass").value = "nope-nope-nope";
T.submitAuth(); settle();
ok(__el("authErr").textContent === "Wrong password.", "the form surfaces a wrong password");
ok(T.state === null, "and stays locked");
__el("authPass").value = "password-1234";
T.submitAuth(); settle();
ok(T.state !== null && T.auth.user === "tester", "the form unlocks with the right password");
ok(__el("authPass").value === "", "and clears the password field");

print("-- profiles do not share a season --");
T.state.user.points = 777; T.saveState();
var firstKey = T.seasonKey();
T.signUp("second", "another-password").then(function(){}, function(e){ print("  FAIL: second profile: "+e.message); });
settle();
T.bootApp();
ok(T.auth.user === "second", "switched to the second profile");
ok(T.seasonKey() !== firstKey, "seasons are stored under different keys");
ok(T.state.user.points === 0, "the second profile starts at zero, got " + T.state.user.points);
ok(T.getKey() === "", "and does not inherit the first profile's key");
ok(JSON.parse(localStorage.getItem(firstKey)).user.points === 777, "the first profile's season is untouched");
ok(T.accountNames().length === 2, "both profiles exist");

T.lockApp();
T.logIn("tester", "password-1234").then(function(){}, function(e){ print("  FAIL: back to first: "+e.message); });
settle(); T.bootApp();
ok(T.state.user.points === 777 && T.getKey() === "sk-ant-secret-value", "switching back restores that profile's season and key");
done();
"""

# A v1 install: season at the un-namespaced storage key, API key in plaintext.
LEGACY = HEAD_RAW + r"""
settle();

print("-- upgrading a v1 install --");
localStorage.setItem("prephero_anthropic_key", "sk-ant-old-plaintext");
localStorage.setItem(T.STORAGE_KEY, JSON.stringify({
  version:2, epoch:"2026-08-02#3", createdAt:"2026-08-02", targetWeeks:16, model:"claude-opus-5",
  autoBrief:true, focus:"", voice:{enabled:false,voiceURI:"",rate:1,lang:"en-US",silence:4},
  user:{points:1234, streak:3, longestStreak:5, lastLogDate:"2026-08-01", history:[]},
  peers:[], lastPeerSyncDate:null, fieldHistory:[], milestones:[], activeSession:null, coach:null }));

T.signUp("owner", "password-1234").then(function(){}, function(e){ print("  FAIL: signup: "+e.message); });
settle();
T.bootApp();
ok(T.auth.user === "owner", "profile created");
ok(T.getKey() === "sk-ant-old-plaintext", "the old plaintext key was adopted");
ok(localStorage.getItem("prephero_anthropic_key") === null, "and the plaintext copy was deleted");
ok(JSON.stringify(__store).indexOf("sk-ant-old-plaintext") < 0, "it is now only stored encrypted");
ok(T.state.user.points === 1234, "the existing season came along, got " + T.state.user.points);
ok(localStorage.getItem(T.STORAGE_KEY) === null, "the un-namespaced season was moved, not copied");
ok(localStorage.getItem(T.STORAGE_KEY + "::owner") !== null, "it now lives under the profile");
done();
"""

# WebCrypto is unavailable on an insecure origin; failing loudly beats a dead form.
NOCRYPTO = HEAD_RAW + r"""
settle();

print("-- no WebCrypto available --");
ok(__el("authTitle").textContent === "Insecure origin", "the lock screen says why, got " + __el("authTitle").textContent);
ok(__el("authLede").textContent.indexOf("http.server") >= 0, "and how to fix it");
ok(__el("authForm")._c.hidden === 1, "the form is hidden rather than dead");
var e = null;
T.signUp("me", "password-1234").then(function(){}, function(x){ e = x; });
settle();
ok(e && e.message.indexOf("insecure origin") >= 0, "signing up refuses with the same reason");
ok(T.state === null, "nothing boots");
done();
"""


def main():
    return {
        "auth":     run("auth", dom(speech_support=True), AUTH),
        "legacy":   run("legacy", dom(speech_support=True), LEGACY),
        "nocrypto": run("nocrypto", dom(speech_support=True, secure=False, crypto_support=False), NOCRYPTO),
    }


if __name__ == "__main__":
    sys.exit(report(main()))
