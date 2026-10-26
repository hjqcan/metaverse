// Real Chrome and HTTP; program-created picture/proposals, no model calls or preview data.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/consent-experience/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const listener = net.createServer();
await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
const port = listener.address().port;
await new Promise(resolve => listener.close(resolve));
const url = `http://127.0.0.1:${port}`, prefix = "/v1/worlds/foundation-01";
const log = fs.openSync(path.join(data, "server.log"), "a");
const results = [], errors = [];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let service, browser, page, peer, access, browserVersion;
async function until(predicate, message, timeout = 12000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await predicate()) return; await delay(40); }
  throw new Error(message);
}
async function check(name, operation) {
  const start = Date.now();
  try { await operation(); results.push({ name, passed: true, milliseconds: Date.now() - start }); console.log("PASS", name); }
  catch (error) { results.push({ name, passed: false, error: error.stack }); throw error; }
}
async function api(actor, suffix, body) {
  const response = await fetch(url + prefix + suffix, { method: body ? "POST" : "GET",
    headers: { Authorization: `Bearer ${access.sessions[actor].token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined });
  const value = await response.json(); assert.equal(response.status, 200, JSON.stringify(value)); return value;
}
const observe = (actor = "a1") => api(actor, "/observation");
async function send(action, actor = "a1") {
  const o = await observe(actor);
  return api(actor, "/commands", { schemaVersion: 1, rulesVersion: "r6", commandId: crypto.randomUUID(), expectedStateVersion: o.stateVersion, action });
}
const visit = async (actor = "a1") => (await send({ type: "visit", activityId: "garden" }, actor)).commandId;
async function propose(x, color, text) {
  const visitCommandId = await visit("a2"), o = await observe("a2");
  return (await send({ type: "mosaic_propose", activityId: "garden", visitCommandId,
    expectedMosaicRevision: o.mosaic.revision, patch: [{ x, y: 2, color }], text }, "a2")).result;
}
async function ready(p = page) {
  const version = (await observe()).stateVersion;
  await until(async () => Number(await p.locator("#state-version").textContent()) === version
    && /每页最多 20 条/.test(await p.locator("#inbox-message").textContent())
    && !/正在|未更新|暂停/.test(await p.locator("#inbox-message").textContent()), "inbox not synchronized");
}
async function connect(p, actor) {
  p.on("pageerror", error => errors.push(error.message));
  await p.goto(url); await p.locator("#token-input").fill(access.sessions[actor].token); await p.locator("#connect-button").click();
  await ready(p); await showAll(p);
}
async function showAll(p = page) {
  await p.locator("#inbox-scope").selectOption("all"); await p.locator("#inbox-status").selectOption("all"); await ready(p);
}
const entry = (p, id) => p.locator(`#consent-list article[data-command="${id}"]`);
async function click(p, locator) {
  await until(async () => !(await locator.isDisabled()), "action not enabled");
  const response = p.waitForResponse(r => r.url() === url + prefix + "/commands" && r.request().method() === "POST");
  await locator.click(); const reply = await response; assert.equal(reply.status(), 200, await reply.text()); await ready(p);
}
try {
  service = spawn("dotnet", [path.join(root, "src/World.Server/bin/Debug/net10.0/World.Server.dll")], {
    cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_SCENARIO: "consent-v1", WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", log, log]
  });
  await until(async () => {
    if (service.exitCode !== null) throw new Error(`service exited ${service.exitCode}`);
    try { return (await fetch(url + "/healthz")).ok; } catch { return false; }
  }, "service unavailable", 20000);
  access = JSON.parse(fs.readFileSync(path.join(data, "access.json"), "utf8"));
  for (let i = 0; i < 5; i++) await send({ type: "move", dx: 0, dy: 1 });
  await send({ type: "mosaic", activityId: "garden", visitCommandId: await visit(), expectedMosaicRevision: 0,
    patch: [1, 2, 3].map(x => ({ x, y: 2, color: "river" })) });
  for (let i = 0; i < 4; i++) await send({ type: "move", dx: 0, dy: 1 }, "a2");
  const first = await propose(1, "sun", "只给河流左端一点阳光，其余河流保留。"), second = await propose(3, "rose", "想把右端标为花红。 ");
  await send({ type: "move", dx: 0, dy: -1 });
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  browserVersion = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  peer = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  await connect(page, "a1"); await connect(peer, "a2");
  const firstRow = entry(page, first.commandId), secondRow = entry(page, second.commandId);

  await check("fresh_proposal_compares_live_picture_and_exact_change_without_mutation", async () => {
    const before = await observe();
    assert.equal(await firstRow.locator(".consent-current [data-color=river]").count(), 3);
    assert.equal(await firstRow.locator(".consent-preview [data-color=river]").count(), 2);
    assert.equal(await firstRow.locator(".consent-preview [data-color=sun][data-draft=true]").count(), 1);
    assert.match(await firstRow.locator(".consent-changes").textContent(), /格 \(1, 2\).*河蓝 → 日黄.*居民 a1/);
    assert.match(await firstRow.locator(".consent-state").textContent(), /等待你的决定.*尚未改图/);
    assert.match(await entry(peer, first.commandId).locator(".consent-state").textContent(), /等待居民 a1 决定/);
    await page.reload(); await ready(); await showAll(); assert.equal(await firstRow.locator(".consent-preview [data-color=river]").count(), 2);
    assert.deepEqual((await observe()).mosaic, before.mosaic); assert.equal((await observe()).stateVersion, before.stateVersion);
    await page.locator("#consent-panel").screenshot({ path: path.join(data, "fresh-desktop.png") });
  });
  await check("reason_errors_explain_disabled_submission_and_preserve_unicode_count", async () => {
    const input = firstRow.locator("textarea"), hint = firstRow.locator(".consent-review-hint");
    await input.fill("同意\n只改端点"); assert.match(await hint.textContent(), /不能换行/); assert.equal(await input.getAttribute("aria-invalid"), "true");
    assert.equal(await firstRow.locator("[data-review=accept]").isDisabled(), true);
    await input.fill("🌱".repeat(161)); assert.match(await hint.textContent(), /161 \/ 160.*超过 160/);
    await input.fill("🌱".repeat(160)); assert.equal(await input.getAttribute("aria-invalid"), "false");
    await peer.locator('#mosaic-palette [data-color="leaf"]').click(); await peer.locator('#mosaic-editor [data-x="2"][data-y="2"]').click();
    await peer.locator("#proposal-text").fill("提议\n加一点绿");
    assert.match(await peer.locator("#proposal-count").textContent(), /不能换行/); assert.equal(await peer.locator("#mosaic-publish").isDisabled(), true);
    await peer.locator("#proposal-text").fill("加一点绿"); assert.equal(await peer.locator("#proposal-text").getAttribute("aria-invalid"), "false");
    await peer.locator("#mosaic-clear").click();
  });
  await check("comparison_refresh_preserves_review_focus_selection_and_draft", async () => {
    const input = firstRow.locator("textarea"); await input.fill("同意，只给左端一点日黄，保留其余河流。");
    const handle = await input.elementHandle(); await input.evaluate(e => { e.focus(); e.setSelectionRange(2, 7); });
    await propose(2, "leaf", "新提议出现时仍可继续输入理由。"); await ready();
    assert.equal(await input.evaluate((e, previous) => e === previous, handle), true);
    assert.deepEqual(await input.evaluate(e => [document.activeElement === e, e.selectionStart, e.selectionEnd]), [true, 2, 7]);
    assert.equal(await firstRow.locator(".consent-preview [data-color=river]").count(), 2);
  });
  await check("accepted_picture_is_confirmed_history_without_unpublished_markers", async () => {
    await send({ type: "move", dx: 0, dy: 1 }); await ready(); await click(page, page.locator("#inbox-visit"));
    const before = await observe(); await click(page, firstRow.locator("[data-review=accept]"));
    const after = await observe(); assert.equal(after.mosaic.revision, before.mosaic.revision + 1);
    assert.equal(after.mosaic.cells.filter((c, i) => c.color !== before.mosaic.cells[i].color).length, 1);
    assert.equal(after.mosaic.cells[11].authorActorId, "a1");
    assert.equal(await firstRow.locator(".consent-preview [data-draft=true]").count(), 0);
    assert.equal(await firstRow.locator(".consent-preview [data-confirmed=true]").count(), 1);
    assert.match(await firstRow.locator(".consent-preview").getAttribute("aria-label"), /此次确认改动/);
    assert.doesNotMatch(await firstRow.locator(".consent-preview").getAttribute("aria-label"), /未发表/);
    assert.match(await firstRow.locator(".consent-state").textContent(), /已同意并改图.*居民 a1/);
    await page.reload(); await ready(); await showAll(); assert.equal(await firstRow.locator(".consent-preview [data-draft=true]").count(), 0);
  });
  await check("expired_state_is_visible_offsite_to_both_authors_and_never_auto_rejects", async () => {
    await send({ type: "move", dx: 0, dy: -1 }); await ready(); await ready(peer);
    const before = await observe();
    for (const p of [page, peer]) {
      const row = entry(p, second.commandId);
      assert.match(await row.locator(".consent-state").textContent(), /已过期，尚未决定.*只能拒绝，不能同意/);
      assert.match(await row.locator(".consent-preview-note").textContent(), /不代表原画布/);
    }
    assert.equal(await secondRow.locator("[data-review=accept]").isDisabled(), true);
    assert.equal(before.mosaicProposals.find(p => p.commandId === second.commandId).review, null);
    assert.equal((await observe()).stateVersion, before.stateVersion);
    await secondRow.screenshot({ path: path.join(data, "expired.png") });
  });
  await check("rejected_proposal_labels_unapplied_colors_and_preserves_picture", async () => {
    await send({ type: "move", dx: 0, dy: 1 }); await ready();
    await secondRow.locator("textarea").fill("画布已经变化，这次保留原图。");
    const before = await observe(); await click(page, secondRow.locator("[data-review=reject]"));
    assert.deepEqual((await observe()).mosaic, before.mosaic);
    assert.match(await secondRow.locator(".consent-state").textContent(), /已拒绝/);
    assert.match(await secondRow.locator(".consent-changes").textContent(), /提议花红（未采纳）；当前河蓝/);
    assert.equal(await secondRow.locator(".consent-preview [data-confirmed=true]").count(), 0);
  });
  await check("later_changes_do_not_rewrite_confirmed_edit_or_confuse_current_picture", async () => {
    await send({ type: "mosaic", activityId: "garden", visitCommandId: await visit(), expectedMosaicRevision: 2, patch: [{ x: 1, y: 2, color: "leaf" }] });
    await ready();
    assert.equal(await firstRow.locator('.consent-current [data-x="1"][data-y="2"]').getAttribute("data-color"), "leaf");
    assert.equal(await firstRow.locator('.consent-preview [data-x="1"][data-y="2"]').getAttribute("data-color"), "sun");
    assert.match(await firstRow.locator(".consent-changes").textContent(), /本次确认日黄；当前叶绿/);
    assert.equal(await firstRow.locator(".consent-preview [data-draft=true]").count(), 0);
    await firstRow.screenshot({ path: path.join(data, "accepted-history-desktop.png") });
  });
  await check("mobile_comparison_has_readable_labels_and_no_horizontal_overflow", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    const dimensions = await page.evaluate(() => [document.documentElement.clientWidth, document.documentElement.scrollWidth]);
    assert.ok(dimensions[1] <= dimensions[0] + 1);
    const a = await firstRow.locator(".consent-current").boundingBox(), b = await firstRow.locator(".consent-preview").boundingBox();
    assert.ok(a.width >= 120 && b.width >= 120 && a.x + a.width <= b.x && b.x + b.width <= 390);
    assert.match(await firstRow.locator(".consent-comparison").textContent(), /当前画布.*此次确认改动/s);
    await firstRow.screenshot({ path: path.join(data, "accepted-history-mobile.png") });
    assert.deepEqual(errors, []);
  });
} catch (error) {
  console.error(error.stack); process.exitCode = 1;
  if (page) await page.screenshot({ path: path.join(data, "failure.png"), fullPage: true }).catch(() => {});
} finally {
  if (browser) await browser.close();
  if (service && service.exitCode === null) { service.kill("SIGTERM"); await until(async () => service.exitCode !== null, "service did not stop", 6000); }
  fs.closeSync(log);
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ suite: "consent-experience-real-chrome", passed: !process.exitCode,
    recordedAtUtc: new Date().toISOString(), browser: browserVersion, tests: results, javascriptErrors: errors,
    actualModelCalls: 0, serviceStopped: service?.exitCode !== null, dataRoot: path.relative(root, data) }, null, 2) + "\n");
  console.log("Evidence:", path.join(data, "results.json"));
}
