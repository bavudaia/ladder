"""Diagram attachments: validation, the downscale/re-encode pipeline, the wire
format Claude actually receives, and what happens when storage runs out."""

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

IMAGES = HEAD + r"""
var PNG = "image/png", JPG = "image/jpeg";

print("-- which activities take diagrams --");
var withImg = T.ACTIVITIES.filter(function(a){ return a.img; }).map(function(a){ return a.id; });
["sd_mock","code_mock","sd_deep","dsa_hard","dsa_med","dsa_easy"].forEach(function(id){
  ok(withImg.indexOf(id)>=0, id+" takes diagrams");
});
["star","rapid","concept","lesson"].forEach(function(id){
  ok(withImg.indexOf(id)<0, id+" does not (a diagram adds nothing there)");
});

print("-- file validation --");
ok(T.validateImageFile(__file("d.png", PNG, 800, 600))===null, "png accepted");
ok(T.validateImageFile(__file("d.jpg", JPG, 800, 600))===null, "jpeg accepted");
ok(T.validateImageFile(__file("d.webp","image/webp",800,600))===null, "webp accepted");
ok(T.validateImageFile(__file("d.gif","image/gif",800,600))===null, "gif accepted");
var pdf = T.validateImageFile(__file("notes.pdf","application/pdf",0,0));
ok(pdf && pdf.indexOf("notes.pdf")>=0 && pdf.indexOf("PNG")>=0, "pdf refused by name and type: "+pdf);
var huge = T.validateImageFile(__file("raw.png", PNG, 9000, 9000, 40*1024*1024));
ok(huge && huge.indexOf("too big")>=0, "oversized file refused before decoding: "+huge);
ok(T.validateImageFile(null)!==null, "null is not a file");

print("-- downscaling arithmetic --");
var d = T.fitDims(4000, 2000, 1400);
ok(d.w===1400 && d.h===700, "long edge clamped, aspect kept: "+d.w+"x"+d.h);
var d2 = T.fitDims(600, 900, 1400);
ok(d2.w===600 && d2.h===900, "smaller images are left alone");
var d3 = T.fitDims(3000, 10, 1400);
ok(d3.h>=1, "a sliver never rounds to zero height, got "+d3.h);

print("-- re-encoding shrinks until it fits the budget --");
globalThis.__encodes = [];
var img = { width: 4000, height: 3000 };
var enc = T.encodeImage(img, true);
ok(!!enc, "produced an encoding");
ok(enc.bytes <= T.IMG_TARGET_BYTES, "under the per-image budget: "+enc.bytes+" <= "+T.IMG_TARGET_BYTES);
ok(Math.max(enc.w, enc.h) <= T.IMG_MAX_EDGE, "never larger than the max edge");
ok(globalThis.__encodes[0].mime===PNG, "lossless source is tried as png first");
ok(globalThis.__encodes.length>1, "fell back when png was too heavy, tries: "+globalThis.__encodes.length);
ok(globalThis.__encodes[0].filled>0 && globalThis.__encodes[0].drawn>0,
   "canvas is flattened onto white before drawing (transparent png would read as nothing)");

globalThis.__encodes = [];
var small = T.encodeImage({width:400,height:300}, true);
ok(small.mime===PNG && globalThis.__encodes.length===1, "a small diagram stays lossless in one pass");
ok(small.w===400 && small.h===300, "and is not upscaled");

globalThis.__encodes = [];
var photo = T.encodeImage({width:3000,height:2000}, false);
ok(photo.mime===JPG, "a photo source never bothers with png");

print("-- reading a file end to end --");
var got = null, err = null;
T.readImageFile(__file("whiteboard.png", PNG, 2000, 1200)).then(function(a){ got=a; }, function(e){ err=e; });
flush();
ok(!err && got, "resolved: "+(err&&err.message));
ok(got.b64.length>0 && got.bytes>0, "carries base64 payload and a byte count");
ok(got.name==="whiteboard.png", "keeps the filename");
ok(got.w<=T.IMG_MAX_EDGE && got.h<=T.IMG_MAX_EDGE, "stored at display-safe dimensions");
ok(T.imgDataUrl(got).indexOf("data:"+got.mime+";base64,")===0, "renders as a data url");

var e2 = null;
T.readImageFile(__file("cv.txt","text/plain",10,10)).then(function(){}, function(e){ e2=e; });
flush();
ok(e2 && e2.message.indexOf("cv.txt")>=0, "a bad type rejects with the filename");

var e3 = null, broken = __file("corrupt.png", PNG, 10, 10); broken.__unreadable = true;
T.readImageFile(broken).then(function(){}, function(e){ e3=e; });
flush();
ok(e3 && e3.message.indexOf("Could not read")>=0, "an unreadable file rejects cleanly");

print("-- attaching to a system design mock --");
T.startSession("sd_mock");
var s = T.state.activeSession;
ok(s.status==="ready", "mock ready");
ok(Array.isArray(s.attachments) && s.attachments.length===0, "starts with no attachments");
var panel = __el("sessionPanel")._html;
ok(panel.indexOf('data-a="attach"')>=0, "attach control rendered");
ok(panel.indexOf('id="imgInput"')>=0, "file input rendered");
ok(panel.indexOf("paste a screenshot")>=0, "tells you paste works");

T.addFiles([__file("arch.png", PNG, 1600, 900)]); flush();
ok(s.attachments.length===1, "attachment landed, got "+s.attachments.length);
var withThumb = __el("sessionPanel")._html;
ok(withThumb.indexOf("thumb-strip")>=0 && withThumb.indexOf("data:image/")>=0, "thumbnail rendered");
ok(withThumb.indexOf('data-a="rmimg"')>=0, "and can be removed");
ok(!__HOLES(withThumb), "no template holes in the attach markup");

T.addFiles([__file("bad.pdf","application/pdf",0,0)]); flush();
ok(s.attachments.length===1, "a rejected file does not attach");
ok(__el("sessionPanel")._html.indexOf("attach-note")>=0, "and the reason is shown in the panel");

print("-- per-turn cap --");
for (var i=0;i<6;i++) { T.addFiles([__file("x"+i+".png", PNG, 400, 300)]); flush(); }
ok(s.attachments.length===T.IMG_MAX_PER_TURN, "capped at "+T.IMG_MAX_PER_TURN+", got "+s.attachments.length);
ok(__el("sessionPanel")._html.indexOf("Only "+T.IMG_MAX_PER_TURN)>=0, "cap is explained, not silent");
ok(__el("sessionPanel")._html.indexOf('data-a="attach" type="button" disabled')>=0, "attach button disables at the cap");

T.removeAttachment(s.attachments[0].id); flush();
ok(s.attachments.length===T.IMG_MAX_PER_TURN-1, "remove drops exactly one");
while (s.attachments.length) T.removeAttachment(s.attachments[0].id);
ok(s.attachments.length===0, "all removable");

print("-- session budget --");
globalThis.__PNG_BPP = 0.55; globalThis.__JPG_BPP = 0.30;
var before = T.sessionImgBytes(s);
T.addFiles([__file("a.png", PNG, 1400, 1000)]); flush();
ok(T.sessionImgBytes(s) > before, "budget accounting moves with attachments");
T.state.activeSession.attachments = [];
T.state.activeSession.messages.push({ role:"user", content:"sent", images:[
  { id:"big", name:"big.png", mime:PNG, b64:new Array(T.IMG_SESSION_BUDGET+9).join("A"),
    bytes:T.IMG_SESSION_BUDGET, w:100, h:100 } ]});
T.addFiles([__file("over.png", PNG, 1200, 900)]); flush();
ok(s.attachments.length===0, "refuses once the session budget is spent");
ok(__el("sessionPanel")._html.indexOf("diagram budget")>=0, "says why");
ok(T.sessionImages(s).length===1, "already-sent images still count toward the budget");

print("-- the turn carries the image --");
T.state.activeSession = null;
T.startSession("sd_mock");
var c = T.state.activeSession;
T.addFiles([__file("design.png", PNG, 1200, 800)]); flush();
ok(c.attachments.length===1, "attached before sending");
T.sendChatTurn("Here is my design. Writes go through the queue.");
var mine = c.messages.filter(function(m){ return m.role==="user"; });
ok(mine.length===1, "turn sent");
ok(mine[0].images && mine[0].images.length===1, "image travels with the turn it belongs to");
ok(c.attachments.length===0, "pending tray cleared after send");
ok(__el("sessionPanel")._html.indexOf("thumb-strip")>=0, "the sent image shows in the transcript");

print("-- an image alone is a valid turn --");
T.addFiles([__file("only.png", PNG, 900, 700)]); flush();
var n0 = c.messages.filter(function(m){ return m.role==="user"; }).length;
T.sendChatTurn("");
ok(c.messages.filter(function(m){ return m.role==="user"; }).length===n0+1, "sent with no typed text");
T.sendChatTurn("");
ok(c.messages.filter(function(m){ return m.role==="user"; }).length===n0+1, "but empty with nothing attached is still a no-op");

print("-- wire format --");
var blocks = T.userContent("What is wrong with this?", [
  {id:"i1", mime:PNG, b64:"AAAA", bytes:3, w:10, h:10},
  {id:"i2", mime:JPG, b64:"BBBB", bytes:3, w:10, h:10}]);
ok(Array.isArray(blocks) && blocks.length===3, "images plus one text block, got "+blocks.length);
ok(blocks[0].type==="image" && blocks[1].type==="image", "images come first, before the question");
ok(blocks[0].source.type==="base64", "base64 source type");
ok(blocks[0].source.media_type===PNG && blocks[1].source.media_type===JPG, "media types preserved per image");
ok(blocks[0].source.data==="AAAA", "raw base64, no data: prefix");
ok(blocks[2].type==="text" && blocks[2].text==="What is wrong with this?", "text block last");
ok(T.userContent("just text", [])==="just text", "no images means a plain string, not a one-block array");
ok(T.userContent("just text", null)==="just text", "and null is handled");
var bare = T.userContent("   ", [{id:"i", mime:PNG, b64:"AAAA", bytes:3, w:1, h:1}]);
ok(bare[1].text.length>0, "an empty text block is never sent (the API rejects it)");
ok(T.userContent("t", [{id:"x", mime:PNG, b64:"", bytes:0}])==="t", "an image with no bytes is dropped");

print("-- grading prompt --");
var gs = T.gradeSpec(c);
ok(Array.isArray(gs.messages[0].content), "grade call carries the images");
ok(gs.messages[0].content.filter(function(b){return b.type==="image";}).length===2, "both attached diagrams");
ok(gs.system.indexOf("diagram")>=0, "grader is told to judge the diagram");
var txt = gs.messages[0].content[gs.messages[0].content.length-1].text;
ok(txt.indexOf("attached")>=0, "the transcript marks which turn the diagram came with");
ok(!__HOLES(txt), "grade prompt has no holes");

var clean = T.gradeSpec({activityId:"dsa_med", engine:"submit", topic:"Arrays", messages:[],
  answers:{approach:"two pointers", code:"f(){}"}, item:{title:"t", rubric:[{label:"L",detail:"D"}]}});
ok(typeof clean.messages[0].content==="string", "a session with no images sends a plain string");
ok(clean.system.indexOf("diagram")<0, "and the grader is not told about diagrams that do not exist");

print("-- interviewer sees the image on the wire --");
globalThis.__requests.length = 0;
globalThis.__reply = "And what happens when that queue backs up?";
T.state.model = "claude-opus-5";
c.source = "ai";
T.addFiles([__file("v2.png", PNG, 1000, 800)]); flush();
T.sendChatTurn("Revised design attached.");
flush(); flush();
var req = globalThis.__requests[globalThis.__requests.length-1];
ok(!!req, "a request went out");
if (req) {
  var last = req.body.messages[req.body.messages.length-1];
  ok(Array.isArray(last.content), "last user turn is a content-block array");
  var imgBlocks = last.content.filter(function(b){ return b.type==="image"; });
  ok(imgBlocks.length===1, "one image block on the wire, got "+imgBlocks.length);
  ok(imgBlocks[0].source.type==="base64" && !!imgBlocks[0].source.data, "with a base64 payload");
  ok(JSON.stringify(req.body).indexOf("data:image")<0, "the data: prefix is never sent");
  ok(req.body.system.indexOf("attach a diagram")>=0, "interviewer is briefed to read diagrams");
}

print("-- offline grading is honest about images --");
var off = { activityId:"sd_deep", engine:"submit", topic:"Consistent hashing", source:"offline",
  item:{ title:"t", rubric:[{label:"Ring", detail:"walk clockwise"}] },
  messages:[], answers:{ answer:"the ring is circular and you walk clockwise to the next node" },
  attachments:[{id:"z", name:"z.png", mime:PNG, b64:"AAAA", bytes:3, w:10, h:10}] };
var rep = T.offlineGrade(off);
var gapText = rep.gaps.join(" ");
ok(gapText.indexOf("not graded")>=0, "says the diagram was not graded");
ok(gapText.indexOf("cannot read images")>=0, "and why");
ok(gapText.indexOf("API key")>=0, "and what to do about it");
off.attachments = [];
ok(T.offlineGrade(off).gaps.join(" ").indexOf("not graded")<0, "no such note when nothing is attached");

print("-- activities that do not take diagrams --");
T.state.activeSession = null;
globalThis.__reply = JSON.stringify({topic:"Ownership", questions:[{q:"Tell me about a conflict.", ideal:"i"}]});
T.startSession("rapid");
var r2 = T.state.activeSession;
for (var f=0; f<6; f++) flush();     /* qset generation is a real async round-trip */
ok(r2.status==="ready", "rapid session settled, got "+r2.status);
ok(__el("sessionPanel")._html.indexOf('data-a="attach"')<0, "no attach control on rapid-fire");
T.addFiles([__file("x.png", PNG, 100, 100)]); flush();
ok(!r2.attachments || r2.attachments.length===0, "and files are refused there");
ok(__el("sessionPanel")._html.indexOf("does not take diagrams")>=0, "with an explanation");

print("-- storage quota --");
T.state.activeSession = null;
T.startSession("sd_mock");
var q = T.state.activeSession;
T.addFiles([__file("keep.png", PNG, 1200, 900)]); flush();
globalThis.__quota = 5000;                 /* anything with an image in it now fails to save */
ok(T.saveState()===true, "a season too big for storage still saves");
globalThis.__quota = 0;
var saved = JSON.parse(localStorage.getItem(T.seasonKey()));
ok(saved.activeSession.attachments.length===1, "the attachment record survives");
ok(saved.activeSession.attachments[0].b64==="", "but its bytes were dropped to fit");
ok(saved.user !== undefined && saved.peers.length===9, "and the season itself is intact");
ok(q.attachments[0].b64.length>0, "the live session keeps the image in memory");
done();
"""


def main():
    stub = dom(speech_support=True, secure=True, key="sk-ant-test").replace(
        "function TextDecoder", FETCH + "\nfunction TextDecoder")
    return {"images": run("images", stub, IMAGES)}


if __name__ == "__main__":
    sys.exit(report(main()))
