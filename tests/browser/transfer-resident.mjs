// Actual gifting/recipient reports, adverse imports and mobile rendering in real Chrome.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0020/browser", new Date().toISOString().replace(/[:.]/g, "-"));
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
  let reports = process.env.TRANSFER_REPORT_DIR;
  if (!reports) {
    const run = spawnSync("python3", ["tests/transfer_mission_api.py", "test_01_real_meeting_gift_return_and_recipient_build"],
      { cwd: root, encoding: "utf8", timeout: 120000 });
    fs.writeFileSync(path.join(data, "mission.log"), run.stdout + run.stderr);
    assert.equal(run.status, 0, run.stderr);
    const evidence = run.stdout.trim().split("\n").findLast(line => line.startsWith("Evidence: ")).slice(10);
    reports = path.join(path.dirname(evidence), "test_01_real_meeting_gift_return_and_recipient_build-world");
  }
  const sender = JSON.parse(fs.readFileSync(path.join(reports, "sender-report.json"), "utf8"));
  const recipient = JSON.parse(fs.readFileSync(path.join(reports, "recipient-report.json"), "utf8"));
  for (const [name, report] of [["sender", sender], ["recipient", recipient]])
    fs.writeFileSync(path.join(data, name + ".json"), JSON.stringify(report, null, 2) + "\n");
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
  await check("legacy_report_still_loads_without_transfer_controls", async () => {
    await until(async () => (await page.locator("#load-message").textContent()).includes("已加载"), "legacy default report absent");
    assert.equal(await page.locator("#transfer-fact").isVisible(), false);
    assert.equal(await page.locator("#recent-transfers").isVisible(), false);
  });
  await check("actual_gift_report_has_original_sender_recipient_and_amount", async () => {
    await imported(sender, "actual-sender.json");
    assert.equal(await page.locator("#transfer-fact").getAttribute("data-verified"), "true");
    assert.match(await page.locator("#transfer-fact").textContent(), /a1 → a2 · 3 木材/);
    assert.equal(await page.locator("#construction-fact").isVisible(), false);
    assert.match(await page.locator("#created-summary").textContent(), /赠送 3/);
    assert.match(await page.locator("#wood-progress").locator("..").textContent(), /木材支出/);
    assert.equal(await page.locator("#wood-progress").getAttribute("aria-label"), "木材支出预算使用量");
    assert.doesNotMatch(await page.locator("#report-warning").textContent(), /不能据此|不一致|未支持/);
    await page.screenshot({ path: path.join(data, "sender-desktop.png"), fullPage: true });
  });
  await check("actual_recipient_separately_shows_received_event_and_own_construction", async () => {
    await imported(recipient, "actual-recipient.json");
    assert.equal(await page.locator("#transfer-fact").isVisible(), false);
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "true");
    assert.match(await page.locator("#recent-transfers").textContent(), /a1 → a2 · 3 木材/);
    assert.match(await page.locator("#created-summary").textContent(), /赠送 0/);
    assert.doesNotMatch(await page.locator("#report-warning").textContent(), /不能据此|不一致|未支持/);
  });
  await check("wrong_transfer_facts_or_authorization_never_claim_verified", async () => {
    for (const mutate of [r => r.facts.transfer.senderActorId = "a2", r => r.facts.transfer.recipientActorId = "a1",
      r => r.facts.transfer.quantity = 2, r => r.facts.transfer.inventoryWoodBefore = 7,
      r => r.facts.transfer.worldInstanceId = "w_" + "0".repeat(32), r => r.mission.allowTransfer = false,
      r => r.facts.woodTransferred = 6, r => r.facts.transfer.commandId = "unrelated"]) {
      const bad = structuredClone(sender); mutate(bad); await imported(bad, "mismatch.json");
      assert.equal(await page.locator("#transfer-fact").getAttribute("data-verified"), "false");
      assert.match(await page.locator("#report-warning").textContent(), /不能据此|不一致/);
    }
  });
  await check("missing_execution_and_mixed_rules_are_rejected_without_replacing_valid_report", async () => {
    for (const mutate of [r => delete r.steps.find(s => s.action.type === "transfer").execution,
      r => r.world.scenarioId = "wilderness-continuous-v1", r => r.mission.rulesVersion = "r8",
      r => r.facts.transfer.quantity = true, r => delete r.facts.transfer.inventoryWoodBefore]) {
      await imported(sender, "valid-original.json");
      const bad = structuredClone(sender); mutate(bad); await rejected(bad);
      assert.equal(await page.locator("#transfer-fact").getAttribute("data-verified"), "true");
    }
  });
  await check("coordinated_self_gift_fields_are_rejected_as_an_impossible_transfer", async () => {
    await imported(sender, "valid-gift.json");
    const bad = structuredClone(sender);
    bad.mission.goal.transfer.recipientActorId = bad.mission.actorId;
    bad.facts.transfer.recipientActorId = bad.mission.actorId;
    bad.steps.find(s => s.action.type === "transfer").action.recipientActorId = bad.mission.actorId;
    await rejected(bad);
    assert.match(await page.locator("#load-message").textContent(), /另一位收件人/);
    assert.match(await page.locator("#transfer-fact").textContent(), /a1 → a2 · 3 木材/);
  });
  await check("matching_step_and_fact_cannot_place_the_gift_outside_the_frozen_meeting", async () => {
    const bad = structuredClone(sender);
    bad.facts.transfer.position = [5, 7];
    bad.steps.find(s => s.action.type === "transfer").position = [5, 7];
    await imported(bad, "wrong-meeting.json");
    assert.equal(await page.locator("#transfer-fact").getAttribute("data-verified"), "false");
    assert.match(await page.locator("#report-warning").textContent(), /不能据此|不一致/);
  });
  await check("unknown_gift_remains_unconfirmed_even_when_an_incoming_event_exists", async () => {
    const unknown = structuredClone(sender), index = unknown.steps.findIndex(s => s.action.type === "transfer");
    unknown.mission.status = "unknown"; unknown.mission.reason = "unconfirmed_transfer_receipt";
    unknown.facts.transferCompleted = false; unknown.facts.transfer = null; unknown.facts.woodTransferred = 0;
    unknown.budget.used.wood = 0; unknown.steps = unknown.steps.slice(0, index + 1);
    unknown.steps[index].status = "unknown"; unknown.steps[index].execution = null;
    await imported(unknown, "unknown-original.json");
    assert.equal(await page.locator("#transfer-fact").getAttribute("data-verified"), "false");
    assert.match(await page.locator("#report-status").textContent(), /未知/);
  });
  await check("recent_events_keep_sender_scope_and_truncation", async () => {
    await imported(sender, "original-event.json");
    const wrong = structuredClone(sender); wrong.world.recentTransfers.items[0].actorId = "a2";
    await rejected(wrong);
    const limited = structuredClone(sender); limited.world.recentTransfers.truncated = true;
    await imported(limited, "partial-history.json");
    assert.match(await page.locator("#recent-transfers").textContent(), /更早记录未包含/);
  });
  await check("mobile_report_keeps_actual_gift_and_build_readable", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await imported(recipient, "mobile-recipient.json");
    assert.equal(await page.locator("#construction-fact").getAttribute("data-verified"), "true");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.screenshot({ path: path.join(data, "recipient-mobile.png"), fullPage: true });
  });
  await check("report_view_has_no_world_commands_or_runtime_errors", async () => {
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
const passed = results.length === 11 && results.every(r => r.passed);
fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ passed, testsRun: results.length, results, errors, worldRequests, browserVersion: version, actualModelCalls: 0 }, null, 2) + "\n");
console.log("Evidence:", path.join(data, "results.json"));
process.exitCode = passed ? 0 : 1;
