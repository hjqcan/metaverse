// Actual material entry reports, original reservation evidence and mobile rendering in real Chrome.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0022/browser", new Date().toISOString().replace(/[:.]/g, "-"));
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
  let reportFile = process.env.MATERIAL_REPORT_FILE;
  if (!reportFile) {
    const run = spawnSync("python3", ["tests/material_access_mission_api.py", "MaterialMissionAcceptance.test_01_same_instance_refusal_cli_platform_and_restart"],
      { cwd: root, encoding: "utf8", timeout: 150000 });
    fs.writeFileSync(path.join(data, "mission.log"), run.stdout + run.stderr);
    assert.equal(run.status, 0, run.stderr);
    const evidence = run.stdout.trim().split("\n").findLast(line => line.startsWith("Evidence: ")).slice(10);
    reportFile = path.join(path.dirname(evidence), "test_01_same_instance_refusal_cli_platform_and_restart-world", "cli-report.json");
  }
  const actual = JSON.parse(fs.readFileSync(reportFile, "utf8"));
  fs.writeFileSync(path.join(data, "actual-report.json"), JSON.stringify(actual, null, 2) + "\n");
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  service = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1", "--directory", "src/World.Server/wwwroot"],
    { cwd: root, stdio: ["ignore", log, log] });
  await until(async () => { try { return (await fetch(url + "/resident.html")).ok; } catch { return false; } }, "static host unavailable");
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  version = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", r => { if (new URL(r.url()).pathname.startsWith("/v1/")) worldRequests.push(r.method()); });
  await page.goto(url + "/resident.html");
  await check("legacy_report_hides_material_facts_and_query_budget", async () => {
    await until(async () => (await page.locator("#load-message").textContent()).includes("已加载"), "legacy report absent");
    assert.equal(await page.locator("#material-fact").isVisible(), false);
    assert.equal(await page.locator("#query-budget-item").isVisible(), false);
  });
  await check("real_material_report_separates_reservation_harvest_and_own_build", async () => {
    await imported(actual, "actual-material.json");
    assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "true");
    assert.match(await page.locator("#material-fact").textContent(), /亲自领取 3 木材/);
    assert.match(await page.locator("#created-summary").textContent(), /预约领取 3/);
    assert.match(await page.locator("#steps-list").textContent(), /预约材料/);
    assert.match(await page.locator("#steps-list").textContent(), /按原预约领取/);
    assert.equal(await page.locator("#queries-budget").textContent(), `${actual.budget.used.queries} / ${actual.budget.limits.queries}`);
    assert.equal(await page.locator("#report-warning").isVisible(), false);
    await page.screenshot({path: path.join(data, "material-desktop.png"), fullPage: true});
  });
  await check("reservation_only_does_not_claim_harvest_or_completed_construction", async () => {
    const partial = structuredClone(actual), index = partial.steps.findIndex(s => s.action.type === "reserve_material");
    partial.steps = partial.steps.slice(0, index + 1); partial.mission.status = "paused";
    partial.facts.materialWoodHarvested = 0; partial.facts.materialHarvests = [];
    partial.facts.constructionBuilt = false; partial.facts.construction = null;
    await imported(partial, "queued-original.json");
    assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "false");
    assert.match(await page.locator("#material-fact").textContent(), /0 \/ 3/);
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "false");
  });
  await check("unrelated_identity_id_permission_or_duplicate_claim_never_settles_materials", async () => {
    for (const mutate of [r => r.facts.materialReservation.reservationId = "m" + "0".repeat(32),
      r => r.facts.materialReservation.actorId = "a1", r => r.mission.allowMaterialAccess = false,
      r => r.facts.materialHarvests[1].commandId = r.facts.materialHarvests[0].commandId,
      r => r.facts.materialHarvests[0].operatorId = "local-operator",
      r => r.facts.materialWoodHarvested = 2]) {
      const bad = structuredClone(actual); mutate(bad); await imported(bad, "mismatch.json");
      assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "false");
      assert.match(await page.locator("#report-warning").textContent(), /不能据此|不一致/);
      assert.match(await page.locator("#report-status").textContent(), /待复核/);
    }
  });
  await check("missing_evidence_query_budget_or_wrong_rules_rejected_preserving_original", async () => {
    for (const mutate of [r => delete r.steps.find(s => s.action.type === "harvest_material").materialEvidence,
      r => delete r.budget.used.queries, r => r.mission.rulesVersion = "r9",
      r => r.facts.materialHarvests[0].quantity = true, r => r.facts.materialHarvests[0].remaining = 3]) {
      await imported(actual, "valid-original.json"); const bad = structuredClone(actual); mutate(bad); await rejected(bad);
      assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "true");
    }
  });
  await check("query_budget_overrun_is_visible", async () => {
    const bad = structuredClone(actual); bad.budget.used.queries = bad.budget.limits.queries + 1;
    await imported(bad, "query-overrun.json");
    assert.match(await page.locator("#report-warning").textContent(), /查询累计值超过/);
    assert.equal(await page.locator("#query-budget-item").getAttribute("data-over"), "true");
  });
  await check("mobile_material_report_keeps_facts_and_budget_readable", async () => {
    await page.setViewportSize({width: 390, height: 844}); await imported(actual, "mobile-material.json");
    assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.screenshot({path: path.join(data, "material-mobile.png"), fullPage: true});
  });
  await check("report_is_readonly_and_has_no_runtime_errors", async () => {
    assert.deepEqual(errors, []); assert.deepEqual(worldRequests, []);
  });
} catch (error) {
  results.push({ name: "run", passed: false, error: error.stack }); console.error(error);
} finally {
  if (browser) await browser.close();
  if (service && service.exitCode === null) {
    service.kill("SIGTERM"); await new Promise(resolve => service.once("exit", resolve));
  }
  fs.closeSync(log);
}
const passed = results.length === 8 && results.every(r => r.passed);
fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ passed, testsRun: results.length, results, errors, worldRequests, browserVersion: version, actualModelCalls: 0 }, null, 2) + "\n");
console.log("Evidence:", path.join(data, "results.json"));
process.exitCode = passed ? 0 : 1;
