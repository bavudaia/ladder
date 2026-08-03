"""Session flows, scoring, voice, and season lifecycle."""

import sys
from harness import HEAD, HEAD_RAW, dom, run, report

# A season already in progress under an older serial must be wiped and re-armed
# to open on the epoch date, keeping preferences and the API key.
STALE = {
    "version": 2, "epoch": "2026-08-01#2", "createdAt": "2026-07-20",
    "targetWeeks": 12, "model": "claude-sonnet-5", "autoBrief": False, "focus": "caches",
    "voice": {"enabled": True, "voiceURI": "v-en-gb", "rate": 1.4, "lang": "en-GB", "silence": 2},
    "user": {"points": 870, "streak": 6, "longestStreak": 9, "lastLogDate": "2026-07-30",
             "history": [{"date": "2026-07-30", "points": 130, "rankThatDay": 4, "entries": [
                 {"activityId": "sd_mock", "name": "System design mock", "cat": "System design",
                  "topic": "t", "base": 100, "bonus": 30, "points": 130, "score": 71,
                  "bar": "Senior", "source": "AI", "at": "2026-07-30T10:00:00Z"}]}]},
    "peers": [{"id": "p%d" % i, "name": "Rival %d" % i, "points": 600 + i,
               "tier": ["GRINDER", "GRINDER", "GRINDER", "STEADY", "STEADY", "STEADY",
                        "CASUAL", "CASUAL", "CASUAL"][i - 1], "move": None} for i in range(1, 10)],
    "lastPeerSyncDate": "2026-07-30", "fieldHistory": [], "milestones": [{"id": "first_log", "done": True}],
    "activeSession": {"activityId": "dsa_hard", "status": "ready", "index": 0, "messages": []}, "coach": None,
}
CURRENT = dict(STALE, epoch="2026-08-02#3")

SESSIONS = HEAD + r"""
print("-- season state --");
/* The epoch is a fixed date, so whether the season has opened depends on when
   this runs. Assert the branch that actually applies today. */
var TODAY = DAY(0);
var PRESEASON = TODAY < "2026-08-02";
ok(T.state.createdAt === (PRESEASON ? "2026-08-02" : TODAY),
   "a season opens on the epoch date, or today once that has passed, got " + T.state.createdAt);
ok(T.state.user.points === 0 && T.state.user.history.length === 0, "progress is empty");
if (PRESEASON) {
  ok(__el("statDay").textContent.indexOf("T-") === 0, "day stat counts down, got " + __el("statDay").textContent);
  ok(__el("paceChip").textContent === "NOT STARTED", "pace shows not started");
  ok(__el("chartSvg")._html.indexOf("Season opens") >= 0, "chart shows the opening notice");
} else {
  ok(/^\d+ \/ \d+$/.test(__el("statDay").textContent), "day stat counts up, got " + __el("statDay").textContent);
  ok(__el("paceChip").textContent !== "NOT STARTED", "pace is live, got " + __el("paceChip").textContent);
  ok(__el("chartSvg")._html.indexOf("Season opens") < 0, "chart is drawing");
}
ok(__el("leaderboardBody")._html.indexOf("Priya") >= 0, "standings still render");
ok(__UNDEF.length === 0, "no undefined in markup: " + __UNDEF.join(","));

print("-- scoring --");
ok(T.consistencyBonus(1)===5 && T.consistencyBonus(4)===20 && T.consistencyBonus(6)===30 && T.consistencyBonus(99)===30, "consistency bonus curve");
ok(T.divisionFor(0).current.n==="Unranked" && T.divisionFor(2500).current.n==="Gold" && T.divisionFor(99999).next===null, "divisions");

print("-- markdown --");
var m = T.md("### H\n\nx **b** and `c`\n\n- one\n\n1. first");
ok(m.indexOf("<h3>H</h3>")>=0 && m.indexOf("<strong>b</strong>")>=0 && m.indexOf("<code>c</code>")>=0, "md inline");
ok(m.indexOf("<ul><li>one</li></ul>")>=0 && m.indexOf("<ol><li>first</li></ol>")>=0, "md lists");
ok(T.md("<img src=x onerror=y>").indexOf("&lt;img")>=0, "md escapes html");

print("-- offline bank --");
/* Recall is excluded on purpose: it is not generated and has no bank entry.
   Its content is the deck, which only exists once other sessions have been
   graded, so it gets its own suite rather than a fixture here. */
var GENERATED = T.ACTIVITIES.filter(function(a){ return !a.hidden; });
GENERATED.forEach(function(a){
  var it = T.offlineItem(a, "zzz");
  ok(!!it, a.id+" has an offline item");
  if (a.engine==="chat") { ok(it.followups.length>=6, a.id+" followups"); ok(it.rubric.length>=4, a.id+" rubric"); }
  else if (a.engine==="qset") { ok(it.questions.length===a.n, a.id+" question count"); }
  else { ok((it.rubric||[]).length>=3, a.id+" rubric"); }
});
Object.keys(T.BANK).forEach(function(k){ T.BANK[k].forEach(function(it,i){
  T.deriveRubric(it).forEach(function(x){ ok(x.k && x.k.length>0, k+"["+i+"] keyword derivation"); }); }); });

print("-- full offline session flows --");
function drive(actId){
  var before = T.state.user.points;
  T.startSession(actId);
  var s = T.state.activeSession, act = T.actById(actId);
  ok(!!s && s.status==="ready", actId+" reached ready (status="+(s&&s.status)+")");
  if(!s || s.status!=="ready") return;
  var ans = "I would use a hash map plus a doubly linked list with sentinel nodes so get and put are O(1) time and O(n) space. On get I promote the node because a read counts as a use. Edge cases: empty input, duplicates, and updating an existing key must not evict. I would sort by start time and use a min-heap, which is O(n log n). I chose partitioning by user id with a cache in front because the read to write ratio is a hundred to one, and the trade-off is staleness.";
  if (act.engine==="chat") { for(var i=0;i<3;i++) T.sendChatTurn(ans);
    ok(s.messages.filter(function(x){return x.role==="user";}).length===3, actId+" recorded 3 user turns"); }
  else if (act.engine==="qset") { s.item.questions.forEach(function(q,i){ s.answers["q"+i]=ans; }); }
  else if (actId==="star") { s.answers.situation="I was on the payments team, 40 engineers, Q3 2024.";
    s.answers.task="I was responsible for cutting checkout latency below 300ms.";
    s.answers.action="I profiled the path and decided to move the call behind a queue instead of caching it, because the data had to be durable.";
    s.answers.result="Latency dropped from 800ms to 120ms, an 85 percent reduction. Since then I always profile first."; }
  else if (actId==="sd_deep") { s.answers.answer = ans + " With modulo sharding changing N remaps every key. The ring is circular, walk clockwise, only 1/N of keys move to the neighbour. Virtual nodes even out load. It does not solve hot keys or range queries."; }
  else { s.answers.approach = ans; s.answers.code = "function f(a){ return a; }"; }
  T.finishSession();
  ok(s.status==="done", actId+" finished");
  ok(s.report && typeof s.report.score==="number" && s.report.score>=0 && s.report.score<=100, actId+" report score valid");
  var gained = T.state.user.points - before, expect = act.pts + (s.entry.bonus||0);
  ok(gained===expect, actId+" awarded "+gained+", expected "+expect);
  ok(!__HOLES(T.reportHtml(s, act)), actId+" report html clean");
  print("  "+actId+": +"+gained+" pts, "+s.report.score+"/100 ("+s.report.bar+")");
  T.state.activeSession = null;
}
GENERATED.forEach(function(a){ drive(a.id); });

print("-- template-hole detector --");
ok(__HOLES("<div>"+undefined+"</div>"), "catches >undefined<");
ok(__HOLES('<div class="'+undefined+'">x</div>'), "catches an attribute hole");
ok(__HOLES("Score: "+undefined+"/100"), "catches undefined/100");
ok(__HOLES(undefined+" pts"), "catches a leading hole");
ok(!__HOLES("<li>n is undefined for a two-dimensional input.</li>"), "spares the word in prose");

print("-- ledger --");
var day = T.state.user.history[0];
ok(T.state.user.history.length===1 && day.entries.length===10, "one day, ten entries");
var base=0, bonus=0; day.entries.forEach(function(e){ base+=e.base; bonus+=e.bonus; });
ok(base===450, "base points total 450, got "+base);
ok(bonus===5, "exactly one +5 consistency bonus, got "+bonus);
ok(T.state.user.points===455, "total 455, got "+T.state.user.points);
ok(T.state.user.streak===1, "streak 1");
T.renderDashboard();
ok(__el("todayEntries")._html.indexOf("System design mock")>=0, "log lists sessions");
ok(__el("chartSvg")._html.indexOf("polyline")>=0, "chart draws once there is a logged day");
ok(__UNDEF.length===0, "no undefined after data render: "+__UNDEF.join(","));
done();
"""

VOICE = HEAD + r"""
print("-- capability detection --");
ok(T.speech.canListen === true, "recognition detected");
ok(T.speech.canSpeak === true, "synthesis detected");
ok(T.voiceBlockedReason() === null, "not blocked on a secure origin");

print("-- speech text prep --");
var clean = T.stripForSpeech("### Head\n**bold** and `code` and ```js\nx=1\n``` see https://a.b/c");
ok(clean.indexOf("**")<0 && clean.indexOf("`")<0 && clean.indexOf("#")<0, "markdown stripped: "+clean);
ok(clean.indexOf("code block omitted")>=0, "fenced code replaced");
ok(clean.indexOf("a link")>=0 && clean.indexOf("https")<0, "urls replaced");
var chunks = T.chunkForSpeech(new Array(9).join("This is a fairly long sentence used for chunking. "));
ok(chunks.length>1, "long text is chunked, got "+chunks.length);
chunks.forEach(function(c){ ok(c.length<=260, "chunk under the cutoff limit ("+c.length+")"); });

print("-- settings render --");
T.renderVoiceSettings();
ok(__el("voiceSelect")._html.indexOf("Samantha")>=0, "english voices listed");
ok(__el("voiceSelect")._html.indexOf("Amelie")<0, "non-english voices filtered out");
ok(__el("voiceSupportNote").textContent.indexOf("text-only")>=0, "support note explains the text-only API");

print("-- mic buttons render per field --");
T.state.voice.enabled = true;
T.startSession("star");
var s = T.state.activeSession;
ok(s.status==="ready", "star session ready");
var html = __el("sessionPanel")._html;
ok(html.indexOf('data-mic="situation"')>=0 && html.indexOf('data-mic="action"')>=0, "mic on every STAR field");
ok(html.indexOf('class="voice-toggle on"')>=0, "voice toggle reflects enabled state");
ok(html.indexOf('id="voiceBar"')>=0, "voice bar present");
T.state.activeSession = null;

print("-- code field has no mic --");
T.startSession("dsa_med");
var h2 = __el("sessionPanel")._html;
ok(h2.indexOf('data-mic="approach"')>=0, "approach field has a mic");
ok(h2.indexOf('data-mic="code"')<0, "code field has no mic (dictating code is useless)");
T.state.activeSession = null;

print("-- hands-free chat loop --");
globalThis.__spoken = [];
T.state.voice.silence = 3;
T.startSession("sd_mock");
var c = T.state.activeSession;
ok(c.status==="ready", "mock ready");
ok(globalThis.__spoken.length>0, "interviewer opener was spoken aloud");
var firstSpoken = globalThis.__spoken.join(" ");
ok(firstSpoken.indexOf(c.messages[0].content.slice(0,25))>=0, "spoke the actual opener text");
ok(T.speech.listening===false, "not listening while still speaking");
globalThis.__flushSpeech();
ok(T.speech.listening===true, "mic opens once the interviewer stops talking");
ok(T.speech.field==="chat", "mic bound to the chat field");
var rec = globalThis.__recs[globalThis.__recs.length-1];
ok(rec.continuous===true && rec.interimResults===true, "recognition configured for continuous dictation");
ok(rec.lang==="en-US", "recognition language applied");

rec.emit("I would start by scoping the requirements", true);
ok(T.fieldValue("chat").indexOf("scoping the requirements")>=0, "final transcript lands in the field");
rec.emit("and then estimate the write throughput", true);
ok(T.fieldValue("chat").indexOf("scoping")>=0 && T.fieldValue("chat").indexOf("throughput")>=0, "transcripts accumulate");
ok(T.speech.countLeft===3, "auto-send countdown armed, got "+T.speech.countLeft);

var spokenBefore = globalThis.__spoken.length;
T.sendChatTurn(T.fieldValue("chat"));
ok(c.messages.filter(function(m){return m.role==="user";}).length===1, "turn was sent");
ok(T.speech.listening===false, "mic closed on send");
ok(T.fieldValue("chat")==="", "draft cleared after send");
ok(globalThis.__spoken.length>spokenBefore, "interviewer reply was spoken");
globalThis.__flushSpeech();
ok(T.speech.listening===true, "mic reopens for the next answer");

print("-- no double-speak on re-render --");
var n1 = globalThis.__spoken.length;
T.renderSession(); T.renderSession();
ok(globalThis.__spoken.length===n1, "re-rendering does not repeat the audio");

print("-- typing while dictating stays in sync --");
var el = __el("f_chat"); el.value = "typed over"; el._attrs["data-f"]="chat";
T.speech.baseText = "typed over";
rec.emit("plus dictated", true);
ok(T.fieldValue("chat").indexOf("typed over")>=0 && T.fieldValue("chat").indexOf("plus dictated")>=0, "typed text is not clobbered");

print("-- dictation appends, and leaves typed text alone --");
var typed = "First paragraph.\n\nSecond one, with  deliberate spacing.";
var elc = __el("f_chat"); elc.value = typed; elc._attrs["data-f"]="chat";
T.speech.baseText = typed;
rec.emit("   and then    the dictated part   ", true);
var after = T.fieldValue("chat");
ok(after.indexOf(typed) === 0, "the existing text is untouched, including line breaks");
ok(after.indexOf("\n\n") > 0, "paragraph breaks survive dictation");
ok(after.indexOf("with  deliberate spacing") > 0, "so does whitespace the user chose");
ok(after.indexOf("and then the dictated part") > 0, "the new speech is appended, tidied");
ok(after.indexOf("part   ") < 0, "without trailing slop");
rec.emit("plus more", true);
ok(T.fieldValue("chat").indexOf("dictated part plus more") > 0, "successive phrases keep appending");

print("-- stopping --");
T.stopListening();
ok(T.speech.listening===false && T.speech.countLeft===0, "stop clears mic and countdown");
T.stopSpeaking();
ok(T.speech.speaking===false, "stop clears playback");
T.resetSpeech();
ok(T.speech.onAutoSend===null && T.speech.field===null, "reset clears voice wiring");

print("-- voice off means silence --");
T.state.voice.enabled = false;
globalThis.__spoken = [];
T.state.activeSession = null;
T.startSession("rapid");
ok(globalThis.__spoken.length===0, "nothing spoken when voice mode is off");
ok(T.speech.listening===false, "mic stays shut when voice mode is off");
ok(__el("sessionPanel")._html.indexOf('data-mic="q0"')>=0, "manual mic button still offered");
done();
"""

NOVOICE = HEAD + r"""
print("-- browser without speech support --");
ok(T.speech.canListen===false && T.speech.canSpeak===false, "capabilities off");
ok(T.voiceBlockedReason().indexOf("Firefox")>=0, "explains which browsers work");
T.state.voice.enabled = true;
T.startSession("sd_mock");
var s = T.state.activeSession;
ok(s.status==="ready", "session still starts");
var h = __el("sessionPanel")._html;
ok(h.indexOf("mic-btn")<0, "no mic buttons rendered");
ok(h.indexOf("voice-toggle")<0, "no voice toggle rendered");
ok(h.indexOf("voiceBar")<0, "no voice bar rendered");
ok(h.indexOf('data-a="send"')>=0, "text controls intact");
T.sendChatTurn("my answer");
ok(s.messages.filter(function(m){return m.role==="user";}).length===1, "text flow unaffected");
T.finishSession();
ok(s.status==="done" && T.state.user.points>0, "session completes and scores");
done();
"""

INSECURE = HEAD + r"""
print("-- file:// origin (mic blocked by the browser) --");
ok(T.speech.canListen===true, "API exists");
var why = T.voiceBlockedReason();
ok(why && why.indexOf("http.server")>=0, "tells the user how to fix it: " + why);
T.state.voice.enabled = true;
T.startListening("chat");
ok(T.speech.listening===false, "does not pretend to listen");
ok(T.speech.error && T.speech.error.indexOf("secure origin")>=0, "surfaces the real reason");
done();
"""

SEASON = HEAD + r"""
print("-- stale season is re-armed for the epoch date --");
ok(T.state.epoch === "2026-08-02#3", "state carries the new season id, got " + T.state.epoch);
var TODAY2 = DAY(0);
ok(T.state.createdAt === (TODAY2 < "2026-08-02" ? "2026-08-02" : TODAY2),
   "a re-armed season opens on the epoch date, or today once that has passed, got " + T.state.createdAt);
ok(T.state.user.points === 0, "points wiped, got " + T.state.user.points);
ok(T.state.user.history.length === 0, "log wiped");
ok(T.state.user.streak === 0 && T.state.user.longestStreak === 0, "streak wiped");
ok(T.state.user.lastLogDate === null, "streak clock reset");
ok(T.state.activeSession === null, "half-finished session dropped");
ok(T.state.lastPeerSyncDate !== "2026-07-30", "the stale rival sync date is gone");
ok(T.state.peers.length === 9, "9 rivals");
ok(T.state.peers.every(function(p){ return p.points < 250; }),
   "every rival restarted from zero (one day of sync tops out at 225)");
ok(T.state.milestones.every(function(m){return !m.done;}), "milestones cleared");

print("-- preferences survive the reset --");
ok(T.state.targetWeeks === 12, "target weeks kept, got " + T.state.targetWeeks);
ok(T.state.model === "claude-sonnet-5", "model kept, got " + T.state.model);
ok(T.state.autoBrief === false, "auto-brief kept");
ok(T.state.voice.rate === 1.4 && T.state.voice.lang === "en-GB" && T.state.voice.voiceURI === "v-en-gb", "voice prefs kept");
ok(T.getKey() === "sk-ant-test", "API key survives the season reset");
ok(localStorage.getItem("prephero_anthropic_key") === null, "and the v1 plaintext copy was deleted");

print("-- countdown --");
ok(__el("statDay").textContent.length > 0, "day stat rendered, got " + __el("statDay").textContent);
ok(__el("paceChip").textContent.length > 0, "pace rendered, got " + __el("paceChip").textContent);
done();
"""

RESUME = HEAD + r"""
print("-- a season already on the current serial is left alone --");
ok(T.state.epoch === "2026-08-02#3", "season id unchanged");
ok(T.state.createdAt === "2026-07-20", "start date preserved, got " + T.state.createdAt);
ok(T.state.user.points === 870, "points preserved, got " + T.state.user.points);
ok(T.state.user.history.length === 1, "log preserved");
ok(T.state.user.streak === 6, "streak preserved");
ok(T.state.activeSession !== null, "half-finished session still waiting");
done();
"""


GUARDS = HEAD_RAW + r"""
settle();

print("-- global listeners fire before there is a season --");
/* The paste handler and the voiceschanged handler are both live on the sign-in
   screen. Neither has a season to read, and both used to reach straight into it. */
ok(T.state === null, "nothing is loaded yet");

var threw = null;
try { T.renderVoiceSettings(); } catch (e) { threw = e; }
ok(threw === null, "the browser finishing its voice list does not throw, got " + (threw && threw.message));

threw = null;
try { ok(T.inSession() === false, "no session while signed out"); } catch (e) { threw = e; }
ok(threw === null, "pasting a password does not throw, got " + (threw && threw.message));

threw = null;
try { ok(T.attachReady() === false, "and nothing accepts an attachment"); } catch (e) { threw = e; }
ok(threw === null, "nor does dropping a file on the sign-in screen, got " + (threw && threw.message));

print("-- and still work once a season exists --");
unlock();
ok(T.state !== null, "signed in");
T.renderVoiceSettings();
ok(__el("voiceSelect")._html.indexOf("Samantha") >= 0, "the voice list renders for real now");
T.startSession("dsa_med");
ok(T.inSession() === true, "a live session is recognised");
ok(T.attachReady() === true, "and it takes diagrams");
done();
"""

MICLOOP = HEAD + r"""
print("-- a microphone that dies the moment it opens is given up on --");
/* Chrome ends the stream on its own pauses and the app restarts it, which is how
   continuous dictation survives them. When recognition cannot run at all it ends
   instantly and reports no error, and that same restart becomes a hot loop that
   pins a core and never yields a working mic. */
T.state.voice.enabled = true;
T.startSession("concept");
globalThis.__instantEnd = true;
T.startListening("q0");
settle();

var rec = globalThis.__recs[globalThis.__recs.length - 1];
ok(rec.starts <= 8, "it stopped restarting instead of spinning, got " + rec.starts + " starts");
ok(T.speech.wantListening === false, "and disarmed itself");
ok(T.speech.listening === false, "so nothing thinks the mic is open");
ok(String(T.speech.error).indexOf("kept stopping") >= 0, "with an error that says what happened, got " + T.speech.error);
ok(String(T.speech.error).indexOf("permission") >= 0, "and points at the likely cause");
ok(String(T.speech.error).indexOf("Typing still works") >= 0, "and says the session is not stuck");

print("-- a normal pause still restarts, because that is the whole point --");
globalThis.__instantEnd = false;
T.speech.error = null;
T.stopListening();                 /* the give-up left the field selected */
T.startListening("q0");
settle();
var rec2 = globalThis.__recs[globalThis.__recs.length - 1];
ok(T.speech.listening === true, "the mic is open");
var startsBefore = rec2.starts;
rec2.endStream();                  /* the browser ending a quiet stretch by itself */
ok(rec2.starts === startsBefore + 1, "it restarted once, got " + (rec2.starts - startsBefore));
ok(T.speech.listening === true, "and dictation carries on");
ok(T.speech.error === null, "with no error raised for an ordinary pause");
done();
"""


def main():
    results = {
        "sessions": run("sessions", dom(speech_support=False), SESSIONS),
        "voice":    run("voice",    dom(speech_support=True),  VOICE),
        "novoice":  run("novoice",  dom(speech_support=False), NOVOICE),
        "insecure": run("insecure", dom(speech_support=True, secure=False), INSECURE),
        "season":   run("season",   dom(speech_support=True, seed=STALE, key="sk-ant-test"), SEASON),
        "resume":   run("resume",   dom(speech_support=True, seed=CURRENT), RESUME),
        "guards":   run("guards",   dom(speech_support=True), GUARDS),
        "micloop":  run("micloop",  dom(speech_support=True), MICLOOP),
    }
    return results


if __name__ == "__main__":
    sys.exit(report(main()))
