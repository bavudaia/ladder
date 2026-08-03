"""Claude API wire format and structured-output schema legality.

Runs against a stubbed fetch, so it proves what the app would put on the wire
without needing a key or spending a token.
"""

import sys
from harness import HEAD, dom, run, report

FETCH = r"""
globalThis.__requests = [];
globalThis.__reply = "{}";
function fetch(url, opts){
  globalThis.__requests.push({url:url, headers:opts.headers, body:JSON.parse(opts.body)});
  var t = 'data: ' + JSON.stringify({type:"content_block_delta",delta:{type:"text_delta",text:globalThis.__reply}}) +
          '\n\n' + 'data: ' + JSON.stringify({type:"message_delta",delta:{stop_reason:"end_turn"}}) + '\n\n';
  var codes=[]; for(var i=0;i<t.length;i++) codes.push(t.charCodeAt(i));
  var sent=false;
  return Promise.resolve({ok:true,status:200,body:{getReader:function(){return {read:function(){
    if(sent) return Promise.resolve({done:true}); sent=true; return Promise.resolve({done:false,value:codes}); }};}}});
}
"""

API = HEAD + r"""
function walk(s, path){
  if(!s || typeof s!=="object") return;
  if(s.type==="object"){
    ok(s.additionalProperties===false, path+": needs additionalProperties:false");
    ok(Array.isArray(s.required), path+": needs required[]");
    var props=Object.keys(s.properties||{}), req=s.required||[];
    props.forEach(function(p){ ok(req.indexOf(p)>=0, path+"."+p+" must be required"); walk(s.properties[p], path+"."+p); });
    req.forEach(function(p){ ok(props.indexOf(p)>=0, path+": required lists unknown "+p); });
  }
  if(s.type==="array") walk(s.items, path+"[]");
  ["minimum","maximum","minLength","maxLength","minItems","maxItems","multipleOf","pattern"].forEach(function(b){
    ok(!(b in s), path+": unsupported schema keyword "+b); });
}
print("-- schemas are structured-output legal --");
walk(T.GRADE_SCHEMA, "grade");
walk(T.RECALL_SCHEMA, "recall");
T.ACTIVITIES.forEach(function(a){
  var sp = T.genSpec(a, "Caching strategies");
  /* A mock is written turn by turn and a review's content is the deck you have
     already earned, so neither has anything to generate up front. */
  if(a.engine==="chat" || a.engine==="recall"){ ok(sp===null, a.id+" needs no generation spec"); return; }
  ok(!!sp && !!sp.schema, a.id+" has a generation schema");
  walk(sp.schema, a.id);
  ok(sp.messages[0].content.indexOf("Caching strategies")>=0, a.id+" threads the topic through");
});
ok(T.RECALL_SCHEMA.properties.cards.items.properties.index.type === "integer",
   "recall grading is per card, not one number for the session");
ok(!T.RECALL_SCHEMA.properties.review_cards,
   "a review does not ask the grader for more cards — it already has them");
ok(!!T.GRADE_SCHEMA.properties.review_cards,
   "every other grading pass does, which is where the deck comes from");

print("-- wire format --");
T.state.model = "claude-opus-5";
globalThis.__reply = JSON.stringify({title:"T",topic:"x",difficulty:"medium",statement:"s",
  examples:[{input:"i",output:"o",why:"w"}],constraints:["c"],hints:["h"],rubric:[{label:"l",detail:"d"}]});
T.aiJSON(T.genSpec(T.actById("dsa_med"),"Binary search")).then(function(p){
  ok(p.title==="T", "structured JSON parsed off the stream");
  var r = globalThis.__requests[globalThis.__requests.length-1];
  ok(r.url==="https://api.anthropic.com/v1/messages", "endpoint");
  ok(r.headers["x-api-key"]==="sk-ant-test", "x-api-key");
  ok(r.headers["anthropic-version"]==="2023-06-01", "anthropic-version");
  ok(r.headers["anthropic-dangerous-direct-browser-access"]==="true", "browser-access header");
  ok(r.body.model==="claude-opus-5" && r.body.stream===true, "model + streaming");
  ok(r.body.output_config.format.type==="json_schema", "structured output");
  ok(["low","medium","high"].indexOf(r.body.output_config.effort)>=0, "effort");
  ok(!("thinking" in r.body), "no thinking param (adaptive is the Opus 5 default)");
  ok(!("temperature" in r.body) && !("top_p" in r.body) && !("top_k" in r.body), "no sampling params");
  ok(JSON.stringify(r.body).indexOf("budget_tokens")<0, "no budget_tokens");
  ok(r.body.messages[r.body.messages.length-1].role==="user", "no assistant prefill");
  T.state.model="claude-haiku-4-5"; globalThis.__requests.length=0;
  return T.aiJSON(T.genSpec(T.actById("dsa_easy"),"Arrays and hashing"));
}).then(function(){
  var r = globalThis.__requests[globalThis.__requests.length-1];
  ok(!r.body.output_config.effort, "effort omitted on haiku (unsupported there)");
  ok(r.body.output_config.format.type==="json_schema", "haiku keeps structured output");
  T.state.model="claude-opus-5";
  T.ACTIVITIES.forEach(function(a){
    var sess={activityId:a.id,engine:a.engine,topic:"Caching",source:"ai",
      item:{title:"t",statement:"s",prompt:"p",brief:"b",task:"k",guidance:"g",
            questions:[{q:"q1",ideal:"i1"},{q:"q2",ideal:"i2"}],rubric:[{label:"L",detail:"D"}]},
      messages:[{role:"assistant",content:"ask"},{role:"user",content:"answer"}],
      answers:{approach:"a",code:"c",answer:"e",situation:"s",task:"t",action:"ac",result:"r",q0:"a0",q1:"a1"}};
    var g=T.gradeSpec(sess);
    ok(g.schema===(a.engine==="recall" ? T.RECALL_SCHEMA : T.GRADE_SCHEMA),
       a.id+" grades against the right schema");
    ok(g.system.length>80 && g.messages[0].content.indexOf("undefined")<0, a.id+" grade prompt is clean");
  });
  ["sd_mock","code_mock"].forEach(function(id){
    var s=T.chatSystem(T.actById(id),"News feed");
    ok(s.indexOf("News feed")>=0 && s.indexOf("XML tags")>=0, id+" chat system prompt");
  });
  done();
}).catch(function(e){ print("EXCEPTION: "+(e&&e.message||e)); print("1 FAILURES"); });
"""


def main():
    stub = dom(speech_support=True, secure=True, key="sk-ant-test").replace(
        "function TextDecoder", FETCH + "\nfunction TextDecoder")
    return {"api": run("api", stub, API)}


if __name__ == "__main__":
    sys.exit(report(main()))
