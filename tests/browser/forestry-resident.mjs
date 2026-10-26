// Render actual fixed forestry CLI reports in real Chrome; no world service.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import crypto from "node:crypto";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
assert.ok(process.env.FORESTRY_REPORT_DIR, "Set FORESTRY_REPORT_DIR to one completed forestry_mission_api evidence directory");
const input = path.resolve(process.env.FORESTRY_REPORT_DIR);
const output = path.join(root, ".local/iter0028/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(output, { recursive: true, mode: 0o700 });
const results = [], errors = [], worldRequests = [];
const digest = file => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const read = name => JSON.parse(fs.readFileSync(path.join(input, name), "utf8"));
const chain = name => read(`test_01_actual_cli_two_generations_restart_and_wood_use/${name}-report.json`);
const reports = { axe: chain("craft-owned-axe"), reserve: chain("reserve-first"), collect: chain("collect-first-seed"),
  plant: chain("plant-first"), harvest: chain("harvest-first"), secondHarvest: chain("harvest-second-waiting") };
assert.ok(process.env.FORESTRY_CANCEL_REPORT_DIR, "Set FORESTRY_CANCEL_REPORT_DIR to the reserve/cancel run directory");
const cancelInput = path.resolve(process.env.FORESTRY_CANCEL_REPORT_DIR);
reports.cancel = JSON.parse(fs.readFileSync(path.join(cancelInput, "test_02_reserve_original_queue_fact_and_cancel/cancel-original-report.json"), "utf8"));
const noReturn = reports.collect;
const faultInput = process.env.FORESTRY_RECOVERY_REPORT_DIR ? path.resolve(process.env.FORESTRY_RECOVERY_REPORT_DIR) : null;
const faultReports = name => JSON.parse(fs.readFileSync(path.join(faultInput, name, "reports.json"), "utf8"));
const source = path.join(root, "src/World.Server/wwwroot/resident.js");
const sourceSha256 = digest(source);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let page, browser, service, browserVersion;
async function until(predicate, message) {
  const end = Date.now() + 15000;
  while (Date.now() < end) { if (await predicate()) return; await delay(40); }
  throw new Error(message);
}
async function check(name, action) {
  try { await action(); results.push({ name, passed: true }); console.log("PASS", name); }
  catch (error) { results.push({ name, passed: false, error: error.stack }); throw error; }
}
async function imported(report, name) {
  await page.locator("#report-file").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) });
  await until(async () => (await page.locator("#load-message").textContent()).includes(name), "Import failed: " + name + " / " + await page.locator("#load-message").textContent());
}
async function rejected(report, name) {
  await page.locator("#report-file").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) });
  await until(async () => (await page.locator("#load-message").textContent()).includes("导入失败"), "Damaged report accepted: " + name);
}
async function downgraded(report, name) {
  await imported(report, name);
  assert.equal(await page.locator("#forestry-report-fact").getAttribute("data-verified"), "false");
  assert.equal(await page.locator("#report-status").textContent(), "完成标记待复核");
  assert.match(await page.locator("#report-warning").textContent(), /林业/);
}
const log = fs.openSync(path.join(output, "static-server.log"), "w");
try {
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  service = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1", "--directory", "src/World.Server/wwwroot"],
    { cwd: root, stdio: ["ignore", log, log] });
  await until(async () => { try { return (await fetch(url + "/resident.html")).ok; } catch { return false; } }, "Static host unavailable");
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  browserVersion = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", r => { if (new URL(r.url()).pathname.startsWith("/v1/")) worldRequests.push({ method: r.method(), url: r.url() }); });
  await page.goto(url + "/resident.html");
  await check("legacy_report_remains_readable", async () => {
    await until(async () => (await page.locator("#load-message").textContent()).includes("已加载"), "Legacy report unavailable");
    assert.equal(await page.locator("#forestry-report-fact").isVisible(), false);
  });
  for (const [name, report] of Object.entries(reports)) await check(`actual_cli_${name}_three_original_records`, async () => {
    await imported(report, name + ".json");
    assert.equal(await page.locator("#forestry-report-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.equal(await page.locator("#report-warning").isVisible(), false, await page.locator("#report-warning").textContent());
    assert.match(await page.locator("#forestry-report-fact").textContent(), /原动作已核对回执、事件和详情/);
    assert.equal(await page.locator("#model-budget").textContent(), "0 / 0");
  });
  await page.screenshot({ path: path.join(output, "forestry-desktop.png"), fullPage: true });
  await check("reserve_is_only_queue_and_plant_is_not_harvest", async () => {
    await imported(reports.reserve, "queue.json");
    assert.match(await page.locator("#forestry-report-fact").textContent(), /只确认已排队/);
    await imported(reports.plant, "planted.json");
    assert.match(await page.locator("#forestry-report-fact").textContent(), /只确认种植/);
    assert.match(await page.locator("#forestry-report-fact").textContent(), /实际收获木材 0/);
  });
  await check("harvest_counts_wood_and_seed_separately", async () => {
    await imported(reports.harvest, "harvest-materials.json");
    assert.match(await page.locator("#forestry-report-fact").textContent(), /实际收获木材 3 \/ 3/);
    assert.match(await page.locator("#forestry-report-fact").textContent(), /收获树种 1 \/ 1/);
    assert.match(await page.locator("#forestry-report-fact").textContent(), /成熟木材仍在树上/);
  });
  await check("explicit_optional_return_is_not_claimed", async () => {
    await imported(noReturn, "no-return.json");
    assert.equal(await page.locator("#forestry-report-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.equal(await page.locator("#returned").getAttribute("data-verified"), "false");
    assert.match(await page.locator("#goal-route").textContent(), /未要求返程/);
    assert.match(await page.locator("#forestry-report-fact").textContent(), /尚未返回原起点/);
  });
  const originalStep = r => r.steps.find(s => s.action.type === r.mission.goal.forestry.action.type);
  for (const field of ["receiptInstanceId", "detailInstanceId", "eventInstanceId"]) await check(`wrong_${field}_cannot_confirm`, async () => {
    const report = structuredClone(reports.harvest); originalStep(report).forestryProof[field] = "w_" + "0".repeat(32);
    await downgraded(report, field + ".json");
  });
  await check("current_inventory_cannot_replace_original_detail", async () => {
    const report = structuredClone(reports.harvest); originalStep(report).forestryProof.detail.forestryAction.inventoryWood += 1;
    await downgraded(report, "different-detail.json");
  });
  await check("original_event_missing_cannot_confirm", async () => {
    const report = structuredClone(reports.harvest); originalStep(report).forestryProof.events.events = [];
    await downgraded(report, "missing-event.json");
  });
  await check("seed_and_wood_facts_cannot_be_forged", async () => {
    for (const key of ["woodHarvested", "seedsHarvested", "seedsCollected", "seedsPlanted"]) {
      const report = structuredClone(reports.harvest); report.facts[key] += 1;
      await downgraded(report, "wrong-" + key + ".json");
    }
  });
  await check("plant_generation_and_axe_identity_remain_bound", async () => {
    for (const key of ["plantId", "reservationId", "toolId"]) {
      const report = structuredClone(reports.harvest); report.mission.goal.forestry.action[key] += "other";
      await downgraded(report, "other-" + key + ".json");
    }
  });
  await check("cross_proof_forged_material_delta_is_not_accepted", async () => {
    const report = structuredClone(reports.harvest), step = originalStep(report);
    for (const d of [report.facts.forestryAction, step.forestryEvidence, step.receipt.result.forestryAction,
      step.forestryProof.detail.forestryAction, step.forestryProof.events.events[0].forestryAction]) d.seeds += 1;
    step.seeds += 1;
    await downgraded(report, "coherent-but-wrong-seeds.json");
  });
  await check("lowered_command_query_and_material_budgets_downgrade", async () => {
    for (const key of ["commands", "queries", "woodHarvested", "seedsHarvested"]) {
      const report = structuredClone(reports.harvest); report.budget.used[key] = 0;
      await downgraded(report, "wrong-used-" + key + ".json");
    }
    const report = structuredClone(reports.harvest); report.budget.limits.woodHarvested = 2;
    await downgraded(report, "wrong-limit.json");
  });
  await check("permission_actor_version_and_unsafe_integer_rejected", async () => {
    const report = structuredClone(reports.harvest); report.mission.allowHarvestTree = false;
    await rejected(report, "no-authority.json");
    report.mission.allowHarvestTree = true; report.mission.goal.forestry.actorId = "a2";
    await rejected(report, "wrong-actor.json");
    report.mission.goal.forestry.actorId = report.mission.actorId; report.mission.forestryVersion = 2;
    await rejected(report, "wrong-version.json");
    report.mission.forestryVersion = 1; report.facts.seedsHarvested = Number.MAX_SAFE_INTEGER + 1;
    await rejected(report, "unsafe-seeds.json");
  });
  await check("unknown_observation_capability_or_geometry_downgrades", async () => {
    const report = structuredClone(reports.harvest); report.world.forestry.version = 2;
    await downgraded(report, "unknown-capability.json");
    report.world.forestry.version = 1; report.world.terrain.obstacles.find(o => o.kind === "forestry_tree").radius = .1;
    await downgraded(report, "wrong-tree-collision.json");
  });
  await check("required_return_missing_downgrades_whole_task", async () => {
    const report = structuredClone(noReturn); report.mission.goal.forestry.returnToOrigin = true;
    await imported(report, "required-return.json");
    assert.equal(await page.locator("#forestry-report-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.locator("#report-status").textContent(), "完成标记待复核");
    assert.match(await page.locator("#forestry-report-fact").textContent(), /返程尚未完成/);
  });
  await check("earlier_world_snapshot_does_not_erase_original_action", async () => {
    await imported(noReturn, "earlier-snapshot.json");
    assert.ok(noReturn.world.observedStateVersion < noReturn.facts.forestryAction.stateVersion);
    assert.equal(await page.locator("#forestry-report-fact").getAttribute("data-verified"), "true");
    assert.match(await page.locator("#map-summary").textContent(), /最近实际观察/);
  });
  await check("newer_actual_observation_cannot_keep_old_return_flag", async () => {
    const report = structuredClone(reports.axe);
    report.world.observedSelf.position = [2, 2]; report.world.observedStateVersion = report.facts.endStateVersion;
    await downgraded(report, "newer-position.json");
  });
  if (faultInput) {
    await check("actual_lost_response_stays_unknown", async () => {
      await imported(faultReports("test_03_dropped_success_restores_original_without_post")[0], "unknown.json");
      assert.equal(await page.locator("#forestry-report-fact").getAttribute("data-verified"), "false");
      assert.equal(await page.locator("#report-status").textContent(), "结果未知");
    });
    await check("actual_missing_proof_budget_preserves_pending", async () => {
      await imported(faultReports("test_04_missing_proof_query_budget_preserves_pending")[0], "partial.json");
      assert.equal(await page.locator("#forestry-report-fact").getAttribute("data-verified"), "false");
      assert.equal(await page.locator("#report-status").textContent(), "预算耗尽");
    });
  }
  await check("mobile_forestry_facts_and_replay_fit", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await imported(reports.harvest, "mobile.json");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.locator("#replay-prev").click();
    assert.ok(await page.locator("#replay-description").textContent());
    await page.screenshot({ path: path.join(output, "forestry-mobile.png"), fullPage: true });
  });
  await check("no_world_requests_no_javascript_errors", async () => {
    assert.deepEqual(worldRequests, []); assert.deepEqual(errors, []);
    assert.equal(digest(source), sourceSha256);
  });
} catch (error) {
  if (!results.some(r => !r.passed)) results.push({ name: "setup_or_runtime", passed: false, error: error.stack });
  process.exitCode = 1;
  console.error(error);
} finally {
  if (browser) await browser.close();
  if (service && service.exitCode === null) {
    service.kill("SIGTERM");
    await Promise.race([new Promise(resolve => service.once("exit", resolve)), delay(3000)]);
    if (service.exitCode === null && service.signalCode === null) { service.kill("SIGKILL"); await new Promise(resolve => service.once("exit", resolve)); }
  }
  fs.closeSync(log);
  fs.writeFileSync(path.join(output, "results.json"), JSON.stringify({ results, errors, worldRequests, browserVersion,
    input, cancelInput, faultInput, sourceSha256, finalSourceSha256: digest(source), actualModelCalls: 0,
    staticServerExited: !service || service.exitCode !== null || service.signalCode !== null }, null, 2) + "\n");
  console.log("Evidence:", output);
}
