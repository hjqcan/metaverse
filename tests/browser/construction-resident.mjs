// Actual fixed-reference CLI report, isolated HTTP/SQLite, real Chrome. No models.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0017/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const results = [], errors = [], worldRequests = [];
let browser, page, service, browserVersion, port;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate, message, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await predicate()) return; await delay(40); }
  throw new Error(message);
}
async function check(name, action) {
  await action(); results.push({ name, passed: true }); console.log("PASS", name);
}
async function imported(report, name) {
  await page.locator("#report-file").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) });
  await until(async () => (await page.locator("#load-message").textContent()).includes(name), "report import did not settle");
}
const log = fs.openSync(path.join(data, "server.log"), "w");
try {
  const run = spawnSync("python3", ["tests/construction_mission_api.py", "test_11_fixed_reference_cli_exports_construction_facts"], { cwd: root, encoding: "utf8", timeout: 90000 });
  fs.writeFileSync(path.join(data, "mission.log"), run.stdout + run.stderr);
  assert.equal(run.status, 0, run.stderr);
  const summaryPath = run.stdout.trim().split("\n").findLast(line => line.startsWith("Evidence: ")).slice(10);
  const report = JSON.parse(fs.readFileSync(path.join(path.dirname(summaryPath), "test_11_fixed_reference_cli_exports_construction_facts/cli-report.json"), "utf8"));
  fs.writeFileSync(path.join(data, "actual-report.json"), JSON.stringify(report, null, 2));
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
  port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  service = spawn("dotnet", [path.join(root, "src/World.Server/bin/Debug/net10.0/World.Server.dll")], {
    cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_SCENARIO: "wilderness-v1", WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", log, log],
  });
  await until(async () => {
    if (service.exitCode !== null) throw new Error(`service exited ${service.exitCode}`);
    try { return (await fetch(url + "/healthz")).ok; } catch { return false; }
  }, "static host unavailable");
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  browserVersion = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (new URL(request.url()).pathname.startsWith("/v1/")) worldRequests.push(request.method()); });
  await page.goto(url + "/resident.html");
  await until(async () => (await page.locator("#load-message").textContent()).includes("已加载"), "default report absent");
  await check("actual_cli_construction_requires_command_entity_and_material", async () => {
    await imported(report, "actual-platform.json");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "true");
    assert.match(await page.locator("#construction-fact").textContent(), /平台.*8.2, 10.4.*消耗 3 木材/);
    assert.match(await page.locator("#goal-route").textContent(), /建造平台/);
    assert.match(await page.locator("#model-budget-note").textContent(), /外部模型 0 次/);
    assert.equal(await page.locator("#report-warning").isVisible(), false);
    await page.screenshot({path:path.join(data,"desktop.png"),fullPage:true});
  });
  await check("arrival_and_existing_entity_cannot_substitute_for_this_build", async () => {
    const invalid=structuredClone(report); invalid.facts.constructionBuilt=false; invalid.facts.construction=null;
    await imported(invalid,"arrival-with-existing-platform.json");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"),"false");
    assert.match(await page.locator("#construction-fact").textContent(),/已有设施不能代替/);
    assert.equal(await page.locator("#report-status").textContent(),"完成标记待复核");
  });
  await check("unknown_build_retains_unconfirmed_fact", async () => {
    const unknown=structuredClone(report); unknown.mission.status="unknown"; unknown.mission.reason="unconfirmed_construction_receipt";
    unknown.facts.constructionBuilt=false; unknown.facts.construction=null; unknown.budget.used.wood=0;
    const index=unknown.steps.findIndex(s=>s.action.type==="build"); unknown.steps=unknown.steps.slice(0,index+1);
    unknown.steps.at(-1).status="unknown"; unknown.facts.goalReached=false; unknown.facts.returned=false;
    if ("execution" in unknown.steps.at(-1)) unknown.steps.at(-1).execution=null;
    await imported(unknown,"unknown-build.json");
    assert.equal(await page.locator("#report-status").textContent(),"结果未知");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"),"false");
  });
  await check("mismatched_identity_permission_material_and_step_are_not_completed", async () => {
    for (const [name,change] of [
      ["owner",r=>r.facts.construction.ownerActorId="a2"],
      ["permission",r=>r.mission.allowBuild=false],
      ["material",r=>r.budget.used.wood=0],
      ["entity",r=>r.world.entities=[]],
      ["command",r=>r.facts.construction.commandId="foreign-build"],
      ["step",r=>delete r.steps.find(s=>s.action.type==="build").action.at],
      ["version",r=>r.world.entities[0].definitionVersion=2],
    ]) {
      const invalid=structuredClone(report); change(invalid); await imported(invalid,name+"-mismatch.json");
      assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"),"false",name);
      assert.equal(await page.locator("#report-status").textContent(),"完成标记待复核",name);
    }
  });
  await check("malformed_construction_retains_previous_report", async () => {
    await imported(report,"valid-platform.json");
    const invalid=structuredClone(report); invalid.facts.construction.position=null;
    await page.locator("#report-file").setInputFiles({name:"invalid-construction.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(invalid))});
    await until(async()=> (await page.locator("#load-message").textContent()).includes("导入失败"),"malformed fact accepted");
    assert.match(await page.locator("#load-message").textContent(),/设施建造记录不完整/);
    assert.equal(await page.locator("#report-status").textContent(),"已完成");
  });
  await check("construction_requires_visit_after_original_build", async () => {
    const early=structuredClone(report), index=early.steps.findIndex(s=>s.action.type==="build");
    early.steps[index-1].position=early.mission.goal.target;
    early.steps=early.steps.filter((s,i)=>i<=index || i===early.steps.length-1);
    await imported(early,"visit-before-construction.json");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"),"true");
    assert.equal(await page.locator("#report-status").textContent(),"完成标记待复核");
    assert.match(await page.locator("#report-warning").textContent(),/建设完成后的记录未支持到达设施中心/);
  });
  await check("legacy_bridge_report_does_not_acquire_a_construction_goal", async () => {
    const legacy=JSON.parse(fs.readFileSync(path.join(root,"docs/iterations/evidence/ITER-0015/test-double-builder.json"),"utf8"));
    await imported(legacy,"legacy-bridge.json");
    assert.equal(await page.locator("#report-status").textContent(),"已完成");
    assert.equal(await page.locator("#construction-fact").isVisible(),false);
  });
  await check("390px_construction_report_is_readonly_without_overflow", async () => {
    await page.setViewportSize({width:390,height:844}); await imported(report,"mobile-platform.json");
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),true);
    await page.screenshot({path:path.join(data,"mobile.png"),fullPage:true});
    assert.deepEqual(errors,[]); assert.deepEqual(worldRequests,[]);
  });
} catch (error) {
  results.push({ name: "failure", passed: false, message: error.stack });
  if (page) await page.screenshot({ path: path.join(data, "failure.png"), fullPage: true }).catch(() => {});
  console.error(error.stack); process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  if (service && service.exitCode === null) {
    service.kill("SIGTERM");
    await until(async () => service.exitCode !== null, "dedicated service did not stop", 6000);
  }
  fs.closeSync(log);
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ suite: "construction-resident-chrome", passed: results.length === 8 && results.every(r => r.passed),
    recordedAtUtc: new Date().toISOString(), actualModelCalls: 0, browser: browserVersion,
    javascriptErrors: errors, worldRequests, port, serviceStopped: !service || service.exitCode !== null, tests: results }, null, 2) + "\n");
  console.log("Browser evidence:", data);
}
