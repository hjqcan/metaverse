// Real Chrome on an isolated r6 service; traffic perturbations are explicit fault tests.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0007/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const evidence = path.join(root, "docs/iterations/evidence/ITER-0007");
const firstReport = JSON.parse(fs.readFileSync(path.join(evidence, "live-proposer.json"), "utf8"));
const secondReport = JSON.parse(fs.readFileSync(path.join(evidence, "live-reviewer.json"), "utf8"));
const visitOnly = JSON.parse(fs.readFileSync(path.join(evidence, "test-double-rejected.json"), "utf8"));
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
    cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_SCENARIO: "consent-v1", WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", log, log],
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
  const o = await observed(actor); return api("/commands", "POST", { schemaVersion: 1, rulesVersion: "r6", commandId: crypto.randomUUID(), expectedStateVersion: o.stateVersion, action }, actor);
}
async function connect(p, actor = "a1") {
  await p.goto(url); await p.locator("#token-input").fill(access.sessions[actor].token); await p.locator("#connect-button").click();
  await until(async () => !(await p.locator("#move-down").isDisabled()), "UI not connected");
  // This historical flow inspects both pending and completed public proposals.
  // The separate inbox suite checks the new received/pending default.
  if (await p.locator('#inbox-scope').count()) {
    await p.locator('#inbox-scope').selectOption('all');
    await p.locator('#inbox-status').selectOption('all');
    await until(async () => /每页最多 20 条/.test(await p.locator('#inbox-message').textContent()), 'public proposal list not ready');
  }
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
  if (await p.locator('#inbox-scope').count()) {
    await until(async () => /每页最多 20 条/.test(await p.locator('#inbox-message').textContent()) && !/正在|未更新|暂停/.test(await p.locator('#inbox-message').textContent()), 'inbox has not caught up with command');
  }
}
const tile = (p, x, y) => p.locator(`#mosaic-editor [data-x="${x}"][data-y="${y}"]`);
async function color(p, id) { await p.locator(`#mosaic-palette [data-color="${id}"]`).click(); }
const entry = (p, id) => p.locator(`#consent-list article[data-command="${id}"]`);
let peer, firstProposal;
async function proposeFromPeer(x, y, shade, text) {
  await version(peer, (await observed()).stateVersion);
  await color(peer,shade); await tile(peer,x,y).click();
  await peer.locator('#proposal-text').fill(text);
  await clickFor(peer,'#visit-button','a2');await clickFor(peer,'#mosaic-publish','a2');
  await version(page,(await observed()).stateVersion);
  return (await observed('a2')).self.mosaicProposals.at(-1);
}
try {
  await start();access=JSON.parse(fs.readFileSync(path.join(data,'access.json'),'utf8'));
  browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true});browserVersion=browser.version();
  page=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});watch(page);
  await check('original_author_creates_picture_through_shared_interface',async()=>{
    await connect(page);assert.match(await page.locator('#mosaic-public-note').textContent(),/先由对方同意/);
    await color(page,'river');for(const x of [1,2,3])await tile(page,x,2).click();
    for(let i=0;i<5;i++)await clickFor(page,'#move-down');await clickFor(page,'#visit-button');await clickFor(page,'#mosaic-publish');
    assert.equal((await observed()).mosaic.revision,1);assert.equal(await page.locator('#mosaic-public [data-color="river"]').count(),3);
  });
  await check('peer_proposal_draft_survives_poll_reload_and_cannot_paint_directly',async()=>{
    peer=await browser.newPage({viewport:{width:1100,height:900}});watch(peer);await connect(peer,'a2');
    await color(peer,'sun');await tile(peer,1,2).click();assert.equal(await peer.locator('#mosaic-publish').textContent(),'提交修改提议');
    await peer.locator('#proposal-text').fill('只把河流端点改为阳光标记。');await delay(1700);await peer.reload();
    await until(async()=>!(await peer.locator('#move-down').isDisabled()),'peer reload failed');
    assert.equal(await peer.locator('#proposal-text').inputValue(),'只把河流端点改为阳光标记。');assert.equal(await tile(peer,1,2).getAttribute('data-draft'),'true');
    for(let i=0;i<4;i++)await clickFor(peer,'#move-down','a2');await clickFor(peer,'#visit-button','a2');const before=await observed();
    await clickFor(peer,'#mosaic-publish','a2');const after=await observed();assert.deepEqual(after.mosaic,before.mosaic);
    firstProposal=after.mosaicProposals.at(-1);assert.equal(firstProposal.targetActorId,'a1');assert.equal(firstProposal.review,null);
    assert.equal(await peer.locator('#mosaic-editor [data-draft="true"]').count(),0);assert.equal(await peer.locator('#proposal-text').inputValue(),'');
    assert.equal(await entry(peer,firstProposal.commandId).locator('[data-review]').count(),0);
    await until(async()=> (await peer.locator('#event-list').textContent()).includes('等待居民 a1 决定'),'proposal event target missing');
    assert.doesNotMatch(await peer.locator('#event-list').textContent(),/undefined/);
  });
  await check('target_accepts_after_own_visit_and_both_contributions_are_attributed',async()=>{
    await version(page,(await observed()).stateVersion);const e=entry(page,firstProposal.commandId);
    await e.locator('textarea').fill('同意这个端点标记，其余河流保持原样。');assert.equal(await e.locator('[data-review="accept"]').isDisabled(),true);
    await clickFor(page,'#visit-button');await clickFor(page,`article[data-command="${firstProposal.commandId}"] [data-review="accept"]`);
    const o=await observed();const r=o.mosaicProposals.find(p=>p.commandId===firstProposal.commandId).review;
    assert.equal(o.mosaic.revision,2);assert.equal(r.proposalActorId,'a2');assert.equal(r.mosaicEdit.authorActorId,'a1');assert.equal(o.mosaic.cells[11].commandId,r.commandId);
    assert.match(await e.textContent(),/已同意并改图.*居民 a1/);assert.deepEqual(o.resourceAudit,{issuedWood:12,depotWood:12,inventoryWood:0,embodiedWood:0,conserved:true});
    await until(async()=> (await page.locator('#event-list').textContent()).includes('同意提议并修改了画布'),'accept event is mislabeled');
  });
  await check('reject_keeps_picture_and_renders_proposal_text_literally',async()=>{
    const p=await proposeFromPeer(3,2,'rose','<img src=x onerror="alert(1)"> 我想加一点花红。');const e=entry(page,p.commandId);const before=await observed();
    assert.equal(await e.locator('img').count(),0);assert.match(await e.textContent(),/<img src=x/);
    await e.locator('textarea').fill('这一端保留河蓝。');await clickFor(page,`article[data-command="${p.commandId}"] [data-review="reject"]`);
    assert.deepEqual((await observed()).mosaic,before.mosaic);assert.match(await e.textContent(),/已拒绝/);assert.equal(await e.locator('[data-review]:visible').count(),0);
    await until(async()=> (await page.locator('#event-list').textContent()).includes('拒绝提议，保留原图'),'reject event missing');
  });
  await check('mixed_draft_is_split_and_stale_proposal_cannot_overwrite_new_picture',async()=>{
    await version(peer,(await observed()).stateVersion);await color(peer,'leaf');await tile(peer,2,2).click();await tile(peer,0,0).click();
    assert.equal(await peer.locator('#mosaic-publish').isDisabled(),true);assert.match(await peer.locator('#mosaic-hint').textContent(),/混合了不同来源/);await peer.locator('#mosaic-clear').click();
    const p=await proposeFromPeer(2,2,'leaf','中间这一格想添一点绿。');const e=entry(page,p.commandId);
    await clickFor(page,'#visit-button');await color(page,'leaf');await tile(page,0,0).click();await clickFor(page,'#mosaic-publish');
    await e.locator('textarea').fill('画布已经变化，请重新提议。');assert.equal(await e.locator('[data-review="accept"]').isDisabled(),true);assert.equal(await e.locator('[data-review="reject"]').isDisabled(),false);
    assert.match(await e.textContent(),/画布已经变化/);const before=await observed();await clickFor(page,`article[data-command="${p.commandId}"] [data-review="reject"]`);assert.deepEqual((await observed()).mosaic,before.mosaic);
  });
  await check('lost_accept_response_reload_recovers_original_review_once',async()=>{
    const p=await proposeFromPeer(3,2,'sun','在另一端也留一个日黄标记。');await clickFor(page,'#visit-button');await entry(page,p.commandId).locator('textarea').fill('同意，两端互相呼应。');
    const before=await observed();let posts=0,hold=true,original;
    const handler=async route=>{if(route.request().method()==='POST'){posts++;original=route.request().postDataJSON();const r=await route.fetch();assert.equal(r.status(),200);await route.abort('failed');}else if(hold)await route.abort('failed');else await route.continue();};
    await page.route(/\/commands(?:\/[^/?]+)?$/,handler);await entry(page,p.commandId).locator('[data-review="accept"]').click();
    await until(async()=>posts===1&&!(await page.locator('#pending-panel').isHidden()),'review not pending');await page.reload();
    await until(async()=>!(await page.locator('#pending-panel').isHidden()),'original review lost after reload');
    // Reload already starts original-receipt recovery. Releasing the transport
    // can settle it before a manual query button becomes clickable.
    const recovered=page.waitForResponse(r=>r.url()===url+prefix+'/commands/'+original.commandId&&r.request().method()==='GET'&&r.status()===200,{timeout:12000});
    hold=false;
    const receipt=await(await recovered).json();assert.equal(receipt.commandId,original.commandId);assert.equal(receipt.status,'committed');
    await until(async()=>await page.locator('#pending-panel').isHidden(),'review recovery failed');await page.unroute(/\/commands(?:\/[^/?]+)?$/,handler);
    const after=await observed();assert.equal(posts,1);assert.equal(after.mosaic.revision,before.mosaic.revision+1);assert.equal(after.self.mosaicReviews.filter(r=>r.commandId===original.commandId).length,1);
    assert.equal(after.mosaicProposals.find(x=>x.commandId===p.commandId).review.commandId,original.commandId);
    await page.screenshot({path:path.join(data,'world-desktop.png'),fullPage:true});
  });
  await check('restart_preserves_proposals_reviews_and_picture',async()=>{
    const before=await observed();await stop();await start();assert.deepEqual(await observed(),before);await version(page,before.stateVersion);
  });
  await check('mobile_world_negotiation_layout_390px',async()=>{
    const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});const p=await context.newPage();watch(p);await connect(p);
    const d=await p.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(d.scroll<=d.width+1);
    await p.screenshot({path:path.join(data,'world-mobile.png'),fullPage:true});await context.close();
  });
  await check('actual_reports_separate_proposed_reviewed_and_painted_facts',async()=>{
    reportPage=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});watch(reportPage,true);
    await reportPage.goto(url+'/resident.html?sample=consent');await until(async()=>(await reportPage.locator('#mission-id').textContent())===firstReport.mission.id,'proposal report missing');
    assert.equal(await reportPage.locator('#report-status').textContent(),'已完成');assert.match(await reportPage.locator('#consent-report-fact').textContent(),/提议已核实.*尚未因此改图/);
    await reportPage.locator('#consent-report-links a[href*="consent-review"]').click();await until(async()=>(await reportPage.locator('#mission-id').textContent())===secondReport.mission.id,'review report missing');
    assert.equal(await reportPage.locator('#report-status').textContent(),'已完成');assert.equal(await reportPage.locator('#consent-report-fact').getAttribute('data-verified'),'true');
    assert.match(await reportPage.locator('#consent-report-origin').textContent(),/提议人 a2.*最后作者 a1/);await reportPage.screenshot({path:path.join(data,'report-desktop.png'),fullPage:true});
  });
  await check('forged_review_rejected_report_and_legacy_report_remain_distinct',async()=>{
    const forged=structuredClone(secondReport);forged.facts.mosaicReview.text='冒充原决定的文本';await importReport(reportPage,forged,'forged-review.json');
    assert.equal(await reportPage.locator('#report-status').textContent(),'完成标记待复核');assert.equal(await reportPage.locator('#consent-report-fact').getAttribute('data-verified'),'false');
    await importReport(reportPage,visitOnly,'rejected.json');assert.equal(await reportPage.locator('#report-status').textContent(),'已完成');assert.match(await reportPage.locator('#consent-report-fact').textContent(),/拒绝已核实.*没有产生绘制/);
    await importReport(reportPage,legacy,'legacy.json');assert.equal(await reportPage.locator('#consent-report-panel').isHidden(),true);assert.equal(await reportPage.locator('#report-status').textContent(),'已完成');
  });
  await check('mobile_actual_review_report_layout_390px',async()=>{
    const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});const p=await context.newPage();watch(p,true);
    await p.goto(url+'/resident.html?sample=consent-review');await until(async()=>(await p.locator('#report-status').textContent())==='已完成','mobile report missing');
    const d=await p.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(d.scroll<=d.width+1);
    await p.screenshot({path:path.join(data,'report-mobile.png'),fullPage:true});await context.close();
  });
  assert.deepEqual(errors,[]);assert.deepEqual(reportWorldRequests,[]);
} catch(error) {results.push({name:'uncaught',passed:false,error:error.stack});console.error(error);process.exitCode=1;}
finally {
  if(browser)await browser.close();await stop();fs.closeSync(log);
  fs.writeFileSync(path.join(data,'results.json'),JSON.stringify({suite:'mosaic-consent-real-chrome-v1',recordedAtUtc:new Date().toISOString(),browser:browserVersion,passed:!process.exitCode,tests:results,javascriptErrors:errors,reportWorldRequests,actualModelCallsDuringUiTest:0,dataRoot:path.relative(root,data)},null,2)+'\n');
  console.log('Evidence:',path.join(data,'results.json'));
}
