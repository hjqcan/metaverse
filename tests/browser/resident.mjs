// Real Chrome, actual exported reports, and the real C# static host.
// Adversarial imports/404 are explicit UI-only perturbations, not model runs.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0003/browser", new Date().toISOString().replace(/[:.]/g, "-"));
fs.mkdirSync(data, { recursive: true, mode: 0o700 });
const evidence = path.join(root, "docs/iterations/evidence/ITER-0003");
const read = name => JSON.parse(fs.readFileSync(path.join(evidence, name), "utf8"));
const builder = read("live-builder.json"), traveler = read("live-traveler.json");
const paused = read("test-double-paused.json"), failed = read("test-double-decision-failed.json");
const listener = net.createServer();
await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
const port = listener.address().port;
await new Promise(resolve => listener.close(resolve));
const url = `http://127.0.0.1:${port}`;
const logFd = fs.openSync(path.join(data, "server.log"), "a");
const results = [], errors = [], worldRequests = [];
let browser, page, service, browserVersion;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate, message, timeout = 12000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await predicate()) return; await delay(50); }
  throw new Error(message);
}
async function check(name, operation) {
  const start = Date.now(); await operation();
  results.push({ name, passed: true, milliseconds: Date.now() - start });
  console.log("PASS", name);
}
function watch(target) {
  target.on("pageerror", error => errors.push(error.message));
  target.on("request", request => { if (new URL(request.url()).pathname.startsWith("/v1/")) worldRequests.push(request.method() + " " + request.url()); });
}
async function importReport(target, report, name = "report.json") {
  await target.locator("#report-file").setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(typeof report === "string" ? report : JSON.stringify(report)) });
  await until(async () => /已加载|导入失败/.test(await target.locator("#load-message").textContent()), "import did not settle");
}

try {
  service = spawn("dotnet", [path.join(root, "src/World.Server/bin/Debug/net10.0/World.Server.dll")], {
    cwd: root, env: { ...process.env, WORLD_URL: url, WORLD_DATA_DIR: data, WORLD_RULES_VERSION: "r2", WORLD_ENABLE_FAULTS: "0" }, stdio: ["ignore", logFd, logFd],
  });
  await until(async () => {
    if (service.exitCode !== null) throw new Error(`service exited ${service.exitCode}`);
    try { return (await fetch(url + "/healthz")).ok; } catch { return false; }
  }, "static host unavailable", 20000);
  browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome", headless: true });
  browserVersion = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 });
  watch(page);

  await check("actual_gpt6_builder_report_facts_usage_actions", async () => {
    await page.goto(url + "/resident.html");
    await until(async () => (await page.locator("#mission-id").textContent()) === builder.mission.id, "real default report absent");
    assert.equal(await page.locator("#report-status").textContent(), "已完成");
    assert.equal(await page.locator("#decision-reason").textContent(), builder.decision.reason);
    assert.equal(await page.locator("#goal-reached").textContent(), "已到达");
    assert.equal(await page.locator("#returned").textContent(), "已返回");
    assert.equal(await page.locator("#command-budget").textContent(), "21 / 50");
    assert.equal(await page.locator("#wood-budget").textContent(), "6 / 6");
    assert.equal(await page.locator("#model-budget").textContent(), "1 / 1");
    assert.match(await page.locator("#model-usage").textContent(), /输入 11,604 token.*输出 81 token.*缓存输入 8,960 token/);
    assert.equal(await page.locator("#steps-list .step").count(), 21);
    const bridgeAt = builder.steps.find(step => step.action.type === "build").action.at;
    assert.ok((await page.locator("#steps-list").textContent()).includes(`建造 · 桥 (${bridgeAt[0]}, ${bridgeAt[1]})`));
    assert.match(await page.locator("#steps-list").textContent(), /移动 · 向右/);
    assert.match(await page.locator("#load-message").textContent(), /历史记录，非实时世界/);
    await page.screenshot({ path: path.join(data, "desktop.png"), fullPage: true });
  });

  await check("keyboard_and_step_position_replay_of_actual_report", async () => {
    const slider = page.locator("#replay-slider");
    await slider.focus(); await page.keyboard.press("Home");
    assert.equal(await slider.inputValue(), "0");
    assert.match(await page.locator("#replay-description").textContent(), /任务开始.*\(1, 1\)/);
    await page.keyboard.press("ArrowRight");
    assert.equal(await slider.inputValue(), "1");
    await page.locator("#steps-list .step-button").nth(5).click();
    assert.equal(await slider.inputValue(), "6");
    const pos = builder.steps[5].position;
    assert.ok((await page.locator("#replay-description").textContent()).includes(`(${pos[0]}, ${pos[1]})`));
    assert.match(await page.locator("#map-context").textContent(), /不表示设施在该步已经建成/);
  });

  await check("actual_traveler_uses_existing_bridges_without_materials", async () => {
    await importReport(page, traveler, "live-traveler.json");
    assert.equal(await page.locator("#actor-id").textContent(), "a2");
    assert.equal(await page.locator("#command-budget").textContent(), "16 / 50");
    assert.equal(await page.locator("#wood-budget").textContent(), "0 / 0");
    assert.equal(await page.locator("#created-summary").textContent(), "0 单位木材 / 0 个设施");
    assert.equal(await page.locator("#steps-list .step").count(), 16);
    assert.doesNotMatch(await page.locator("#steps-list").textContent(), /建造 ·|领取木材/);
  });

  await check("actual_http_paused_and_decision_failed_records", async () => {
    await importReport(page, paused, "test-double-paused.json");
    assert.equal(await page.locator("#report-status").textContent(), "已暂停");
    assert.equal(await page.locator("#command-budget").textContent(), "4 / 50");
    assert.match(await page.locator("#provider-kind").textContent(), /测试替身/);
    await importReport(page, failed, "test-double-decision-failed.json");
    assert.equal(await page.locator("#report-status").textContent(), "目标选择失败");
    assert.equal(await page.locator("#steps-list .step").count(), 0);
    assert.equal(await page.locator("#command-budget").textContent(), "0 / 50");
    assert.equal(await page.locator("#model-budget").textContent(), "1 / 1");
    assert.equal(await page.locator("#replay-slider").isDisabled(), true);
  });

  await check("adversarial_text_and_false_completion_not_rendered_as_success", async () => {
    const edited = structuredClone(builder);
    edited.decision.reason = '<img src=x onerror="window.injected=1"><script>window.injected=1</script>';
    edited.facts.goalReached = false;
    await importReport(page, edited, "adversarial-ui-only.json");
    assert.equal(await page.locator("#decision-reason").textContent(), edited.decision.reason);
    assert.equal(await page.locator("#decision-reason img, #decision-reason script").count(), 0);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.equal(await page.locator("#report-status").textContent(), "完成标记待复核");
    assert.equal(await page.locator("#report-status").getAttribute("data-tone"), "warning");
  });

  await check("invalid_json_schema_steps_and_size_preserve_valid_report", async () => {
    await importReport(page, builder, "live-builder.json");
    const many = structuredClone(builder);
    many.steps = Array.from({ length: 101 }, (_, i) => ({ ...builder.steps[0], index: i + 1 }));
    for (const bad of ["{bad json", { ...builder, schemaVersion: 2 }, many, " ".repeat(2 * 1024 * 1024 + 1)]) {
      await importReport(page, bad, "invalid-ui-only.json");
      assert.match(await page.locator("#load-message").textContent(), /导入失败.*上一份有效报告/);
      assert.equal(await page.locator("#mission-id").textContent(), builder.mission.id);
      assert.equal(await page.locator("#steps-list .step").count(), 21);
    }
  });

  await check("default_missing_report_still_allows_actual_file_import", async () => {
    const p = await browser.newPage(); watch(p);
    await p.route("**/reports/resident-demo.json", route => route.fulfill({ status: 404, body: "" }));
    await p.goto(url + "/resident.html");
    await until(async () => /HTTP 404/.test(await p.locator("#load-message").textContent()), "404 feedback absent");
    await importReport(p, builder, "live-builder.json");
    assert.equal(await p.locator("#report-status").textContent(), "已完成");
    await p.close();
  });

  await check("mobile_390px_actual_report_no_overflow_or_world_calls", async () => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    const p = await context.newPage(); watch(p);
    await p.goto(url + "/resident.html");
    await until(async () => (await p.locator("#mission-id").textContent()) === builder.mission.id, "mobile report absent");
    const dimensions = await p.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(dimensions.scroll <= dimensions.width + 1);
    const box = await p.locator("#replay-canvas").boundingBox();
    assert.ok(Math.abs(box.width - box.height) < 2);
    await p.screenshot({ path: path.join(data, "mobile.png"), fullPage: true });
    await context.close();
    assert.deepEqual(errors, []); assert.deepEqual(worldRequests, []);
  });
  console.log("Browser evidence:", data);
} catch (error) {
  results.push({ name: "failure", passed: false, message: error.stack });
  if (page) await page.screenshot({ path: path.join(data, "failure.png"), fullPage: true }).catch(() => {});
  console.error(error.stack); process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  if (service && service.exitCode === null) {
    service.kill("SIGTERM");
    await until(async () => service.exitCode !== null, "dedicated service did not stop", 6000);
  }
  fs.closeSync(logFd);
  fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({
    suite: "resident-real-report-chrome-v1", recordedAtUtc: new Date().toISOString(), browser: browserVersion,
    passed: results.length === 8 && results.every(r => r.passed), tests: results,
    javascriptErrors: errors, worldRequests, actualModelCallsDuringUiTest: 0, dataRoot: path.relative(root, data),
  }, null, 2) + "\n");
}
