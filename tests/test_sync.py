"""Hosted mode: Access identity instead of a lock screen, the API key held by
the server, and one season merged across devices.

The merge is the part worth testing hard. Two devices that both practised
offline must end up with the union of what they did — last-write-wins would
quietly delete a session, and you would never know which one.
"""

import sys
from harness import HEAD_RAW, dom, run, report

# A stubbed deployment: /api/me, /api/state (an in-memory KV), /api/claude.
HOSTED_FETCH = r"""
globalThis.__remote = null;          /* what the "KV" holds */
globalThis.__calls = [];
globalThis.__me = { hosted:true, authed:true, email:"me@example.com", hasServerKey:true,
                    sync:true, configured:true, authMethod:"access" };
globalThis.__stateStatus = 200;      /* force 409 / 500 for specific tests */

function __res(status, obj){
  return Promise.resolve({
    ok: status >= 200 && status < 300, status: status,
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
  globalThis.__calls.push({ url:url, method:opts.method || "GET", headers:opts.headers || {},
                            body: opts.body ? JSON.parse(opts.body) : null, keepalive: !!opts.keepalive });
  if (url === "/api/me") {
    return globalThis.__me ? __res(200, globalThis.__me) : __res(404, {});
  }
  if (url === "/api/state") {
    if ((opts.method || "GET") === "GET") return __res(200, { state: globalThis.__remote });
    if (globalThis.__stateStatus === 409) {
      globalThis.__stateStatus = 200;
      return __res(409, { error:{message:"Stale write refused."}, state: globalThis.__remote });
    }
    if (globalThis.__stateStatus !== 200) return __res(globalThis.__stateStatus, { error:{message:"boom"} });
    globalThis.__remote = JSON.parse(opts.body);
    return __res(200, { ok:true });
  }
  if (url === "/api/claude") return __res(200, {});
  return __res(404, {});
}
"""


def season(points, entries, updated, rev=1, extra=None):
    """A season blob as the app stores it."""
    days = {}
    for e in entries:
        days.setdefault(e["date"], []).append(e)
    history = [{"date": d, "points": sum(x["points"] for x in days[d]),
                "rankThatDay": 3, "entries": [
                    {"activityId": x["id"], "name": x["id"], "cat": "Coding", "topic": "t",
                     "base": x["points"], "bonus": 0, "points": x["points"], "score": 70,
                     "bar": "Meets the senior bar", "source": "AI", "at": x["at"]}
                    for x in days[d]]} for d in sorted(days)]
    s = {
        "version": 2, "epoch": "2026-08-02#3", "createdAt": "2026-08-01", "targetWeeks": 16,
        "model": "claude-opus-5", "autoBrief": True, "focus": "", "rev": rev, "updatedAt": updated,
        "voice": {"enabled": False, "voiceURI": "", "rate": 1, "lang": "en-US", "silence": 4},
        "user": {"points": points, "streak": 1, "longestStreak": 1,
                 "lastLogDate": sorted(days)[-1] if days else None, "history": history},
        "peers": [{"id": "p%d" % i, "name": "R%d" % i, "points": 100,
                   "tier": ["GRINDER"] * 3 + ["STEADY"] * 3 + ["CASUAL"] * 3, "move": None}
                  for i in range(1, 10)],
        "lastPeerSyncDate": "2026-08-01", "fieldHistory": [],
        "milestones": [{"id": "first_log", "done": False}], "activeSession": None, "coach": None,
    }
    for p in s["peers"]:
        p["tier"] = "GRINDER"
    if extra:
        s.update(extra)
    return s


LAPTOP = season(130, [{"date": "2026-08-01", "id": "sd_mock", "points": 130, "at": "2026-08-01T09:00:00.000Z"}],
                "2026-08-01T09:05:00.000Z", rev=4)
PHONE = season(50, [{"date": "2026-08-01", "id": "dsa_hard", "points": 50, "at": "2026-08-01T18:00:00.000Z"}],
               "2026-08-01T18:02:00.000Z", rev=7)

SYNC = HEAD_RAW + r"""
settle();

print("-- hosted mode replaces the lock screen --");
ok(T.SYNC.hosted === true, "the deployment answered /api/me");
ok(T.SYNC.email === "me@example.com", "identity comes from Access, got " + T.SYNC.email);
ok(T.auth.user === "me@example.com", "and becomes the user context");
ok(T.state !== null, "the season booted without a password");
ok(__el("authView")._c.hidden === 1, "no lock screen");
ok(__el("appShell")._c.hidden === undefined, "the app is showing");
ok(__el("whoName").textContent === "me@example.com", "topbar names the Access identity");
ok(__el("lockBtn")._c.hidden === 1, "the Lock button is hidden (Access owns the session)");
ok(__el("syncChip")._c.hidden === undefined, "a sync indicator is shown");

print("-- the key is the server's, not the browser's --");
ok(T.hasKey() === true, "the app has a key");
ok(T.getKey() === "", "but this browser does not hold one");
ok(JSON.stringify(__store).indexOf("sk-ant") < 0, "nothing key-shaped is in localStorage");
T.renderSettings();
ok(__el("keyStatus").textContent.indexOf("server") >= 0, "settings says the server holds it");
ok(__el("apiKeyInput").disabled === true, "and the key input is disabled");

print("-- API calls go through the proxy --");
globalThis.__calls.length = 0;
globalThis.__reply = JSON.stringify({title:"T",topic:"x",difficulty:"medium",statement:"s",
  examples:[{input:"i",output:"o",why:"w"}],constraints:["c"],hints:["h"],rubric:[{label:"l",detail:"d"}]});
var got = null;
T.aiJSON(T.genSpec(T.actById("dsa_med"), "Binary search")).then(function(p){ got = p; }, function(e){ got = "ERR "+e.message; });
settle();
ok(got && got.title === "T", "the call worked through the proxy");
var call = globalThis.__calls.filter(function(c){ return c.url === "/api/claude"; })[0];
ok(!!call, "it went to /api/claude, not api.anthropic.com");
ok(globalThis.__calls.every(function(c){ return c.url.indexOf("anthropic.com") < 0; }), "the browser never contacts Anthropic directly");
ok(!call.headers["x-api-key"], "no key header is sent from the browser");
ok(!call.headers["anthropic-dangerous-direct-browser-access"], "and no direct-browser-access header");
ok(call.body.model === "claude-opus-5" && call.body.stream === true, "the request body is otherwise unchanged");

print("-- the season round-trips to the server --");
T.state.user.points = 500;
var pushed = null;
T.pushRemote().then(function(r){ pushed = r; });
settle();
ok(pushed === true, "push succeeded");
ok(globalThis.__remote && globalThis.__remote.user.points === 500, "the server has the season");
ok(T.SYNC.status === "synced", "status reflects it, got " + T.SYNC.status);
ok(__el("syncChip").textContent === "Synced", "and so does the chip");

print("-- diagrams do not sync --");
T.startSession("sd_mock");
T.state.activeSession.attachments = [{ id:"i1", name:"d.png", mime:"image/png",
  b64:"QUFBQUFBQUFBQQ==", bytes:9, w:10, h:10 }];
T.pushRemote(); settle();
var sent = globalThis.__remote.activeSession.attachments[0];
ok(!!sent, "the attachment record is sent");
ok(sent.b64 === "", "but its bytes are stripped — they belong to the device that made them");
T.state.activeSession = null;
done();
"""

MERGE = HEAD_RAW + r"""
settle();
/*FIXTURES*/

print("-- two devices, one ladder --");
/* The laptop did a system design mock this morning; the phone did a DSA hard
   this evening. Neither device saw the other. Nothing may be lost. */
var laptop = LAPTOP, phone = PHONE;
var m = T.mergeSeasons(laptop, phone);
var entries = m.user.history[0].entries;
ok(m.user.history.length === 1, "one day");
ok(entries.length === 2, "both sessions survived, got " + entries.length);
ok(entries[0].activityId === "sd_mock" && entries[1].activityId === "dsa_hard", "in the order they happened");
ok(m.user.points === 180, "points are recomputed from the merged log, got " + m.user.points);
ok(m.user.history[0].points === 180, "and so is the day total");
ok(m.rev === 8, "revision moves past both, got " + m.rev);

print("-- merging is stable and order-independent --");
var m2 = T.mergeSeasons(phone, laptop);
ok(m2.user.points === m.user.points && m2.user.history[0].entries.length === 2, "same result either way round");
var again = T.mergeSeasons(m, phone);
ok(again.user.points === 180, "re-merging an already-merged season changes nothing, got " + again.user.points);
ok(again.user.history[0].entries.length === 2, "and does not duplicate entries");

print("-- a reset is not undone by the server --");
var lastSeason = JSON.parse(JSON.stringify(phone));
lastSeason.epoch = "2026-08-01#2";          /* the season before the reset */
lastSeason.user.points = 9999;
var kept = T.mergeSeasons(laptop, lastSeason);
ok(kept === laptop, "a season from a previous serial is ignored, not merged");
ok(kept.user.points === 130, "so its points cannot come back, got " + kept.user.points);
var both = T.mergeSeasons(lastSeason, lastSeason);
ok(both === null, "two stale seasons merge to nothing rather than resurrecting one");

print("-- one side empty --");
ok(T.mergeSeasons(null, phone) === phone, "a device with nothing takes the server's season");
ok(T.mergeSeasons(laptop, null) === laptop, "and vice versa");

print("-- streaks are derived, never merged --");
var wk = [];
["2026-08-01","2026-08-02","2026-08-03"].forEach(function(d,i){
  wk.push({date:d, id:"lesson", points:10, at:d+"T0"+(i+1)+":00:00.000Z"});
});
var runA = MKSEASON([wk[0], wk[2]], "2026-08-03T09:00:00.000Z", 2);
var runB = MKSEASON([wk[1]], "2026-08-02T09:00:00.000Z", 3);
var mr = T.mergeSeasons(runA, runB);
ok(mr.user.history.length === 3, "three days once merged, got " + mr.user.history.length);
ok(mr.user.streak === 3, "the streak the union earns is 3, got " + mr.user.streak);
ok(mr.user.longestStreak === 3, "longest too, got " + mr.user.longestStreak);
ok(mr.user.lastLogDate === "2026-08-03", "last log date follows the log");
ok(mr.user.points === 30, "points follow the log, got " + mr.user.points);

print("-- milestones and rivals --");
var withMs = MKSEASON([wk[0]], "2026-08-01T09:00:00.000Z", 1);
withMs.milestones = [{id:"first_log", done:true}];
withMs.lastPeerSyncDate = "2026-08-05";
withMs.peers = [{id:"p1", name:"Ahead", tier:"GRINDER", points:9999, move:null}];
var newer = MKSEASON([wk[1]], "2026-08-09T09:00:00.000Z", 9);
var mm = T.mergeSeasons(withMs, newer);
ok(mm.milestones[0].done === true, "a milestone ticked on either device stays ticked");
ok(mm.lastPeerSyncDate === "2026-08-05" && mm.peers[0].points === 9999, "rivals come from whichever device simulated furthest");

print("-- an unfinished session is not lost --");
var busy = MKSEASON([wk[0]], "2026-08-01T09:00:00.000Z", 1);
busy.activeSession = { activityId:"sd_mock", status:"ready", messages:[], answers:{}, attachments:[] };
var idle = MKSEASON([wk[1]], "2026-08-09T09:00:00.000Z", 9);
ok(T.mergeSeasons(busy, idle).activeSession !== null, "the half-finished mock survives the merge");

print("-- a stale write is merged, not clobbered --");
globalThis.__remote = phone;
globalThis.__stateStatus = 409;
T.state = null;
done();
"""

CONFLICT = HEAD_RAW + r"""
settle();
/*FIXTURES*/

print("-- the server rejects a stale write and the client merges --");
ok(T.state !== null, "booted hosted");
/* the season this device booted with, plus a session done here */
T.state.user.history = [{date:"2026-08-01", points:130, rankThatDay:3, entries:[
  {activityId:"sd_mock", name:"n", cat:"System design", topic:"t", base:130, bonus:0, points:130,
   score:70, bar:"b", source:"AI", at:"2026-08-01T09:00:00.000Z"}]}];
T.state.user.points = 130;
T.state.rev = 2;

/* meanwhile another device pushed something newer */
globalThis.__remote = PHONE;
globalThis.__stateStatus = 409;

var out = null;
T.pushRemote().then(function(r){ out = r; });
settle();
ok(out === true, "the push eventually succeeded, got " + out);
ok(T.state.user.history[0].entries.length === 2, "both devices' sessions are in the local season now");
ok(T.state.user.points === 180, "points recomputed after the merge, got " + T.state.user.points);
ok(globalThis.__remote.user.points === 180, "and the server has the merged season");
done();
"""

NOSERVER = HEAD_RAW + r"""
settle();

print("-- a plain static host falls back to local mode --");
ok(T.SYNC.hosted === false, "no hosted deployment detected");
ok(T.state === null, "so nothing boots on its own");
ok(__el("authTitle").textContent === "Create your profile", "the lock screen takes over");
ok(T.hasKey() === false, "and there is no server key to borrow");
done();
"""


def js_fixtures():
    import json as _json
    return (
        "var LAPTOP = %s;\nvar PHONE = %s;\nLAPTOP.epoch = T.SEASON_ID; PHONE.epoch = T.SEASON_ID;\n" % (_json.dumps(LAPTOP), _json.dumps(PHONE)) +
        """
function MKSEASON(items, updated, rev){
  var byDate = {};
  items.forEach(function(it){
    if(!byDate[it.date]) byDate[it.date] = [];
    byDate[it.date].push({activityId:it.id, name:it.id, cat:"Coding", topic:"t", base:it.points,
      bonus:0, points:it.points, score:70, bar:"b", source:"AI", at:it.at});
  });
  var s = JSON.parse(JSON.stringify(LAPTOP));
  s.rev = rev; s.updatedAt = updated; s.epoch = T.SEASON_ID;
  s.user.history = Object.keys(byDate).sort().map(function(d){
    return { date:d, points:byDate[d].reduce(function(n,e){return n+e.points;},0), rankThatDay:1, entries:byDate[d] };
  });
  s.user.points = s.user.history.reduce(function(n,d){ return n + d.points; }, 0);
  s.milestones = [{id:"first_log", done:false}];
  s.activeSession = null;
  return s;
}
"""
    )


def main():
    hosted = dom(speech_support=True).replace("function TextDecoder", HOSTED_FETCH + "\nfunction TextDecoder")
    # same stub, but the deployment answers nothing: a plain static host
    offline = dom(speech_support=True).replace(
        "function TextDecoder",
        HOSTED_FETCH + "\nglobalThis.__me = null;\nfunction TextDecoder")
    fx = js_fixtures()
    return {
        "sync":     run("sync", hosted, SYNC),
        "merge":    run("merge", hosted, MERGE.replace("/*FIXTURES*/", fx)),
        "conflict": run("conflict", hosted, CONFLICT.replace("/*FIXTURES*/", fx)),
        "noserver": run("noserver", offline, NOSERVER),
    }


if __name__ == "__main__":
    sys.exit(report(main()))
