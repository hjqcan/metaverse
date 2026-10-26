// Actual Chrome against a dedicated r3 server. Only explicit fault routes drop/delay traffic.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0004/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const evidence = path.join(root, "docs/iterations/evidence/ITER-0004");
const comparison = JSON.parse(fs.readFileSync(path.join(evidence, "comparison.json"), "utf8"));
const panorama = comparison.cases[0].runs[1].report;
const arrivalOnly = JSON.parse(fs.readFileSync(path.join(evidence, "test-double-arrival-only.json"), "utf8"));
const legacy = JSON.parse(fs.readFileSync(path.join(root, "docs/iterations/evidence/ITER-0003/live-builder.json"), "utf8"));
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
    cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_SCENARIO: "activities-v1", WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", log, log],
  });
  await until(async () => {
    if (service.exitCode !== null) throw new Error(`service exited ${service.exitCode}`);
    try { return (await fetch(url + "/healthz")).ok; } catch { return false; }
  }, "service unavailable", 20000);
}
async function stop() {
  if (service && service.exitCode === null) { service.kill("SIGTERM"); await until(async () => service.exitCode !== null, "service failed to stop", 6000); }
}
async function api(suffix, method = "GET", body) {
  const r = await fetch(url + prefix + suffix, { method, headers: { Authorization: `Bearer ${access.sessions.a1.token}`, "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  return { status: r.status, body: await r.json() };
}
async function observed() { const r = await api("/observation"); assert.equal(r.status, 200); return r.body; }
async function command(action) {
  const o = await observed(); return api("/commands", "POST", { schemaVersion: 1, rulesVersion: "r3", commandId: crypto.randomUUID(), expectedStateVersion: o.stateVersion, action });
}
async function connect(p) {
  await p.goto(url); await p.locator("#token-input").fill(access.sessions.a1.token); await p.locator("#connect-button").click();
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

try {
  await start(); access = JSON.parse(fs.readFileSync(path.join(data, "access.json"), "utf8"));
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  browserVersion = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 }); watch(page);

  await check("three_live_activities_and_select_keyboard_isolation", async () => {
    await connect(page);
    assert.equal(await page.locator("#activity-catalog article").count(), 3);
    assert.match(await page.locator("#activity-catalog").textContent(), /静谧花园.*河岸步道.*彼岸观景台/);
    assert.equal(await page.locator("#visit-button").isDisabled(), true);
    const before = await observed();
    await page.locator("#activity-select").focus(); await page.keyboard.press("ArrowDown");
    assert.equal((await observed()).stateVersion, before.stateVersion);
    await page.locator("#activity-select").selectOption("garden");
    assert.match(await page.locator("#activity-hint").textContent(), /先走到静谧花园/);
  });

  await check("human_walk_and_visit_commit_real_fact_without_resources", async () => {
    for (let i = 0; i < 5; i++) await click("#move-down");
    const at = await observed(); assert.deepEqual(at.self.position, [1, 6]); assert.deepEqual(at.self.visits, []);
    await click("#visit-button");
    const o = await observed(); assert.equal(o.self.visits.length, 1); assert.equal(o.self.visits[0].activityId, "garden");
    assert.equal(o.stateVersion, at.stateVersion + 1); assert.deepEqual(o.resourceAudit, at.resourceAudit);
    assert.match(await page.locator("#visit-history").textContent(), /静谧花园/);
    assert.match(await page.locator("#event-list").textContent(), /到访了静谧花园/);
  });

  await check("actual_stale_visit_rejection_is_shown_and_never_written", async () => {
    const before = await observed(); let changed = false;
    const handler = async route => {
      if (route.request().method() === "POST" && route.request().postDataJSON().action.type === "visit" && !changed) {
        changed = true;
        assert.equal((await command({ type: "move", dx: 0, dy: -1 })).status, 200);
      }
      await route.continue();
    };
    await page.route("**/commands", handler);
    await click("#visit-button", 409);
    await page.unroute("**/commands", handler);
    assert.equal((await observed()).self.visits.length, before.self.visits.length);
    assert.match(await page.locator("#feedback").textContent(), /STALE_STATE|世界已更新/);
    assert.equal(await page.locator("#visit-button").isDisabled(), true);
    await click("#move-down");
  });

  await check("lost_visit_response_reload_recovers_original_id_once", async () => {
    const before = await observed(); let posts = 0, hold = true, original;
    const handler = async route => {
      if (route.request().method() === "POST") {
        posts++; original = route.request().postDataJSON();
        const response = await route.fetch(); assert.equal(response.status(), 200); await route.abort("failed");
      } else if (hold) await route.abort("failed");
      else await route.continue();
    };
    await page.route(/\/commands(?:\/[^/?]+)?$/, handler);
    await until(async () => !(await page.locator("#visit-button").isDisabled()), "visit unavailable");
    await page.locator("#visit-button").click();
    await until(async () => posts === 1 && !(await page.locator("#pending-panel").isHidden()), "visit not retained");
    await page.reload();
    await until(async () => !(await page.locator("#pending-panel").isHidden()), "r3 pending lost on reload");
    hold = false;
    await until(async () => !(await page.locator("#query-command-button").isDisabled()), "query unavailable");
    await page.locator("#query-command-button").click();
    await until(async () => await page.locator("#pending-panel").isHidden(), "visit not recovered");
    const after = await observed();
    assert.equal(posts, 1); assert.equal(after.stateVersion, before.stateVersion + 1);
    assert.equal(after.self.visits.filter(v => v.commandId === original.commandId).length, 1);
    assert.deepEqual(after.resourceAudit, before.resourceAudit);
    await page.unroute(/\/commands(?:\/[^/?]+)?$/, handler);
    await page.screenshot({ path: path.join(data, "world-desktop.png"), fullPage: true });
  });

  await check("server_restart_retains_live_visit_history", async () => {
    const before = await observed(); await stop();
    await until(async () => await page.locator("#visit-button").isDisabled(), "offline state absent");
    await start(); assert.deepEqual(await observed(), before);
    await until(async () => !(await page.locator("#visit-button").isDisabled()), "restart recovery absent");
    assert.match(await page.locator("#visit-history").textContent(), /静谧花园/);
  });

  await check("mobile_world_catalog_and_controls_390px", async () => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    const p = await context.newPage(); watch(p); await connect(p);
    const dimensions = await p.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(dimensions.scroll <= dimensions.width + 1);
    assert.equal(await p.locator("#activity-catalog article").count(), 3);
    await p.screenshot({ path: path.join(data, "world-mobile.png"), fullPage: true }); await context.close();
  });

  await check("actual_gpt6_activity_report_requires_verified_visit", async () => {
    reportPage = await browser.newPage({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 }); watch(reportPage, true);
    await reportPage.goto(url + "/resident.html?sample=activities");
    await until(async () => (await reportPage.locator("#mission-id").textContent()) === panorama.mission.id, "activity sample absent");
    assert.match(await reportPage.locator("#activity-fact").textContent(), /到访已核实.*彼岸观景台/);
    assert.equal(await reportPage.locator("#report-status").textContent(), "已完成");
    assert.equal(await reportPage.locator("#command-budget").textContent(), "22 / 30");
    assert.match(await reportPage.locator("#steps-list").textContent(), /到访 · 彼岸观景台/);
    assert.equal(await reportPage.locator("#decision-reason").textContent(), panorama.decision.reason);
  });

  await check("paired_evidence_shows_purpose_mismatch_and_real_call_counts", async () => {
    await until(async () => !(await reportPage.locator("#comparison-panel").isHidden()), "comparison missing");
    await reportPage.locator("#comparison-panel > summary").click();
    assert.equal(await reportPage.locator(".comparison-case").count(), 4);
    const first = reportPage.locator(".comparison-case").first();
    assert.match(await first.locator(".comparison-run").nth(0).textContent(), /未符合本例目的.*外部模型 0 次/);
    assert.match(await first.locator(".comparison-run").nth(1).textContent(), /符合本例目的.*外部模型 1 次/);
    await first.locator("button").nth(0).click();
    assert.equal(await reportPage.locator("#mission-id").textContent(), "panorama-fixed");
    assert.equal(await reportPage.locator("#model-budget-label").textContent(), "目标选择次数");
    assert.match(await reportPage.locator("#model-budget-note").textContent(), /外部模型 0 次/);
    await first.locator("button").nth(1).click();
    assert.equal(await reportPage.locator("#mission-id").textContent(), "panorama-model");
    await reportPage.screenshot({ path: path.join(data, "comparison-desktop.png"), fullPage: true });
  });

  await check("arrival_only_forged_completion_and_legacy_report_separated", async () => {
    await importReport(reportPage, arrivalOnly, "arrival-only.json");
    assert.equal(await reportPage.locator("#goal-reached").textContent(), "已到达");
    assert.match(await reportPage.locator("#activity-fact").textContent(), /尚未核实本次到访/);
    const forged = structuredClone(arrivalOnly);
    forged.mission.status = "completed"; forged.facts.returned = true; forged.facts.activityCompleted = true;
    await importReport(reportPage, forged, "forged-ui-only.json");
    assert.equal(await reportPage.locator("#report-status").textContent(), "完成标记待复核");
    await importReport(reportPage, legacy, "legacy-builder.json");
    assert.equal(await reportPage.locator("#report-status").textContent(), "已完成");
    assert.equal(await reportPage.locator("#activity-fact").isHidden(), true);
  });

  await check("mobile_comparison_no_overflow_or_live_world_requests", async () => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    const p = await context.newPage(); watch(p, true);
    await p.goto(url + "/resident.html?sample=activities");
    await until(async () => (await p.locator(".comparison-case").count()) === 4, "mobile comparison absent");
    await p.locator("#comparison-panel > summary").click();
    const dimensions = await p.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(dimensions.scroll <= dimensions.width + 1);
    await p.screenshot({ path: path.join(data, "comparison-mobile.png"), fullPage: true });
    await context.close(); assert.deepEqual(errors, []); assert.deepEqual(reportWorldRequests, []);
  });
  console.log("Browser evidence:", data);
} catch (error) {
  results.push({ name: "failure", passed: false, message: error.stack });
  if (page) await page.screenshot({ path: path.join(data, "failure.png"), fullPage: true }).catch(() => {});
  console.error(error.stack); process.exitCode = 1;
} finally {
  if (browser) await browser.close(); await stop(); fs.closeSync(log);
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ suite: "activities-real-chrome-v1", recordedAtUtc: new Date().toISOString(), browser: browserVersion,
    passed: results.length === 10 && results.every(r => r.passed), tests: results, javascriptErrors: errors, reportWorldRequests,
    actualModelCallsDuringUiTest: 0, dataRoot: path.relative(root, data) }, null, 2) + "\n");
}
