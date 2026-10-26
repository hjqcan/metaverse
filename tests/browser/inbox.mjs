// Real Chrome on an isolated r6 service; traffic perturbations are explicit fault tests.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0008/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const evidence = path.join(root, "docs/iterations/evidence/ITER-0008");
const firstReport = JSON.parse(fs.readFileSync(path.join(evidence, "live-proposer.json"), "utf8"));
const secondReport = JSON.parse(fs.readFileSync(path.join(evidence, "live-reviewer.json"), "utf8"));
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
const entry = (p, id) => p.locator(`#consent-list article[data-command="${id}"]`);
const listPattern=/\/mosaic-proposals\?/;
let oldest, added, focusProposal;
async function send(action,actor='a1') {const r=await command(action,actor);assert.equal(r.status,200,JSON.stringify(r.body));return r.body;}
async function visit(actor='a1'){return (await send({type:'visit',activityId:'garden'},actor)).commandId;}
async function propose(text='程序样本：想在河流端点添一点日黄。') {
 const o=await observed('a2');return (await send({type:'mosaic_propose',activityId:'garden',visitCommandId:await visit('a2'),expectedMosaicRevision:o.mosaic.revision,patch:[{x:1,y:2,color:'sun'}],text},'a2')).result;
}
async function reject(p){return send({type:'mosaic_review',activityId:'garden',visitCommandId:await visit(),proposalActorId:p.authorActorId,proposalCommandId:p.commandId,decision:'reject',text:'程序历史样本保留原图。'});}
async function ready(p=page) {await until(async()=>/每页最多 20 条/.test(await p.locator('#inbox-message').textContent())&&!/正在|未更新|暂停/.test(await p.locator('#inbox-message').textContent()),'inbox not ready');}
async function filter(scope,status,p=page) {
 await p.locator('#inbox-scope').selectOption(scope);await p.locator('#inbox-status').selectOption(status);await ready(p);
 assert.equal(await p.locator('#inbox-scope').inputValue(),scope);assert.equal(await p.locator('#inbox-status').inputValue(),status);
}
async function ids(p=page){return p.locator('#consent-list article').evaluateAll(nodes=>nodes.map(n=>n.dataset.command));}
async function switchActor(actor){await page.locator('#token-input').fill(access.sessions[actor].token);await page.locator('#connect-button').click();await until(async()=>!(await page.locator('#move-down').isDisabled()),'switch not connected');await ready();}
try {
 await start();access=JSON.parse(fs.readFileSync(path.join(data,'access.json'),'utf8'));
 for(let i=0;i<5;i++)await send({type:'move',dx:0,dy:1});
 await send({type:'mosaic',activityId:'garden',visitCommandId:await visit(),expectedMosaicRevision:0,patch:[1,2,3].map(x=>({x,y:2,color:'river'}))});
 for(let i=0;i<4;i++)await send({type:'move',dx:0,dy:1},'a2');
 oldest=await propose('最早未决定的提议：河流端点加一格阳光。');
 for(let i=0;i<51;i++)await reject(await propose(`明确程序历史样本 ${i+1}`));
 for(let i=0;i<5;i++)await send({type:'move',dx:0,dy:-1});
 browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true});browserVersion=browser.version();
 page=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});watch(page);
 await check('default_inbox_finds_oldest_pending_beyond_recent_50_without_world_commands',async()=>{
   const before=await observed();assert.equal(before.mosaicProposals.length,50);assert.ok(!before.mosaicProposals.some(p=>p.commandId===oldest.commandId));
   await connect(page);await ready();assert.deepEqual(await ids(),[oldest.commandId]);
   assert.match(await page.locator('#inbox-counts').textContent(),/等待决定 1.*已处理 51.*合计 52/);
   assert.match(await page.locator('#inbox-location').textContent(),/当前位置.*1, 1.*花园/);assert.equal(await page.locator('#inbox-visit').isDisabled(),true);
   assert.equal((await observed()).stateVersion,before.stateVersion);
 });
 await check('scope_status_cursor_pages_remain_stable_when_new_record_arrives',async()=>{
   await filter('sent','all');assert.deepEqual(await ids(),[]);assert.match(await page.locator('#inbox-counts').textContent(),/合计 0/);
   await filter('received','reviewed');assert.equal((await ids()).length,20);
   await filter('all','all');const first=await ids();assert.equal(first.length,20);
   await page.locator('#inbox-older').click();await ready();const second=await ids();assert.equal(second.length,20);assert.equal(second.some(id=>first.includes(id)),false);
   added=await propose('分页期间新插入的待办。');await version(page,(await observed()).stateVersion);await ready();assert.deepEqual(await ids(),second);
   await page.locator('#inbox-newer').click();await ready();assert.equal((await ids())[0],added.commandId);
   await page.locator('#inbox-older').click();await ready();await page.locator('#inbox-newest').click();await ready();assert.equal((await ids())[0],added.commandId);
 });
 await check('reason_dom_focus_and_selection_survive_poll_and_new_proposal',async()=>{
   await filter('received','pending');const input=entry(page,oldest.commandId).locator('textarea');await input.fill('保留其余河流，只给端点一点日黄。');
   const handle=await input.elementHandle();await input.evaluate(e=>{e.focus();e.setSelectionRange(2,7);});
   focusProposal=await propose('输入理由时出现的新提议。');await version(page,(await observed()).stateVersion);await ready();
   await until(async()=>await entry(page,focusProposal.commandId).count()===1,'new proposal missing');
   assert.equal(await input.evaluate((e,old)=>e===old,handle),true);
   assert.deepEqual(await input.evaluate(e=>({focused:document.activeElement===e,start:e.selectionStart,end:e.selectionEnd,value:e.value})),{focused:true,start:2,end:7,value:'保留其余河流，只给端点一点日黄。'});
 });
 await check('onsite_visit_shortcut_and_failed_reads_preserve_list_and_disable_review',async()=>{
   for(let i=0;i<5;i++)await clickFor(page,'#move-down');await clickFor(page,'#inbox-visit');await ready();
   const accept=entry(page,oldest.commandId).locator('[data-review="accept"]');await until(async()=>!(await accept.isDisabled()),'accept unavailable after visit');
   const before=await ids();const broken=route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'UNAVAILABLE',message:'explicit network fault'}})});
   await page.route(listPattern,broken);await page.locator('#inbox-newest').click();
   await until(async()=>(await page.locator('#inbox-message').textContent()).includes('收件箱未更新'),'error not visible');
   assert.deepEqual(await ids(),before);assert.equal(await accept.isDisabled(),true);assert.match(await page.locator('#inbox-counts').textContent(),/合计 54/);
   await page.unroute(listPattern,broken);await page.locator('#inbox-newest').click();await ready();await until(async()=>!(await accept.isDisabled()),'review did not recover');
 });
 await check('late_filter_response_cannot_replace_current_pending_page',async()=>{
   let release,captured=false;const gate=new Promise(r=>release=r);
   const delayed=async route=>{const q=new URL(route.request().url()).searchParams;if(q.get('status')==='all'&&!captured){captured=true;const response=await route.fetch();await gate;await route.fulfill({response});}else await route.continue();};
   await page.route(listPattern,delayed);await page.locator('#inbox-status').selectOption('all');await until(async()=>captured,'older request not captured');
   await page.locator('#inbox-status').selectOption('pending');await ready();const pendingIds=await ids();release();await delay(400);
   assert.deepEqual(await ids(),pendingIds);assert.equal(await page.locator('#inbox-status').inputValue(),'pending');await page.unroute(listPattern,delayed);
 });
 await check('identity_switch_ignores_late_response_and_isolates_draft_and_filters',async()=>{
   let release,captured=false;const gate=new Promise(r=>release=r);const delayed=async route=>{if(!captured){captured=true;const response=await route.fetch();await gate;await route.fulfill({response});}else await route.continue();};
   await page.route(listPattern,delayed);await page.locator('#inbox-newest').click();await until(async()=>captured,'identity request not captured');
   await switchActor('a2');release();await delay(400);assert.deepEqual(await ids(),[]);assert.equal(await page.locator('#consent-list textarea').count(),0);
   await filter('sent','all');assert.equal((await ids()).length,20);assert.equal(await page.locator('#consent-list [data-review]').count(),0);
   await page.unroute(listPattern,delayed);await switchActor('a1');assert.equal(await page.locator('#inbox-scope').inputValue(),'received');
   assert.equal(await entry(page,oldest.commandId).locator('textarea').inputValue(),'保留其余河流，只给端点一点日黄。');
 });
 await check('original_older_proposal_accepts_once_and_history_exposes_confirmed_result',async()=>{
   const before=await observed();await clickFor(page,`article[data-command="${oldest.commandId}"] [data-review="accept"]`);await ready();
   await until(async()=>await entry(page,oldest.commandId).count()===0,'completed proposal remains pending');
   const after=await observed();assert.equal(after.mosaic.revision,2);assert.equal(after.mosaic.cells.filter((c,i)=>c.color!==before.mosaic.cells[i].color).length,1);
   const d=(await api(`/mosaic-proposals/a2/${oldest.commandId}`)).body.proposal;assert.equal(d.review.decision,'accept');assert.equal(d.review.mosaicEdit.authorActorId,'a1');
   await filter('received','reviewed');while(!(await page.locator('#inbox-older').isDisabled())){await page.locator('#inbox-older').click();await ready();}
   assert.match(await entry(page,oldest.commandId).textContent(),/已同意并改图/);await filter('received','pending');
 });
 await check('legacy_r6_service_uses_recent50_and_explicitly_marks_incomplete_scope',async()=>{
   const legacyPage=await browser.newPage({viewport:{width:1000,height:850}});watch(legacyPage);let requests=0;
   legacyPage.on('request',r=>{if(r.url().includes('/mosaic-proposals'))requests++;});
   await legacyPage.route('**/observation',async route=>{const response=await route.fetch();const body=await response.json();delete body.mosaicProposalInbox;await route.fulfill({response,json:body});});
   await connect(legacyPage);await until(async()=>/可能遗漏更早待办/.test(await legacyPage.locator('#inbox-message').textContent()),'legacy warning missing');
   assert.match(await legacyPage.locator('#inbox-counts').textContent(),/非完整待办/);await delay(1800);assert.equal(requests,0);await legacyPage.close();
 });
 await check('lost_reject_response_and_reload_recover_original_command_without_resubmit',async()=>{
   const input=entry(page,added.commandId).locator('textarea');await input.fill('图已变化，拒绝这份旧提议。');const before=await observed();let posts=0,hold=true,original;
   const handler=async route=>{if(route.request().method()==='POST'){posts++;original=route.request().postDataJSON();const r=await route.fetch();assert.equal(r.status(),200);await route.abort('failed');}else if(hold)await route.abort('failed');else await route.continue();};
   await page.route(/\/commands(?:\/[^/?]+)?$/,handler);await entry(page,added.commandId).locator('[data-review="reject"]').click();
   await until(async()=>posts===1&&!(await page.locator('#pending-panel').isHidden()),'reject not pending');await page.reload();await until(async()=>!(await page.locator('#pending-panel').isHidden()),'pending lost after reload');hold=false;
   await until(async()=>!(await page.locator('#query-command-button').isDisabled()),'query disabled');await page.locator('#query-command-button').click();await until(async()=>await page.locator('#pending-panel').isHidden(),'recovery failed');
   await page.unroute(/\/commands(?:\/[^/?]+)?$/,handler);await ready();assert.equal(posts,1);assert.deepEqual((await observed()).mosaic,before.mosaic);
   const p=(await api(`/mosaic-proposals/a2/${added.commandId}`)).body.proposal;assert.equal(p.review.commandId,original.commandId);assert.equal(p.review.decision,'reject');
 });
 await check('restart_preserves_inbox_counts_and_original_details',async()=>{
   const before=await api('/mosaic-proposals');const detail=await api(`/mosaic-proposals/a2/${oldest.commandId}`);await stop();await start();assert.deepEqual(await api('/mosaic-proposals'),before);assert.deepEqual(await api(`/mosaic-proposals/a2/${oldest.commandId}`),detail);
   await version(page,(await observed()).stateVersion);await ready();await page.screenshot({path:path.join(data,'world-desktop.png'),fullPage:true});
 });
 await check('mobile_inbox_and_history_controls_fit_390px',async()=>{
   const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});const p=await context.newPage();watch(p);await connect(p);await ready(p);
   const d=await p.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(d.scroll<=d.width+1);assert.match(await p.locator('#inbox-counts').textContent(),/等待决定 1/);
   await p.screenshot({path:path.join(data,'world-mobile.png'),fullPage:true});await context.close();
 });
 await check('actual_report_verifies_original_older_proposal_without_recent_list_membership',async()=>{
   assert.equal(secondReport.world.mosaicProposals.some(p=>p.commandId===secondReport.decision.mosaicProposal.commandId),false);
   reportPage=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});watch(reportPage,true);await reportPage.goto(url+'/resident.html?sample=inbox');
   await until(async()=>(await reportPage.locator('#mission-id').textContent())===firstReport.mission.id,'inbox proposer report missing');assert.equal(await reportPage.locator('#report-status').textContent(),'已完成');
   await reportPage.locator('#inbox-report-links a[href*="inbox-review"]').click();await until(async()=>(await reportPage.locator('#mission-id').textContent())===secondReport.mission.id,'inbox review report missing');
   assert.equal(await reportPage.locator('#report-status').textContent(),'已完成');assert.equal(await reportPage.locator('#consent-report-fact').getAttribute('data-verified'),'true');
   await reportPage.screenshot({path:path.join(data,'report-desktop.png'),fullPage:true});await importReport(reportPage,legacy,'legacy.json');assert.equal(await reportPage.locator('#report-status').textContent(),'已完成');
 });
 await check('mobile_actual_inbox_review_report_fits_390px',async()=>{
   const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});const p=await context.newPage();watch(p,true);await p.goto(url+'/resident.html?sample=inbox-review');
   await until(async()=>(await p.locator('#report-status').textContent())==='已完成','mobile report missing');const d=await p.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(d.scroll<=d.width+1);
   await p.screenshot({path:path.join(data,'report-mobile.png'),fullPage:true});await context.close();
 });
 assert.deepEqual(errors,[]);assert.deepEqual(reportWorldRequests,[]);
} catch(error) {results.push({name:'uncaught',passed:false,error:error.stack});console.error(error);process.exitCode=1;}
finally {
 if(browser)await browser.close();await stop();fs.closeSync(log);
 fs.writeFileSync(path.join(data,'results.json'),JSON.stringify({suite:'mosaic-inbox-real-chrome-v1',recordedAtUtc:new Date().toISOString(),browser:browserVersion,passed:!process.exitCode,tests:results,javascriptErrors:errors,reportWorldRequests,actualModelCallsDuringUiTest:0,fixtureSource:'explicit-program-normal-HTTP',dataRoot:path.relative(root,data)},null,2)+'\n');console.log('Evidence:',path.join(data,'results.json'));
}
