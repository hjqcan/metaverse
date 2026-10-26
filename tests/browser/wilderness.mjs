// Real Chrome on an isolated wilderness service; traffic perturbations are explicit fault tests.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0010/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
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
    cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_SCENARIO: "wilderness-v1", WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", log, log],
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
  const o = await observed(actor); return api("/commands", "POST", { schemaVersion: 1, rulesVersion: "r7", commandId: crypto.randomUUID(), expectedStateVersion: o.stateVersion, action }, actor);
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
async function clickFor(p, id, actor = "a1", status = 200) {
  await until(async () => !(await p.locator(id).isDisabled()), `${id} disabled for ${actor}`);
  const wait = p.waitForResponse(r => r.url() === url + prefix + "/commands" && r.request().method() === "POST");
  await p.locator(id).click(); const response = await wait;
  assert.equal(response.status(), status, await response.text()); await version(p, (await observed(actor)).stateVersion);
}
async function send(action,actor='a1'){const r=await command(action,actor);assert.equal(r.status,200,JSON.stringify(r.body));return r.body;}
async function sync(p,actor='a1'){
 const o=await observed(actor);await version(p,o.stateVersion);
 await until(async()=>await p.locator('#entry-panel').getAttribute('data-version')===String(o.stateVersion)&&!(await p.locator('[data-entry-select="garden"]').isDisabled()),'guide not synchronized');
 return o;
}
async function walkApi(target,actor='a1'){
 for(let count=0;count<64;count++){
  const o=await observed(actor),origin=o.self.position;if(JSON.stringify(origin)===JSON.stringify(target))return;
  const key=p=>p.join(','),blocked=new Set(o.world.blocked.map(key)),queue=[[origin,[]]],seen=new Set([key(origin)]);let route;
  while(queue.length){const [cell,path]=queue.shift();if(key(cell)===key(target)){route=path;break;}for(const [dx,dy] of [[1,0],[0,1],[-1,0],[0,-1]]){const n=[cell[0]+dx,cell[1]+dy];if(n.some(v=>v<0||v>=8)||blocked.has(key(n))||seen.has(key(n)))continue;seen.add(key(n));queue.push([n,[...path,n]]);}}
  assert.ok(route?.length);await send({type:'move',dx:route[0][0]-origin[0],dy:route[0][1]-origin[1]},actor);
 }
 throw new Error('walk did not finish');
}
async function choose(p,node){await until(async()=>!(await p.locator('#gather-node').isDisabled()),'tree choices unavailable');await p.locator('#gather-node').selectOption(node);}
const nodeAt=(o,id)=>o.resourceNodes.find(n=>n.nodeId===id);
const WEST='tree-west-north', EAST='tree-east-south';
try {
 await start();access=JSON.parse(fs.readFileSync(path.join(data,'access.json'),'utf8'));
 browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true});browserVersion=browser.version();
 page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});watch(page);
 await check('empty_hands_scattered_residents_trees_and_no_depot_or_ready_made_creative_services',async()=>{
  await connect(page);const o=await sync(page);assert.deepEqual(o.residents.map(r=>r.position),[[1,1],[6,6]]);assert.equal(await page.locator('#inventory-wood').textContent(),'0');
  assert.equal(await page.locator('#claim-section').isHidden(),true);assert.equal(await page.locator('#depot-legend').isHidden(),true);assert.equal(await page.locator('#mosaic-panel').isHidden(),true);assert.equal(await page.locator('#postcards-panel').isHidden(),true);
  assert.equal(await page.locator('#gather-panel').isVisible(),true);assert.match(await page.locator('#entry-materials').textContent(),/没有现成的公共储备.*砍取/);assert.match(await page.locator('#world-summary').textContent(),/野生树木.*居民：a1 \(1, 1\)；a2 \(6, 6\)/);
  assert.match(await page.locator('#event-list').textContent(),/木材仍在树上/);await page.screenshot({path:path.join(data,'wilderness-initial-desktop.png'),fullPage:true});await page.locator('#world-canvas').screenshot({path:path.join(data,'initial-map.png')});
 });
 await check('selecting_tree_does_not_harvest_and_distance_gates_cutting',async()=>{
  const before=await observed();await choose(page,EAST);assert.equal(await page.locator('#gather-button').isDisabled(),true);assert.match(await page.locator('#gather-hint').textContent(),/先走到树旁/);
  await choose(page,WEST);assert.equal(await page.locator('#gather-button').isDisabled(),false);assert.equal((await observed()).stateVersion,before.stateVersion);
 });
 await check('real_cut_reduces_tree_and_credits_only_current_resident',async()=>{
  await clickFor(page,'#gather-button');const o=await sync(page);assert.equal(nodeAt(o,WEST).remainingWood,2);assert.equal(o.self.inventory.wood,1);assert.equal((await observed('a2')).self.inventory.wood,0);
  assert.equal(await page.locator('#inventory-wood').textContent(),'1');assert.match(await page.locator('#event-list').textContent(),/砍取了 1 单位木材/);assert.match(await page.locator('#gather-hint').textContent(),/还可采 2/);
 });
 await check('version_conflict_does_not_double_credit_and_new_cut_uses_new_command',async()=>{
  let intercepted=false;const stale=async route=>{const request=route.request();if(request.method()==='POST'&&JSON.parse(request.postData()).action.type==='gather'&&!intercepted){intercepted=true;await send({type:'move',dx:0,dy:-1},'a2');}await route.continue();};
  await page.route('**/commands',stale);await clickFor(page,'#gather-button','a1',409);await page.unroute('**/commands',stale);await sync(page);assert.equal((await observed()).self.inventory.wood,1);assert.match(await page.locator('#feedback').textContent(),/STALE_STATE/);
  await clickFor(page,'#gather-button');await clickFor(page,'#gather-button');await sync(page);assert.equal((await observed()).self.inventory.wood,3);assert.equal(nodeAt(await observed(),WEST).remainingWood,0);
  assert.equal(await page.locator('#gather-button').isDisabled(),true);assert.match(await page.locator('#gather-hint').textContent(),/已采空/);
 });
 await check('collected_wood_builds_real_platform_on_cleared_tree_ground',async()=>{
  await page.locator('#recipe-select').selectOption('platform.v1');await clickFor(page,'#build-button');const o=await sync(page);assert.equal(o.self.inventory.wood,0);assert.equal(o.entities.length,1);assert.deepEqual(o.entities[0].position,[0,1]);assert.equal(o.entities[0].embodiedWood,3);
  await page.screenshot({path:path.join(data,'gathered-and-built-desktop.png'),fullPage:true});await page.locator('#gather-panel').screenshot({path:path.join(data,'gather-panel-desktop.png')});
 });
 await check('other_scattered_identity_starts_empty_and_sees_previous_work',async()=>{
  await page.locator('#token-input').fill(access.sessions.a2.token);await page.locator('#connect-button').click();await sync(page,'a2');assert.equal(await page.locator('#inventory-wood').textContent(),'0');assert.equal((await observed('a2')).entities.length,1);
  await clickFor(page,'#move-down','a2');await choose(page,EAST);assert.equal(await page.locator('#gather-button').isDisabled(),false);assert.equal(await page.locator('#entry-panel').getAttribute('data-actor'),'a2');
 });
 await check('lost_committed_cut_response_reload_recovers_original_id_once',async()=>{
  let cut;let posts=0;const lost=async route=>{const req=JSON.parse(route.request().postData());if(req.action.type==='gather'){posts++;cut=req;await route.fetch();await route.abort('failed');}else await route.continue();};const block=async route=>route.abort('failed');
  await page.route('**/commands/*',block);await page.route('**/commands',lost);await page.locator('#gather-button').click();await until(async()=>Boolean(cut)&&(await page.locator('#pending-panel').isVisible()),'original cut not retained');
  await until(async()=>(await observed('a2')).self.inventory.wood===1,'cut did not commit');assert.equal(posts,1);await page.unroute('**/commands',lost);await page.unroute('**/commands/*',block);await page.reload();
  await until(async()=>await page.locator('#pending-panel').isHidden()&&!(await page.locator('#move-down').isDisabled()),'reload did not recover cut');await sync(page,'a2');assert.equal((await observed('a2')).self.inventory.wood,1);
  const receipt=await api('/commands/'+cut.commandId,'GET',undefined,'a2');assert.equal(receipt.status,200);assert.equal(receipt.body.result.nodeId,EAST);assert.equal(nodeAt(await observed('a2'),EAST).remainingWood,2);
 });
 await check('mismatched_cut_receipt_stays_unresolved_until_original_receipt_is_queried',async()=>{
  await choose(page,EAST);let cut;const corrupt=async route=>{const req=JSON.parse(route.request().postData());if(req.action.type==='gather'){cut=req;const response=await route.fetch(),body=await response.json();body.result.nodeId=WEST;await route.fulfill({response,json:body});}else await route.continue();};const block=async route=>route.abort('failed');
  await page.route('**/commands/*',block);await page.route('**/commands',corrupt);await page.locator('#gather-button').click();await until(async()=>Boolean(cut)&&(await page.locator('#pending-panel').isVisible()),'false cut receipt accepted');
  await until(async()=>(await page.locator('#feedback').textContent()).includes('原命令已保留')&&(await observed('a2')).self.inventory.wood===2,'corrupt receipt not processed');assert.equal(await page.locator('#pending-panel').isVisible(),true);await page.unroute('**/commands',corrupt);await page.unroute('**/commands/*',block);await page.locator('#query-command-button').click();await until(async()=>await page.locator('#pending-panel').isHidden(),'original cut query did not resolve');await sync(page,'a2');assert.equal(nodeAt(await observed('a2'),EAST).remainingWood,1);
 });
 await check('observation_failure_keeps_known_materials_and_pauses_cutting',async()=>{
  await choose(page,EAST);const before=await page.locator('#inventory-wood').textContent();const fail=async route=>route.abort('failed');await page.route('**/observation',fail);
  await until(async()=>await page.locator('#gather-button').isDisabled(),'cut not paused');assert.equal(await page.locator('#inventory-wood').textContent(),before);assert.match(await page.locator('#entry-state').textContent(),/上次观察/);
  await page.unroute('**/observation',fail);await sync(page,'a2');
 });
 await check('restart_preserves_tree_stumps_materials_and_resident_positions',async()=>{
  const before=await observed('a2');await stop();await start();assert.deepEqual(await observed('a2'),before);await sync(page,'a2');
 });
 await check('mobile_390px_tree_selection_cut_and_material_labels_are_usable',async()=>{
  const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});const p=await context.newPage();watch(p);await connect(p,'a2');await sync(p,'a2');await choose(p,EAST);await clickFor(p,'#gather-button','a2');await sync(p,'a2');assert.equal(await p.locator('#inventory-wood').textContent(),'3');assert.equal(await p.locator('#gather-button').isDisabled(),true);
  const dims=await p.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(dims.scroll<=dims.width+1);await p.screenshot({path:path.join(data,'wilderness-mobile.png'),fullPage:true});await p.locator('#gather-panel').screenshot({path:path.join(data,'gather-panel-mobile.png')});await context.close();
 });
 assert.deepEqual(errors,[]);
} catch(error){results.push({name:'uncaught',passed:false,error:error.stack});console.error(error);process.exitCode=1;}
finally{if(browser)await browser.close();await stop();fs.closeSync(log);fs.writeFileSync(path.join(data,'results.json'),JSON.stringify({suite:'wilderness-real-chrome-v1',recordedAtUtc:new Date().toISOString(),browser:browserVersion,passed:!process.exitCode,tests:results,javascriptErrors:errors,actualModelCalls:0,decisionSource:'explicit-program-and-human-UI',dataRoot:path.relative(root,data)},null,2)+'\n');console.log('Evidence:',path.join(data,'results.json'));}
