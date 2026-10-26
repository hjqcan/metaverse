#!/usr/bin/env python3
"""Independent HTTP acceptance of the two-land passage against real services."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import unittest
import uuid

from foundation_api import Candidate, DLL, EvidenceResult, FoundationAcceptance, ROOT
from foundation_agent import WorldClient, run_resident
from passage_agent import plan, run_trip

RUN_ROOT = ROOT / ".local/iter0002/api" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])


class PassageCandidate(Candidate):
    def __init__(self, name, scenario="passage-v1", fixture=False):
        self.data = RUN_ROOT / name
        self.data.mkdir(parents=True, mode=0o700)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, "WORLD_URL": self.url, "WORLD_DATA_DIR": str(self.data), "WORLD_ENABLE_FAULTS": "1"}
        self.env.pop("WORLD_SCENARIO", None)
        if scenario is not None:
            self.env["WORLD_SCENARIO"] = scenario
        if fixture:
            with sqlite3.connect(self.data / "world.db") as db:
                db.executescript((ROOT / "tests/fixtures/foundation-v1-populated.sql").read_text())
            access = {"sessions": {actor: {"token": "fixture-" + actor} for actor in ("a1", "a2")}}
            (self.data / "access.json").write_text(json.dumps(access))
            self.fixture_before = self.dump()
        self.process = self.log = None
        self.start()
        self.access = json.loads((self.data / "access.json").read_text())

    def dump(self):
        with sqlite3.connect(f"file:{self.data / 'world.db'}?mode=ro", uri=True) as db:
            return "\n".join(db.iterdump())


class PassageAcceptance(unittest.TestCase):
    send = FoundationAcceptance.send
    audit = FoundationAcceptance.audit
    tearDown = FoundationAcceptance.tearDown

    def setUp(self):
        self.world = PassageCandidate(self._testMethodName)
        self.a, self.b = self.world.client(), self.world.client("a2")
        self.trace = []

    def intent(self, client, action, command_id=None, version=None):
        o = client.observe()
        return {"schemaVersion": 1, "rulesVersion": o["rulesVersion"], "commandId": command_id or uuid.uuid4().hex,
                "expectedStateVersion": o["stateVersion"] if version is None else version, "action": action}

    def walk(self, client, goal):
        while client.observe()["self"]["position"] != list(goal):
            o = client.observe()
            route = plan(o, goal, False)
            self.assertIsNotNone(route, (o["self"]["position"], goal))
            nxt = route[0][0]
            self.send(client, {"type": "move", "dx": nxt[0]-o["self"]["position"][0], "dy": nxt[1]-o["self"]["position"][1]})

    def ready_builder(self, client=None, quantity=6):
        client = client or self.a
        self.send(client, {"type": "claim", "quantity": quantity})
        self.walk(client, [3, 3])

    def test_01_water_blocks_goal_and_walk_only_control(self):
        o = self.audit()
        self.assertEqual("r2", o["rulesVersion"])
        self.assertEqual("passage-v1", o["world"]["scenarioId"])
        self.assertEqual({(x, y) for x in (4, 5) for y in range(8)}, {tuple(p) for p in o["world"]["water"]})
        self.assertEqual(19, len(o["world"]["blocked"]))
        self.assertEqual([6, 1], o["world"]["goal"])
        self.assertIsNone(plan(o, o["world"]["goal"], False))
        result = run_trip(self.a)
        self.assertEqual("blocked", result["outcome"])
        self.assertEqual(0, result["commands"])
        self.assertEqual(o, self.audit())
        (self.world.data / "control-trace.json").write_text(json.dumps(result, indent=2))

    def test_02_progressive_bridge_changes_reachability(self):
        self.ready_builder()
        self.send(self.a, {"type": "move", "dx": 1, "dy": 0}, expected=422)
        self.send(self.a, {"type": "build", "recipeId": "bridge.v1", "at": [4, 3]})
        o = self.audit()
        self.assertIn([4, 3], o["world"]["water"])
        self.assertNotIn([4, 3], o["world"]["blocked"])
        self.assertIsNone(plan(o, o["world"]["goal"], False))
        self.walk(self.a, [4, 3])
        self.send(self.a, {"type": "move", "dx": 1, "dy": 0}, expected=422)
        self.send(self.a, {"type": "build", "recipeId": "bridge.v1", "at": [5, 3]})
        o = self.audit()
        self.assertEqual(2, len({e["entityId"] for e in o["entities"]}))
        self.assertTrue(all(e["definitionId"] == "bridge" and e["rulesVersion"] == "r2" for e in o["entities"]))
        self.walk(self.a, o["world"]["goal"])
        self.walk(self.a, [1, 1])
        result = run_trip(self.b)
        self.assertTrue(result["roundTripCompleted"])
        self.assertTrue(all(t["request"]["action"]["type"] == "move" for t in result["trace"]))
        self.assertEqual(0, self.b.observe()["self"]["inventory"]["wood"])
        self.assertEqual(6, self.audit()["depot"]["wood"])

    def test_03_invalid_construction_and_insufficient_material(self):
        self.ready_builder(quantity=3)
        for target in ([3, 3], [3, 2], [5, 3], [-1, 3], [9223372036854775807, 0]):
            before = self.audit()
            _, rejected = self.send(self.a, {"type": "build", "recipeId": "bridge.v1", "at": target}, expected=422)
            self.assertEqual("UNREACHABLE", rejected["error"]["code"])
            self.assertEqual("r2", rejected["rulesVersion"])
            self.assertEqual(before, self.audit())
        self.send(self.a, {"type": "build", "recipeId": "platform.v1", "at": [4, 3]}, expected=422)
        self.send(self.a, {"type": "build", "recipeId": "bridge.v1", "at": [4, 3]})
        self.walk(self.a, [4, 3])
        before = self.audit()
        _, rejected = self.send(self.a, {"type": "build", "recipeId": "bridge.v1", "at": [5, 3]}, expected=422)
        self.assertEqual("INSUFFICIENT_RESOURCE", rejected["error"]["code"])
        self.assertEqual(before, self.audit())

    def test_04_parallel_duplicate_bridge_and_parameter_conflict(self):
        self.ready_builder()
        intent = self.intent(self.a, {"type": "build", "recipeId": "bridge.v1", "at": [4, 3]}, "bridge-once")
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: self.a.command(intent), range(12)))
        self.assertEqual(200, replies[0][0])
        self.assertTrue(all(reply == replies[0] for reply in replies))
        different = {**intent, "action": {**intent["action"], "at": [4, 4]}}
        self.assertEqual(409, self.a.command(different)[0])
        self.assertEqual(1, len(self.audit()["entities"]))
        self.assertEqual(3, self.audit()["self"]["inventory"]["wood"])

    def test_05_two_actors_compete_for_same_water_cell(self):
        self.ready_builder(quantity=3)
        self.ready_builder(self.b, quantity=3)
        action = {"type": "build", "recipeId": "bridge.v1", "at": [4, 3]}
        pairs = [(c, self.intent(c, action)) for c in (self.a, self.b)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda p: p[0].command(p[1]), pairs))
        self.assertEqual([200, 409], sorted(s for s, _ in replies))
        loser = self.a if replies[0][0] != 200 else self.b
        _, rejected = self.send(loser, action, expected=409)
        self.assertEqual("CELL_OCCUPIED", rejected["error"]["code"])
        self.assertEqual(3, loser.observe()["self"]["inventory"]["wood"])
        self.assertEqual(3, self.audit()["resourceAudit"]["embodiedWood"])

    def test_06_failure_after_debit_rolls_back_bridge(self):
        self.ready_builder()
        before = self.audit()
        intent = self.intent(self.a, {"type": "build", "recipeId": "bridge.v1", "at": [4, 3]})
        status, error = self.a.request("POST", self.a.prefix + "/commands", intent, {"X-Test-Fault": "throw-after-debit"})
        self.assertEqual(503, status)
        self.assertIsNone(error["error"]["mutated"])
        self.assertEqual(before, self.audit())
        self.assertEqual(404, self.a.request("GET", self.a.prefix + "/commands/" + intent["commandId"])[0])
        self.assertEqual(200, self.a.command(intent)[0])
        self.assertNotIn([4, 3], self.audit()["world"]["blocked"])

    def crash_bridge(self, point, code, committed):
        self.ready_builder()
        before = self.audit()
        intent = self.intent(self.a, {"type": "build", "recipeId": "bridge.v1", "at": [4, 3]})
        try:
            self.a.request("POST", self.a.prefix + "/commands", intent, {"X-Test-Fault": point})
        except (OSError, ValueError):
            pass
        self.assertEqual(code, self.world.process.wait(timeout=10))
        self.world.restart()
        o = self.audit()
        self.assertEqual(int(committed), len(o["entities"]))
        if not committed:
            self.assertEqual(before, o)
        status, receipt = self.a.command(intent)
        self.assertEqual(200, status)
        self.assertEqual(1, len(self.audit()["entities"]))
        self.assertEqual(3, self.audit()["self"]["inventory"]["wood"])
        self.assertEqual(receipt, self.a.request("GET", self.a.prefix + "/commands/" + intent["commandId"])[1])

    def test_07_bridge_exit_before_commit(self):
        self.crash_bridge("before-commit", 81, False)

    def test_08_bridge_exit_after_commit(self):
        self.crash_bridge("after-commit", 82, True)

    def test_09_scenario_persists_and_cannot_be_reinterpreted(self):
        self.ready_builder()
        intent, receipt = self.send(self.a, {"type": "build", "recipeId": "bridge.v1", "at": [4, 3]})
        before = self.audit()
        self.world.stop()
        self.world.env.pop("WORLD_SCENARIO")
        self.world.start()
        self.assertEqual(before, self.audit())
        self.assertEqual((200, receipt), self.a.command(intent))
        self.world.stop()
        saved = self.world.dump()
        attempt = subprocess.run(["dotnet", str(DLL)], cwd=ROOT,
                                 env={**self.world.env, "WORLD_SCENARIO": "foundation-v1"},
                                 capture_output=True, timeout=15)
        self.assertNotEqual(0, attempt.returncode)
        self.assertEqual(saved, self.world.dump())
        self.world.start()

    def test_10_populated_schema_v1_keeps_original_facts(self):
        legacy = PassageCandidate(self._testMethodName + "_legacy", scenario=None, fixture=True)
        try:
            self.assertEqual(legacy.fixture_before, legacy.dump(), "startup must not rewrite legacy state")
            a = legacy.client()
            o = a.observe()
            self.assertEqual("r1", o["rulesVersion"])
            self.assertEqual([2, 1], o["self"]["position"])
            self.assertEqual(3, o["self"]["inventory"]["wood"])
            self.assertEqual(6, o["depot"]["wood"])
            self.assertEqual("platform", o["entities"][0]["definitionId"])
            with sqlite3.connect(legacy.data / "world.db") as db:
                old = list(db.execute("SELECT command_id,status_code,result_json FROM receipts"))
            for command_id, code, body in old:
                self.assertEqual((code, json.loads(body)), a.request("GET", a.prefix + "/commands/" + command_id))
            self.assertEqual(400, a.command(self.intent(a, {"type": "build", "recipeId": "bridge.v1", "at": [2, 2]}))[0])
            self.assertTrue(run_resident(legacy.client("a2"))["goalReached"])
            self.assertEqual(o["entities"], a.observe()["entities"])
            legacy.restart()
            self.assertEqual(o["resourceAudit"], a.observe()["resourceAudit"])
        finally:
            legacy.stop()

    def test_11_fixed_builder_and_free_traveler_comparison(self):
        control = run_trip(self.a)
        builder = run_trip(self.a, True, pending_path=self.world.data / "builder.pending.json")
        traveler = run_trip(self.b)
        self.assertEqual("blocked", control["outcome"])
        for result in (builder, traveler):
            self.assertEqual("completed", result["outcome"], result)
            self.assertEqual(0, result["modelCalls"])
            self.assertLessEqual(result["commands"], 100)
        actions = [t["request"]["action"] for t in builder["trace"]]
        self.assertEqual([6], [a["quantity"] for a in actions if a["type"] == "claim"])
        self.assertEqual(2, sum(a["type"] == "build" for a in actions))
        self.assertTrue(all(t["request"]["action"]["type"] == "move" for t in traveler["trace"]))
        self.assertEqual(6, self.audit()["depot"]["wood"])
        self.assertEqual(0, self.audit()["resourceAudit"]["inventoryWood"])
        self.assertEqual(6, self.audit()["resourceAudit"]["embodiedWood"])
        self.assertFalse((self.world.data / "builder.pending.json").exists())
        (self.world.data / "comparison.json").write_text(json.dumps({"control": control, "builder": builder, "traveler": traveler}, ensure_ascii=False, indent=2))

    def test_12_rules_rejection_and_all_state_envelopes(self):
        o = self.audit()
        intent = {**self.intent(self.a, {"type": "claim", "quantity": 1}), "rulesVersion": "r1"}
        status, rejected = self.a.command(intent)
        self.assertEqual(409, status)
        self.assertEqual("RULES_VERSION_MISMATCH", rejected["error"]["code"])
        for path in ("/events?after=0", "/events?after=99999", "/commands/missing", "/commands/" + intent["commandId"]):
            _, body = self.a.request("GET", self.a.prefix + path)
            self.assertEqual("r2", body["rulesVersion"], path)
        self.assertEqual(o, self.audit())

    def test_13_resident_unknown_bridge_recovers_same_trip_and_id(self):
        class CrashClient(WorldClient):
            def command(self, intent):
                headers = {"X-Test-Fault": "after-commit"} if intent["action"]["type"] == "build" else None
                return self.request("POST", self.prefix + "/commands", intent, headers)

        pending = self.world.data / "resident.pending.json"
        crashed = CrashClient(self.world.url, self.world.access["sessions"]["a1"]["token"])
        first = run_trip(crashed, True, pending_path=pending)
        self.assertEqual("unknown", first["outcome"])
        self.assertEqual(82, self.world.process.wait(timeout=10))
        original = json.loads(pending.read_text())["request"]
        self.world.restart()
        second = run_trip(self.a, True, pending_path=pending)
        self.assertEqual("completed", second["outcome"])
        self.assertEqual(original, second["trace"][0]["request"])
        self.assertTrue(second["trace"][0]["recovery"])
        self.assertEqual([1, 1], second["final"]["self"]["position"], "recovery must return to the original trip origin")
        self.assertEqual(2, len(self.audit()["entities"]))
        self.assertEqual(6, self.audit()["depot"]["wood"])
        self.assertFalse(pending.exists())


if __name__ == "__main__":
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PassageAcceptance)
    if len(sys.argv) > 1:
        selected = set(sys.argv[1:])
        suite = unittest.TestSuite(t for t in suite if t._testMethodName in selected)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {"suite": "passage-http-v1", "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "passed": result.wasSuccessful(), "testsRun": result.testsRun, "tests": result.records,
              "failures": [{"test": str(t), "detail": d} for t, d in result.failures + result.errors],
              "dataRoot": str(RUN_ROOT.relative_to(ROOT))}
    (RUN_ROOT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", RUN_ROOT / "results.json")
    raise SystemExit(0 if result.wasSuccessful() else 1)
