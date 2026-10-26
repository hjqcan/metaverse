// Render actual fixed workshop CLI reports in real Chrome; no world service.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import crypto from "node:crypto";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
assert.ok(process.env.WORKSHOP_REPORT_DIR, "Set WORKSHOP_REPORT_DIR to one completed workshop_mission_api evidence directory");
const input = path.resolve(process.env.WORKSHOP_REPORT_DIR);
const output = path.join(root, ".local/iter0027/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(output, { recursive: true, mode: 0o700 });
const results = [], errors = [], worldRequests = [];
const digest = file => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const read = name => JSON.parse(fs.readFileSync(path.join(input, name), "utf8"));
const chain = name => read(`test_01_actual_cli_chain_restart_storage_and_reuse/${name}-report.json`);
const reports = { bench: chain("build-bench"), mallet: chain("craft-mallet"), chest: chain("build-chest"),
  deposit: chain("deposit-three"), withdraw: chain("withdraw-after-restart") };
const unknown = read("test_02_dropped_success_restores_original_without_post/reports.json")[0];
const partial = read("test_15_missing_proof_query_budget_retains_original/reports.json")[0];
const noReturn = read("test_09_workshop_success_without_required_return_is_separate/reports.json")[0];
const externalMove = read("test_20_newer_actual_position_does_not_claim_original_return/reports.json")[1];
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
  assert.equal(await page.locator("#workshop-report-fact").getAttribute("data-verified"), "false");
  assert.equal(await page.locator("#report-status").textContent(), "完成标记待复核");
  assert.match(await page.locator("#report-warning").textContent(), /工坊/);
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
    assert.equal(await page.locator("#workshop-report-fact").isVisible(), false);
  });
  for (const [name, report] of Object.entries(reports)) await check(`actual_cli_${name}_three_original_records`, async () => {
    await imported(report, name + ".json");
    assert.equal(await page.locator("#workshop-report-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.equal(await page.locator("#report-warning").isVisible(), false, await page.locator("#report-warning").textContent());
    assert.match(await page.locator("#workshop-report-fact").textContent(), /原动作已核对回执、事件和详情/);
    assert.equal(await page.locator("#model-budget").textContent(), "0 / 0");
  });
  await page.screenshot({ path: path.join(output, "workshop-desktop.png"), fullPage: true });
  await check("deposit_and_withdraw_are_not_recipe_cost", async () => {
    await imported(reports.deposit, "storage-cost.json");
    assert.match(await page.locator("#workshop-report-fact").textContent(), /配方用材 0 \/ 0 · 存取周转 3 \/ 3 · 存入 3 · 取出 0/);
    await imported(reports.withdraw, "withdraw-cost.json");
    assert.match(await page.locator("#workshop-report-fact").textContent(), /存入 0 · 取出 3/);
  });
  await check("lost_response_keeps_success_unknown", async () => {
    await imported(unknown, "unknown.json");
    assert.equal(await page.locator("#workshop-report-fact").getAttribute("data-verified"), "false");
    assert.equal(await page.locator("#report-status").textContent(), "结果未知");
  });
  await check("query_budget_exhausted_preserves_pending_fact", async () => {
    await imported(partial, "partial.json");
    assert.equal(await page.locator("#workshop-report-fact").getAttribute("data-verified"), "false");
    assert.equal(await page.locator("#report-status").textContent(), "预算耗尽");
    assert.equal(await page.locator("#queries-budget").textContent(), "3 / 3");
  });
  await check("explicit_optional_return_is_not_claimed", async () => {
    await imported(noReturn, "no-return.json");
    assert.equal(await page.locator("#workshop-report-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.equal(await page.locator("#returned").getAttribute("data-verified"), "false");
    assert.match(await page.locator("#goal-route").textContent(), /未要求返程/);
    assert.match(await page.locator("#workshop-report-fact").textContent(), /尚未返回原起点/);
  });
  const originalStep = r => r.steps.find(s => s.action.type === r.mission.goal.workshop.action.type);
  for (const field of ["receiptInstanceId", "detailInstanceId", "eventInstanceId"]) await check(`wrong_${field}_cannot_confirm`, async () => {
    const report = structuredClone(reports.deposit); originalStep(report).workshopProof[field] = "w_" + "0".repeat(32);
    await downgraded(report, field + ".json");
  });
  await check("current_inventory_cannot_replace_original_detail", async () => {
    const report = structuredClone(reports.deposit); originalStep(report).workshopProof.detail.workshopAction.inventoryWood += 1;
    await downgraded(report, "different-detail.json");
  });
  await check("original_event_missing_or_wrong_action_cannot_confirm", async () => {
    const report = structuredClone(reports.withdraw); originalStep(report).workshopProof.events.events = [];
    await downgraded(report, "missing-event.json");
  });
  await check("forged_quantity_fact_cannot_confirm_storage", async () => {
    const report = structuredClone(reports.deposit); report.facts.woodDeposited = 4;
    await downgraded(report, "wrong-quantity.json");
  });
  await check("lowered_command_or_query_budget_downgrades", async () => {
    const report = structuredClone(reports.chest); report.budget.used.commands = 0;
    await downgraded(report, "wrong-commands.json");
    report.budget.used.commands = reports.chest.budget.used.commands; report.budget.used.queries = 0;
    await downgraded(report, "wrong-queries.json");
  });
  await check("missing_permission_or_wrong_actor_is_rejected", async () => {
    const report = structuredClone(reports.deposit); report.mission.allowDepositWood = false;
    await rejected(report, "no-authority.json");
    report.mission.allowDepositWood = true; report.mission.goal.workshop.actorId = "a3";
    await rejected(report, "wrong-actor.json");
  });
  await check("required_return_missing_downgrades_whole_task", async () => {
    const report = structuredClone(noReturn); report.mission.goal.workshop.returnToOrigin = true;
    await imported(report, "required-return.json");
    assert.equal(await page.locator("#workshop-report-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.locator("#report-status").textContent(), "完成标记待复核");
    assert.match(await page.locator("#workshop-report-fact").textContent(), /返程尚未完成/);
  });
  await check("earlier_world_snapshot_does_not_erase_original_action", async () => {
    await imported(noReturn, "earlier-snapshot.json");
    assert.ok(noReturn.world.observedStateVersion < noReturn.facts.workshopAction.stateVersion);
    assert.equal(await page.locator("#workshop-report-fact").getAttribute("data-verified"), "true");
    assert.match(await page.locator("#map-summary").textContent(), /最近实际观察/);
  });
  await check("newer_actual_observation_cannot_keep_old_return_flag", async () => {
    await imported(externalMove, "external-move.json");
    assert.equal(await page.locator("#report-status").textContent(), "受阻");
    assert.equal(await page.locator("#returned").getAttribute("data-verified"), "false");
    assert.equal(await page.locator("#report-warning").isVisible(), false);
  });
  await check("mobile_storage_facts_and_replay_fit", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await imported(reports.withdraw, "mobile.json");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.locator("#replay-prev").click();
    assert.ok(await page.locator("#replay-description").textContent());
    await page.screenshot({ path: path.join(output, "workshop-mobile.png"), fullPage: true });
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
    input, sourceSha256, finalSourceSha256: digest(source), actualModelCalls: 0,
    staticServerExited: !service || service.exitCode !== null || service.signalCode !== null }, null, 2) + "\n");
  console.log("Evidence:", output);
}
