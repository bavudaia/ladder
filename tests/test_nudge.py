"""The daily nudge: does it say a true thing, and only one thing?

This mail exists to compete with every other notification on the phone, and the
mechanics it borrows only keep working while every number in it is real. So the
suite is mostly about honesty: a streak it claims must exist, a rival it names
must be ahead, and a card it says is due must actually be due today. The other
half is that there is exactly one call to action — a mail offering three good
options is a mail that gets postponed.
"""

import os
import re
import subprocess
import sys

from harness import BUILD, JSC, ROOT, report

LIB = os.path.join(ROOT, "functions", "api", "_nudge.js")

STUB = r"""
var fails=0, checks=0;
function ok(c,m){ checks++; if(!c){ fails++; print("  FAIL: "+m); } }
function done(){ print(""); print(fails===0 ? ("ALL "+checks+" CHECKS PASSED") : (fails+" FAILURES of "+checks)); }

var PEERS = [
  {id:"p1", name:"Priya Nair", points:900}, {id:"p2", name:"Marcus Chen", points:640},
  {id:"p3", name:"Elena Ivanova", points:500}, {id:"p4", name:"Diego Alvarez", points:380},
  {id:"p5", name:"Aisha Rahman", points:300}, {id:"p6", name:"Noah Kim", points:240},
  {id:"p7", name:"Wei Zhang", points:180}, {id:"p8", name:"Sam Osei", points:120},
  {id:"p9", name:"Jordan Blake", points:60}
];

/* A season shaped like the real one, with knobs for the things the copy reads. */
function season(o){
  o = o || {};
  return {
    epoch:"2026-08-02#3", createdAt:"2026-08-02",
    user: { points: o.points===undefined ? 420 : o.points,
            streak: o.streak===undefined ? 4 : o.streak,
            longestStreak: o.longestStreak===undefined ? 6 : o.longestStreak,
            lastLogDate: o.lastLogDate===undefined ? "2026-08-09" : o.lastLogDate,
            history: o.history || [
              { date:"2026-08-08", points:130, entries:[{activityId:"dsa_med", name:"DSA medium", cat:"Coding", points:130, score:71, bar:"Meets the senior bar"}] },
              { date:"2026-08-09", points:145, entries:[{activityId:"concept", name:"Concept review", cat:"Fundamentals", points:145, score:64, bar:"Meets the senior bar"}] }
            ] },
    peers: o.peers || PEERS,
    cards: o.cards || [],
    recall: o.recall || { streak:0, longestStreak:0, lastDate:null, sessions:0, reviewed:0 }
  };
}
function card(due, activityId){
  return { id:"c"+Math.random(), q:"q", ideal:"i", cat:"Coding", topic:"t",
           activityId:activityId||"concept", box:1, due:due, reps:0, lapses:0,
           lastScore:null, lastAt:null, createdAt:"2026-08-01", history:[] };
}
function bodyOf(n){ return n.text + " " + n.html; }
"""

TESTS = r"""
var TODAY = "2026-08-10";
var URL = "https://prephero.pages.dev";

print("-- the signals come off the season, not out of the air --");
var sig = readSignals(season(), TODAY);
ok(sig.points === 420, "points read through, got " + sig.points);
ok(sig.rank === 4, "rank is computed against the rivals, got " + sig.rank);
ok(sig.above.name === "Elena Ivanova", "and knows who is directly above, got " + (sig.above||{}).name);
ok(sig.below.name === "Diego Alvarez", "and below");
ok(sig.daysSinceLast === 1, "days since the last session, got " + sig.daysSinceLast);
ok(sig.loggedToday === false, "nothing logged today");
ok(sig.sessions === 2, "session count, got " + sig.sessions);
ok(sig.division === "Bronze", "division, got " + sig.division);
ok(sig.nextDivision === "Silver" && sig.toNextDivision === 480, "and the gap to the next one");
ok(sig.weakest === "System design", "the thinnest track, got " + sig.weakest);
ok(sig.mockThisWeek === false, "no mock in the last seven days");

print("-- a card is due only if it is due today --");
var s2 = readSignals(season({ cards:[card("2026-08-10"), card("2026-08-09"), card("2026-08-11")] }), TODAY);
ok(s2.cardsDue === 2, "today and overdue count, got " + s2.cardsDue);
ok(s2.deck === 3, "the deck is bigger than what is due");
ok(s2.nextDue === "2026-08-11", "and it knows when the rest come back, got " + s2.nextDue);

print("-- the review's value follows the block the cards came from --");
ok(readSignals(season({ cards:[card(TODAY,"sd_mock")] }), TODAY).dueValue === 100, "mock cards are worth a mock");
ok(readSignals(season({ cards:[card(TODAY,"lesson")] }), TODAY).dueValue === 10, "lesson cards are worth a lesson");
ok(readSignals(season({ cards:[] }), TODAY).dueValue === 0, "nothing due is worth nothing");

print("-- a live streak leads with what is about to be lost --");
var n = buildNudge(season({ streak:12, lastLogDate:"2026-08-09" }), TODAY, URL);
ok(n.hook.id === "streak-at-risk", "the streak hook wins, got " + n.hook.id);
ok(n.subject.indexOf("12") >= 0, "the real number is in the subject: " + n.subject);
ok(n.hook.headline === "12 days", "and in the headline, got " + n.hook.headline);
ok(bodyOf(n).indexOf("midnight") >= 0, "with the actual deadline");

print("-- and it does not claim a streak that is not there --");
var n0 = buildNudge(season({ streak:0, longestStreak:0, lastLogDate:null, history:[], points:0 }), TODAY, URL);
ok(n0.hook.id === "cold-start", "an empty season gets the cold-start hook, got " + n0.hook.id);
ok(bodyOf(n0).indexOf("streak") < 0, "no invented streak: " + n0.subject);
ok(n0.hook.headline === "0 points", "and the headline is the honest number");

print("-- a broken streak says so without pretending it survived --");
var nb = buildNudge(season({ streak:0, longestStreak:9, lastLogDate:"2026-08-06" }), TODAY, URL);
ok(nb.hook.id === "streak-broken", "got " + nb.hook.id);
ok(bodyOf(nb).indexOf("9-day") >= 0, "it names the run that was lost");
ok(bodyOf(nb).indexOf("4 days off") >= 0, "and how long it has been, got " + nb.hook.headline);

print("-- a named rival is a real rival at a real distance --");
var nr = buildNudge(season({ streak:1, lastLogDate:"2026-08-04", longestStreak:1, points:480 }), TODAY, URL);
ok(nr.hook.id === "overtaken", "got " + nr.hook.id);
ok(bodyOf(nr).indexOf("Elena Ivanova") >= 0, "names the one directly above");
ok(bodyOf(nr).indexOf("20 points") >= 0, "with the exact gap, got: " + nr.subject);
ok(bodyOf(nr).indexOf("Priya") < 0, "and not a rival who is nowhere near");

print("-- due cards outrank a comfortable position --");
var nc = buildNudge(season({ streak:1, lastLogDate:"2026-08-04", longestStreak:1, points:5,
                             cards:[card(TODAY),card(TODAY),card(TODAY)] }), TODAY, URL);
ok(nc.hook.id === "cards-due", "got " + nc.hook.id);
/* Which of the three subject variants runs depends on the date, and one of
   them leads with the time cost rather than the count — both are true, and the
   time one is the better lever. So pin the parts that must always hold. */
ok(nc.hook.headline === "3 due", "the headline carries the count, got " + nc.hook.headline);
ok(bodyOf(nc).indexOf("3 cards are scheduled") >= 0, "and the body states it plainly");
ok(/\d/.test(nc.subject), "the subject carries a real number either way: " + nc.subject);

print("-- and once today is logged the mail changes tone rather than nagging --");
var nd = buildNudge(season({ lastLogDate:TODAY,
  history:[{date:TODAY, points:100, entries:[{activityId:"dsa_med", cat:"Coding", points:100, score:70}]}] }), TODAY, URL);
ok(nd.hook.id === "logged-today", "got " + nd.hook.id);
ok(bodyOf(nd).indexOf("streak is safe") >= 0, "it confirms rather than pushes");
ok(nd.hook.actionHeading === "If you want more", "and the action is framed as optional, got " + nd.hook.actionHeading);
ok(bodyOf(nd).indexOf("Do this") < 0, "so it does not read as a demand on a day already done");
ok(buildNudge(season(), TODAY, URL).hook.actionHeading === "Do this", "every other day still says do this");

print("-- exactly one action, and it is the right one --");
var act = nextAction(readSignals(season({ cards:[card(TODAY),card(TODAY)] }), TODAY));
ok(act.label.indexOf("Review 2 cards") >= 0, "due cards win, got " + act.label);
ok(nextAction(readSignals(season({ history:[], points:0 }), TODAY)).label.indexOf("DSA medium") >= 0,
   "an empty season gets the cheapest first rep");
ok(nextAction(readSignals(season(), TODAY)).label.indexOf("system design mock") >= 0,
   "a week with no mock asks for a mock");
var withMock = season({ history:[
  { date:"2026-08-09", points:100, entries:[
      {activityId:"sd_mock", cat:"System design", points:100, score:70},
      {activityId:"dsa_med", cat:"Coding", points:100, score:70},
      {activityId:"star", cat:"Behavioral", points:100, score:70}] }] });
ok(nextAction(readSignals(withMock, TODAY)).label.indexOf("concept review") >= 0,
   "otherwise the thinnest track, got " + nextAction(readSignals(withMock, TODAY)).label);

print("-- one call to action in the markup, not a menu --");
var mail = buildNudge(season({ cards:[card(TODAY)] }), TODAY, URL);
ok((mail.html.match(/<a /g) || []).length === 1, "one link in the whole mail");
ok(mail.html.indexOf('href="' + URL + '"') >= 0, "pointing at the app");
ok(mail.html.indexOf("Do this") >= 0, "under a heading that says what it is for");

print("-- the mail is renderable and clean --");
ok(mail.subject.length > 0 && mail.subject.length < 90, "subject is a subject, got " + mail.subject.length + " chars");
ok(mail.html.indexOf("undefined") < 0, "no holes in the html");
ok(mail.text.indexOf("undefined") < 0, "or the plain-text part");
ok(mail.html.indexOf("<!doctype html>") === 0, "it is a document");
ok(mail.text.indexOf(URL) >= 0, "the text part carries the link for clients that strip html");
ok(mail.html.indexOf("PrepHero") >= 0, "and it says who it is from");

print("-- rival names cannot inject markup --");
var evil = buildNudge(season({ streak:1, lastLogDate:"2026-08-04", longestStreak:1, points:480,
  peers:[{id:"p1", name:"<script>alert(1)</script>", points:500}] }), TODAY, URL);
ok(evil.html.indexOf("<script>alert") < 0, "the name is escaped in the html");
ok(evil.html.indexOf("&lt;script&gt;") >= 0, "and shown as text instead");

print("-- the wording rotates so two mornings do not read identically --");
var subjects = {};
["2026-08-10","2026-08-11","2026-08-12"].forEach(function(d){
  var st = season({ streak:12, lastLogDate:addDays(d, -1) });
  subjects[buildNudge(st, d, URL).subject] = 1;
});
ok(Object.keys(subjects).length === 3, "three days, three subject lines, got " + Object.keys(subjects).length);
var same = buildNudge(season({streak:12, lastLogDate:"2026-08-09"}), TODAY, URL).subject;
ok(same === buildNudge(season({streak:12, lastLogDate:"2026-08-09"}), TODAY, URL).subject,
   "but the same day always renders the same mail");

print("-- date helpers agree with the app's own --");
ok(daysBetween("2026-08-01","2026-08-10") === 9, "days between");
ok(addDays("2026-08-31", 1) === "2026-09-01", "month rollover");
ok(addDays("2026-08-01", -1) === "2026-07-31", "and backwards");
ok(humanDate("2026-08-09") === "9 Aug", "human dates, got " + humanDate("2026-08-09"));

print("-- a season with nothing in it still produces a sendable mail --");
var bare = buildNudge({ user:{}, peers:[] }, TODAY, URL);
ok(bare.subject.length > 0, "there is a subject");
ok(bare.html.indexOf("undefined") < 0, "and no holes, got: " + bare.subject);
ok(bare.signals.rank === 1, "a season with no rivals ranks you first");
done();
"""


def main():
    src = re.sub(r"^export ", "", open(LIB, encoding="utf-8").read(), flags=re.M)
    if not os.path.isdir(BUILD):
        os.makedirs(BUILD)
    path = os.path.join(BUILD, "run_nudge.js")
    open(path, "w", encoding="utf-8").write(STUB + src + TESTS)
    r = subprocess.run([JSC, path], capture_output=True, text=True)
    out = r.stdout.strip()
    print("=== nudge ===")
    print(out if out else "(no output)")
    if r.stderr.strip():
        print("STDERR:", r.stderr.strip()[:1500])
    m = re.search(r"(?:ALL (\d+) CHECKS PASSED|(\d+) FAILURES of (\d+))", out)
    checks = int(m.group(1) or m.group(3)) if m else 0
    return {"nudge": (("PASSED" in out and "FAIL" not in out), checks)}


if __name__ == "__main__":
    sys.exit(report(main()))
