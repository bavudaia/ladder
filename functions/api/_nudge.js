/* The daily nudge: what to say, and why that particular thing.
 *
 * This is the part of the product that has to compete with every other
 * notification on the phone, so it borrows the mechanics that work — loss
 * aversion on a streak, a named rival with an exact gap, an open loop, one
 * tap — and refuses the one that does not survive contact with the reader:
 * making things up. Every number below comes out of the season blob. A
 * fabricated "3 people are practising right now" works exactly once on someone
 * who wrote the app, and after that the mail gets filtered.
 *
 * The other rule is that there is always exactly one action. A mail that offers
 * three good options is a mail that gets postponed.
 *
 * Pure functions only: no fetch, no env, no Date.now(). The caller passes today
 * in. That is what makes the copy testable without sending anything.
 */

export function parseDate(s) {
  const p = String(s || "").split("-").map(Number);
  return new Date(Date.UTC(p[0], (p[1] || 1) - 1, p[2] || 1));
}

export function daysBetween(a, b) {
  if (!a || !b) return null;
  return Math.round((parseDate(b) - parseDate(a)) / 86400000);
}

export function addDays(s, n) {
  const d = parseDate(s);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function humanDate(s) {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const d = parseDate(s);
  return `${d.getUTCDate()} ${months[d.getUTCMonth()]}`;
}

const ACTIVITY_POINTS = {
  sd_mock: 100, code_mock: 100, sd_deep: 60, dsa_hard: 50, star: 40,
  dsa_med: 30, rapid: 25, concept: 20, dsa_easy: 15, lesson: 10
};

/* Everything the copy is allowed to know. If it is not in here it does not go
 * in the mail. */
export function readSignals(state, today) {
  const s = state || {};
  const user = s.user || {};
  const history = user.history || [];
  const cards = s.cards || [];
  const recall = s.recall || {};

  const loggedToday = history.some(h => h.date === today && (h.entries || []).length);
  const daysSinceLast = user.lastLogDate ? daysBetween(user.lastLogDate, today) : null;

  const peers = (s.peers || []).map(p => ({ name: p.name, points: p.points || 0 }));
  const rows = peers.concat([{ name: "You", points: user.points || 0, you: true }])
    .sort((a, b) => b.points - a.points);
  const rank = rows.findIndex(r => r.you) + 1;
  const above = rank > 1 ? rows[rank - 2] : null;
  const below = rank < rows.length ? rows[rank] : null;

  const due = cards.filter(c => c && String(c.due || "") <= today);
  /* "next" means the next one to come back, so the overdue pile does not count:
     saying the next cards arrive last Tuesday would be worse than saying
     nothing. */
  const nextDue = cards
    .map(c => String((c && c.due) || ""))
    .filter(d => d > today)
    .sort()[0] || null;

  /* What the review is worth, by the same rule the app uses: a card pays what
     the block it came from pays. */
  const dueValue = due.length
    ? Math.round(due.slice(0, 5).reduce((n, c) => n + (ACTIVITY_POINTS[c.activityId] || 20), 0) / Math.min(due.length, 5))
    : 0;

  const recent = [];
  history.slice(-5).forEach(h => (h.entries || []).forEach(e => recent.push({ ...e, date: h.date })));
  const lastSession = recent.length ? recent[recent.length - 1] : null;

  const catPoints = {};
  history.forEach(h => (h.entries || []).forEach(e => {
    const c = e.cat || "Coding";
    catPoints[c] = (catPoints[c] || 0) + (e.points || 0);
  }));
  const tracks = ["System design", "Coding", "Behavioral", "Fundamentals"];
  const weakest = tracks.reduce((w, c) => ((catPoints[c] || 0) < (catPoints[w] || 0) ? c : w), tracks[0]);

  const mockCutoff = addDays(today, -7);
  const mockThisWeek = history.some(h => h.date > mockCutoff &&
    (h.entries || []).some(e => e.activityId === "sd_mock" || e.activityId === "code_mock"));

  const divisions = [
    { n: "Unranked", at: 0 }, { n: "Bronze", at: 250 }, { n: "Silver", at: 900 },
    { n: "Gold", at: 2200 }, { n: "Platinum", at: 4200 }, { n: "Diamond", at: 7500 },
    { n: "Master", at: 12000 }
  ];
  let division = divisions[0], nextDivision = null;
  for (const d of divisions) {
    if ((user.points || 0) >= d.at) division = d;
    else { nextDivision = d; break; }
  }

  return {
    today,
    points: user.points || 0,
    streak: user.streak || 0,
    longestStreak: user.longestStreak || 0,
    lastLogDate: user.lastLogDate || null,
    daysSinceLast,
    loggedToday,
    sessions: history.reduce((n, h) => n + (h.entries || []).length, 0),
    rank, above, below,
    division: division.n,
    nextDivision: nextDivision ? nextDivision.n : null,
    toNextDivision: nextDivision ? nextDivision.at - (user.points || 0) : null,
    deck: cards.length,
    cardsDue: due.length,
    dueValue,
    nextDue: nextDue && nextDue > today ? nextDue : null,
    recallStreak: recall.streak || 0,
    weakest,
    mockThisWeek,
    lastSession
  };
}

/* The single next thing. Never a menu. */
export function nextAction(sig) {
  if (sig.cardsDue) {
    const n = Math.min(sig.cardsDue, 5);
    return { label: `Review ${n} card${n === 1 ? "" : "s"}`,
      why: `${Math.max(2, Math.round(n * 1.5))} minutes, ${sig.dueValue} points, and it is the only thing here that stops you forgetting.` };
  }
  if (!sig.sessions) {
    return { label: "Run one DSA medium",
      why: "Thirty points, one problem, and the season has a first entry in it." };
  }
  if (!sig.mockThisWeek) {
    return { label: "Run a system design mock",
      why: "A hundred points, and no mock has been logged in seven days — it is the only rep that tests you under pressure." };
  }
  const byTrack = {
    "System design": { label: "Run a deep-dive + explain-back", why: "Sixty points on your thinnest track." },
    "Coding": { label: "Clear one DSA hard", why: "Fifty points on your thinnest track." },
    "Behavioral": { label: "Polish one STAR story", why: "Forty points on your thinnest track." },
    "Fundamentals": { label: "Run a concept review", why: "Twenty points, five questions, on your thinnest track." }
  };
  return byTrack[sig.weakest] || byTrack.Coding;
}

/* Hooks in priority order. The first one whose condition holds wins, so the
 * strongest real fact about today is the one that gets the subject line.
 *
 * The order is the opinionated part. An empty season beats everything, because
 * nobody who has logged nothing cares that a rival is 60 points ahead. Due cards
 * beat the leaderboard, because forgetting is the failure mode this whole
 * feature exists to prevent and the review is also the cheapest thing on the
 * board. The leaderboard is what is left when neither of those is true. */
const HOOKS = [
  {
    id: "cold-start",
    when: s => !s.sessions,
    subjects: () => [
      "The season is open and empty",
      "Nothing logged yet",
      "Day one is still available"
    ],
    headline: () => "0 points",
    line: () => `Nothing has been logged this season. The rivals are already moving. ` +
      `The first entry is the hard one and it takes fifteen minutes.`
  },
  {
    id: "streak-at-risk",
    when: s => !s.loggedToday && s.streak >= 2 && s.daysSinceLast === 1,
    subjects: s => [
      `Your ${s.streak}-day streak ends tonight`,
      `${s.streak} days. Tonight decides whether it is ${s.streak + 1} or zero.`,
      `${s.streak} days on the line tonight`
    ],
    headline: s => `${s.streak} days`,
    line: s => `You have practised ${s.streak} days running. Nothing has been logged today, and the streak is counted at midnight. ` +
      `One session — any session — keeps it.`
  },
  {
    id: "streak-broken",
    when: s => !s.loggedToday && s.longestStreak >= 3 && (s.daysSinceLast === null || s.daysSinceLast > 1),
    subjects: s => [
      `${s.daysSinceLast} days off. Today is day 1.`,
      `Your best run was ${s.longestStreak} days`,
      `Nothing logged since ${humanDate(s.lastLogDate)}`
    ],
    headline: s => `${s.daysSinceLast} days off`,
    line: s => `The ${s.longestStreak}-day run is gone and there is no getting it back by feeling bad about it. ` +
      `A new streak starts at 1 the moment you finish anything at all.`
  },
  {
    id: "cards-due",
    when: s => s.cardsDue > 0,
    subjects: s => [
      `${s.cardsDue} card${s.cardsDue === 1 ? "" : "s"} came back today`,
      `${Math.min(s.cardsDue, 5)} questions you got wrong are due`,
      `${Math.max(2, Math.round(Math.min(s.cardsDue, 5) * 1.5))} minutes of recall is due`
    ],
    headline: s => `${s.cardsDue} due`,
    line: s => `${s.cardsDue} card${s.cardsDue === 1 ? " is" : "s are"} scheduled for today — questions you have already been ` +
      `graded on, coming back at the point where you are about to forget them. Five at a time, one tap, no setup.`
  },
  {
    id: "overtaken",
    when: s => !s.loggedToday && s.above && s.above.points - s.points <= 250 && s.rank > 1,
    subjects: s => [
      `${s.above.name} is ${s.above.points - s.points} points ahead`,
      `You are #${s.rank}. ${s.above.name} is #${s.rank - 1}.`,
      `${s.above.points - s.points} points between you and ${s.rank - 1}st`
    ],
    headline: s => `#${s.rank} of 10`,
    line: s => `${s.above.name} is on ${s.above.points} and you are on ${s.points}. ` +
      `That is ${s.above.points - s.points} points — ` +
      `${s.above.points - s.points <= 100 ? "one mock closes it" : "two good sessions close it"}.`
  },
  {
    id: "division",
    when: s => !s.loggedToday && s.nextDivision && s.toNextDivision <= 300,
    subjects: s => [
      `${s.toNextDivision} points from ${s.nextDivision}`,
      `${s.nextDivision} is ${s.toNextDivision} points away`
    ],
    headline: s => `${s.toNextDivision} to go`,
    line: s => `You are ${s.toNextDivision} points off ${s.nextDivision}. ` +
      `That is inside one session's reach, today, if you start one.`
  },
  {
    id: "logged-today",
    when: s => s.loggedToday,
    subjects: s => [
      `Logged. ${s.streak} day${s.streak === 1 ? "" : "s"} and counting.`,
      `Day ${s.streak} is done`,
      `${s.points} points, #${s.rank} of 10`
    ],
    headline: s => `Day ${s.streak}`,
    /* Telling someone who has already practised today to "do this" reads as a
       demand rather than a reward, and the reward is the point of this one. */
    actionHeading: "If you want more",
    line: s => `Today is already logged — the streak is safe. ` +
      (s.nextDue ? `The next cards come back on ${humanDate(s.nextDue)}.` : `Nothing else is outstanding.`)
  },
  {
    id: "default",
    when: () => true,
    subjects: s => [
      `${s.points} points, #${s.rank} of 10`,
      `Day ${s.streak} of the streak, and nothing logged yet`,
      `${s.weakest} is your thinnest track`
    ],
    headline: s => `#${s.rank}`,
    line: s => `You are on ${s.points} points at #${s.rank} of 10, and ${s.weakest.toLowerCase()} is the track carrying the least weight. ` +
      `Motivation shows up after you start, not before.`
  }
];

/* Rotate the wording by date so the same hook does not arrive word for word two
 * mornings running — the fastest way to teach someone to stop opening a mail. */
export function rotationIndex(today, n) {
  const d = parseDate(today);
  const days = Math.floor(d.getTime() / 86400000);
  return ((days % n) + n) % n;
}

export function chooseHook(sig) {
  const hook = HOOKS.find(h => h.when(sig)) || HOOKS[HOOKS.length - 1];
  const subjects = hook.subjects(sig);
  return {
    id: hook.id,
    subject: subjects[rotationIndex(sig.today, subjects.length)],
    headline: hook.headline(sig),
    line: hook.line(sig),
    actionHeading: hook.actionHeading || "Do this"
  };
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function renderEmail(sig, hook, appUrl) {
  const action = nextAction(sig);
  const url = String(appUrl || "").replace(/\/+$/, "") || "#";

  const stats = [
    ["Points", sig.points.toLocaleString()],
    ["Rank", `#${sig.rank} of 10`],
    ["Streak", `${sig.streak}d`],
    ["Due", String(sig.cardsDue)]
  ];

  const text = [
    hook.headline,
    "",
    hook.line,
    "",
    `${hook.actionHeading}: ${action.label}`,
    action.why,
    "",
    stats.map(([k, v]) => `${k}: ${v}`).join("  ·  "),
    "",
    url
  ].join("\n");

  const html = `<!doctype html><html><body style="margin:0;padding:0;background:#0d0f12;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0d0f12;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#15181d;border:1px solid #262b33;border-radius:6px;">

<tr><td style="padding:22px 24px 6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#7c8593;">
PrepHero &middot; ${esc(humanDate(sig.today))}
</td></tr>

<tr><td style="padding:0 24px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:40px;font-weight:700;color:#e8b339;line-height:1.05;">
${esc(hook.headline)}
</td></tr>

<tr><td style="padding:12px 24px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;color:#d7dce4;">
${esc(hook.line)}
</td></tr>

<tr><td style="padding:20px 24px 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#1b1f26;border-left:3px solid #e8b339;border-radius:0 4px 4px 0;">
<tr><td style="padding:14px 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#7c8593;margin-bottom:6px;">${esc(hook.actionHeading)}</div>
<div style="font-size:16px;font-weight:600;color:#f2f5f9;margin-bottom:4px;">${esc(action.label)}</div>
<div style="font-size:13px;line-height:1.5;color:#9aa3b1;">${esc(action.why)}</div>
</td></tr></table>
</td></tr>

<tr><td style="padding:20px 24px 0;">
<a href="${esc(url)}" style="display:block;background:#e8b339;color:#0d0f12;text-decoration:none;text-align:center;padding:14px 20px;border-radius:4px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;">Open PrepHero</a>
</td></tr>

<tr><td style="padding:18px 24px 24px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
${stats.map(([k, v]) => `<td align="center" style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">
<div style="font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:#7c8593;margin-bottom:4px;">${esc(k)}</div>
<div style="font-size:16px;font-weight:700;color:#f2f5f9;">${esc(v)}</div></td>`).join("")}
</tr></table>
</td></tr>

</table>
<div style="max-width:520px;margin-top:14px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;color:#5d6675;text-align:center;">
You set this up yourself. Turn it off by deleting the scheduled workflow.
</div>
</td></tr></table>
</body></html>`;

  return { subject: hook.subject, html, text };
}

export function buildNudge(state, today, appUrl) {
  const sig = readSignals(state, today);
  const hook = chooseHook(sig);
  const mail = renderEmail(sig, hook, appUrl);
  return { signals: sig, hook, ...mail };
}
