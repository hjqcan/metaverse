// Actual continuous-source CLI and exhausted-query reports, rendered in real Chrome.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const data = path.join(root, ".local/iter0025/browser", new Date().toISOString().replace(/[:.]/g, "-"));
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
  let inputDir = process.env.ENTITY_CANVAS_REPORT_DIR;
  if (!inputDir) {
    const run = spawnSync("python3", ["tests/entity_canvas_mission_api.py",
      "test_01_actual_cli_two_original_round_trips", "test_04_old_success_after_own_repaint_keeps_fact_stops_route",
      "test_05_older_than_recent_fifty_still_confirms_original_edit", "test_07_first_failed_observation_and_query_budget_are_durable"],
      {cwd:root,encoding:"utf8",timeout:240000,detached:true});
    // A killed Python runner cannot execute unittest cleanup. Its isolated
    // process group also owns any .NET candidates it started.
    if (run.pid) {
      try { process.kill(-run.pid,"SIGTERM"); }
      catch (error) { if (error.code !== "ESRCH") throw error; }
    }
    fs.writeFileSync(path.join(data,"mission.log"),run.stdout+run.stderr);
    assert.equal(run.status,0,run.stderr);
    const evidence = run.stdout.trim().split("\n").findLast(line=>line.startsWith("Evidence: ")).slice(10);
    inputDir = path.dirname(evidence);
  }
  const read = relative => JSON.parse(fs.readFileSync(path.join(inputDir,relative),"utf8"));
  const first = read("test_01_actual_cli_two_original_round_trips-world/a1_alias-report.json");
  const second = read("test_01_actual_cli_two_original_round_trips-world/a2-report.json");
  const repaints = read("test_04_old_success_after_own_repaint_keeps_fact_stops_route-world/reports.json");
  const history = read("test_05_older_than_recent_fifty_still_confirms_original_edit-world/reports.json").at(-1);
  const queries = read("test_07_first_failed_observation_and_query_budget_are_durable-world/reports.json");
  fs.writeFileSync(path.join(data,"inputs.json"),JSON.stringify({inputDir,first,second,repaints,history,queries},null,2)+"\n");
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
  await check("old_report_without_canvas_remains_readable", async()=>{
    await until(async()=>(await page.locator("#load-message").textContent()).includes("已加载"),"legacy absent");
    assert.equal(await page.locator("#entity-canvas-panel").isVisible(),false);
  });
  await check("first_actual_cli_original_edit_and_snapshot", async()=>{
    await imported(first,"first.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"true");
    assert.equal(await page.locator(".entity-canvas-cell").count(),25);
    assert.equal(await page.locator('.entity-canvas-cell[data-author="a1_alias"]').count(),3);
    assert.equal(await page.locator("#report-warning").isVisible(),false);
    assert.match(await page.locator("#entity-canvas-current").textContent(),/平台建造者 a2/);
  });
  await check("second_actual_cli_keeps_first_author_and_builder_separate",async()=>{
    await imported(second,"second.json");
    assert.equal(await page.locator("#report-status").textContent(),"已完成");
    assert.equal(await page.locator('.entity-canvas-cell[data-author="a1_alias"]').count(),3);
    assert.equal(await page.locator('.entity-canvas-cell[data-author="a2"]').count(),2);
    assert.equal(await page.locator("#report-warning").isVisible(),false);
    await page.screenshot({path:path.join(data,"canvas-desktop.png"),fullPage:true});
  });
  await check("lost_response_current_color_cannot_prove_original_success",async()=>{
    await imported(repaints[0],"unknown.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"false");
    assert.equal(await page.locator("#report-status").textContent(),"结果未知");
  });
  await check("own_later_repaint_preserves_original_success_stops_return",async()=>{
    await imported(repaints.at(-1),"later-own.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"true");
    assert.equal(await page.locator("#report-status").textContent(),"受阻");
    assert.equal(await page.locator("#returned").getAttribute("data-verified"),"false");
  });
  await check("original_edit_outside_recent_fifty_still_verified",async()=>{
    assert.equal(history.world.entityCanvas.recentEdits.some(e=>e.commandId===history.facts.entityCanvasEdit.commandId),false);
    await imported(history,"outside-recent.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"true");
    assert.equal(await page.locator("#report-status").textContent(),"已完成");
  });
  await check("four_query_budget_keeps_confirmed_edit_with_older_snapshot",async()=>{
    await imported(queries.at(-1),"query4.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"true");
    assert.match(await page.locator("#entity-canvas-current").textContent(),/快照早于本次确认/);
    assert.equal(await page.locator("#report-status").textContent(),"预算耗尽");
    assert.equal(await page.locator("#queries-budget").textContent(),"4 / 4");
  });
  await check("three_queries_do_not_claim_incomplete_proof",async()=>{
    await imported(queries.find(r=>r.budget.used.queries===3),"query3.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"false");
  });
  await check("forged_summary_author_downgrades_completion",async()=>{
    const changed=structuredClone(second);changed.facts.entityCanvasEdit.authorActorId="a1_alias";changed.facts.entityCanvasEdit.operatorId="local-operator";
    await imported(changed,"forged-author.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"false");
    assert.equal(await page.locator("#report-status").textContent(),"完成标记待复核");
  });
  await check("missing_permission_does_not_confirm_edit",async()=>{
    const changed=structuredClone(second);changed.mission.allowEntityCanvas=false;
    await imported(changed,"permission.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"false");
  });
  await check("missing_queries_and_malformed_patch_rejected",async()=>{
    const missing=structuredClone(second);delete missing.budget.used.queries;await rejected(missing);
    const malformed=structuredClone(second);malformed.mission.goal.entityCanvas.patch[0].x=0.5;await rejected(malformed);
  });
  await check("wrong_execution_version_is_rejected",async()=>{
    const changed=structuredClone(second);const step=changed.steps.find(s=>s.action.type==="paint_entity_canvas");
    step.execution.appliedOnStateVersion+=1;await rejected(changed);
  });
  await check("wrong_adoption_world_is_rejected",async()=>{
    const changed=structuredClone(second);changed.world.entityCanvas.adoption.worldInstanceId="w_"+"0".repeat(32);await rejected(changed);
  });
  await check("query_overrun_remains_visible",async()=>{
    const changed=structuredClone(queries.at(-1));changed.budget.used.queries=5;await imported(changed,"overrun.json");
    assert.equal(await page.locator("#query-budget-item").getAttribute("data-over"),"true");
    assert.match(await page.locator("#report-warning").textContent(),/查询累计值超过/);
  });
  await check("mobile_grid_authors_and_budget_fit",async()=>{
    await page.setViewportSize({width:390,height:844});await imported(second,"mobile.json");
    assert.equal(await page.locator(".entity-canvas-cell").count(),25);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
    await page.screenshot({path:path.join(data,"canvas-mobile.png"),fullPage:true});
  });
  await check("forged_budget_downgrades_whole_mission_without_erasing_edit",async()=>{
    const changed=structuredClone(second);changed.budget.used.commands=0;changed.budget.used.queries=0;await imported(changed,"understated-budget.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"true");
    assert.equal(await page.locator("#report-status").textContent(),"完成标记待复核");
    changed.budget.used.commands=second.budget.used.commands;changed.budget.used.queries=801;await imported(changed,"completed-overrun.json");
    assert.equal(await page.locator("#report-status").textContent(),"完成标记待复核");
  });
  await check("missing_current_picture_preserves_original_confirmed_fact",async()=>{
    const changed=structuredClone(second);delete changed.world.entityCanvas;await imported(changed,"no-current-picture.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"true");
    assert.equal(await page.locator(".entity-canvas-cell").count(),0);
    assert.equal(await page.locator("#report-status").textContent(),"已完成");
  });
  await check("original_unsorted_request_matches_canonical_immutable_edit",async()=>{
    const changed=structuredClone(second);changed.mission.goal.entityCanvas.patch.reverse();
    changed.steps.find(s=>s.action.type==="paint_entity_canvas").action.patch.reverse();
    await imported(changed,"unsorted-original.json");
    assert.equal(await page.locator("#entity-canvas-fact").getAttribute("data-verified"),"true");
    assert.equal(await page.locator("#report-status").textContent(),"已完成");
  });
  await check("readonly_no_world_requests_or_errors",async()=>{assert.deepEqual(errors,[]);assert.deepEqual(worldRequests,[]);});
} catch (error) {
  results.push({ name: "run", passed: false, error: error.stack }); console.error(error);
} finally {
  if (browser) await browser.close();
  if (service && service.exitCode === null) {
    service.kill("SIGTERM"); await new Promise(resolve => service.once("exit", resolve));
  }
  fs.closeSync(log);
}
const passed = results.length === 19 && results.every(r => r.passed);
fs.writeFileSync(path.join(data, "results.json"), JSON.stringify({ passed, testsRun: results.length, results, errors, worldRequests, browserVersion: version, actualModelCalls: 0 }, null, 2) + "\n");
console.log("Evidence:", path.join(data, "results.json"));
process.exitCode = passed ? 0 : 1;
