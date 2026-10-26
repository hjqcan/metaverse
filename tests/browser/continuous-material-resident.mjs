// Actual continuous-source CLI and exhausted-query reports, rendered in real Chrome.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0024/browser", new Date().toISOString().replace(/[:.]/g, "-"));
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
  let reportFile = process.env.CONTINUOUS_MATERIAL_REPORT_FILE;
  let queryFile = process.env.CONTINUOUS_MATERIAL_QUERY_REPORT_FILE;
  if (!reportFile || !queryFile) {
    const run = spawnSync("python3", ["tests/continuous_material_mission_api.py",
      "test_01_actual_cli_fifth_platform_and_later_production",
      "test_04_confirmed_reservation_and_query_limit_coexist"],
      { cwd: root, encoding: "utf8", timeout: 240000 });
    fs.writeFileSync(path.join(data, "mission.log"), run.stdout + run.stderr);
    assert.equal(run.status, 0, run.stderr);
    const evidence = run.stdout.trim().split("\n").findLast(line => line.startsWith("Evidence: ")).slice(10);
    reportFile = path.join(path.dirname(evidence), "test_01_actual_cli_fifth_platform_and_later_production-world", "cli-report.json");
    queryFile = path.join(path.dirname(evidence), "query4-confirmed-reservation-report.json");
  }
  const actual = JSON.parse(fs.readFileSync(reportFile, "utf8"));
  const partial = JSON.parse(fs.readFileSync(queryFile, "utf8"));
  fs.writeFileSync(path.join(data, "actual-report.json"), JSON.stringify(actual, null, 2) + "\n");
  fs.writeFileSync(path.join(data, "query4-report.json"), JSON.stringify(partial, null, 2) + "\n");
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
  await check("legacy_report_without_source_remains_readable", async () => {
    await until(async () => (await page.locator("#load-message").textContent()).includes("已加载"), "legacy report absent");
    assert.equal(await page.locator("#material-source-policy").isVisible(), false);
  });
  await check("actual_continuous_cli_separates_supply_from_claims_and_fifth_platform", async () => {
    assert.equal(actual.mission.status, "completed");
    assert.ok(actual.world.materialAccess.generatedWood > 12);
    await imported(actual, "actual-continuous.json");
    const text = await page.locator("#material-source-policy").textContent();
    assert.match(text, /持续材料来源.*每10服务秒最多产3.*当前未采.*累计产出/);
    assert.match(text, /停服不产出.*库存满时跳过/);
    assert.doesNotMatch(text, /余量|剩余总额/);
    assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "true");
    assert.match(await page.locator("#material-fact").textContent(), /亲自领取 3 木材/);
    assert.equal(await page.locator("#report-warning").isVisible(), false);
    await page.screenshot({path: path.join(data, "continuous-desktop.png"), fullPage: true});
  });
  await check("actual_query_four_keeps_confirmed_reservation_without_harvest_or_build", async () => {
    assert.equal(partial.budget.used.queries, 4);
    assert.equal(partial.mission.status, "budget_exhausted");
    assert.ok(partial.facts.materialReservation);
    await imported(partial, "actual-query4.json");
    assert.equal(await page.locator("#queries-budget").textContent(), "4 / 4");
    assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "false");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "false");
    assert.match(await page.locator("#material-fact").textContent(), /已确认原预约.*0 \/ 3/);
    assert.match(await page.locator("#report-status").textContent(), /预算/);
    await page.screenshot({path: path.join(data, "continuous-query4.png"), fullPage: true});
  });
  await check("unknown_or_incomplete_source_policy_is_rejected_preserving_original", async () => {
    const mutations = [r => r.world.materialAccess.version = 3,
      r => r.world.materialAccess.inputBudget = 12,
      r => delete r.world.materialAccess.inputBudget,
      r => r.world.materialAccess.productionPolicy.id = "future-policy",
      r => r.world.materialAccess.productionPolicy.version = 2,
      ...["adoptedAtServiceMs", "adoptedAtStateVersion", "adoptedAtEventCursor", "generatedWoodAtAdoption", "productionPeriodAtAdoption"]
        .map(k => r => delete r.world.materialAccess.productionPolicy[k])];
    for (const mutate of mutations) {
      await imported(actual, "valid-original.json");
      const bad = structuredClone(actual); mutate(bad); await rejected(bad);
      assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "true");
    }
  });
  await check("inconsistent_phase_and_adoption_facts_are_rejected", async () => {
    for (const mutate of [r => r.world.materialAccess.productionPolicy.adoptedAtEventCursor++,
      r => r.world.materialAccess.productionPolicy.generatedWoodAtAdoption = 13,
      r => r.world.materialAccess.productionPolicy.adoptedAtServiceMs = r.world.materialAccess.serviceMs + 1,
      r => r.world.materialAccess.enabledAtServiceMs = null,
      r => r.world.materialAccess.nextProductionAtMs++,
      r => r.world.materialAccess.stockWood = 7,
      r => r.world.materialAccess.generatedWood = true]) {
      await imported(actual, "valid-phase.json"); const bad = structuredClone(actual); mutate(bad); await rejected(bad);
    }
  });
  await check("source_production_alone_does_not_confirm_reservation_or_material_acquisition", async () => {
    const synthetic = structuredClone(partial);
    synthetic.facts.materialReservation = null; synthetic.steps = [];
    synthetic.world.materialAccess.currentReservation = null;
    await imported(synthetic, "synthetic-unclaimed-source.json");
    assert.equal(await page.locator("#material-source-policy").isVisible(), true);
    assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "false");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "false");
    assert.doesNotMatch(await page.locator("#material-fact").textContent(), /已确认原预约/);
  });
  await check("historical_report_without_optional_source_snapshot_remains_valid", async () => {
    const legacy = structuredClone(actual); delete legacy.world.materialAccess;
    await imported(legacy, "historical-report.json");
    assert.equal(await page.locator("#material-source-policy").isVisible(), false);
    assert.equal(await page.locator("#material-fact").getAttribute("data-verified"), "true");
  });
  await check("queries_over_budget_remain_visible", async () => {
    const bad = structuredClone(partial); bad.budget.used.queries = 5;
    await imported(bad, "query-overrun.json");
    assert.match(await page.locator("#report-warning").textContent(), /查询累计值超过/);
    assert.equal(await page.locator("#query-budget-item").getAttribute("data-over"), "true");
  });
  await check("continuous_mobile_report_keeps_source_claims_and_budget_readable", async () => {
    await page.setViewportSize({width: 390, height: 844}); await imported(actual, "mobile-continuous.json");
    assert.equal(await page.locator("#material-source-policy").isVisible(), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.screenshot({path: path.join(data, "continuous-mobile.png"), fullPage: true});
  });
  await check("report_is_readonly_without_runtime_errors", async () => {
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
const passed = results.length === 10 && results.every(r => r.passed);
fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ passed, testsRun: results.length, results, errors, worldRequests, browserVersion: version, actualModelCalls: 0 }, null, 2) + "\n");
console.log("Evidence:", path.join(data, "results.json"));
process.exitCode = passed ? 0 : 1;
