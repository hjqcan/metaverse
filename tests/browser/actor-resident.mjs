// Actual interference report plus adversarial imports in Chrome. No model calls.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import crypto from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0019/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const results = [], errors = [], worldRequests = [];
let browser, page, service, browserVersion, port, reportPath;
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
async function rejected(report, name) {
  await page.locator("#report-file").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) });
  await until(async () => (await page.locator("#load-message").textContent()).includes("导入失败"), "damaged execution was accepted: " + name);
  assert.equal(await page.locator("#report-status").textContent(), "已完成", "bad import replaced the last valid report");
}
const log = fs.openSync(path.join(data, "static-server.log"), "w");
const sourceBefore = crypto.createHash("sha256").update(fs.readFileSync(path.join(root, "src/World.Server/wwwroot/resident.js"))).digest("hex");
try {
  reportPath = process.env.ACTOR_REPORT;
  if (!reportPath) {
    const run = spawnSync("python3", ["tests/actor_mission_api.py", "test_01_real_interference_all_actions_finish_one_platform"],
      { cwd: root, encoding: "utf8", timeout: 90000 });
    fs.writeFileSync(path.join(data, "mission.log"), run.stdout + run.stderr);
    assert.equal(run.status, 0, run.stderr);
    const summaryPath = run.stdout.trim().split("\n").findLast(line => line.startsWith("Evidence: ")).slice(10);
    reportPath = path.join(path.dirname(summaryPath), "test_01_real_interference_all_actions_finish_one_platform/actual-report.json");
  }
  const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
  assert.equal(report.mission.preconditionMode, "actor-state-v1");
  assert.ok(report.steps.every(s => s.execution.appliedOnStateVersion > s.expectedStateVersion));
  fs.writeFileSync(path.join(data, "actual-report.json"), JSON.stringify(report, null, 2) + "\n");
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
  port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  service = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1", "--directory", "src/World.Server/wwwroot"],
    { cwd: root, stdio: ["ignore", log, log] });
  await until(async () => {
    if (service.exitCode !== null || service.signalCode !== null) throw new Error(`static service exited ${service.exitCode ?? service.signalCode}`);
    try { return (await fetch(url + "/resident.html")).ok; } catch { return false; }
  }, "static host unavailable");
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  browserVersion = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (new URL(request.url()).pathname.startsWith("/v1/")) worldRequests.push(request.method()); });
  await page.goto(url + "/resident.html");
  await until(async () => (await page.locator("#load-message").textContent()).includes("已加载"), "default report absent");
  await check("real_interference_report_has_verified_build_and_return", async () => {
    await imported(report, "actual-actor-platform.json");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "true");
    assert.match(await page.locator("#construction-fact").textContent(), /消耗 3 木材/);
    assert.match(await page.locator("#provider-kind").textContent(), /测试替身.*非真实模型/);
    assert.match(await page.locator("#report-warning").textContent(), /测试替身/);
    await page.screenshot({ path: path.join(data, "desktop.png"), fullPage: true });
  });
  await check("missing_wrong_or_noninteger_execution_preserves_last_valid_report", async () => {
    for (const change of [s => delete s.execution, s => s.execution = null,
      s => s.execution.preconditionMode = "unknown", s => s.execution.observedStateVersion = true,
      s => s.execution.observedStateVersion++, s => s.execution.appliedOnStateVersion++,
      s => s.execution.appliedOnStateVersion = -1, s => s.stateVersion++]) {
      await imported(report, "valid-before-execution-check.json");
      const bad = structuredClone(report); change(bad.steps.find(s => s.action.type === "build"));
      await rejected(bad, "bad-execution.json");
    }
  });
  await check("missing_mission_mode_cannot_downgrade_actor_steps", async () => {
    for (const change of [r => delete r.mission.preconditionMode, r => r.mission.preconditionMode = null,
      r => r.mission.preconditionMode = "unknown", r => r.mission.worldInstanceId = "w_" + "0".repeat(32)]) {
      await imported(report, "valid-before-mode-check.json");
      const bad = structuredClone(report); change(bad); await rejected(bad, "bad-mode.json");
    }
  });
  await check("wrong_step_anchor_or_mode_is_not_a_confirmed_command", async () => {
    for (const change of [s => delete s.expectedStateVersion, s => s.expectedStateVersion = -1,
      s => s.expectedStateVersion++, s => delete s.preconditionMode]) {
      await imported(report, "valid-before-anchor-check.json");
      const bad = structuredClone(report); change(bad.steps[0]); await rejected(bad, "bad-anchor.json");
    }
  });
  function unknownBuild() {
    const unknown = structuredClone(report), index = unknown.steps.findIndex(s => s.action.type === "build");
    unknown.mission.status = "unknown"; unknown.mission.reason = "unconfirmed_execution";
    unknown.facts.constructionBuilt = false; unknown.facts.construction = null;
    unknown.facts.goalReached = false; unknown.facts.returned = false; unknown.budget.used.wood = 0;
    unknown.steps = unknown.steps.slice(0, index + 1);
    unknown.steps.at(-1).status = "unknown"; unknown.steps.at(-1).execution = null;
    unknown.steps.at(-1).stateVersion = unknown.steps.at(-1).expectedStateVersion;
    return unknown;
  }
  await check("unknown_build_has_no_confirmed_execution_or_construction", async () => {
    await imported(unknownBuild(), "unknown-actor-build.json");
    assert.equal(await page.locator("#report-status").textContent(), "结果未知");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "false");
  });
  await check("unsettled_step_cannot_keep_a_success_execution", async () => {
    await imported(report, "valid-before-unknown-check.json");
    const bad = unknownBuild(); bad.steps.at(-1).execution = report.steps.find(s => s.action.type === "build").execution;
    await rejected(bad, "unknown-with-commit-evidence.json");
  });
  await check("rejected_execution_uses_current_version_and_future_anchor_boundary", async () => {
    const denied = unknownBuild(), step = denied.steps.at(-1);
    denied.mission.status = "blocked"; denied.mission.reason = "command_rejected:STATE_VERSION_AHEAD";
    step.status = "rejected"; step.errorCode = "STATE_VERSION_AHEAD";
    step.expectedStateVersion = step.stateVersion + 100;
    step.execution = { preconditionMode: "actor-state-v1", observedStateVersion: step.expectedStateVersion,
      appliedOnStateVersion: step.stateVersion };
    await imported(denied, "rejected-future-anchor-ui-fixture.json");
    assert.equal(await page.locator("#report-status").textContent(), "受阻");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "false");
  });
  await check("old_strict_construction_report_remains_readable", async () => {
    const old = JSON.parse(fs.readFileSync(path.join(root, "docs/iterations/evidence/ITER-0017/fixed-platform.json"), "utf8"));
    assert.equal(old.mission.preconditionMode, undefined);
    await imported(old, "legacy-strict-platform.json");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "true");
  });
  await check("390px_report_is_readonly_and_has_no_horizontal_overflow", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await imported(report, "mobile-actor-platform.json");
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
  if (service && service.exitCode === null && service.signalCode === null) {
    service.kill("SIGTERM");
    await until(async () => service.exitCode !== null || service.signalCode !== null, "dedicated static host did not stop", 6000);
  }
  fs.closeSync(log);
  const sourceAfter = crypto.createHash("sha256").update(fs.readFileSync(path.join(root, "src/World.Server/wwwroot/resident.js"))).digest("hex");
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ suite: "actor-resident-chrome",
    passed: results.length === 9 && results.every(r => r.passed) && sourceBefore === sourceAfter,
    recordedAtUtc: new Date().toISOString(), actualModelCalls: 0, browser: browserVersion,
    sourceBefore, sourceAfter, actualReportPath: reportPath, javascriptErrors: errors, worldRequests,
    port, serviceStopped: !service || service.exitCode !== null || service.signalCode !== null, tests: results }, null, 2) + "\n");
  console.log("Browser evidence:", data);
}
