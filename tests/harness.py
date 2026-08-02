"""Shared test harness for PrepHero.

index.html is one file with one <script>, so the suites pull that script out,
append an export hook just before the closing IIFE, and run it under
JavaScriptCore against a stubbed DOM. Nothing here touches the network or the
real browser APIs: fetch, localStorage, Web Speech, FileReader, Image, and
canvas are all faked, which is what makes the wire format and the image
pipeline assertable without an API key.
"""

import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "index.html")
BUILD = os.path.join(ROOT, "tests", ".build")
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"

# Everything the suites are allowed to reach into. Anything not listed here is
# private to the app and gets exercised through the UI instead.
EXPORT = """
  globalThis.__T = { get state() { return state; }, get auth() { return auth; },
    signUp: signUp, logIn: logIn, setKey: setKey, getKey: getKey, hasKey: hasKey,
    bootApp: bootApp, lockApp: lockApp, showAuth: showAuth, submitAuth: submitAuth,
    renderAuth: renderAuth, accountNames: accountNames, readAccounts: readAccounts,
    seasonKey: seasonKey, renderSettings: renderSettings, MIN_PASSWORD: MIN_PASSWORD,
    SEASON_ID: SEASON_ID, mergeSeasons: mergeSeasons,
    get SYNC() { return SYNC; }, mergeSeasons: mergeSeasons, pushRemote: pushRemote,
    pullRemote: pullRemote, probeHost: probeHost, recomputeFromLog: recomputeFromLog,
    usingProxy: usingProxy, saveLocal: saveLocal, hostedLogin: hostedLogin,
    hostedLogout: hostedLogout, showHostedAuth: showHostedAuth, bootHosted: bootHosted,
    ACCOUNTS_STORE: ACCOUNTS_STORE, STORAGE_KEY: STORAGE_KEY, KEY_STORE: KEY_STORE,
    startSession: startSession, finishSession: finishSession,
    offlineGrade: offlineGrade, offlineItem: offlineItem, actById: actById, md: md,
    consistencyBonus: consistencyBonus, renderDashboard: renderDashboard, renderSession: renderSession,
    heuristicGrade: heuristicGrade, BANK: BANK, ACTIVITIES: ACTIVITIES, divisionFor: divisionFor,
    myRank: myRank, deriveRubric: deriveRubric, sendChatTurn: sendChatTurn, reportHtml: reportHtml,
    categoryTotals: categoryTotals, activityStats: activityStats, saveState: saveState,
    genSpec: genSpec, gradeSpec: gradeSpec, chatSystem: chatSystem, aiJSON: aiJSON,
    GRADE_SCHEMA: GRADE_SCHEMA, speech: speech, speak: speak, startListening: startListening,
    stopListening: stopListening, stopSpeaking: stopSpeaking, updateVoiceUI: updateVoiceUI,
    stripForSpeech: stripForSpeech, chunkForSpeech: chunkForSpeech, voiceBlockedReason: voiceBlockedReason,
    fieldValue: fieldValue, renderVoiceSettings: renderVoiceSettings, resetSpeech: resetSpeech,
    matchCommand: matchCommand, matchActivity: matchActivity, runCommand: runCommand,
    startCommandListening: startCommandListening, COMMAND_GRAMMAR: COMMAND_GRAMMAR, WAKE: WAKE,
    normalizeCmd: normalizeCmd, showCommandHelp: showCommandHelp, CMD_SCHEMA: CMD_SCHEMA,
    addFiles: addFiles, removeAttachment: removeAttachment, readImageFile: readImageFile,
    validateImageFile: validateImageFile, fitDims: fitDims, encodeImage: encodeImage,
    userContent: userContent, thumbsHtml: thumbsHtml, attachHtml: attachHtml,
    sessionImages: sessionImages, sessionImgBytes: sessionImgBytes, imgDataUrl: imgDataUrl,
    IMG_MAX_PER_TURN: IMG_MAX_PER_TURN, IMG_SESSION_BUDGET: IMG_SESSION_BUDGET,
    IMG_TARGET_BYTES: IMG_TARGET_BYTES, IMG_MAX_EDGE: IMG_MAX_EDGE };
"""


def app_script():
    src = open(APP, encoding="utf-8").read()
    js = re.search(r"<script>(.*)</script>", src, re.S).group(1)
    i = js.rindex("})();")
    return js[:i] + EXPORT + js[i:]


JSX = app_script()

TEST_USER = "tester"
TEST_PASS = "password-1234"

HEAD = """
var T = globalThis.__T; var fails=0, checks=0;
function ok(c,m){ checks++; if(!c){ fails++; print("  FAIL: "+m); } }
function flush(){ if (typeof drainMicrotasks === "function") drainMicrotasks(); }
function settle(n){ for (var i=0;i<(n||20);i++) flush(); }
function done(){ print(""); print(fails===0 ? ("ALL "+checks+" CHECKS PASSED") : (fails+" FAILURES of "+checks)); }

/* The app boots locked, so a suite has no state to assert against until a
   profile exists. Create and unlock a throwaway one. A key seeded through
   dom(key=...) sits in the v1 plaintext store and is adopted on the way in,
   which is exactly what an upgrading user goes through. */
function unlock(){
  var err = null;
  T.signUp("%s", "%s").then(function(){ T.bootApp(); }, function(e){ err = e; });
  settle();
  if (err) print("  FAIL: could not unlock the test profile: " + (err && err.message || err));
}
""" % (TEST_USER, TEST_PASS)

# Suites that exercise the app assume an unlocked profile, so HEAD unlocks one.
# HEAD_RAW leaves the app locked, for the suite that tests the gate itself.
HEAD_RAW = HEAD
HEAD = HEAD + "\nunlock();\n"

SPEECH_STUB = r"""
/* --- Web Speech API stub --- */
globalThis.__spoken = [];
globalThis.__recs = [];
function SpeechSynthesisUtterance(text){ this.text=text; this.onend=null; this.onerror=null; this.rate=1; }
window.speechSynthesis = {
  speaking:false, paused:false,
  getVoices:function(){ return [
    {voiceURI:"v-en-us", name:"Samantha", lang:"en-US", localService:true},
    {voiceURI:"v-en-gb", name:"Daniel", lang:"en-GB", localService:true},
    {voiceURI:"v-fr", name:"Amelie", lang:"fr-FR", localService:true}]; },
  speak:function(u){ globalThis.__spoken.push(u.text); var self=this; self.speaking=true;
    globalThis.__pending = function(){ self.speaking=false; if(u.onend) u.onend(); }; },
  cancel:function(){ this.speaking=false; globalThis.__pending=null; },
  resume:function(){}, pause:function(){}, addEventListener:function(){}
};
function FakeRecognition(){ globalThis.__recs.push(this); this.continuous=false; this.interimResults=false;
  this.lang=""; this.started=false; var self=this;
  this.start=function(){ if(self.started) throw new Error("already started"); self.started=true; };
  this.stop=function(){ self.started=false; if(self.onend) self.onend(); };
  this.abort=function(){ self.started=false; };
  /* helper the tests drive */
  this.emit=function(text, isFinal){
    self.onresult({ resultIndex:0, results:[ Object.assign([{transcript:text}], {0:{transcript:text}, length:1, isFinal:isFinal}) ] });
  };
}
window.SpeechRecognition = FakeRecognition;
/* drain the synthesis queue synchronously */
globalThis.__flushSpeech = function(){ var n=0; while(globalThis.__pending && n<200){ var f=globalThis.__pending; globalThis.__pending=null; f(); n++; } };
"""

# WebCrypto stub. PBKDF2 and AES-GCM are stood in for by a keyed XOR with an
# authentication tag, which is worthless as crypto but has the property the app
# depends on: decrypting under the wrong derived key throws instead of returning
# garbage. Real AES-GCM correctness is WebCrypto's problem, not this app's --
# what these suites check is that the app drives it correctly.
CRYPTO_STUB = r"""
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
  for (var i=0;i<s.length;i++){
    acc=(acc<<6)|__B64.indexOf(s.charAt(i)); bits+=6;
    if(bits>=8){ bits-=8; out += String.fromCharCode((acc>>bits)&0xff); }
  }
  return out;
}
function TextEncoder(){ this.encode=function(s){
  s=String(s); var a=new Uint8Array(s.length);
  for(var i=0;i<s.length;i++) a[i]=s.charCodeAt(i)&0xff;
  return a; }; }

function __bytesToStr(b){ var a=new Uint8Array(b), s=""; for(var i=0;i<a.length;i++) s+=String.fromCharCode(a[i]); return s; }
function __stream(k,n){ var s=k.__k, o=new Uint8Array(n); for(var i=0;i<n;i++) o[i]=s.charCodeAt(i%s.length)&0xff; return o; }
function __tag(k){ var h=0, s=k.__k; for(var i=0;i<s.length;i++) h=(h*31+s.charCodeAt(i))>>>0;
  return [h&255,(h>>8)&255,(h>>16)&255,(h>>24)&255]; }

globalThis.__derivations = 0;
var __randState = 987654321;
window.crypto = {
  getRandomValues: function(a){
    for (var i=0;i<a.length;i++){ __randState=(__randState*1103515245+12345)%2147483648; a[i]=__randState&0xff; }
    return a;
  },
  subtle: {
    importKey: function(fmt, raw){ return Promise.resolve({ __raw: __bytesToStr(raw) }); },
    deriveKey: function(params, base){
      globalThis.__derivations++;
      globalThis.__lastDerive = { iterations: params.iterations, hash: params.hash, name: params.name };
      return Promise.resolve({ __k: "k|" + base.__raw + "|" + __bytesToStr(params.salt) + "|" + params.iterations });
    },
    encrypt: function(alg, key, data){
      var src = new Uint8Array(data), tag = __tag(key);
      var full = new Uint8Array(4 + src.length), ks = __stream(key, 4 + src.length);
      for (var i=0;i<4;i++) full[i] = tag[i];
      full.set(src, 4);
      for (var j=0;j<full.length;j++) full[j] = full[j] ^ ks[j];
      return Promise.resolve(full);
    },
    decrypt: function(alg, key, data){
      var src = new Uint8Array(data), ks = __stream(key, src.length);
      var plain = new Uint8Array(src.length);
      for (var i=0;i<src.length;i++) plain[i] = src[i] ^ ks[i];
      var tag = __tag(key);
      for (var t=0;t<4;t++) if (plain[t] !== tag[t]) return Promise.reject(new Error("OperationError"));
      return Promise.resolve(plain.slice(4));
    }
  }
};
"""

# Image stub. A fake file carries its pixel dimensions in the data URL, the fake
# Image reads them back, and the fake canvas returns a base64 payload whose
# length scales with area and quality -- so the real downscale/re-encode loop in
# encodeImage() is exercised for real, just against predictable sizes.
IMAGE_STUB = r"""
globalThis.__encodes = [];
globalThis.__PNG_BPP = 0.55;   /* base64 chars per pixel */
globalThis.__JPG_BPP = 0.30;

globalThis.__file = function(name, type, w, h, size){
  return { name:name, type:type, size:(size===undefined ? 40000 : size), w:w||800, h:h||600 };
};

function FileReader(){
  var self=this; this.onload=null; this.onerror=null; this.result=null;
  this.readAsDataURL=function(f){
    if (f && f.__unreadable) { if(self.onerror) self.onerror(); return; }
    self.result = "data:" + f.type + ";base64," + (f.w||100) + "x" + (f.h||100);
    if (self.onload) self.onload();
  };
}

function Image(){
  var self=this; this.onload=null; this.onerror=null; this.width=0; this.height=0;
  Object.defineProperty(this, "src", { set:function(v){
    var m = /base64,(\d+)x(\d+)$/.exec(String(v));
    if (!m) { if (self.onerror) self.onerror(); return; }
    self.width = parseInt(m[1],10); self.height = parseInt(m[2],10);
    if (self.onload) self.onload();
  }});
}

function FakeCanvas(){
  var self=this; this.width=0; this.height=0; this.filled=0; this.drawn=0;
  this.getContext=function(){ return {
    fillStyle:"", fillRect:function(){ self.filled++; }, drawImage:function(){ self.drawn++; } }; };
  this.toDataURL=function(mime,q){
    var px = self.width * self.height;
    var per = mime === "image/png" ? globalThis.__PNG_BPP : globalThis.__JPG_BPP * (q === undefined ? 0.85 : q);
    var n = Math.max(8, Math.round(px * per));
    globalThis.__encodes.push({ mime:mime, q:q, w:self.width, h:self.height, chars:n,
                                filled:self.filled, drawn:self.drawn });
    return "data:" + mime + ";base64," + new Array(n+1).join("A");
  };
}
"""


def dom(speech_support=True, secure=True, key=None, seed=None, crypto_support=True):
    entries = []
    if key:
        # v1 plaintext store: the profile adopts and deletes it on first unlock.
        entries.append('"prephero_anthropic_key":%s' % json.dumps(key))
    if seed is not None:
        entries.append('"prephero_ladder_v2::%s":%s' % (TEST_USER, json.dumps(json.dumps(seed))))
    return r"""
var __store = {%s};
var localStorage = {
  getItem:function(k){ return Object.prototype.hasOwnProperty.call(__store,k)?__store[k]:null; },
  setItem:function(k,v){ if(globalThis.__quota && String(v).length>globalThis.__quota) throw new Error("QuotaExceededError");
    __store[k]=String(v); }, removeItem:function(k){ delete __store[k]; }
};
globalThis.__UNDEF = [];
globalThis.__all = [];
/* A template hole renders "undefined" glued to markup or punctuation (>undefined<,
   ="undefined", undefined/100). The bank legitimately uses the word in prose
   ("n is undefined for a 2-D input"), so only flag it when it isn't space-delimited. */
globalThis.__HOLES = function(html){ return /(^|[^\s])undefined|undefined([^\s.,;]|$)/.test(String(html)); };
function FakeEl(id){ this.id=id||""; this.textContent=""; this._html=""; this.value=""; this.checked=false;
  this.className=""; this.disabled=false; this.style={}; this.options=[]; this.scrollTop=0; this.scrollHeight=0;
  this.files=[]; this.clicked=0;
  var s=this; this._c={}; this._attrs={}; globalThis.__all.push(this);
  this.classList={add:function(c){s._c[c]=1;},remove:function(c){delete s._c[c];},contains:function(c){return !!s._c[c];},
    toggle:function(c,f){ if(f===undefined) f=!s._c[c]; if(f)s._c[c]=1; else delete s._c[c]; return f; }}; }
Object.defineProperty(FakeEl.prototype,'innerHTML',{get:function(){return this._html;},
  set:function(v){ if(v===undefined||v===null) throw new Error("innerHTML="+v+" on #"+this.id);
    this._html=String(v); if(globalThis.__HOLES(this._html)) globalThis.__UNDEF.push(this.id||"?"); }});
FakeEl.prototype.addEventListener=function(){}; FakeEl.prototype.querySelector=function(){return new FakeEl("q");};
FakeEl.prototype.querySelectorAll=function(){return [];}; FakeEl.prototype.closest=function(){return new FakeEl("c");};
FakeEl.prototype.getAttribute=function(k){return this._attrs[k]===undefined?null:this._attrs[k];};
FakeEl.prototype.setAttribute=function(k,v){this._attrs[k]=v;};
FakeEl.prototype.focus=function(){}; FakeEl.prototype.scrollIntoView=function(){}; FakeEl.prototype.appendChild=function(){};
FakeEl.prototype.click=function(){ this.clicked++; };
var __els={};
var document={ getElementById:function(id){ if(!__els[id]) __els[id]=new FakeEl(id); return __els[id]; },
  createElement:function(tag){ return String(tag).toLowerCase()==="canvas" ? new FakeCanvas() : new FakeEl("n"); },
  querySelectorAll:function(){return [];}, addEventListener:function(){},
  documentElement:new FakeEl("h") };
var window={ scrollTo:function(){}, isSecureContext:%s, addEventListener:function(){} };
var location={ protocol:"%s" };
function confirm(){return true;} function alert(){}
function setTimeout(f){ return 0; } function clearTimeout(){}
function setInterval(){ return 0; } function clearInterval(){}
function TextDecoder(){ this.decode=function(a){ var s=""; for(var i=0;i<a.length;i++) s+=String.fromCharCode(a[i]); return s; }; }
globalThis.__el=function(id){ return __els[id]; };
%s
%s
%s
""" % (
        ",".join(entries),
        "true" if secure else "false",
        "http:" if secure else "file:",
        CRYPTO_STUB if crypto_support else "window.crypto = { getRandomValues:function(a){return a;} };",
        IMAGE_STUB,
        SPEECH_STUB if speech_support else "",
    )


def run(name, stub, test):
    """Run one suite; returns (passed, checks)."""
    if not os.path.isdir(BUILD):
        os.makedirs(BUILD)
    path = os.path.join(BUILD, "run_%s.js" % name)
    open(path, "w", encoding="utf-8").write(stub + JSX + test)
    r = subprocess.run([JSC, path], capture_output=True, text=True)
    out = r.stdout.strip()
    print("=== %s ===" % name)
    print(out if out else "(no output)")
    if r.stderr.strip():
        print("STDERR:", r.stderr.strip()[:1500])
    m = re.search(r"(?:ALL (\d+) CHECKS PASSED|(\d+) FAILURES of (\d+))", out)
    checks = int(m.group(1) or m.group(3)) if m else 0
    return ("PASSED" in out and "FAIL" not in out), checks


def report(results):
    total = sum(c for _, c in results.values())
    bad = [n for n, (p, _) in results.items() if not p]
    print("\n" + "-" * 52)
    for n, (p, c) in results.items():
        print("  %-10s %5d checks  %s" % (n, c, "ok" if p else "FAILED"))
    print("-" * 52)
    print(">>> %d checks across %d suites — %s"
          % (total, len(results), "ALL GREEN" if not bad else "FAILED: " + ", ".join(bad)))
    return 0 if not bad else 1
