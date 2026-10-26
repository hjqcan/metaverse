// Real Chrome on an isolated r6 service; traffic perturbations are explicit fault tests.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0009/browser", new Date().toISOString().replace(/[:.]/g, "-"));
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
let newcomer;
try {
 await start();access=JSON.parse(fs.readFileSync(path.join(data,'access.json'),'utf8'));
 browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true});browserVersion=browser.version();
 page=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});watch(page);
 await check('arrival_shows_actual_routes_and_selection_does_not_act',async()=>{
  await connect(page);const before=await sync(page);assert.equal(await page.locator('#entry-panel').isHidden(),false);
  assert.match(await page.locator('#entry-bridges').textContent(),/没有已建桥段/);assert.equal(await page.locator('#entry-places [data-reachable="true"]').count(),2);assert.equal(await page.locator('#entry-places [data-place="lookout"]').getAttribute('data-reachable'),'false');
  await page.locator('[data-entry-select="riverwalk"]').click();assert.equal(await page.locator('#activity-select').inputValue(),'riverwalk');await page.keyboard.press('ArrowDown');await delay(300);assert.equal((await observed()).stateVersion,before.stateVersion);
  await page.locator('[data-place="riverwalk"] summary').click();assert.match(await page.locator('[data-place="riverwalk"] .entry-route').textContent(),/\(1, 1\).*\(2, 5\)/);
 });
 await check('one_built_bridge_stays_blocked_then_complete_route_becomes_available',async()=>{
  await send({type:'claim',quantity:6});await walkApi([3,3]);await send({type:'build',recipeId:'bridge.v1',at:[4,3]});await sync(page);
  assert.match(await page.locator('#entry-bridges').textContent(),/已有 1 段公共桥/);assert.equal(await page.locator('[data-place="lookout"]').getAttribute('data-reachable'),'false');
  await send({type:'move',dx:1,dy:0});await send({type:'build',recipeId:'bridge.v1',at:[5,3]});await sync(page);assert.equal(await page.locator('[data-place="lookout"]').getAttribute('data-reachable'),'true');
  assert.match(await page.locator('#entry-bridges').textContent(),/居民 a1 建于.*不要求你重建/);
 });
 await check('newcomer_first_connection_uses_existing_bridges_and_returns_without_work',async()=>{
  newcomer=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1});watch(newcomer);await connect(newcomer,'a2');const before=await sync(newcomer,'a2');const guide=before.entryGuide,p=guide.places.find(p=>p.id==='lookout');assert.equal(p.bridgeEntityIds.length,2);
  await newcomer.locator('[data-entry-select="lookout"]').click();assert.equal(await newcomer.locator('#activity-select').inputValue(),'lookout');
  const go=async(target)=>{const o=await observed('a2'),dx=target[0]-o.self.position[0],dy=target[1]-o.self.position[1];const direction=dx===1?'right':dx===-1?'left':dy===1?'down':'up';await clickFor(newcomer,'#move-'+direction,'a2');};
  for(const step of p.route)await go(step);await clickFor(newcomer,'#visit-button','a2');await sync(newcomer,'a2');assert.match(await newcomer.locator('[data-place="lookout"]').textContent(),/你已在这里/);
  for(const step of [guide.position,...p.route].slice(0,-1).reverse())await go(step);const after=await sync(newcomer,'a2');assert.deepEqual(after.self.position,guide.position);assert.deepEqual(after.entities,before.entities);assert.deepEqual(after.resourceAudit,before.resourceAudit);assert.equal(after.self.inventory.wood,0);
 });
 await check('exhausted_public_stock_is_honest_about_building_and_free_creative_options',async()=>{
  await walkApi([1,1]);await send({type:'claim',quantity:6});await sync(newcomer,'a2');assert.match(await newcomer.locator('#entry-materials').textContent(),/公共木材 0.*自己库存 0.*储备已空/);
  assert.match(await newcomer.locator('#entry-participation').textContent(),/公开手记，不需木材.*他人格子需要对方同意/);await newcomer.screenshot({path:path.join(data,'entry-desktop.png'),fullPage:true});await newcomer.locator('#entry-panel').screenshot({path:path.join(data,'entry-panel-desktop.png')});
 });
 await check('failed_observation_marks_old_guide_and_disables_selection_until_recovery',async()=>{
  const old=await newcomer.locator('#entry-places').textContent();const failure=route=>route.abort('failed');await newcomer.route('**/observation',failure);
  await until(async()=>(await newcomer.locator('#entry-state').textContent()).includes('上次观察'),'stale guide unmarked');assert.equal(await newcomer.locator('[data-entry-select="garden"]').isDisabled(),true);assert.equal(await newcomer.locator('#entry-places').textContent(),old);
  await newcomer.unroute('**/observation',failure);await sync(newcomer,'a2');
 });
 await check('identity_switch_refreshes_own_materials_and_disconnect_clears_guide',async()=>{
  await newcomer.locator('#token-input').fill(access.sessions.a1.token);await newcomer.locator('#connect-button').click();await sync(newcomer);assert.match(await newcomer.locator('#entry-materials').textContent(),/自己库存 6/);assert.equal(await newcomer.locator('#entry-panel').getAttribute('data-actor'),'a1');
  await newcomer.locator('#disconnect-button').click();assert.equal(await newcomer.locator('#entry-panel').isHidden(),true);assert.equal(await newcomer.locator('#entry-materials').textContent(),'');await connect(newcomer,'a2');await sync(newcomer,'a2');
 });
 await check('malformed_route_is_not_shown_as_confirmed_access',async()=>{
  const corrupt=async route=>{const response=await route.fetch(),body=await response.json();body.entryGuide.places[0].route=[[3,0]];await route.fulfill({response,json:body});};
  await newcomer.route('**/observation',corrupt);await until(async()=>(await newcomer.locator('#entry-state').textContent()).includes('导览尚未确认'),'invalid guide accepted');assert.equal(await newcomer.locator('#entry-places article').count(),0);
  await newcomer.unroute('**/observation',corrupt);await sync(newcomer,'a2');
 });
 await check('legacy_service_without_guide_preserves_existing_interface',async()=>{
  const old=await browser.newPage();watch(old);await old.route('**/observation',async route=>{const response=await route.fetch(),body=await response.json();delete body.entryGuide;await route.fulfill({response,json:body});});await connect(old);assert.equal(await old.locator('#entry-panel').isHidden(),true);assert.equal(await old.locator('#activities-panel').isHidden(),false);await old.close();
 });
 await check('restart_keeps_same_guide_and_world_state',async()=>{
  const before=await observed('a2');await stop();await start();assert.deepEqual(await observed('a2'),before);await sync(newcomer,'a2');
 });
 await check('mobile_arrival_390px_routes_and_access_controls_are_readable',async()=>{
  const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});const p=await context.newPage();watch(p);await connect(p,'a2');await sync(p,'a2');await p.locator('[data-place="lookout"] summary').click();
  const dims=await p.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(dims.scroll<=dims.width+1);await p.screenshot({path:path.join(data,'entry-mobile.png'),fullPage:true});await p.locator('#entry-panel').screenshot({path:path.join(data,'entry-panel-mobile.png')});await context.close();
 });
 assert.deepEqual(errors,[]);
} catch(error){results.push({name:'uncaught',passed:false,error:error.stack});console.error(error);process.exitCode=1;}
finally{if(browser)await browser.close();await stop();fs.closeSync(log);fs.writeFileSync(path.join(data,'results.json'),JSON.stringify({suite:'entry-guide-real-chrome-v1',recordedAtUtc:new Date().toISOString(),browser:browserVersion,passed:!process.exitCode,tests:results,javascriptErrors:errors,actualModelCalls:0,decisionSource:'explicit-program-and-human-UI',dataRoot:path.relative(root,data)},null,2)+'\n');console.log('Evidence:',path.join(data,'results.json'));}
