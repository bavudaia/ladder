"""Spaced review: the deck, the schedule, and what a review is worth.

The interesting property is not that cards exist — it is that the schedule is the
only thing deciding what you may review, because a review pays what the block it
came from pays. If a card could be reviewed twice in a day, or if a card the
grader forgot to mention kept its old due date, this stops being a memory system
and becomes the cheapest way to farm the ladder. Most of what follows is aimed
at those two failures.
"""

import sys
from harness import HEAD, dom, run, report

SEED = r"""
globalThis.__n = 0;
function seedCard(o){
  o = o || {};
  var id = o.id || ("card" + (++globalThis.__n));
  var c = { id:id, q:o.q || ("What is " + id + "?"),
    ideal:o.ideal || "consistent hashing ring virtual nodes clockwise remap",
    cat:o.cat || "Fundamentals", topic:o.topic || "Consistent hashing",
    activityId:o.activityId || "concept",
    box:o.box || 1, due:o.due || DAY(0), reps:o.reps || 0, lapses:o.lapses || 0,
    lastScore:(o.lastScore === undefined ? null : o.lastScore),
    lastAt:o.lastAt || null, createdAt:o.createdAt || DAY(-5), history:o.history || [] };
  T.state.cards.push(c);
  return c;
}
function ids(list){ return list.map(function(c){ return c.id; }).join(","); }
var GOOD = "The ring is circular so you walk clockwise to the next node. Virtual nodes even out load. Only one over n of the keys remap when a node leaves, unlike modulo sharding which moves everything.";
"""

DECK = HEAD + SEED + r"""
print("-- a graded question set leaves its questions behind --");
T.startSession("concept");
var s = T.state.activeSession;
var nq = s.item.questions.length;
s.item.questions.forEach(function(q,i){ s.answers["q"+i] = GOOD; });
T.finishSession(); settle();
ok(T.state.cards.length === nq, "one card per question, got " + T.state.cards.length + " for " + nq);
ok(T.state.cards[0].q === s.item.questions[0].q, "the card is the question itself");
ok(T.state.cards[0].ideal === s.item.questions[0].ideal, "and carries its reference answer");
ok(T.state.cards[0].activityId === "concept", "it remembers which block it came from");
ok(T.state.cards[0].cat === "Fundamentals", "and which track");
ok(s.captured === nq, "the report says how many were captured");

print("-- the same idea twice is one card --");
var was = T.state.cards.length;
T.state.activeSession = null;
T.startSession("concept");
var s2 = T.state.activeSession;
s2.item.questions = JSON.parse(JSON.stringify(s.item.questions));  /* same questions again */
s2.item.questions.forEach(function(q,i){ s2.answers["q"+i] = GOOD; });
T.finishSession(); settle();
ok(T.state.cards.length === was, "a repeated question does not duplicate, got " + T.state.cards.length);
T.state.activeSession = null;

print("-- a blank answer always comes back tomorrow --");
T.state.cards = [];
T.startSession("concept");
var s3 = T.state.activeSession;
s3.item.questions.forEach(function(q,i){ s3.answers["q"+i] = (i === 0 ? "" : GOOD); });
T.finishSession(); settle();
ok(T.state.cards[0].box === 1, "the blank one seeds in box 1, got " + T.state.cards[0].box);
ok(T.state.cards[0].due === DAY(1), "due tomorrow, got " + T.state.cards[0].due);
T.state.activeSession = null;

print("-- a session you aced does not flood tomorrow with what you know --");
ok(T.seedBox(95, false) === 3, "a strong session seeds at box 3");
ok(T.seedBox(75, false) === 2, "a solid one at box 2");
ok(T.seedBox(40, false) === 1, "a weak one at box 1");
ok(T.seedBox(95, true) === 1, "but a blank answer overrides the session score");
ok(T.seedBox(null, false) === 1, "and an ungraded session is treated as weak");

print("-- the grader's own review_cards are picked up --");
T.state.cards = [];
var sess = { activityId:"dsa_med", engine:"submit", topic:"Binary search",
             item:{ rubric:[{label:"Stated the complexity", detail:"O(log n)"}] }, answers:{} };
var n = T.captureCards(sess, { score:50, review_cards:[
  {q:"Why does lo <= hi loop forever with mid = (lo+hi)/2 rounding down?", ideal:"Because hi never moves."},
  {q:"When is binary search wrong on a rotated array?", ideal:"When duplicates hide the pivot."} ] });
ok(n === 2, "both cards captured, got " + n);
ok(T.state.cards[0].q.indexOf("lo <= hi") >= 0, "the grader's question is used verbatim");
ok(T.state.cards[0].cat === "Coding", "and takes the category of the block it came from");

print("-- offline there is no grader, so the rubric writes the cards --");
T.state.cards = [];
var n2 = T.captureCards({ activityId:"sd_deep", engine:"submit", topic:"Caching strategies",
  item:{ rubric:[{label:"Named the eviction policy", detail:"LRU versus LFU and why"},
                 {label:"Covered write-through versus write-back", detail:"Durability against latency"}] },
  answers:{} }, { score:30 });
ok(n2 === 2, "a card per missed rubric point, got " + n2);
ok(T.state.cards[0].q.indexOf("Caching strategies") >= 0, "the card names its topic so it stands alone later");
ok(T.state.cards[0].ideal.indexOf("LRU") >= 0, "and the rubric detail becomes the reference");

print("-- a review does not reseed itself --");
T.state.cards = [];
seedCard({});
ok(T.captureCards({ activityId:"recall", engine:"recall", item:{questions:[{q:"x",ideal:"y"}]}, answers:{} },
   { score:90, review_cards:[{q:"new one", ideal:"z"}] }) === 0, "recall captures nothing");
ok(T.state.cards.length === 1, "so the deck cannot grow by reviewing it");

print("-- the deck is capped, and what you have mastered retires first --");
T.state.cards = [];
for (var i = 0; i < T.RECALL_MAX_CARDS + 20; i++) {
  seedCard({ id:"c"+i, box:(i < 20 ? 1 : 5), lastAt:DAY(-i % 30) });
}
T.trimDeck();
ok(T.state.cards.length === T.RECALL_MAX_CARDS, "trimmed to the cap, got " + T.state.cards.length);
var kept1 = T.state.cards.filter(function(c){ return c.box === 1; }).length;
ok(kept1 === 20, "every box-1 card survived — those are the ones you still get wrong, got " + kept1);
done();
"""

SCHEDULE = HEAD + SEED + r"""
print("-- only what is due can be reviewed --");
T.state.cards = [];
seedCard({ id:"today", due:DAY(0) });
seedCard({ id:"overdue", due:DAY(-3) });
seedCard({ id:"tomorrow", due:DAY(1) });
seedCard({ id:"next-month", due:DAY(30) });
ok(T.dueCards().length === 2, "two are due, got " + T.dueCards().length);
ok(ids(T.dueCards()).indexOf("tomorrow") < 0, "a card due tomorrow is not due today");
ok(T.nextDueDate() === DAY(-3), "the next due date is the oldest outstanding one, got " + T.nextDueDate());

print("-- a review is mostly what went badly, with a couple that went fine --");
T.state.cards = [];
for (var i = 0; i < 6; i++) seedCard({ id:"bad"+i, box:1, cat:"Coding" });
for (var j = 0; j < 6; j++) seedCard({ id:"ok"+j, box:4, cat:"System design" });
var picked = T.pickRecallCards(T.RECALL_N);
ok(picked.length === T.RECALL_N, "exactly five, got " + picked.length);
var shaky = picked.filter(function(c){ return c.box <= 2; }).length;
ok(shaky === 3, "three from the shaky pile, got " + shaky);
ok(picked.length - shaky === 2, "and two you got right, which are the ones about to slip");

print("-- and it is interleaved, not five of the same thing --");
var runs = 0;
for (var k = 1; k < picked.length; k++) if (picked[k].cat === picked[k-1].cat) runs++;
ok(runs <= 1, "categories alternate rather than clumping, got " + runs + " repeats in " + picked.map(function(c){return c.cat;}).join(">"));

print("-- fewer due than five means fewer cards, not padding --");
T.state.cards = [];
seedCard({ id:"only" }); seedCard({ id:"future", due:DAY(9) });
var few = T.pickRecallCards(T.RECALL_N);
ok(few.length === 1, "one due, one card, got " + few.length);
ok(few[0].id === "only", "and it is the due one");

print("-- nothing due means nothing to start --");
T.state.cards = [];
seedCard({ due:DAY(4) });
ok(T.pickRecallCards(T.RECALL_N).length === 0, "no cards offered");
ok(T.startRecall() === false, "and a review cannot be started");
ok(T.state.activeSession === null, "so no session exists to award points for");

print("-- a review pays what the block it came from pays --");
ok(T.recallBase([{activityId:"sd_mock"}]) === 100, "mock cards pay like a mock");
ok(T.recallBase([{activityId:"lesson"}]) === 10, "lesson cards pay like a lesson");
ok(T.recallBase([{activityId:"sd_mock"},{activityId:"concept"}]) === 60, "a mixed review pays the average, got " +
   T.recallBase([{activityId:"sd_mock"},{activityId:"concept"}]));
ok(T.recallBase([]) === 0, "an empty review pays nothing");
ok(T.dominantCat([{cat:"Coding"},{cat:"Coding"},{cat:"Behavioral"}]) === "Coding",
   "the entry is filed under the track most of the cards came from");
done();
"""

SESSION = HEAD + SEED + r"""
print("-- starting a review asks you nothing --");
T.state.cards = [];
for (var i = 0; i < 5; i++) seedCard({ id:"c"+i, activityId:"concept", cat:"Fundamentals", box:1 });
var before = globalThis.__requests ? globalThis.__requests.length : 0;
ok(T.startRecall() === true, "it starts");
var s = T.state.activeSession;
ok(s.status === "ready", "and lands on card one immediately, no generation wait, got " + s.status);
ok(s.item.questions.length === 5, "five cards loaded, got " + s.item.questions.length);
ok(s.index === 0, "on the first one");
ok(s.basePts === 20, "worth what a concept review is worth, got " + s.basePts);
ok(s.catOverride === "Fundamentals", "filed under the track it reviewed");
ok(__el("viewSession")._c.hidden === undefined, "the session view is showing");

print("-- one card on screen, and the end is visible from the start --");
var h = __el("sessionPanel")._html;
ok(!__HOLES(h), "no template holes in the card view");
ok(h.indexOf("Card 1 of 5") >= 0, "the position is stated");
ok((h.match(/step-dot/g) || []).length === 5, "one dot per card");
ok(h.indexOf(s.item.questions[0].q) >= 0, "the current question is shown");
ok(h.indexOf(s.item.questions[1].q) < 0, "and the next one is not");
ok(h.indexOf("first review") >= 0, "a card you have not seen says so");
ok(h.indexOf("box 1 of 5") >= 0, "and where it sits in the schedule");

print("-- being stuck has an exit that is not quitting --");
ok(h.indexOf('data-a="reveal"') >= 0, "a nudge is offered");
ok(h.indexOf(s.item.questions[0].ideal) < 0, "but the answer is not on screen yet");
T.state.activeSession.revealed = { q0: 1 };
T.renderSession();
var h1 = __el("sessionPanel")._html;
ok(h1.indexOf("Nudge") >= 0, "the first press gives a nudge");
ok(h1.indexOf("Show the whole answer") >= 0, "with a way to go further");
T.state.activeSession.revealed = { q0: 2 };
T.renderSession();
var h2 = __el("sessionPanel")._html;
ok(h2.indexOf(s.item.questions[0].ideal) >= 0, "the second press shows the reference");
ok(h2.indexOf("holds its box") >= 0, "and says plainly what that costs");
ok(T.firstClause("The ring is circular. Virtual nodes even out load.") === "The ring is circular.",
   "a nudge is the first sentence, not the whole thing");
ok(T.firstClause("").indexOf("No reference") >= 0, "a card with no reference still says something useful");

print("-- a card carries what you scored on it last time --");
T.state.activeSession = null;
T.state.cards = [];
seedCard({ id:"seen", lastScore:45, reps:2, box:2 });
T.startRecall();
ok(T.state.activeSession.item.questions[0].lastScore === 45, "the previous score rides along");
ok(__el("sessionPanel")._html.indexOf("last time 45/100") >= 0, "and is on screen before you answer");
T.state.activeSession = null;
done();
"""

GRADING = HEAD + SEED + r"""
print("-- offline, every card is graded separately --");
T.state.cards = [];
for (var i = 0; i < 3; i++) seedCard({ id:"c"+i });
T.startRecall();
var s = T.state.activeSession;
s.answers.q0 = GOOD;    /* hits the reference */
s.answers.q1 = "no idea";
s.answers.q2 = "";
var g = T.offlineRecallGrade(s);
ok(g.cards.length === 3, "one grade per card, got " + g.cards.length);
ok(g.cards[0].score > g.cards[1].score, "a real answer outscores a shrug");
ok(g.cards[2].score === 0, "a blank scores zero");
ok(g.cards[2].verdict === "Left blank.", "and says so, got " + g.cards[2].verdict);
ok(g.cards[1].correction.length > 0, "a missed card comes with the correction");
ok(g.cards[0].correction === "", "a hit does not");
ok(typeof g.score === "number" && g.score >= 0 && g.score <= 100, "the session still gets one number for the log");

print("-- the AI grading prompt asks for per-card scores --");
var spec = T.gradeSpec(s);
ok(spec.schema === T.RECALL_SCHEMA, "against the recall schema");
ok(spec.system.indexOf("0-based index") >= 0, "with the index contract spelled out");
ok(spec.system.indexOf("schedules nothing") >= 0, "and why one averaged number is useless here");
var body = spec.messages[0].content;
ok(body.indexOf("CARD 0") >= 0 && body.indexOf("CARD 2") >= 0, "every card is in the prompt");
ok(body.indexOf("Reference answer:") >= 0, "with its reference");
ok(body.indexOf("undefined") < 0, "and no holes in it");

print("-- a revealed card is flagged to the grader --");
s.revealed = { q0: 2 };
ok(T.gradeSpec(s).messages[0].content.indexOf("revealed the reference") >= 0,
   "so it is not scored for reciting what it was just shown");
T.state.activeSession = null;
done();
"""

SCHEDULING = HEAD + SEED + r"""
print("-- a card you got right waits longer; one you missed comes back tomorrow --");
T.state.cards = [];
seedCard({ id:"up", box:2 });
seedCard({ id:"hold", box:3 });
seedCard({ id:"down", box:4 });
T.startRecall();
var s = T.state.activeSession;
var order = s.item.questions.map(function(q){ return q.cardId; });
function scoreFor(id, n){ return { index: order.indexOf(id), score: n, verdict:"v", correction:"" }; }
T.applyRecallResults(s, { score:60, cards:[ scoreFor("up",85), scoreFor("hold",55), scoreFor("down",20) ] });

var up = T.cardById("up"), hold = T.cardById("hold"), down = T.cardById("down");
ok(up.box === 3, "a good answer moves the card up a box, got " + up.box);
ok(up.due === DAY(T.RECALL_DAYS[2]), "and pushes it out to that box's interval, got " + up.due);
ok(hold.box === 3, "a partial answer holds the box, got " + hold.box);
ok(hold.due === DAY(T.RECALL_DAYS[2]), "but still reschedules from today");
ok(down.box === 1, "a miss drops straight to box 1, got " + down.box);
ok(down.due === DAY(1), "back tomorrow, got " + down.due);
ok(down.lapses === 1, "and it counts as a lapse");
ok(up.reps === 1 && up.lastScore === 85 && up.lastAt === DAY(0), "the card records what happened");
ok(up.history.length === 1 && up.history[0].score === 85, "and keeps a short history for the next comparison");

print("-- a card the grader forgot is still rescheduled --");
T.state.cards = [];
seedCard({ id:"orphan", box:2 });
T.state.activeSession = null;
T.startRecall();
T.applyRecallResults(T.state.activeSession, { score:80, cards:[] });
ok(T.cardById("orphan").due !== DAY(0), "it does not silently keep today's due date");
ok(T.cardById("orphan").reps === 1, "it counted as a review");

print("-- reading the answer and writing it back is not recall --");
T.state.cards = [];
seedCard({ id:"peeked", box:2 });
T.state.activeSession = null;
T.startRecall();
var s2 = T.state.activeSession;
s2.revealed = { q0: 2 };
T.applyRecallResults(s2, { score:95, cards:[{index:0, score:95, verdict:"v", correction:""}] });
ok(T.cardById("peeked").box === 2, "a revealed card holds its box however well it then scores, got " + T.cardById("peeked").box);

print("-- boxes do not run off the end --");
T.state.cards = [];
seedCard({ id:"top", box:T.RECALL_BOXES });
T.state.activeSession = null;
T.startRecall();
T.applyRecallResults(T.state.activeSession, { score:99, cards:[{index:0, score:99, verdict:"v", correction:""}] });
ok(T.cardById("top").box === T.RECALL_BOXES, "the last box is the last box, got " + T.cardById("top").box);
ok(T.cardById("top").due === DAY(T.RECALL_DAYS[T.RECALL_BOXES-1]), "on the longest interval");

print("-- the intervals actually get longer --");
var rising = true;
for (var i = 1; i < T.RECALL_DAYS.length; i++) if (T.RECALL_DAYS[i] <= T.RECALL_DAYS[i-1]) rising = false;
ok(rising, "each box waits longer than the one below it: " + T.RECALL_DAYS.join(","));
ok(T.RECALL_DAYS[0] === 1, "box 1 means tomorrow");
T.state.activeSession = null;
done();
"""

POINTS = HEAD + SEED + r"""
print("-- a review is worth what the block is worth --");
T.state.cards = [];
for (var i = 0; i < 3; i++) seedCard({ id:"m"+i, activityId:"sd_mock", cat:"System design" });
var before = T.state.user.points;
T.startRecall();
var s = T.state.activeSession;
s.item.questions.forEach(function(q,i){ s.answers["q"+i] = GOOD; });
T.finishSession(); settle();
var e = s.entry;
ok(e.base === 100, "the base is the mock's own value, got " + e.base);
ok(e.activityId === "recall" && e.name === "Recall review", "logged as a review");
ok(e.cat === "System design", "under the track it reviewed, so the gauges stay honest");
ok(T.state.user.points - before === e.points, "the points landed, got " + (T.state.user.points - before));

print("-- with its own streak on top --");
ok(e.recallBonus === T.consistencyBonus(1), "day one review bonus, got " + e.recallBonus);
ok(e.points === e.base + e.bonus + e.recallBonus, "points are base plus both bonuses");
ok(T.state.recall.streak === 1, "the review streak opened");
ok(T.state.recall.sessions === 1 && T.state.recall.reviewed === 3, "and the counters moved");

print("-- but the review streak only moves once a day --");
T.state.activeSession = null;
T.state.cards = [];
seedCard({ activityId:"concept" });
T.startRecall();
var s2 = T.state.activeSession;
s2.answers.q0 = GOOD;
T.finishSession(); settle();
ok(T.state.recall.streak === 1, "still day one, got " + T.state.recall.streak);
ok(!s2.entry.recallBonus, "and the second review of the day pays no second bonus");

print("-- consecutive days build it, a gap resets it --");
T.state.recall = { streak:3, longestStreak:3, lastDate:DAY(-1), sessions:0, reviewed:0 };
ok(T.bumpRecallStreak(DAY(0)) === T.consistencyBonus(4), "a day later it climbs to four");
ok(T.state.recall.streak === 4, "streak is four, got " + T.state.recall.streak);
T.state.recall = { streak:9, longestStreak:9, lastDate:DAY(-4), sessions:0, reviewed:0 };
T.bumpRecallStreak(DAY(0));
ok(T.state.recall.streak === 1, "four days off starts again at one, got " + T.state.recall.streak);
ok(T.state.recall.longestStreak === 9, "but the best is remembered");

print("-- and there is nothing here to farm --");
T.state.activeSession = null;
T.state.cards = [];
seedCard({ id:"solo", activityId:"sd_mock" });
T.startRecall();
var s3 = T.state.activeSession;
s3.answers.q0 = GOOD;
T.finishSession(); settle();
ok(T.cardById("solo").due > DAY(0), "the card just reviewed is no longer due, got " + T.cardById("solo").due);
ok(T.dueCards().length === 0, "so nothing is due");
T.state.activeSession = null;
ok(T.startRecall() === false, "and the review cannot be run again for more points");
done();
"""

FEEDBACK = HEAD + SEED + r"""
print("-- a first attempt says it is the baseline --");
T.state.cards = [];
T.startSession("dsa_easy");
var s = T.state.activeSession;
s.answers.approach = "Two pointers from both ends, O(n) time and O(1) space. Edge cases: empty input and duplicates.";
s.answers.code = "function f(a){ return a; }";
T.finishSession(); settle();
var h = T.reportHtml(s, T.actById("dsa_easy"));
ok(!__HOLES(h), "report renders clean");
ok(h.indexOf("Against your last time") >= 0, "the comparison block is there");
ok(h.indexOf("baseline") >= 0, "and says this is the baseline");
var first = s.report.score;
T.state.activeSession = null;

print("-- the second is measured against the first --");
T.startSession("dsa_easy");
var s2 = T.state.activeSession;
s2.answers.approach = "Sort first, then scan. O(n log n) time, O(1) space. Handles empty input, duplicates, negatives and overflow.";
s2.answers.code = "function f(a){ return a.sort(); }";
T.finishSession(); settle();
ok(s2.prev !== null, "the previous attempt was found");
ok(s2.prev.n === 1 && s2.prev.last.score === first, "and it is the right one, got " + JSON.stringify(s2.prev.last));
var h2 = T.reportHtml(s2, T.actById("dsa_easy"));
ok(!__HOLES(h2), "still clean");
ok(h2.indexOf("vs " + first) >= 0, "the old score is shown next to the new one");
ok(h2.indexOf("pl-delta") >= 0, "with the change between them");
ok(h2.indexOf("Season average") >= 0, "plus the running average and best");
/* Offline, a repeat of the same activity often yields nothing new: the rubric
   labels are the same, so dedupe swallows them. Either outcome is right — what
   must not happen is the report claiming a capture that did not occur. */
ok(typeof s2.captured === "number", "the capture count is recorded either way");
ok((h2.indexOf("went into the deck") >= 0) === (s2.captured > 0),
   "the deck line appears exactly when cards were captured, got " + s2.captured);
T.state.activeSession = null;

print("-- comparisons are like for like --");
T.startSession("star");
var s3 = T.state.activeSession;
["situation","task","action","result"].forEach(function(f){ s3.answers[f] = "I owned the migration and cut latency by 80 percent."; });
T.finishSession(); settle();
ok(s3.prev === null, "a different activity does not borrow the DSA history");
T.state.activeSession = null;

print("-- a review reports card by card, against last time --");
T.state.cards = [];
seedCard({ id:"a", q:"How does consistent hashing limit remapping?", box:2, lastScore:40, reps:1 });
seedCard({ id:"b", q:"When does a write-back cache lose data?", box:1, lastScore:null, cat:"System design" });
T.startRecall();
var r = T.state.activeSession;
var order = r.item.questions.map(function(q){ return q.cardId; });
T.applyRecallResults(r, { score:70, cards:[
  { index:order.indexOf("a"), score:82, verdict:"Solid.", correction:"" },
  { index:order.indexOf("b"), score:30, verdict:"Missed the mechanism.", correction:"Dirty pages are lost until they are flushed." } ] });
r.report = { score:70, bar:"Meets the senior bar", verdict:"v", strengths:["s"], gaps:["g"], next_actions:["n"], detail:"", gradedBy:"ai" };
r.prev = null;
r.entry = { base:20, bonus:5, recallBonus:5, points:30 };
var hr = T.reportHtml(r, T.actById("recall"));
ok(!__HOLES(hr), "the review report renders clean");
ok(hr.indexOf("Card by card") >= 0, "every card is accounted for");
ok(hr.indexOf("was 40") >= 0, "a card you have seen shows what you got last time");
ok(hr.indexOf("+42") >= 0, "and the change since then");
ok(hr.indexOf("first review") >= 0, "a new card says so instead of inventing a comparison");
ok(hr.indexOf("box 2 &rarr; 3") >= 0, "the box move is shown, got no arrow");
ok(hr.indexOf("Dirty pages are lost") >= 0, "the correction for what you missed is there");
ok(hr.indexOf("1 moved up") >= 0 && hr.indexOf("1 dropped back") >= 0, "with the summary line");
ok(hr.indexOf("recall bonus") >= 0, "and the review streak bonus is named in the award");
T.state.activeSession = null;
done();
"""

PANEL = HEAD + SEED + r"""
print("-- an empty deck explains itself --");
T.state.cards = [];
T.renderRecall();
var h = __el("recallBody")._html;
ok(!__HOLES(h), "no holes");
ok(h.indexOf("Nothing to review yet") >= 0, "it says the deck is empty");
ok(h.indexOf("data-recall") < 0, "and offers no button to press");

print("-- nothing due says when, and why waiting is the point --");
T.state.cards = [];
seedCard({ due:DAY(3) }); seedCard({ due:DAY(6) });
T.renderRecall();
var h2 = __el("recallBody")._html;
ok(h2.indexOf("Nothing due today") >= 0, "states it plainly");
ok(h2.indexOf("2 cards scheduled") >= 0, "with the deck size");
ok(h2.indexOf("does not pay points") >= 0, "and that reviewing early earns nothing");
ok(h2.indexOf("data-recall") < 0, "still no button");

print("-- cards due means one button with the number on it --");
T.state.cards = [];
for (var i = 0; i < 9; i++) seedCard({ id:"d"+i, activityId:"concept" });
T.renderRecall();
var h3 = __el("recallBody")._html;
ok(!__HOLES(h3), "no holes");
ok((h3.match(/data-recall/g) || []).length === 1, "exactly one button — nothing to choose between");
ok(h3.indexOf("Review 5 cards") >= 0, "capped at five however many are due, got " + h3.slice(0,200));
ok(h3.indexOf("9 due in total") >= 0, "the backlog is stated but not offered");
ok(h3.indexOf("minutes") >= 0, "with how long it will take");
ok(h3.indexOf("20 points at stake") >= 0, "and what it is worth");
ok(__el("recallHint").textContent.indexOf("deck") >= 0, "the header counts the deck when there is no streak");

print("-- once you have a streak the header shows that instead --");
T.state.recall = { streak:6, longestStreak:6, lastDate:DAY(0), sessions:4, reviewed:20 };
T.renderRecall();
ok(__el("recallHint").textContent === "6 day review streak", "got " + __el("recallHint").textContent);
ok(__el("recallBody")._html.indexOf("20 reviewed") >= 0, "and the totals are on the panel");

print("-- the review is not a card in the training grid --");
T.renderDashboard();
ok(__el("activityGrid")._html.indexOf("data-start=\"recall\"") < 0, "recall has no tile");
ok(__el("activityGrid")._html.indexOf("Coding mock") >= 0, "the real activities still do");
ok(__UNDEF.length === 0, "no undefined anywhere on the dashboard: " + __UNDEF.join(","));

print("-- and it can be started by voice --");
ok(T.matchActivity("review") === "recall", "\"review\" starts one");
ok(T.matchActivity("recall") === "recall", "so does \"recall\"");
ok(T.matchActivity("my cards") === "recall", "and \"my cards\"");
ok(T.matchActivity("concept review") === "concept", "but \"concept review\" is still the concept block");
T.state.cards = [];
seedCard({ due:DAY(5) });
ok(T.runCommand({intent:"start", activity:"recall"}) === true, "asking for a review when none is due is handled");
ok(T.state.activeSession === null, "no empty session is started");
ok(__el("cmdNote").textContent.indexOf("Nothing is due") >= 0, "it says so on screen, got " + __el("cmdNote").textContent);
ok(__el("cmdNote").textContent.indexOf("next card comes back") >= 0, "with when to come back");
ok(globalThis.__spoken.join(" ").indexOf("Nothing is due") >= 0, "and out loud, since you asked out loud");
done();
"""

MERGE = HEAD + SEED + r"""
print("-- two devices merge decks rather than overwriting them --");
T.state.cards = [];
seedCard({ id:"shared", box:1, reps:0 });
seedCard({ id:"laptop-only", box:2 });
var laptop = JSON.parse(JSON.stringify(T.state));
laptop.updatedAt = "2026-08-02T09:00:00.000Z";

var phone = JSON.parse(JSON.stringify(laptop));
phone.updatedAt = "2026-08-02T18:00:00.000Z";
phone.cards = phone.cards.filter(function(c){ return c.id === "shared"; });
phone.cards[0].box = 3; phone.cards[0].reps = 1; phone.cards[0].lastScore = 88;
phone.cards[0].due = DAY(7); phone.cards[0].lastAt = DAY(0);
phone.cards.push({ id:"phone-only", q:"phone card", ideal:"i", cat:"Coding", topic:"t",
  activityId:"dsa_med", box:1, due:DAY(1), reps:0, lapses:0, lastScore:null, lastAt:null,
  createdAt:DAY(0), history:[] });

var m = T.mergeSeasons(laptop, phone);
ok(m.cards.length === 3, "the union of both decks, got " + m.cards.length);
var shared = m.cards.filter(function(c){ return c.id === "shared"; })[0];
ok(shared.box === 3, "a box moved on the phone survives the laptop's stale copy, got " + shared.box);
ok(shared.due === DAY(7), "along with its new due date");
ok(m.cards.filter(function(c){ return c.id === "laptop-only"; }).length === 1, "a card only the laptop had is kept");
ok(m.cards.filter(function(c){ return c.id === "phone-only"; }).length === 1, "and one only the phone had");

print("-- an older device cannot undo a review --");
var m2 = T.mergeSeasons(phone, laptop);   /* other way round */
var shared2 = m2.cards.filter(function(c){ return c.id === "shared"; })[0];
ok(shared2.box === 3, "merge order does not matter, got " + shared2.box);
ok(shared2.reps === 1, "the reviewed copy wins on either side");

print("-- the review streak comes from whichever device reviewed last --");
laptop.recall = { streak:2, longestStreak:5, lastDate:DAY(-1), sessions:4, reviewed:12 };
phone.recall = { streak:3, longestStreak:3, lastDate:DAY(0), sessions:6, reviewed:20 };
var m3 = T.mergeSeasons(laptop, phone);
ok(m3.recall.streak === 3, "today's device knows the streak, got " + m3.recall.streak);
ok(m3.recall.longestStreak === 5, "but the best ever is kept from either, got " + m3.recall.longestStreak);
ok(m3.recall.reviewed === 20, "and the totals take the higher count");

print("-- a season from before a reset still brings nothing back --");
var stale = JSON.parse(JSON.stringify(phone));
stale.epoch = "2026-08-01#2";
stale.cards.push({ id:"ghost", q:"from the old season", ideal:"", cat:"Coding", topic:"",
  activityId:"dsa_med", box:1, due:DAY(0), reps:0, lapses:0, lastScore:null, lastAt:null, createdAt:DAY(-30), history:[] });
var m4 = T.mergeSeasons(laptop, stale);
ok(m4 === laptop, "the stale season is ignored outright");
ok(m4.cards.filter(function(c){ return c.id === "ghost"; }).length === 0, "so its cards cannot come back either");
done();
"""


def main():
    stub = dom(speech_support=True)
    return {
        "deck":      run("recall_deck", stub, DECK),
        "schedule":  run("recall_sched", stub, SCHEDULE),
        "review":    run("recall_session", stub, SESSION),
        "grading":   run("recall_grade", stub, GRADING),
        "boxes":     run("recall_boxes", stub, SCHEDULING),
        "points":    run("recall_points", stub, POINTS),
        "feedback":  run("recall_feedback", stub, FEEDBACK),
        "panel":     run("recall_panel", stub, PANEL),
        "deckmerge": run("recall_merge", stub, MERGE),
    }


if __name__ == "__main__":
    sys.exit(report(main()))
