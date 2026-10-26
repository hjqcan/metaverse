// Actual fixed-reference CLI report, isolated HTTP/SQLite, real Chrome. No models.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0015/browser", new Date().toISOString().replace(/[:.]/g, "-"));
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
  const run = spawnSync("python3", ["tests/continuous_mission_api.py", "test_08_fixed_reference_cli_exports_fractional_report"], { cwd: root, encoding: "utf8", timeout: 90000 });
  fs.writeFileSync(path.join(data, "mission.log"), run.stdout + run.stderr);
  assert.equal(run.status, 0, run.stderr);
  const summaryPath = run.stdout.trim().split("\n").findLast(line => line.startsWith("Evidence: ")).slice(10);
  const report = JSON.parse(fs.readFileSync(path.join(path.dirname(summaryPath), "test_08_fixed_reference_cli_exports_fractional_report/cli-report.json"), "utf8"));
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
  await check("actual_continuous_cli_report_and_meter_coordinates", async () => {
    await imported(report, "actual-walk.json");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.match(await page.locator("#map-summary").textContent(), /32 × 24 米 · 连续自然地形/);
    assert.match(await page.locator("#goal-route").textContent(), /8.25, 7.35/);
    assert.equal(await page.locator("#report-warning").isVisible(), false);
    assert.equal(await page.locator(".step-button").filter({ hasText: "行走" }).count(), report.steps.length);
    assert.match(await page.locator("#model-budget-note").textContent(), /外部模型 0 次/);
    await page.screenshot({ path: path.join(data, "desktop.png"), fullPage: true });
    await page.locator("#replay-canvas").screenshot({ path: path.join(data, "natural-map.png") });
  });
  await check("fractional_replay_uses_confirmed_position_and_natural_geometry", async () => {
    await page.locator(".step-button").first().click();
    assert.match(await page.locator("#replay-description").textContent(), /行走.*记录位置 \(5.6, 7\)/);
    const terrain = await page.locator("#replay-canvas").evaluate(canvas => {
      const ctx = canvas.getContext("2d"), sample = (x,z) => [...ctx.getImageData(Math.floor(34+x*652/32),Math.floor(34+(652-24*652/32)/2+z*652/32),1,1).data];
      return [sample(16,2), sample(2,2), sample(3,3)];
    });
    assert.deepEqual(terrain[0].slice(0,3), [175,208,210]);
    assert.deepEqual(terrain[1],terrain[2]);
  });
  await check("unknown_walk_does_not_turn_target_into_confirmed_position", async () => {
    const unknown = structuredClone(report);
    unknown.mission.status="unknown"; unknown.mission.reason="pending_command_retained";
    unknown.facts.goalReached=false; unknown.facts.returned=true;
    unknown.steps=[unknown.steps[0]]; unknown.steps[0].status="unknown"; unknown.steps[0].position=[5,7];
    await imported(unknown,"unknown-walk.json");
    assert.match(await page.locator("#replay-description").textContent(), /记录位置 \(5, 7\).*动作结果未确认/);
    assert.equal(await page.locator("#report-status").textContent(),"结果未知");
  });
  await check("completion_requires_actual_arrival_and_return_trace", async () => {
    const invalid=structuredClone(report); invalid.steps=invalid.steps.slice(0,1);
    await imported(invalid,"false-completion.json");
    assert.equal(await page.locator("#report-status").textContent(),"完成标记待复核");
    assert.match(await page.locator("#report-warning").textContent(),/连续行走记录未支持/);
  });
  await check("invalid_continuous_geometry_retains_previous_report", async () => {
    const invalid=structuredClone(report); invalid.world.terrain.river.polygon[0]=[100,2];
    await page.locator("#report-file").setInputFiles({name:"invalid-river.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(invalid))});
    await until(async()=> (await page.locator("#load-message").textContent()).includes("导入失败"),"invalid river not rejected");
    assert.match(await page.locator("#load-message").textContent(),/连续河道几何不正确/);
    assert.equal(await page.locator("#report-status").textContent(),"完成标记待复核");
  });
  await check("actual_bridge_report_has_r8_gather_facts_and_full_footprint", async () => {
    const built=JSON.parse(fs.readFileSync(path.join(root,"docs/iterations/evidence/ITER-0015/test-double-builder.json"),"utf8"));
    await imported(built,"actual-r8-bridge.json");
    assert.equal(await page.locator("#report-status").textContent(),"已完成");
    assert.match(await page.locator("#created-summary").textContent(),/采集 6 · 领取 0 单位木材 \/ 1 个设施/);
    assert.match(await page.locator("#report-warning").textContent(),/测试替身/);
    const position=built.world.entities[0].position;
    const color=await page.locator("#replay-canvas").evaluate((canvas,p)=>[...canvas.getContext("2d").getImageData(Math.floor(34+(p[0]+1.1)*652/32),Math.floor(34+(652-24*652/32)/2+(p[1]+.4)*652/32),1,1).data],position);
    assert.deepEqual(color.slice(0,3),[189,153,102]);
    await page.locator("#replay-canvas").screenshot({path:path.join(data,"bridge-map.png")});
  });
  await check("390px_continuous_map_readonly_without_overflow", async () => {
    await page.setViewportSize({width:390,height:844});
    await imported(report,"mobile-walk.json");
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
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ suite: "continuous-resident-chrome", passed: results.length === 7 && results.every(r => r.passed),
    recordedAtUtc: new Date().toISOString(), actualModelCalls: 0, browser: browserVersion,
    javascriptErrors: errors, worldRequests, port, serviceStopped: !service || service.exitCode !== null, tests: results }, null, 2) + "\n");
  console.log("Browser evidence:", data);
}
