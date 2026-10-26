// Real Chrome on an isolated r4 service; traffic perturbations are explicit fault tests.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0005/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const evidence = path.join(root, "docs/iterations/evidence/ITER-0005");
const firstReport = JSON.parse(fs.readFileSync(path.join(evidence, "live-first.json"), "utf8"));
const secondReport = JSON.parse(fs.readFileSync(path.join(evidence, "live-second.json"), "utf8"));
const visitOnly = JSON.parse(fs.readFileSync(path.join(evidence, "test-double-visit-only.json"), "utf8"));
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
    cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_SCENARIO: "postcards-v1", WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", log, log],
  });
  await until(async () => {
    if (service.exitCode !== null) throw new Error(`service exited ${service.exitCode}`);
    try { return (await fetch(url + "/healthz")).ok; } catch { return false; }
  }, "service unavailable", 20000);
}
async function stop() {
  if (service && service.exitCode === null) { service.kill("SIGTERM"); await until(async () => service.exitCode !== null, "service failed to stop", 6000); }
}
async function api(suffix, method = "GET", body, actor = "a1") {
  const r = await fetch(url + prefix + suffix, { method, headers: { Authorization: `Bearer ${access.sessions[actor].token}`, "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  return { status: r.status, body: await r.json() };
}
async function observed(actor = "a1") { const r = await api("/observation", "GET", undefined, actor); assert.equal(r.status, 200); return r.body; }
async function command(action, actor = "a1") {
  const o = await observed(actor); return api("/commands", "POST", { schemaVersion: 1, rulesVersion: "r4", commandId: crypto.randomUUID(), expectedStateVersion: o.stateVersion, action }, actor);
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

  await check("public_notice_draft_persists_polling_and_keyboard_does_not_move", async () => {
    await connect(page);
    assert.equal(await page.locator("#postcards-panel").isHidden(), false);
    assert.match(await page.locator("#postcard-public-note").textContent(), /向这个世界的居民公开/);
    assert.equal(await page.locator("#postcard-button").isDisabled(), true);
    await page.locator("#postcard-text").fill("留给下一位来客：在这里慢慢走。🌱");
    await page.keyboard.press("ArrowDown");
    const before = await observed(); await delay(1700);
    assert.equal((await observed()).stateVersion, before.stateVersion);
    assert.equal(await page.locator("#postcard-text").inputValue(), "留给下一位来客：在这里慢慢走。🌱");
  });

  await check("human_visit_and_share_create_public_fact_and_clear_only_after_success", async () => {
    for (let i = 0; i < 5; i++) await click("#move-down");
    assert.equal(await page.locator("#postcard-button").isDisabled(), true);
    await click("#visit-button");
    const before = await observed(); await click("#postcard-button");
    const o = await observed(); assert.equal(o.postcards.length, 1); assert.equal(o.postcards[0].authorActorId, "a1");
    assert.equal(o.postcards[0].visitCommandId, before.self.visits[0].commandId);
    assert.equal(o.stateVersion, before.stateVersion + 1); assert.deepEqual(o.resourceAudit, before.resourceAudit);
    assert.equal(await page.locator("#postcard-text").inputValue(), "");
    assert.equal(await page.locator("#postcard-list .postcard-message").textContent(), o.postcards[0].text);
    assert.match(await page.locator("#event-list").textContent(), /留下了一篇手记/);
  });

  await check("another_resident_reads_shared_text_and_place_filter_is_real", async () => {
    const peer = await browser.newPage(); watch(peer);
    await peer.goto(url); await peer.locator("#token-input").fill(access.sessions.a2.token); await peer.locator("#connect-button").click();
    await until(async () => (await peer.locator("#postcard-list .postcard").count()) === 1, "peer did not see shared text");
    assert.match(await peer.locator("#postcard-list").textContent(), /居民 a1/);
    for (const [dx, dy] of [[1,0],[0,1],[0,1],[0,1]]) assert.equal((await command({ type: "move", dx, dy }, "a2")).status, 200);
    const visit = await command({ type: "visit", activityId: "riverwalk" }, "a2");
    assert.equal(visit.status, 200);
    const text = '<img src=x onerror="window.postcardInjected=true"> 河边留一句问候。';
    assert.equal((await command({ type: "postcard", activityId: "riverwalk", visitCommandId: visit.body.commandId, text }, "a2")).status, 200);
    await version(page, (await observed()).stateVersion);
    await page.locator("#activity-select").selectOption("riverwalk");
    assert.equal(await page.locator("#postcard-list .postcard-message").textContent(), text);
    assert.match(await page.locator("#postcard-list").textContent(), /居民 a2/);
    assert.equal(await page.locator("#postcard-list img").count(), 0);
    assert.equal(await page.evaluate(() => Boolean(window.postcardInjected)), false);
    await page.locator("#activity-select").selectOption("garden");
    assert.equal(await page.locator("#postcard-list .postcard").count(), 1);
    await peer.close();
  });

  await check("unicode_limit_counts_scalars_and_preserves_draft_by_place", async () => {
    await click("#visit-button");
    await page.locator("#postcard-text").fill("🌱".repeat(160));
    assert.equal(await page.locator("#postcard-count").textContent(), "160 / 160 字");
    assert.equal(await page.locator("#postcard-button").isDisabled(), false);
    await page.locator("#postcard-text").fill("🌱".repeat(161));
    assert.equal(await page.locator("#postcard-button").isDisabled(), true);
    await page.locator("#postcard-text").fill("这一段尚未公开，等确认后再留下。");
    await page.locator("#activity-select").selectOption("riverwalk");
    assert.equal(await page.locator("#postcard-text").inputValue(), "");
    await page.locator("#activity-select").selectOption("garden");
    assert.equal(await page.locator("#postcard-text").inputValue(), "这一段尚未公开，等确认后再留下。");
  });

  await check("actual_stale_share_rejection_preserves_draft", async () => {
    const before = await observed(); let changed = false;
    const handler = async route => {
      if (route.request().method() === "POST" && route.request().postDataJSON().action.type === "postcard" && !changed) {
        changed = true; assert.equal((await command({ type: "move", dx: 0, dy: -1 })).status, 200);
      }
      await route.continue();
    };
    await page.route("**/commands", handler); await click("#postcard-button", 409); await page.unroute("**/commands", handler);
    assert.equal((await observed()).postcards.length, before.postcards.length);
    assert.match(await page.locator("#feedback").textContent(), /STALE_STATE|世界已更新/);
    assert.equal(await page.locator("#postcard-text").inputValue(), "这一段尚未公开，等确认后再留下。");
    await click("#move-down");
  });

  await check("lost_share_response_reload_recovers_same_id_once", async () => {
    await page.locator("#postcard-text").fill("愿每个后来的人，都能找到自己的风景。");
    const before = await observed(); let posts = 0, hold = true, original;
    const handler = async route => {
      if (route.request().method() === "POST") {
        posts++; original = route.request().postDataJSON();
        const response = await route.fetch(); assert.equal(response.status(), 200); await route.abort("failed");
      } else if (hold) await route.abort("failed");
      else await route.continue();
    };
    await page.route(/\/commands(?:\/[^/?]+)?$/, handler);
    await page.locator("#postcard-button").click();
    await until(async () => posts === 1 && !(await page.locator("#pending-panel").isHidden()), "share not pending");
    await page.reload();
    await until(async () => !(await page.locator("#pending-panel").isHidden()), "r4 pending lost");
    assert.equal(await page.locator("#postcard-text").inputValue(), original.action.text);
    hold = false;
    await until(async () => !(await page.locator("#query-command-button").isDisabled()), "query unavailable");
    await page.locator("#query-command-button").click();
    await until(async () => await page.locator("#pending-panel").isHidden(), "share not recovered");
    const after = await observed(); assert.equal(posts, 1); assert.equal(after.stateVersion, before.stateVersion + 1);
    assert.equal(after.postcards.filter(p => p.commandId === original.commandId).length, 1);
    assert.equal(await page.locator("#postcard-text").inputValue(), "");
    assert.deepEqual(after.resourceAudit, before.resourceAudit);
    await page.unroute(/\/commands(?:\/[^/?]+)?$/, handler);
    await page.screenshot({ path: path.join(data, "world-desktop.png"), fullPage: true });
  });

  await check("server_restart_preserves_public_and_author_records", async () => {
    const before = await observed(); await stop();
    await until(async () => await page.locator("#visit-button").isDisabled(), "offline not shown");
    await start(); assert.deepEqual(await observed(), before);
    await until(async () => !(await page.locator("#visit-button").isDisabled()), "restart not recovered");
    assert.equal(await page.locator("#postcard-list .postcard").count(), 2);
  });

  await check("unsent_drafts_are_isolated_between_actor_logins", async () => {
    await page.locator("#postcard-text").fill("a1 尚未公开的草稿。");
    await page.locator("#token-input").fill(access.sessions.a2.token); await page.locator("#connect-button").click();
    await until(async () => (await page.locator("#resident-title").textContent()) === "居民 a2", "actor switch failed");
    assert.equal(await page.locator("#postcard-text").inputValue(), "");
    await page.locator("#token-input").fill(access.sessions.a1.token); await page.locator("#connect-button").click();
    await until(async () => (await page.locator("#resident-title").textContent()) === "居民 a1", "actor restore failed");
    assert.equal(await page.locator("#postcard-text").inputValue(), "a1 尚未公开的草稿。");
  });

  await check("mobile_world_read_and_write_layout_390px", async () => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    const p = await context.newPage(); watch(p); await connect(p);
    await p.locator("#postcard-text").fill("这本共同手记，可以从一句问候开始。");
    const dimensions = await p.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(dimensions.scroll <= dimensions.width + 1);
    await p.screenshot({ path: path.join(data, "world-mobile.png"), fullPage: true }); await context.close();
  });

  await check("actual_two_gpt6_reports_separate_draft_and_confirmed_share", async () => {
    reportPage = await browser.newPage({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 }); watch(reportPage, true);
    await reportPage.goto(url + "/resident.html?sample=postcards");
    await until(async () => (await reportPage.locator("#mission-id").textContent()) === firstReport.mission.id, "first sample absent");
    assert.equal(await reportPage.locator("#postcard-draft").textContent(), firstReport.decision.postcardText);
    assert.equal(await reportPage.locator("#postcard-shared-text").textContent(), firstReport.facts.postcard.text);
    assert.match(await reportPage.locator("#postcard-fact").textContent(), /分享已核实.*居民 a1/);
    assert.equal(await reportPage.locator("#report-status").textContent(), "已完成");
    assert.match(await reportPage.locator("#steps-list").textContent(), /分享手记 · 静谧花园/);
    await reportPage.locator('#postcard-report-links a[href*="postcards-reply"]').click();
    await until(async () => (await reportPage.locator("#mission-id").textContent()) === secondReport.mission.id, "second sample absent");
    assert.equal(await reportPage.locator("#postcard-shared-text").textContent(), secondReport.facts.postcard.text);
    assert.match(await reportPage.locator("#postcard-fact").textContent(), /居民 a2/);
    await reportPage.screenshot({ path: path.join(data, "report-desktop.png"), fullPage: true });
  });

  await check("visit_only_and_forged_share_never_show_completed_and_legacy_still_loads", async () => {
    await importReport(reportPage, visitOnly, "visit-only.json");
    assert.match(await reportPage.locator("#activity-fact").textContent(), /到访已核实/);
    assert.match(await reportPage.locator("#postcard-fact").textContent(), /尚未核实本次分享/);
    const forged = structuredClone(firstReport); forged.facts.postcard.text = "一篇没有匹配提交的文字。";
    await importReport(reportPage, forged, "forged-ui-only.json");
    assert.equal(await reportPage.locator("#report-status").textContent(), "完成标记待复核");
    assert.equal(await reportPage.locator("#postcard-shared-text").isHidden(), true);
    await importReport(reportPage, legacy, "legacy-builder.json");
    assert.equal(await reportPage.locator("#report-status").textContent(), "已完成");
    assert.equal(await reportPage.locator("#postcard-fact-panel").isHidden(), true);
  });

  await check("mobile_report_no_overflow_javascript_errors_or_world_requests", async () => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    const p = await context.newPage(); watch(p, true); await p.goto(url + "/resident.html?sample=postcards-reply");
    await until(async () => (await p.locator("#mission-id").textContent()) === secondReport.mission.id, "mobile report absent");
    const dimensions = await p.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(dimensions.scroll <= dimensions.width + 1);
    await p.screenshot({ path: path.join(data, "report-mobile.png"), fullPage: true });
    await context.close(); assert.deepEqual(errors, []); assert.deepEqual(reportWorldRequests, []);
  });
  console.log("Browser evidence:", data);
} catch (error) {
  results.push({ name: "failure", passed: false, message: error.stack });
  if (page) await page.screenshot({ path: path.join(data, "failure.png"), fullPage: true }).catch(() => {});
  console.error(error.stack); process.exitCode = 1;
} finally {
  if (browser) await browser.close(); await stop(); fs.closeSync(log);
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ suite: "postcards-real-chrome-v1", recordedAtUtc: new Date().toISOString(), browser: browserVersion,
    passed: results.length === 12 && results.every(r => r.passed), tests: results, javascriptErrors: errors, reportWorldRequests,
    actualModelCallsDuringUiTest: 0, dataRoot: path.relative(root, data) }, null, 2) + "\n");
}
