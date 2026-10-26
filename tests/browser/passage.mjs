// Real Chromium + real candidate service. No mocked world responses.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const exec = promisify(execFile);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0002/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const dll = path.join(root, "src/World.Server/bin/Debug/net10.0/World.Server.dll");
const listen = net.createServer();
await new Promise(resolve => listen.listen(0, "127.0.0.1", resolve));
const port = listen.address().port;
await new Promise(resolve => listen.close(resolve));
const url = `http://127.0.0.1:${port}`;
const prefix = "/v1/worlds/foundation-01";
const logFd = fs.openSync(path.join(data, "server.log"), "a");
const results = [];
const errors = [];
let service, browser, page, access;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function until(predicate, message, timeout = 12000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await delay(100);
  }
  throw new Error(message);
}

async function startService() {
  service = spawn("dotnet", [dll], { cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_ENABLE_FAULTS: "0", WORLD_SCENARIO: "passage-v1" }, stdio: ["ignore", logFd, logFd] });
  await until(async () => {
    if (service.exitCode !== null) throw new Error(`Candidate exited ${service.exitCode}`);
    try { return (await fetch(url + "/healthz")).ok; } catch { return false; }
  }, "service did not become healthy", 20000);
}

async function stopService() {
  if (service && service.exitCode === null) {
    service.kill("SIGTERM");
    await until(async () => service.exitCode !== null, "dedicated service did not stop", 6000);
  }
}

async function api(actor, suffix, method = "GET", body) {
  const response = await fetch(url + (suffix.startsWith("/v1/") ? suffix : prefix + suffix), {
    method, headers: { "Authorization": `Bearer ${access.sessions[actor].token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  return { status: response.status, body: text ? JSON.parse(text) : null };
}

async function observed(actor = "a1") {
  const result = await api(actor, "/observation");
  assert.equal(result.status, 200);
  return result.body;
}

async function command(actor, action) {
  const o = await observed(actor);
  const result = await api(actor, "/commands", "POST", { schemaVersion: 1, rulesVersion: o.rulesVersion, commandId: crypto.randomUUID(), expectedStateVersion: o.stateVersion, action });
  assert.equal(result.status, 200, JSON.stringify(result.body));
  return result.body;
}

async function connect(target) {
  await target.goto(url);
  await target.locator("#token-input").fill(access.sessions.a1.token);
  await target.locator("#connect-button").click();
  await until(async () => (await target.locator("#inventory-wood").textContent()).trim() !== "—", "browser did not connect");
  await until(async () => !(await target.locator("#move-right").isDisabled()), "browser actions not ready");
}

async function waitVersion(target, version) {
  await until(async () => Number((await target.locator("#state-version").textContent()).trim()) === version, `UI did not show version ${version}`);
}

async function clickCommand(id, expectedStatus = 200) {
  await until(async () => !(await page.locator(id).isDisabled()), `${id} not enabled`);
  const pending = page.waitForResponse(response => response.url() === url + prefix + "/commands" && response.request().method() === "POST");
  await page.locator(id).click();
  const response = await pending;
  const body = await response.json();
  assert.equal(response.status(), expectedStatus, JSON.stringify(body));
  const o = await observed();
  await waitVersion(page, o.stateVersion);
  return body;
}

async function choose(x, y) {
  const canvas = page.locator("#world-canvas");
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  await canvas.click({ position: { x: box.width * (x + 0.5) / 8, y: box.height * (y + 0.5) / 8 } });
  const text = await page.locator("#selected-cell").textContent();
  assert.match(text, new RegExp(`${x}\\s*[,，]\\s*${y}`), "canvas click selected wrong cell");
}

async function check(name, operation) {
  const started = Date.now();
  await operation();
  results.push({ name, passed: true, milliseconds: Date.now() - started });
  console.log("PASS", name);
}

try {
  await startService();
  access = JSON.parse(fs.readFileSync(path.join(data, "access.json"), "utf8"));
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 });
  page = await context.newPage();
  page.setDefaultTimeout(12000);
  page.on("pageerror", error => errors.push(error.message));

  await check("passage_connect_recipes_and_land_rejection", async () => {
    await connect(page);
    const o = await observed();
    assert.equal(o.rulesVersion, "r2");
    assert.equal(o.world.water.length, 16);
    assert.equal(await page.locator("#recipe-select option").count(), 2);
    await page.locator("#claim-quantity").fill("6");
    await clickCommand("#claim-button");
    await page.locator("#recipe-select").selectOption("bridge.v1");
    await choose(1, 1);
    const denied = await clickCommand("#build-button", 422);
    assert.equal(denied.error.code, "UNREACHABLE");
    assert.equal((await observed()).self.inventory.wood, 6);
  });

  await check("river_blocks_movement_and_platform_cannot_pave_water", async () => {
    for (const direction of ["right", "down", "down", "right"]) await clickCommand(`#move-${direction}`);
    assert.deepEqual((await observed()).self.position, [3, 3]);
    await clickCommand("#move-right", 422);
    await page.locator("#recipe-select").selectOption("platform.v1");
    await choose(4, 3);
    await clickCommand("#build-button", 422);
    assert.equal((await observed()).entities.length, 0);
    assert.equal((await observed()).self.inventory.wood, 6);
  });

  await check("first_bridge_is_walkable_but_second_water_cell_blocks", async () => {
    await page.locator("#recipe-select").selectOption("bridge.v1");
    await choose(4, 3);
    await clickCommand("#build-button");
    await clickCommand("#move-right");
    await clickCommand("#move-right", 422);
    const o = await observed();
    assert.deepEqual(o.self.position, [4, 3]);
    assert.equal(o.entities[0].definitionId, "bridge");
    assert.equal(o.self.inventory.wood, 3);
    assert.equal(o.world.blocked.some(p => p[0] === 4 && p[1] === 3), false);
    assert.equal(o.world.blocked.some(p => p[0] === 5 && p[1] === 3), true);
  });

  await check("second_bridge_lost_response_reload_queries_original_receipt", async () => {
    await choose(5, 3);
    const before = await observed();
    let original, posts = 0, committed = false, hold = true;
    const handler = async route => {
      if (route.request().method() === "POST") {
        posts++;
        original = route.request().postDataJSON();
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        committed = true;
        await route.abort("failed");
      } else if (hold) await route.abort("failed");
      else await route.continue();
    };
    await page.route(/\/commands(?:\/[^/?]+)?$/, handler);
    await page.locator("#build-button").click();
    await until(async () => committed && !(await page.locator("#pending-panel").isHidden()), "bridge commit not retained as pending");
    assert.equal(await page.locator("#build-button").isDisabled(), true);
    await page.reload();
    await until(async () => !(await page.locator("#pending-panel").isHidden()), "r2 pending bridge lost on reload");
    hold = false;
    await until(async () => !(await page.locator("#query-command-button").isDisabled()), "query unavailable");
    await page.locator("#query-command-button").click();
    await until(async () => await page.locator("#pending-panel").isHidden(), "bridge receipt recovery failed");
    assert.equal(posts, 1);
    assert.equal(original.action.recipeId, "bridge.v1");
    assert.equal(original.rulesVersion, "r2");
    const o = await observed();
    assert.equal(o.stateVersion, before.stateVersion + 1);
    assert.equal(o.entities.length, 2);
    assert.equal(o.self.inventory.wood, 0);
    assert.equal(o.resourceAudit.embodiedWood, 6);
    assert.equal((await api("a1", "/commands/" + original.commandId)).status, 200);
    await page.unroute(/\/commands(?:\/[^/?]+)?$/, handler);
  });

  await check("human_crosses_and_returns_other_resident_uses_free_bridge", async () => {
    for (const direction of ["right", "right", "up", "up"]) await clickCommand(`#move-${direction}`);
    assert.deepEqual((await observed()).self.position, [6, 1]);
    await page.screenshot({ path: path.join(data, "desktop.png"), fullPage: true });
    for (const direction of ["down", "down", "left", "left", "left", "left", "left", "up", "up"]) await clickCommand(`#move-${direction}`);
    assert.deepEqual((await observed()).self.position, [1, 1]);
    await exec("python3", ["scripts/passage_agent.py", "--url", url, "--access-file", path.join(data, "access.json"), "--actor", "a2", "--output", path.join(data, "traveler-trace.json")], { cwd: root, timeout: 60000 });
    const trace = JSON.parse(fs.readFileSync(path.join(data, "traveler-trace.json"), "utf8"));
    assert.equal(trace.outcome, "completed");
    assert.ok(trace.trace.every(t => t.request.action.type === "move"));
    const o = await observed();
    assert.equal(o.depot.wood, 6);
    assert.equal(o.resourceAudit.inventoryWood, 0);
    assert.equal(o.resourceAudit.conserved, true);
    await waitVersion(page, o.stateVersion);
  });

  await check("restart_retains_bridge_ids_and_live_ui", async () => {
    const before = await observed();
    await stopService();
    await until(async () => await page.locator("#move-right").isDisabled(), "outage not shown");
    await startService();
    assert.deepEqual(await observed(), before);
    await waitVersion(page, before.stateVersion);
    await until(async () => !(await page.locator("#move-right").isDisabled()), "reconnect unavailable");
  });

  await check("recipe_keyboard_does_not_move_actor", async () => {
    const before = await observed();
    await page.locator("#recipe-select").focus();
    const unexpected = page.waitForRequest(request => request.url() === url + prefix + "/commands" && request.method() === "POST", { timeout: 350 }).then(() => true, () => false);
    await page.keyboard.press("ArrowDown");
    assert.equal(await unexpected, false);
    assert.equal((await observed()).stateVersion, before.stateVersion);
  });

  await check("mobile_water_bridge_selection_and_layout", async () => {
    const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    const p = await mobile.newPage();
    p.on("pageerror", error => errors.push(error.message));
    await connect(p);
    await p.locator("#recipe-select").selectOption("bridge.v1");
    assert.match(await p.locator("#recipe-cost").textContent(), /3/);
    const dimensions = await p.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(dimensions.scroll <= dimensions.width + 1, "mobile horizontal overflow");
    const canvas = await p.locator("#world-canvas").boundingBox();
    assert.ok(Math.abs(canvas.width - canvas.height) < 2);
    await p.screenshot({ path: path.join(data, "mobile.png"), fullPage: true });
    await mobile.close();
  });
  assert.deepEqual(errors, []);
  console.log("Browser evidence:", data);
} catch (error) {
  results.push({ name: "failure", passed: false, message: error.stack });
  if (page) await page.screenshot({ path: path.join(data, "failure.png"), fullPage: true }).catch(() => {});
  console.error(error.stack);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  await stopService();
  fs.closeSync(logFd);
  const report = { suite: "passage-real-chrome-v1", recordedAtUtc: new Date().toISOString(), passed: results.length > 0 && results.every(r => r.passed), tests: results, javascriptErrors: errors, dataRoot: path.relative(root, data) };
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify(report, null, 2) + "\n");
}
