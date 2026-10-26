// Actual fixed-reference CLI report, isolated HTTP/SQLite, real Chrome. No models.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0013/browser", new Date().toISOString().replace(/[:.]/g, "-"));
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
  const run = spawnSync("python3", ["tests/wilderness_mission_api.py", "test_13_fixed_reference_cli_exports_actual_gather_report_without_models"], { cwd: root, encoding: "utf8", timeout: 40000 });
  fs.writeFileSync(path.join(data, "mission.log"), run.stdout + run.stderr);
  assert.equal(run.status, 0, run.stderr);
  const summaryPath = run.stdout.trim().split("\n").findLast(line => line.startsWith("Evidence: ")).slice(10);
  const report = JSON.parse(fs.readFileSync(path.join(path.dirname(summaryPath), "test_13_fixed_reference_cli_exports_actual_gather_report_without_models/cli-report.json"), "utf8"));
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
  await check("actual_fixed_reference_gather_and_bridge_facts", async () => {
    await imported(report, "actual-gather.json");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.match(await page.locator("#created-summary").textContent(), /采集 6 · 领取 0 单位木材 \/ 2 个设施/);
    assert.equal(await page.locator("#wood-budget").textContent(), "6 / 6");
    assert.equal(await page.locator("#model-budget-label").textContent(), "目标选择次数");
    assert.match(await page.locator("#model-budget-note").textContent(), /外部模型 0 次/);
    assert.match(await page.locator("#model-usage").textContent(), /无模型 token 消耗/);
    assert.match(await page.locator("#decision-boundary").textContent(), /目标由固定策略选择/);
    assert.equal(await page.locator("#report-warning").isVisible(), false);
    assert.equal(await page.locator(".step-button").filter({ hasText: "采集木材" }).count(), 6);
    await page.screenshot({ path: path.join(data, "desktop.png"), fullPage: true });
  });
  await check("gather_replay_retains_resident_position", async () => {
    await page.locator(".step-button").filter({ hasText: "采集木材" }).first().click();
    assert.match(await page.locator("#replay-description").textContent(), /采集木材.*tree-west-north.*记录位置 \(1, 1\)/);
  });
  await check("unknown_cut_is_not_counted_as_collected", async () => {
    const unknown = structuredClone(report);
    unknown.mission.status = "unknown"; unknown.mission.reason = "pending_command_retained";
    unknown.facts.woodGathered = 0; unknown.facts.goalReached = false; unknown.facts.createdEntityIds = [];
    unknown.steps = [unknown.steps[0]]; unknown.steps[0].status = "unknown";
    unknown.budget.used.commands = 1; unknown.budget.used.wood = 0;
    await imported(unknown, "unknown-cut.json");
    assert.match(await page.locator("#created-summary").textContent(), /采集 0/);
    assert.match(await page.locator("#replay-description").textContent(), /动作结果未确认/);
  });
  await check("mismatched_gather_total_cannot_present_verified_completion", async () => {
    const invalid = structuredClone(report); invalid.facts.woodGathered = 12;
    await imported(invalid, "incorrect-total.json");
    assert.match(await page.locator("#report-warning").textContent(), /采集汇总与原采集步骤或任务权限不一致/);
    assert.equal(await page.locator("#report-status").textContent(), "完成标记待复核");
  });
  await check("invalid_source_rejected_during_import", async () => {
    const invalid = structuredClone(report); delete invalid.steps[0].action.nodeId;
    await page.locator("#report-file").setInputFiles({ name: "missing-source.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(invalid)) });
    await until(async () => (await page.locator("#load-message").textContent()).includes("导入失败"), "invalid import did not fail");
    assert.match(await page.locator("#load-message").textContent(), /缺少采集来源/);
  });
  await check("390px_material_summary_and_readonly_report", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await imported(report, "mobile-gather.json");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true);
    await page.screenshot({ path: path.join(data, "mobile.png"), fullPage: true });
    assert.deepEqual(errors, []); assert.deepEqual(worldRequests, []);
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
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ suite: "wilderness-resident-chrome", passed: results.length === 6 && results.every(r => r.passed),
    recordedAtUtc: new Date().toISOString(), actualModelCalls: 0, browser: browserVersion,
    javascriptErrors: errors, worldRequests, port, serviceStopped: !service || service.exitCode !== null, tests: results }, null, 2) + "\n");
  console.log("Browser evidence:", data);
}
