// Actual entity-note reports, immutable original evidence and mobile rendering in real Chrome.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0023/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const results = [], errors = [], worldRequests = [];
let browser, page, service, version;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate, message) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) { if (await predicate()) return; await delay(40); }
  throw new Error(message);
}
async function check(name, action) { await action(); results.push({ name, passed: true }); console.log("PASS", name); }
async function imported(report, name) {
  await page.locator("#report-file").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) });
  await until(async () => (await page.locator("#load-message").textContent()).includes(name), "report import did not settle: " + name);
}
async function rejected(report) {
  await page.locator("#report-file").setInputFiles({ name: "damaged.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) });
  await until(async () => (await page.locator("#load-message").textContent()).includes("导入失败"), "damaged report was accepted");
}
const log = fs.openSync(path.join(data, "server.log"), "w");
try {
  let reportFile = process.env.ENTITY_NOTE_REPORT_FILE;
  if (!reportFile) {
    const run = spawnSync("python3", ["tests/entity_notes_mission_api.py", "test_01_actual_cli_first_note_and_original_reference_reply"], {cwd:root,encoding:"utf8",timeout:600000});
    fs.writeFileSync(path.join(data,"mission.log"),run.stdout+run.stderr);
    assert.equal(run.status,0,run.stderr);
    const evidence = run.stdout.trim().split("\n").findLast(line => line.startsWith("Evidence: ")).slice(10);
    const search = directory => fs.readdirSync(directory,{withFileTypes:true}).flatMap(e => e.isDirectory()
      ? search(path.join(directory,e.name)) : e.name.endsWith(".json") ? [path.join(directory,e.name)] : []);
    reportFile = search(path.dirname(evidence)).find(file => {
      try {const r=JSON.parse(fs.readFileSync(file,"utf8"));return r.kind === "resident-mission-report" && r.mission.status === "completed" && r.facts.entityNoteShared === true && !r._state;} catch {return false;}
    });
    assert.ok(reportFile,"actual completed note report absent");
  }
  const actual=JSON.parse(fs.readFileSync(reportFile,"utf8"));
  fs.writeFileSync(path.join(data,"actual-report.json"),JSON.stringify(actual,null,2)+"\n");
  const listener=net.createServer();await new Promise(resolve=>listener.listen(0,"127.0.0.1",resolve));
  const port=listener.address().port;await new Promise(resolve=>listener.close(resolve));const url=`http://127.0.0.1:${port}`;
  service=spawn("python3",["-m","http.server",String(port),"--bind","127.0.0.1","--directory","src/World.Server/wwwroot"],{cwd:root,stdio:["ignore",log,log]});
  await until(async()=>{try{return(await fetch(url+"/resident.html")).ok;}catch{return false;}},"static host unavailable");
  browser=await chromium.launch({executablePath:process.env.CHROME_PATH||"/usr/bin/google-chrome",headless:true});version=browser.version();
  page=await browser.newPage({viewport:{width:1440,height:1080}});
  page.on("pageerror",error=>errors.push(error.message));
  page.on("request",r=>{if(new URL(r.url()).pathname.startsWith("/v1/"))worldRequests.push(r.method());});
  await page.goto(url+"/resident.html");
  await check("old_report_hides_note_panel",async()=>{
    await until(async()=>(await page.locator("#load-message").textContent()).includes("已加载"),"initial report absent");
    assert.equal(await page.locator("#entity-note-panel").isVisible(),false);
  });
  await check("actual_cli_text_reference_and_author_match",async()=>{
    await imported(actual,"actual-note.json");
    assert.equal(await page.locator("#entity-note-fact").getAttribute("data-verified"),"true");
    assert.equal(await page.locator("#entity-note-text").textContent(),actual.facts.entityNote.text);
    assert.ok((await page.locator("#entity-note-fact").textContent()).includes(actual.mission.actorId));
    assert.equal(await page.locator("#queries-budget").textContent(),`${actual.budget.used.queries} / ${actual.budget.limits.queries}`);
    assert.equal(await page.locator("#report-warning").isVisible(),false);
    await page.screenshot({path:path.join(data,"notes-desktop.png"),fullPage:true});
  });
  await check("draft_or_arrival_never_claims_publication",async()=>{
    const r=structuredClone(actual);r.mission.status="paused";r.facts.entityNoteShared=false;r.facts.entityNote=null;
    r.steps=r.steps.filter(s=>s.action.type!=="append_entity_note");
    await imported(r,"draft-only.json");
    assert.equal(await page.locator("#entity-note-fact").getAttribute("data-verified"),"false");
    assert.equal(await page.locator("#entity-note-text").textContent(),"");
  });
  await check("mismatched_note_author_reference_target_or_permission_is_unconfirmed",async()=>{
    for(const mutate of [r=>r.mission.allowEntityNotes=false,r=>r.facts.entityNote.commandId="another-command",
      r=>r.facts.entityNote.text="另一份正文",r=>r.facts.entityNote.replyToNoteId="n"+"0".repeat(32),
      r=>r.facts.entityNote.worldInstanceId="w_"+"0".repeat(32),r=>r.mission.goal.entityNote.entityId="e"+"0".repeat(32),
      r=>r.steps.find(s=>s.action.type==="append_entity_note").entityNoteEvidence.text="别人的记录",
      r=>r.steps.find(s=>s.action.type==="append_entity_note").evidenceSource="command_receipt",
      r=>r.world.entityNotes.notes.find(n=>n.noteId===r.facts.entityNote.noteId).text="另一条观察记录"]){
      const r=structuredClone(actual);mutate(r);await imported(r,"mismatch.json");
      assert.equal(await page.locator("#entity-note-fact").getAttribute("data-verified"),"false");
      assert.match(await page.locator("#report-status").textContent(),/待复核/);
    }
  });
  await check("damaged_evidence_or_query_budget_rejected",async()=>{
    for(const mutate of [r=>delete r.budget.used.queries,r=>delete r.steps.find(s=>s.action.type==="append_entity_note").entityNoteEvidence,
      r=>r.facts.entityNote.inventoryWood=true,r=>r.facts.entityNote.text="x".repeat(161),r=>r.world.entityNotes.notes[0].eventCursor=false]){
      await imported(actual,"original.json");const bad=structuredClone(actual);mutate(bad);await rejected(bad);
      assert.equal(await page.locator("#entity-note-text").textContent(),actual.facts.entityNote.text);
    }
  });
  await check("literal_text_never_executes_markup",async()=>{
    const r=structuredClone(actual),literal='<img src=x onerror="window.notesInjected=true">';
    r.mission.goal.entityNote.text=literal;r.facts.entityNote.text=literal;
    const s=r.steps.find(s=>s.action.type==="append_entity_note");s.action.text=literal;s.entityNoteEvidence.text=literal;
    r.world.entityNotes.notes.find(n=>n.noteId===r.facts.entityNote.noteId).text=literal;
    await imported(r,"literal-test-double.json");
    assert.equal(await page.locator("#entity-note-text").textContent(),literal);
    assert.equal(await page.locator("#entity-note-panel img").count(),0);
    assert.equal(await page.evaluate(()=>window.notesInjected),undefined);
  });
  await check("repeat_import_has_no_world_writes",async()=>{
    await imported(actual,"repeat-one.json");await imported(actual,"repeat-two.json");assert.deepEqual(worldRequests,[]);
  });
  await check("mobile_notes_readable_without_overflow",async()=>{
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.equal(await page.locator("#entity-note-text").textContent(),actual.facts.entityNote.text);
    await page.screenshot({path:path.join(data,"notes-mobile.png"),fullPage:true});
  });
  assert.deepEqual(errors,[]);
} catch(error) {
  results.push({name:"failed",passed:false,error:String(error.stack||error)});console.error(error);
} finally {
  if(browser)await browser.close();
  if(service){service.kill("SIGTERM");await new Promise(resolve=>service.once("exit",resolve));}
  fs.closeSync(log);
  fs.writeFileSync(path.join(data,"results.json"),JSON.stringify({passed:results.every(r=>r.passed),testsRun:results.length,actualModelCalls:0,version,results,errors,worldRequests},null,2)+"\n");
  console.log("Browser evidence:",path.join(data,"results.json"));
}
process.exitCode=results.every(r=>r.passed)?0:1;
