// Real Chrome on an isolated r5 service; traffic perturbations are explicit fault tests.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0006/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const evidence = path.join(root, "docs/iterations/evidence/ITER-0006");
const firstReport = JSON.parse(fs.readFileSync(path.join(evidence, "live-first.json"), "utf8"));
const secondReport = JSON.parse(fs.readFileSync(path.join(evidence, "live-second.json"), "utf8"));
const visitOnly = JSON.parse(fs.readFileSync(path.join(evidence, "test-double-visit-only.json"), "utf8"));
const legacy = JSON.parse(fs.readFileSync(path.join(root, "docs/iterations/evidence/ITER-0003/live-builder.json"), "utf8"));
const listener = net.createServer();
await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
const port = listener.address().port;
await new Promise(resolve => listener.close(resolve));
const url = `http://127.0.0.1:${port}`, prefix = "/v1/worlds/foundation-01";
const log = fs.openSync(path.join(data, "server.log"), "a");
const results = [], errors = [], reportWorldRequests = [];
let service, browser, page, access, reportPage, browserVersion;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate, message, timeout = 12000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await predicate()) return; await delay(50); }
  throw new Error(message);
}
async function check(name, operation) {
  const start = Date.now(); await operation();
  results.push({ name, passed: true, milliseconds: Date.now() - start }); console.log("PASS", name);
}
async function start() {
  service = spawn("dotnet", [path.join(root, "src/World.Server/bin/Debug/net10.0/World.Server.dll")], {
    cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_SCENARIO: "mosaic-v1", WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", log, log],
  });
  await until(async () => {
    if (service.exitCode !== null) throw new Error(`service exited ${service.exitCode}`);
    try { return (await fetch(url + "/healthz")).ok; } catch { return false; }
  }, "service unavailable", 20000);
}
async function stop() {
  if (service && service.exitCode === null) { service.kill("SIGTERM"); await until(async () => service.exitCode !== null, "service failed to stop", 6000); }
}
async function api(suffix, method = "GET", body, actor = "a1") {
  const r = await fetch(url + prefix + suffix, { method, headers: { Authorization: `Bearer ${access.sessions[actor].token}`, "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  return { status: r.status, body: await r.json() };
}
async function observed(actor = "a1") { const r = await api("/observation", "GET", undefined, actor); assert.equal(r.status, 200); return r.body; }
async function command(action, actor = "a1") {
  const o = await observed(actor); return api("/commands", "POST", { schemaVersion: 1, rulesVersion: "r5", commandId: crypto.randomUUID(), expectedStateVersion: o.stateVersion, action }, actor);
}
async function connect(p, actor = "a1") {
  await p.goto(url); await p.locator("#token-input").fill(access.sessions[actor].token); await p.locator("#connect-button").click();
  await until(async () => !(await p.locator("#move-down").isDisabled()), "UI not connected");
}
async function version(p, expected) { await until(async () => Number(await p.locator("#state-version").textContent()) === expected, "UI version stale"); }
async function click(id, status = 200) {
  await until(async () => !(await page.locator(id).isDisabled()), `${id} disabled`);
  const wait = page.waitForResponse(r => r.url() === url + prefix + "/commands" && r.request().method() === "POST");
  await page.locator(id).click(); const response = await wait;
  assert.equal(response.status(), status, await response.text());
  await version(page, (await observed()).stateVersion);
}
function watch(p, isReport = false) {
  p.on("pageerror", e => errors.push(e.message));
  if (isReport) p.on("request", r => { if (new URL(r.url()).pathname.startsWith("/v1/")) reportWorldRequests.push(r.url()); });
}
async function importReport(p, report, name) {
  await p.locator("#report-file").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) });
  await until(async () => (await p.locator("#load-message").textContent()).includes(`已加载：${name}`), "report import failed");
}
async function clickFor(p, id, actor = "a1", status = 200) {
  await until(async () => !(await p.locator(id).isDisabled()), `${id} disabled for ${actor}`);
  const wait = p.waitForResponse(r => r.url() === url + prefix + "/commands" && r.request().method() === "POST");
  await p.locator(id).click(); const response = await wait;
  assert.equal(response.status(), status, await response.text()); await version(p, (await observed(actor)).stateVersion);
}
const tile = (p, x, y) => p.locator(`#mosaic-editor [data-x="${x}"][data-y="${y}"]`);
async function color(p, id) { await p.locator(`#mosaic-palette [data-color="${id}"]`).click(); }
let peer;
try {
  await start(); access = JSON.parse(fs.readFileSync(path.join(data, "access.json"), "utf8"));
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  browserVersion = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 }); watch(page);
  await check("draft_is_separate_keyboard_does_not_move_and_poll_keeps_colors", async () => {
    await connect(page); assert.equal(await page.locator("#mosaic-panel").isHidden(), false);
    assert.match(await page.locator("#mosaic-panel").textContent(), /公开.*之后也能被别人修改/);
    await color(page, "river"); for (const x of [1,2,3]) await tile(page,x,2).click();
    await tile(page,1,2).focus(); await page.keyboard.press("ArrowRight");
    assert.equal(await tile(page,2,2).evaluate(el => el === document.activeElement), true);
    await delay(1700); assert.equal((await observed()).stateVersion, 0);
    assert.equal(await page.locator('#mosaic-editor [data-draft="true"]').count(), 3);
    assert.equal(await page.locator('#mosaic-public [data-color="river"]').count(), 0);
    assert.equal(await page.locator("#mosaic-publish").isDisabled(), true);
  });
  await check("human_visit_publishes_batch_with_author_and_clears_draft", async () => {
    for (let i=0;i<5;i++) await clickFor(page,"#move-down");
    assert.equal(await page.locator("#mosaic-publish").isDisabled(), true);
    await clickFor(page,"#visit-button"); const before=await observed(); await clickFor(page,"#mosaic-publish");
    const o=await observed(); assert.equal(o.mosaic.revision,1); assert.equal(o.mosaicEdits.length,1);
    assert.equal(o.mosaicEdits[0].visitCommandId,before.self.visits.at(-1).commandId);
    assert.deepEqual(o.resourceAudit,before.resourceAudit); assert.equal(await page.locator('#mosaic-editor [data-draft="true"]').count(),0);
    assert.equal(await page.locator('#mosaic-public [data-color="river"]').count(),3);
    assert.match(await page.locator("#mosaic-authors").textContent(),/居民 a1/);
    assert.match(await page.locator("#event-list").textContent(),/为花园共同画布/);
  });
  await check("second_human_reads_and_continues_actual_shared_picture", async () => {
    peer=await browser.newPage({viewport:{width:1100,height:900}});watch(peer);await connect(peer,"a2");
    assert.equal(await peer.locator('#mosaic-public [data-color="river"]').count(),3);
    await color(peer,"leaf");await tile(peer,1,1).click();await tile(peer,2,1).click();
    for(let i=0;i<4;i++) await clickFor(peer,"#move-down","a2");
    await clickFor(peer,"#visit-button","a2");await clickFor(peer,"#mosaic-publish","a2");
    await version(page,(await observed()).stateVersion);
    const o=await observed();assert.equal(o.mosaic.revision,2);assert.equal(o.mosaic.cells.filter(c=>c.authorActorId==="a1").length,3);
    assert.equal(o.mosaic.cells.filter(c=>c.authorActorId==="a2").length,2);
    assert.match(await page.locator("#mosaic-authors").textContent(),/居民 a1.*居民 a2|居民 a2.*居民 a1/);
  });
  await check("eight_cell_limit_draft_reload_and_actor_isolation", async () => {
    await color(page,"rose");for(const [x,y] of [[0,0],[1,0],[2,0],[3,0],[4,0],[0,1],[3,1],[4,1],[0,2]])await tile(page,x,y).click();
    assert.equal(await page.locator('#mosaic-editor [data-draft="true"]').count(),8);assert.match(await page.locator("#feedback").textContent(),/最多改 8 格/);
    await page.locator("#mosaic-clear").click();await color(page,"sun");await tile(page,4,4).click();await page.reload();
    await until(async()=>!(await page.locator("#move-down").isDisabled()),"reload disconnected");
    assert.equal(await tile(page,4,4).getAttribute("data-color"),"sun");
    for(const actor of ["a2","a1"]){
      await page.locator("#token-input").fill(access.sessions[actor].token);await page.locator("#connect-button").click();
      await until(async()=>(await page.locator("#resident-title").textContent())===`居民 ${actor}`,"switch failed");
      assert.equal(await page.locator('#mosaic-editor [data-draft="true"]').count(),actor==="a1"?1:0);
    }
  });
  await check("concurrent_board_revision_keeps_old_draft_and_never_overwrites", async () => {
    const visit=await command({type:"visit",activityId:"garden"},"a2");assert.equal(visit.status,200);
    const o=await observed("a2");const r=await command({type:"mosaic",activityId:"garden",visitCommandId:visit.body.commandId,expectedMosaicRevision:o.mosaic.revision,patch:[{x:0,y:0,color:"leaf"}]},"a2");assert.equal(r.status,200);
    await version(page,(await observed()).stateVersion);assert.equal(await page.locator("#mosaic-publish").isDisabled(),true);
    assert.equal(await tile(page,4,4).getAttribute("data-color"),"sun");assert.match(await page.locator("#mosaic-hint").textContent(),/旧草图没有发表/);
    assert.equal(await page.locator("#mosaic-hint").getAttribute("data-conflict"),"true");
    assert.equal((await observed()).mosaic.revision,3);
    await page.locator("#mosaic-clear").click();assert.equal(await page.locator('#mosaic-editor [data-draft="true"]').count(),0);
  });
  await check("real_world_stale_rejection_preserves_unpublished_patch", async () => {
    await clickFor(page,"#visit-button");await color(page,"sun");await tile(page,4,4).click();let changed=false;
    const handler=async route=>{if(route.request().method()==="POST"&&route.request().postDataJSON().action.type==="mosaic"&&!changed){changed=true;assert.equal((await command({type:"move",dx:0,dy:-1})).status,200);}await route.continue();};
    await page.route("**/commands",handler);await clickFor(page,"#mosaic-publish","a1",409);await page.unroute("**/commands",handler);
    assert.equal((await observed()).mosaic.revision,3);assert.equal(await tile(page,4,4).getAttribute("data-draft"),"true");
    await clickFor(page,"#move-down");
  });
  await check("lost_commit_response_reload_recovers_original_patch_once", async () => {
    const before=await observed();let posts=0,hold=true,original;
    const handler=async route=>{if(route.request().method()==="POST"){posts++;original=route.request().postDataJSON();const response=await route.fetch();assert.equal(response.status(),200);await route.abort("failed");}else if(hold)await route.abort("failed");else await route.continue();};
    await page.route(/\/commands(?:\/[^/?]+)?$/,handler);await page.locator("#mosaic-publish").click();
    await until(async()=>posts===1&&!(await page.locator("#pending-panel").isHidden()),"not pending");
    await page.reload();await until(async()=>!(await page.locator("#pending-panel").isHidden()),"pending lost");
    assert.equal(await tile(page,4,4).getAttribute("data-draft"),"true");hold=false;
    await until(async()=>!(await page.locator("#query-command-button").isDisabled()),"query disabled");await page.locator("#query-command-button").click();
    await until(async()=>await page.locator("#pending-panel").isHidden(),"not recovered");
    assert.equal(posts,1);const after=await observed();assert.equal(after.mosaic.revision,before.mosaic.revision+1);
    assert.equal(after.mosaicEdits.filter(e=>e.commandId===original.commandId).length,1);assert.deepEqual(after.resourceAudit,before.resourceAudit);
    assert.equal(await page.locator('#mosaic-editor [data-draft="true"]').count(),0);await page.unroute(/\/commands(?:\/[^/?]+)?$/,handler);
    await page.screenshot({path:path.join(data,"world-desktop.png"),fullPage:true});
  });
  await check("server_restart_preserves_picture_and_edit_sources", async () => {
    const before=await observed();await stop();await until(async()=>await page.locator("#visit-button").isDisabled(),"offline not shown");
    await start();assert.deepEqual(await observed(),before);await until(async()=>!(await page.locator("#visit-button").isDisabled()),"restart not recovered");
  });
  await check("mobile_world_picture_editor_layout_390px", async () => {
    const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});
    const p=await context.newPage();watch(p);await connect(p);await color(p,"rose");await tile(p,4,0).click();
    const d=await p.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(d.scroll<=d.width+1);
    await p.screenshot({path:path.join(data,"world-mobile.png"),fullPage:true});await context.close();
  });
  await check("actual_model_reports_show_proposal_confirmed_edit_and_shared_picture", async () => {
    reportPage=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});watch(reportPage,true);
    await reportPage.goto(url+"/resident.html?sample=mosaic");await until(async()=>(await reportPage.locator("#mission-id").textContent())===firstReport.mission.id,"first missing");
    assert.equal(await reportPage.locator("#report-status").textContent(),"已完成");assert.equal(await reportPage.locator("#mosaic-fact").getAttribute("data-verified"),"true");
    assert.equal(await reportPage.locator('#mosaic-proposal [data-draft="true"]').count(),firstReport.decision.mosaicPatch.length);
    await reportPage.locator('#mosaic-report-links a[href*="mosaic-reply"]').click();await until(async()=>(await reportPage.locator("#mission-id").textContent())===secondReport.mission.id,"second missing");
    assert.match(await reportPage.locator("#mosaic-fact").textContent(),/绘制已核实.*居民 a2/);assert.match(await reportPage.locator("#steps-list").textContent(),/绘制画布 · 静谧花园/);
    assert.equal(await reportPage.locator('#mosaic-final [data-color="river"]').count(),firstReport.decision.mosaicPatch.length);
    await reportPage.screenshot({path:path.join(data,"report-desktop.png"),fullPage:true});
  });
  await check("forged_patch_and_visit_only_cannot_claim_completed_and_old_reports_work", async () => {
    const forged=structuredClone(secondReport);forged.facts.mosaicEdit.patch[0].color=forged.facts.mosaicEdit.patch[0].color==="sun"?"ink":"sun";
    await importReport(reportPage,forged,"forged-edit.json");assert.equal(await reportPage.locator("#mosaic-fact").getAttribute("data-verified"),"false");assert.equal(await reportPage.locator("#report-status").textContent(),"完成标记待复核");
    await importReport(reportPage,visitOnly,"visit-only.json");assert.equal(await reportPage.locator("#mosaic-fact").getAttribute("data-verified"),"false");
    await importReport(reportPage,legacy,"legacy.json");assert.equal(await reportPage.locator("#mosaic-report-panel").isHidden(),true);assert.equal(await reportPage.locator("#report-status").textContent(),"已完成");
  });
  await check("mobile_actual_report_layout_390px", async () => {
    const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});const p=await context.newPage();watch(p,true);
    await p.goto(url+"/resident.html?sample=mosaic-reply");await until(async()=>(await p.locator("#report-status").textContent())==="已完成","mobile report not loaded");
    const d=await p.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(d.scroll<=d.width+1);
    await p.screenshot({path:path.join(data,"report-mobile.png"),fullPage:true});await context.close();
  });
  assert.deepEqual(errors,[]);assert.deepEqual(reportWorldRequests,[]);
} catch(error) {
  results.push({name:"uncaught",passed:false,error:error.stack});console.error(error);process.exitCode=1;
} finally {
  if(browser)await browser.close();await stop();fs.closeSync(log);
  fs.writeFileSync(path.join(data,"results.json"),JSON.stringify({suite:"mosaic-real-chrome-v1",recordedAtUtc:new Date().toISOString(),browser:browserVersion,passed:!process.exitCode,tests:results,javascriptErrors:errors,reportWorldRequests,actualModelCallsDuringUiTest:0,dataRoot:path.relative(root,data)},null,2)+"\n");
  console.log("Evidence:",path.join(data,"results.json"));
}
