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
const data = path.join(root, ".local/iter0001/browser", new Date().toISOString().replace(/[:.]/g, "-"));
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
  service = spawn("dotnet", [dll], { cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", logFd, logFd] });
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
  const result = await api(actor, "/commands", "POST", { schemaVersion: 1, rulesVersion: "r1", commandId: crypto.randomUUID(), expectedStateVersion: o.stateVersion, action });
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

  await check("connect_claim_build_and_reject", async () => {
    await connect(page);
    await page.locator("#claim-quantity").fill("4");
    await clickCommand("#claim-button");
    await until(async () => (await page.locator("#inventory-wood").textContent()).trim() === "4", "claim inventory");
    await choose(2, 1);
    await clickCommand("#build-button");
    const o = await observed();
    assert.equal(o.entities.length, 1);
    assert.equal(o.self.inventory.wood, 1);
    assert.equal(o.depot.wood, 8);
    await choose(1, 1);
    const failed = await clickCommand("#build-button", 422);
    assert.equal(failed.error.code, "INSUFFICIENT_RESOURCE");
    await until(async () => /材料|木材|不足/.test(await page.locator("#feedback").textContent()), "resource rejection not visible");
    await page.screenshot({ path: path.join(data, "desktop-built.png"), fullPage: true });
  });

  await check("human_navigation_and_wall_rejection", async () => {
    await clickCommand("#move-right");
    await clickCommand("#move-right", 422);
    assert.deepEqual((await observed()).self.position, [2, 1]);
    for (const direction of ["down", "down", "right", "right", "up", "up", "right"]) await clickCommand(`#move-${direction}`);
    assert.deepEqual((await observed()).self.position, [5, 1]);
  });

  await check("fixed_resident_and_shared_observation", async () => {
    await exec("python3", ["scripts/foundation_agent.py", "--url", url, "--access-file", path.join(data, "access.json"), "--output", path.join(data, "resident-trace.json")], { cwd: root, timeout: 60000 });
    const o = await observed();
    assert.deepEqual(o.residents.find(actor => actor.actorId === "a2").position, [5, 1]);
    assert.equal(o.resourceAudit.conserved, true);
    await waitVersion(page, o.stateVersion);
    await page.screenshot({ path: path.join(data, "desktop-two-residents.png"), fullPage: true });
  });

  await check("keyboard_after_button_focus_and_input_isolation", async () => {
    await page.locator("#move-left").focus();
    const responsePromise = page.waitForResponse(response => response.url() === url + prefix + "/commands" && response.request().method() === "POST");
    await page.keyboard.press("ArrowLeft");
    assert.equal((await responsePromise).status(), 200);
    assert.deepEqual((await observed()).self.position, [4, 1]);
    await waitVersion(page, (await observed()).stateVersion);
    await page.locator("#claim-quantity").focus();
    const unexpected = page.waitForRequest(request => request.url() === url + prefix + "/commands" && request.method() === "POST", { timeout: 350 }).then(() => true, () => false);
    await page.keyboard.press("ArrowRight");
    assert.equal(await unexpected, false, "arrow key inside an input must not move the resident");
    await clickCommand("#move-right");
    assert.deepEqual((await observed()).self.position, [5, 1]);
  });

  await check("offline_then_fresh_snapshot", async () => {
    await context.setOffline(true);
    await until(async () => await page.locator("#move-left").isDisabled(), "offline controls not disabled");
    await command("a2", { type: "move", dx: -1, dy: 0 });
    await context.setOffline(false);
    await waitVersion(page, (await observed()).stateVersion);
    await until(async () => !(await page.locator("#move-left").isDisabled()), "reconnect did not re-enable actions");
  });

  await check("committed_response_lost_then_query", async () => {
    const initial = await observed();
    let postBody, postCount = 0, holdQueries = true, serverCommitted = false;
    const handler = async route => {
      if (route.request().method() === "POST") {
        postCount++;
        postBody = route.request().postDataJSON();
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        serverCommitted = true;
        await route.abort("failed");
      } else if (holdQueries) await route.abort("failed");
      else await route.continue();
    };
    await page.route(/\/commands(?:\/[^/?]+)?$/, handler);
    await page.locator("#move-left").click();
    await until(async () => serverCommitted && postCount === 1 && !(await page.locator("#pending-panel").isHidden()), "unknown command not retained after commit");
    assert.equal((await observed()).stateVersion, initial.stateVersion + 1);
    assert.equal(await page.locator("#move-left").isDisabled(), true);
    await page.reload();
    await until(async () => !(await page.locator("#pending-panel").isHidden()), "reload lost pending command");
    holdQueries = false;
    await until(async () => !(await page.locator("#query-command-button").isDisabled()), "query recovery unavailable");
    await page.locator("#query-command-button").click();
    await until(async () => await page.locator("#pending-panel").isHidden(), "receipt did not resolve pending action");
    assert.equal(postCount, 1);
    const receipt = await api("a1", "/commands/" + postBody.commandId);
    assert.equal(receipt.status, 200);
    assert.equal((await observed()).stateVersion, initial.stateVersion + 1);
    await page.unroute(/\/commands(?:\/[^/?]+)?$/, handler);
  });

  await check("not_sent_404_then_same_command_retry", async () => {
    const before = await observed();
    const posts = [];
    let drop = true;
    const handler = async route => {
      if (route.request().method() === "POST") {
        posts.push(route.request().postDataJSON());
        if (drop) { drop = false; await route.abort("failed"); }
        else await route.continue();
      } else await route.continue();
    };
    await page.route(/\/commands(?:\/[^/?]+)?$/, handler);
    await until(async () => !(await page.locator("#move-right").isDisabled()), "actions unavailable after prior resolution");
    await page.locator("#move-right").click();
    await until(async () => posts.length === 1 && !(await page.locator("#query-command-button").isDisabled()), "unsent command not pending");
    await page.locator("#query-command-button").click();
    await until(async () => !(await page.locator("#retry-command-button").isDisabled()), "same-command retry unavailable after 404");
    assert.equal((await observed()).stateVersion, before.stateVersion);
    await page.locator("#retry-command-button").click();
    await until(async () => await page.locator("#pending-panel").isHidden(), "retried command did not finish");
    assert.equal(posts.length, 2);
    assert.deepEqual(posts[0], posts[1]);
    assert.equal((await observed()).stateVersion, before.stateVersion + 1);
    await page.unroute(/\/commands(?:\/[^/?]+)?$/, handler);
  });

  await check("service_restart_preserves_visible_world", async () => {
    const before = await observed();
    await stopService();
    await until(async () => await page.locator("#move-left").isDisabled(), "server outage did not disable actions");
    await startService();
    assert.deepEqual(await observed(), before);
    await waitVersion(page, before.stateVersion);
    await until(async () => !(await page.locator("#move-left").isDisabled()), "service restart did not reconnect");
  });

  await check("mobile_layout_and_accessible_controls", async () => {
    const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    const mobilePage = await mobile.newPage();
    mobilePage.on("pageerror", error => errors.push(error.message));
    await connect(mobilePage);
    const dimensions = await mobilePage.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(dimensions.scroll <= dimensions.width + 1, "horizontal overflow at mobile width");
    const canvas = await mobilePage.locator("#world-canvas").boundingBox();
    assert.ok(Math.abs(canvas.width - canvas.height) < 2, "map is not square");
    await mobilePage.screenshot({ path: path.join(data, "mobile.png"), fullPage: true });
    await mobile.close();
  });

  await check("revocation_clears_browser_access", async () => {
    assert.equal((await api("a1", "/v1/session", "DELETE")).status, 204);
    await until(async () => /重新|失效|认证|撤销|过期/.test(await page.locator("#feedback").textContent()), "401 not visible");
    assert.equal(await page.locator("#move-left").isDisabled(), true);
    assert.equal(await page.locator("#token-input").inputValue(), "");
  });
  assert.deepEqual(errors, [], "browser JavaScript errors");
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
  const report = { suite: "foundation-real-chrome-v1", recordedAtUtc: new Date().toISOString(), passed: results.length > 0 && results.every(result => result.passed), tests: results, javascriptErrors: errors, dataRoot: path.relative(root, data) };
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify(report, null, 2) + "\n");
}
