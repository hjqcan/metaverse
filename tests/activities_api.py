#!/usr/bin/env python3
"""Independent actual HTTP/SQLite tests; all mission choices are explicit doubles."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import unittest
import uuid

from foundation_api import Candidate, DLL, EvidenceResult, FoundationAcceptance, ROOT
from foundation_agent import WorldClient
from passage_agent import plan
from resident_mission import run_mission
from resident_mission_api import Choice
from activity_choice import choose_lowest_cost

RUN_ROOT = ROOT / ".local/iter0004/api" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])


class ActivityCandidate(Candidate):
    def __init__(self, name, scenario="activities-v1", fixture=None):
        self.data = RUN_ROOT / name
        self.data.mkdir(parents=True, mode=0o700)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); self.port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, "WORLD_URL": self.url, "WORLD_DATA_DIR": str(self.data), "WORLD_ENABLE_FAULTS": "1"}
        self.env.pop("WORLD_SCENARIO", None)
        if scenario is not None: self.env["WORLD_SCENARIO"] = scenario
        if fixture:
            with sqlite3.connect(self.data / "world.db") as db:
                db.executescript((ROOT / "tests/fixtures" / fixture).read_text())
            (self.data / "access.json").write_text(json.dumps({"sessions": {a: {"token": "fixture-r2-" + a} for a in ("a1", "a2")}}))
            self.fixture_before = self.dump()
        self.process = self.log = None
        self.start()
        self.access = json.loads((self.data / "access.json").read_text())

    def dump(self):
        with sqlite3.connect(f"file:{self.data / 'world.db'}?mode=ro", uri=True) as db:
            return "\n".join(db.iterdump())


def mission(name="activity-test", commands=30, wood=6):
    job = deepcopy(json.loads((ROOT / "examples/activities/cases.json").read_text())["cases"][0]["spec"])
    job["missionId"] = name
    job["budgets"].update(commands=commands, wood=wood)
    return job


class ActivityAcceptance(unittest.TestCase):
    audit = FoundationAcceptance.audit
    send = FoundationAcceptance.send

    def setUp(self):
        self.world = ActivityCandidate(self._testMethodName)
        self.a, self.b = self.world.client(), self.world.client("a2")
        self.trace, self.reports = [], []
        self.state = self.world.data / "mission.json"
        self.choice = Choice("garden")

    def tearDown(self):
        (self.world.data / "reports.json").write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + "\n")
        FoundationAcceptance.tearDown(self)
        with sqlite3.connect(f"file:{self.world.data / 'world.db'}?mode=ro", uri=True) as db:
            # A visit must have its committed receipt and matching public event, with no material entry.
            for actor, command, activity, version, x, y in db.execute("SELECT actor_id,command_id,activity_id,state_version,x,y FROM visits"):
                receipt = json.loads(db.execute("SELECT result_json FROM receipts WHERE actor_id=? AND command_id=?", (actor, command)).fetchone()[0])
                event = json.loads(db.execute("SELECT event_json FROM events WHERE state_version=?", (version,)).fetchone()[0])
                self.assertEqual(("committed", "visit", activity, [x, y]), (receipt["status"], receipt["result"]["action"], receipt["result"]["activityId"], receipt["result"]["position"]))
                self.assertEqual(("visited", command, activity), (event["type"], event["commandId"], event["activityId"]))
                self.assertEqual(0, db.execute("SELECT count(*) FROM resource_ledger WHERE command_id=?", (command,)).fetchone()[0])
            self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())

    def intent(self, client, action, command_id=None, version=None):
        o = client.observe()
        return {"schemaVersion": 1, "rulesVersion": o["rulesVersion"], "commandId": command_id or uuid.uuid4().hex,
                "expectedStateVersion": o["stateVersion"] if version is None else version, "action": action}

    def walk(self, client, target):
        while client.observe()["self"]["position"] != list(target):
            o = client.observe(); route = plan(o, target, False)
            self.assertIsNotNone(route)
            nxt = route[0][0]
            self.send(client, {"type": "move", "dx": nxt[0] - o["self"]["position"][0], "dy": nxt[1] - o["self"]["position"][1]})

    def task(self, job=None, client=None, choose=None, **kwargs):
        report = run_mission(client or self.a, job or mission(), self.state, choose or self.choice, **kwargs)
        self.reports.append(report)
        return report

    def test_01_catalog_and_identity_private_visits(self):
        o = self.audit()
        self.assertEqual("r3", o["rulesVersion"])
        self.assertEqual("activities-v1", o["world"]["scenarioId"])
        self.assertEqual({"garden": [1, 6], "riverwalk": [2, 5], "lookout": [6, 1]}, {a["id"]: a["position"] for a in o["activities"]})
        self.assertEqual([], o["self"]["visits"])
        self.assertTrue(all("visits" not in r for r in o["residents"]))
        self.assertTrue(all(a["description"] for a in o["activities"]))

    def test_02_not_at_unknown_and_invalid_visit_never_change_world(self):
        before = self.audit()
        for action, status, code in [({"type": "visit", "activityId": "garden"}, 422, "NOT_AT_ACTIVITY"),
                                     ({"type": "visit", "activityId": "invented"}, 422, "ACTIVITY_NOT_FOUND"),
                                     ({"type": "visit", "activityId": True}, 400, "INVALID_REQUEST"),
                                     ({"type": "visit", "activityId": "garden", "actorId": "a2"}, 403, "IDENTITY_OVERRIDE"),
                                     ({"type": "visit", "activityId": "garden", "reward": 10}, 400, "INVALID_REQUEST")]:
            _, response = self.send(self.a, action, expected=status)
            self.assertEqual(code, response["error"]["code"])
        self.assertEqual(before, self.audit())

    def test_03_visit_transaction_idempotence_and_other_actor_scope(self):
        self.walk(self.a, [1, 6]); before = self.audit()
        intent, response = self.send(self.a, {"type": "visit", "activityId": "garden"})
        self.assertEqual((200, response), self.a.command(intent))
        after = self.audit()
        self.assertEqual(before["stateVersion"] + 1, after["stateVersion"])
        self.assertEqual(before["resourceAudit"], after["resourceAudit"])
        self.assertEqual(intent["commandId"], after["self"]["visits"][0]["commandId"])
        self.assertEqual([], self.b.observe()["self"]["visits"])
        self.assertEqual(404, self.b.request("GET", self.b.prefix + "/commands/" + intent["commandId"])[0])
        self.world.restart(); self.assertEqual(after, self.audit())

    def test_04_concurrent_same_visit_id_creates_one_record(self):
        self.walk(self.a, [2, 5]); before = self.audit()
        intent = self.intent(self.a, {"type": "visit", "activityId": "riverwalk"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.a.command(intent), range(2)))
        self.assertEqual(responses[0], responses[1]); self.assertEqual(200, responses[0][0])
        self.assertEqual(before["stateVersion"] + 1, self.audit()["stateVersion"])
        self.assertEqual(1, len(self.audit()["self"]["visits"]))

    def crash_visit(self, fault, code, committed):
        self.walk(self.a, [1, 6]); before = self.audit()
        intent = self.intent(self.a, {"type": "visit", "activityId": "garden"})
        with self.assertRaises((OSError, RuntimeError, ValueError)):
            self.a.request("POST", self.a.prefix + "/commands", intent, {"X-Test-Fault": fault})
        self.assertEqual(code, self.world.process.wait(timeout=10)); self.world.restart()
        self.assertEqual(before["stateVersion"] + int(committed), self.audit()["stateVersion"])
        self.assertEqual(200 if committed else 404, self.a.request("GET", self.a.prefix + "/commands/" + intent["commandId"])[0])
        self.assertEqual(200, self.a.command(intent)[0])
        self.assertEqual(1, len(self.audit()["self"]["visits"]))
        self.assertEqual(before["stateVersion"] + 1, self.audit()["stateVersion"])

    def test_05_visit_exit_before_commit_is_atomic(self): self.crash_visit("before-commit", 81, False)
    def test_06_visit_exit_after_commit_keeps_original_receipt(self): self.crash_visit("after-commit", 82, True)

    def test_07_arrival_without_visit_is_not_activity_completion(self):
        report = self.task(mission(commands=5))
        self.assertEqual("budget_exhausted", report["mission"]["status"])
        self.assertTrue(report["facts"]["goalReached"])
        self.assertFalse(report["facts"]["activityCompleted"])
        self.assertFalse(report["facts"]["returned"])
        self.assertEqual([], self.audit()["self"]["visits"])

    def test_08_activity_roundtrip_completed_resume_noop(self):
        first = self.task(max_steps=5)
        self.assertTrue(first["facts"]["goalReached"]); self.assertFalse(first["facts"]["activityCompleted"])
        final = self.task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertTrue(final["facts"]["activityCompleted"] and final["facts"]["returned"])
        self.assertEqual(11, final["budget"]["used"]["commands"])
        visit = [s for s in final["steps"] if s["action"]["type"] == "visit"]
        self.assertEqual(1, len(visit)); self.assertEqual(visit[0]["commandId"], final["facts"]["activityVisit"]["commandId"])
        before = self.audit(); self.task(); self.assertEqual(before, self.audit()); self.assertEqual(1, self.choice.calls)

    def test_09_pending_visit_after_service_exit_recovers_same_task(self):
        class Crash(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                if method == "POST" and payload.get("action", {}).get("type") == "visit": headers = {"X-Test-Fault": "after-commit"}
                return super().request(method, path, payload, headers)
        client = Crash(self.world.url, self.world.access["sessions"]["a1"]["token"])
        first = self.task(client=client); self.assertEqual("unknown", first["mission"]["status"])
        original = first["steps"][-1]["commandId"]
        self.assertEqual(82, self.world.process.wait(timeout=10)); self.world.restart()
        final = self.task(); self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(original, final["facts"]["activityVisit"]["commandId"])
        self.assertEqual(11, final["budget"]["used"]["commands"])
        self.assertEqual(1, len(self.audit()["self"]["visits"]))

    def test_10_previous_visit_cannot_complete_new_mission(self):
        self.walk(self.a, [1, 6]); prior, _ = self.send(self.a, {"type": "visit", "activityId": "garden"}); self.walk(self.a, [1, 1])
        first = self.task(max_steps=5)
        self.assertFalse(first["facts"]["activityCompleted"])
        final = self.task(); self.assertTrue(final["facts"]["activityCompleted"])
        self.assertNotEqual(prior["commandId"], final["facts"]["activityVisit"]["commandId"])
        self.assertEqual(2, len(self.audit()["self"]["visits"]))

    def test_11_invalid_catalog_binding_precedes_choice_and_actions(self):
        before = self.audit()
        for modify in [lambda j: j["goals"][0].update(target=[1, 5]), lambda j: j["goals"][0].update(activityId="invented")]:
            job = mission(); modify(job)
            with self.assertRaises(ValueError): self.task(job)
        self.assertEqual(0, self.choice.calls); self.assertEqual(before, self.audit())
        self.task(max_steps=1)
        modified = mission(); modified["goals"][0].pop("activityId")
        with self.assertRaises(ValueError): self.task(modified)

    def test_12_cost_baseline_uses_feasibility_and_counts_visit(self):
        final = self.task(choose=choose_lowest_cost)
        self.assertEqual("garden", final["mission"]["goal"]["id"])
        self.assertEqual("fixed-reference", final["decision"]["provider"]["kind"])
        self.assertEqual(11, final["budget"]["used"]["commands"])
        self.state = self.world.data / "estimate.json"
        choice = Choice("garden"); self.task(mission("estimate", commands=10), choose=choice, max_steps=0)
        garden = next(c for c in choice.contexts[0]["candidates"] if c["id"] == "garden")
        self.assertEqual(11, garden["estimatedCommands"]); self.assertFalse(garden["feasible"])
        self.assertIn("description", garden)
        with self.assertRaises(ValueError): choose_lowest_cost({"candidates": [{"id": "none", "feasible": False}]})

    def test_13_wrong_activity_in_success_receipt_retains_pending(self):
        class CorruptReceipt(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                status, result = super().request(method, path, payload, headers)
                if method == "POST" and payload.get("action", {}).get("type") == "visit" and status == 200: result["result"]["activityId"] = "lookout"
                return status, result
        client = CorruptReceipt(self.world.url, self.world.access["sessions"]["a1"]["token"])
        first = self.task(client=client)
        self.assertEqual("unknown", first["mission"]["status"]); self.assertFalse(first["facts"]["activityCompleted"])
        original = first["steps"][-1]["commandId"]
        final = self.task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(original, final["facts"]["activityVisit"]["commandId"])
        self.assertEqual(1, len(self.audit()["self"]["visits"]))

    def test_14_existing_schema2_world_unchanged_and_visit_unavailable(self):
        old = ActivityCandidate(self._testMethodName + "-r2", scenario=None, fixture="passage-v2-populated.sql")
        try:
            self.assertEqual(old.fixture_before, old.dump())
            a = old.client(); o = a.observe(); self.assertEqual("r2", o["rulesVersion"])
            self.assertEqual([], o.get("activities", []))
            _, denied = self.send(a, {"type": "visit", "activityId": "garden"}, expected=422)
            self.assertEqual("ACTIVITY_UNAVAILABLE", denied["error"]["code"])
            self.assertEqual(o, a.observe())
            old.stop(); before = old.dump(); old.start(); self.assertEqual(before, old.dump())
        finally: old.stop()

    def test_15_recent_visits_are_ordered_bounded_and_without_rewards(self):
        self.walk(self.a, [1, 6]); audit = self.audit()["resourceAudit"]
        ids = []
        for _ in range(101):
            intent, _ = self.send(self.a, {"type": "visit", "activityId": "garden"}); ids.append(intent["commandId"])
        visits = self.audit()["self"]["visits"]
        self.assertEqual(ids[1:], [v["commandId"] for v in visits])
        self.assertEqual(audit, self.audit()["resourceAudit"])
        self.assertEqual([], self.b.observe()["self"]["visits"])


if __name__ == "__main__":
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ActivityAcceptance)
    if len(sys.argv) > 1:
        names = set(sys.argv[1:]); suite = unittest.TestSuite(t for t in suite if t._testMethodName in names)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {"suite": "activity-http-v1", "decisionSource": "test-double-or-fixed-reference", "actualModelCalls": 0,
              "recordedAtUtc": datetime.now(timezone.utc).isoformat(), "passed": result.wasSuccessful(),
              "testsRun": result.testsRun, "tests": result.records, "dataRoot": str(RUN_ROOT.relative_to(ROOT)),
              "failures": [{"test": str(t), "detail": d} for t, d in result.failures + result.errors]}
    (RUN_ROOT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", RUN_ROOT / "results.json")
    raise SystemExit(0 if result.wasSuccessful() else 1)
