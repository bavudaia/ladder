"""Voice commands: grammar, wake word, and execution against live sessions."""

import sys
from harness import HEAD, dom, run, report

CMD = HEAD + r"""
print("-- grammar parses the phrasings people actually use --");
var cases = [
  ["send", "send"], ["send it", "send"], ["that's my answer", "send"],
  ["next question", "next"], ["move on", "next"], ["previous", "back"],
  ["say that again", "repeat"], ["repeat the question", "repeat"], ["pardon", "repeat"],
  ["submit", "finish"], ["grade it", "finish"], ["end round", "endround"], ["i'm done", "endround"],
  ["hint", "hint"], ["stop listening", "stopmic"], ["be quiet", "quiet"],
  ["exit", "exit"], ["read my feedback", "readback"], ["what's my rank", "status"],
  ["daily briefing", "briefing"], ["what can i say", "help"]
];
cases.forEach(function(c){
  var m = T.matchCommand(c[0]);
  ok(m && m.intent === c[1], '"' + c[0] + '" -> ' + c[1] + " (got " + (m?m.intent:"null") + ")");
});

print("-- start commands resolve to activities --");
[["start a coding mock","code_mock"], ["begin a system design mock","sd_mock"], ["run a dsa hard","dsa_hard"],
 ["give me a medium","dsa_med"], ["do an easy problem","dsa_easy"], ["start rapid fire","rapid"],
 ["launch a concept review","concept"], ["start a star story","star"], ["begin a deep dive","sd_deep"],
 ["give me a lesson","lesson"]].forEach(function(c){
  var m = T.matchCommand(c[0]);
  ok(m && m.intent==="start" && m.activity===c[1], '"'+c[0]+'" -> '+c[1]+" (got "+(m?m.activity:"null")+")");
});

print("-- non-commands are rejected --");
["i would use a hash map","the answer is order n log n","next i would shard the database by user id",
 "", "so send the request to the queue and then submit it to the worker"].forEach(function(t){
  ok(T.matchCommand(t)===null, 'not a command: "'+t.slice(0,40)+'"');
});

print("-- wake word extraction --");
[["hero next question","next question"], ["Hero, send it","send it"], ["hey hero repeat that","repeat that"],
 ["prep hero status","status"], ["hero: start a coding mock","start a coding mock"]].forEach(function(c){
  var m = c[0].match(T.WAKE);
  ok(m && T.normalizeCmd(m[3])===c[1], 'wake strip "'+c[0]+'" -> "'+c[1]+'" (got '+(m?m[3]:"null")+')');
});
ok("heroic efforts to shard".match(T.WAKE)===null, "does not trigger on 'heroic'");
ok("my answer is hero".match(T.WAKE)===null, "wake word must lead the utterance");

print("-- command schema is structured-output legal --");
ok(T.CMD_SCHEMA.additionalProperties===false, "additionalProperties false");
ok(T.CMD_SCHEMA.required.length===2, "both fields required");
ok(T.CMD_SCHEMA.properties.intent.enum.indexOf("none")>=0, "has a none escape hatch");

print("-- commands execute against real sessions --");
T.state.voice.enabled = true;
ok(T.runCommand({intent:"start", activity:"rapid"})===true, "start command opens a session");
var s = T.state.activeSession;
ok(s && s.activityId==="rapid" && s.status==="ready", "rapid session is live");
__el("viewSession").classList.remove("hidden");

var i0 = s.index || 0;
ok(T.runCommand({intent:"next"})===true, "next advances");
ok(s.index === i0+1, "index moved to "+s.index);
ok(T.runCommand({intent:"back"})===true, "back returns");
ok(s.index === i0, "index restored");
ok(T.runCommand({intent:"back"})===false, "back at the first question is a no-op");

globalThis.__spoken = [];
ok(T.runCommand({intent:"repeat"})===true, "repeat works");
ok(globalThis.__spoken.join(" ").indexOf(s.item.questions[0].q.slice(0,20))>=0, "repeat spoke the current question");
globalThis.__flushSpeech();

globalThis.__spoken = [];
ok(T.runCommand({intent:"status"})===true, "status works");
ok(globalThis.__spoken.join(" ").indexOf("rank")>=0, "status spoke the rank");
globalThis.__flushSpeech();

ok(T.runCommand({intent:"send"})===false, "send is rejected outside a chat round");
s.item.questions.forEach(function(q,i){ s.answers["q"+i]="a real spoken answer about ownership and impact"; });
ok(T.runCommand({intent:"finish"})===true, "finish grades the session");
ok(s.status==="done" && T.state.user.points>0, "session graded and points logged");
globalThis.__flushSpeech();
ok(T.runCommand({intent:"readback"})===true, "readback works on a finished session");
globalThis.__flushSpeech();

print("-- chat round commands --");
T.state.activeSession = null;
T.runCommand({intent:"start", activity:"sd_mock"});
var c = T.state.activeSession;
__el("viewSession").classList.remove("hidden");
globalThis.__flushSpeech();
var rec = globalThis.__recs[globalThis.__recs.length-1];
rec.emit("I would start by scoping the read and write paths", true);
ok(T.fieldValue("chat").indexOf("scoping")>=0, "dictation captured");
rec.emit("hero send it", true);
ok(c.messages.filter(function(m){return m.role==="user";}).length===1, "wake-word command sent the turn");
ok(T.fieldValue("chat")==="", "draft cleared");
ok(T.fieldValue("chat").indexOf("hero")<0, "wake phrase never leaks into the answer");

print("-- help --");
T.showCommandHelp(true);
ok(__el("cmdHelp")._html.indexOf("coding mock")>=0, "help lists a start example");
ok(__el("cmdHelp")._html.indexOf("undefined")<0, "help text clean");
ok(T.COMMAND_GRAMMAR.length>=15, "command set is broad enough: "+T.COMMAND_GRAMMAR.length);
done();
"""


def main():
    return {"commands": run("commands", dom(speech_support=True), CMD)}


if __name__ == "__main__":
    sys.exit(report(main()))
