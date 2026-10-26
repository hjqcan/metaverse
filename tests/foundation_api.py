#!/usr/bin/env python3
"""Black-box acceptance for ITER-0001; uses dedicated processes and data only."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from foundation_agent import WorldClient, run_resident  # noqa: E402

DLL = ROOT / "src/World.Server/bin/Debug/net10.0/World.Server.dll"
RUN_ROOT = ROOT / ".local/iter0001/api" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])


class Candidate:
    def __init__(self, name, faults=True):
        self.data = RUN_ROOT / name
        self.data.mkdir(parents=True, mode=0o700)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, "WORLD_URL": self.url, "WORLD_DATA_DIR": str(self.data), "WORLD_SCENARIO": "foundation-v1", "WORLD_ENABLE_FAULTS": "1" if faults else "0"}
        self.process = None
        self.log = None
        self.start()
        self.access = json.loads((self.data / "access.json").read_text())

    def start(self):
        self.log = (self.data / "server.log").open("a")
        self.process = subprocess.Popen(["dotnet", str(DLL)], cwd=ROOT, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"Candidate exited {self.process.returncode}; see {self.data / 'server.log'}")
            try:
                status, health = WorldClient(self.url, "").request("GET", "/healthz")
                if status == 200:
                    self.health = health
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        self.stop()
        raise RuntimeError(f"Candidate startup timed out; see {self.data / 'server.log'}")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()  # Only the exact dedicated process started above.
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()

    def restart(self):
        self.stop()
        self.start()

    def client(self, actor="a1"):
        return WorldClient(self.url, self.access["sessions"][actor]["token"])

    def issue(self, actor, ttl):
        self.stop()
        output = self.data / ("issued-" + actor + ".json")
        result = subprocess.run(["dotnet", str(DLL), "issue-session", "--actor", actor, "--ttl-seconds", str(ttl), "--output", str(output)],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RuntimeError("Offline session command failed: " + result.stderr)
        issued = json.loads(output.read_text())
        self.start()
        return WorldClient(self.url, issued["token"])


class FoundationAcceptance(unittest.TestCase):
    def setUp(self):
        self.world = Candidate(self._testMethodName)
        self.a = self.world.client()
        self.b = self.world.client("a2")
        self.trace = []

    def tearDown(self):
        self.world.stop()
        (self.world.data / "http-trace.json").write_text(json.dumps(self.trace, ensure_ascii=False, indent=2) + "\n")
        # Privileged verifier after the service has stopped: independent of API audit calculations.
        with sqlite3.connect(f"file:{self.world.data / 'world.db'}?mode=ro", uri=True) as connection:
            balances = {}
            for source, destination, quantity in connection.execute("SELECT source_account,destination_account,quantity FROM resource_ledger"):
                balances[source] = balances.get(source, 0) - quantity
                balances[destination] = balances.get(destination, 0) + quantity
            self.assertEqual(-12, balances.pop("initial-issuance"))
            self.assertEqual(connection.execute("SELECT depot_wood FROM worlds").fetchone()[0], balances.pop("depot", 0))
            for actor, wood in connection.execute("SELECT actor_id,wood FROM residents"):
                self.assertEqual(wood, balances.pop("inventory:" + actor, 0))
            for entity, wood in connection.execute("SELECT entity_id,embodied_wood FROM entities"):
                self.assertEqual(wood, balances.pop("entity:" + entity, 0))
            self.assertEqual({}, balances, "unknown resource accounts remain")
            version = connection.execute("SELECT state_version FROM worlds").fetchone()[0]
            self.assertEqual(version + 1, connection.execute("SELECT count(*) FROM events").fetchone()[0])

    def intent(self, client, action, command_id=None, version=None):
        observed = client.observe()
        return {"schemaVersion": 1, "rulesVersion": "r1", "commandId": command_id or uuid.uuid4().hex,
                "expectedStateVersion": observed["stateVersion"] if version is None else version, "action": action}

    def send(self, client, action, command_id=None, version=None, expected=200, headers=None):
        intent = self.intent(client, action, command_id, version)
        status, body = client.request("POST", client.prefix + "/commands", intent, headers)
        self.trace.append({"request": intent, "status": status, "response": body})
        self.assertEqual(expected, status, body)
        return intent, body

    def audit(self, client=None):
        observation = (client or self.a).observe()
        audit = observation["resourceAudit"]
        self.assertEqual(12, audit["issuedWood"])
        self.assertEqual(12, audit["depotWood"] + audit["inventoryWood"] + audit["embodiedWood"])
        self.assertTrue(audit["conserved"])
        self.assertTrue(all(audit[key] >= 0 for key in ("depotWood", "inventoryWood", "embodiedWood")))
        return observation

    def test_01_initial_identity_and_world_boundary(self):
        o = self.audit()
        self.assertEqual([1, 1], o["self"]["position"])
        self.assertEqual(0, o["stateVersion"])
        self.assertEqual(1, o["eventCursor"])
        self.assertEqual(12, o["depot"]["wood"])
        self.assertEqual([[3, 0], [3, 1], [3, 2]], o["world"]["blocked"])
        self.assertTrue(all("inventory" not in resident for resident in o["residents"]))
        self.assertEqual(401, WorldClient(self.world.url, "invalid").request("GET", self.a.prefix + "/observation")[0])
        status, body = self.a.request("GET", "/v1/worlds/other/observation")
        self.assertEqual(404, status, body)
        self.assertEqual(0o600, (self.world.data / "access.json").stat().st_mode & 0o777)

    def test_02_move_rejects_wall_boundary_and_invalid_shape(self):
        self.send(self.a, {"type": "move", "dx": 1, "dy": 0})
        old = self.a.observe()
        _, wall = self.send(self.a, {"type": "move", "dx": 1, "dy": 0}, expected=422)
        self.assertEqual("UNREACHABLE", wall["error"]["code"])
        self.assertEqual(old, self.a.observe())
        for action in [{"type": "move", "dx": 2, "dy": 0}, {"type": "move", "dx": 2147483647, "dy": 2147483647}]:
            self.send(self.a, action, expected=422)
        for action in [{"type": "move", "dx": 1.5, "dy": 0}, {"type": "claim", "quantity": -1},
                       {"type": "claim", "quantity": 1.5}, {"type": "claim", "quantity": 13},
                       {"type": "build", "recipeId": "platform.v1", "at": [1, 1, 1]}]:
            self.send(self.a, action, expected=400)
        self.send(self.a, {"type": "move", "dx": 0, "dy": -1})
        self.send(self.a, {"type": "move", "dx": 0, "dy": -1}, expected=422)
        self.audit()

    def test_03_finite_source_build_and_stable_rejection(self):
        self.send(self.a, {"type": "claim", "quantity": 4})
        _, built = self.send(self.a, {"type": "build", "recipeId": "platform.v1", "at": [2, 1]})
        o = self.audit()
        self.assertEqual(8, o["depot"]["wood"])
        self.assertEqual(1, o["self"]["inventory"]["wood"])
        self.assertEqual(built["result"]["entityId"], o["entities"][0]["entityId"])
        self.assertEqual(3, o["entities"][0]["embodiedWood"])
        denied, response = self.send(self.a, {"type": "build", "recipeId": "platform.v1", "at": [1, 1]}, expected=422)
        self.assertEqual("INSUFFICIENT_RESOURCE", response["error"]["code"])
        self.send(self.a, {"type": "claim", "quantity": 3})
        self.assertEqual((422, response), self.a.command(denied))
        self.assertEqual(1, len(self.audit()["entities"]))

    def test_04_parallel_duplicates_and_normalized_payload(self):
        intent = self.intent(self.a, {"type": "claim", "quantity": 4}, "parallel-same")
        with ThreadPoolExecutor(max_workers=12) as pool:
            replies = list(pool.map(lambda _: self.a.command(intent), range(16)))
        self.assertTrue(all(reply == replies[0] for reply in replies))
        self.assertEqual(200, replies[0][0])
        reordered = {key: intent[key] for key in reversed(intent)}
        reordered["action"] = {"quantity": 4, "type": "claim"}
        self.assertEqual(replies[0], self.a.command(reordered))
        changed = {**intent, "action": {"type": "claim", "quantity": 5}}
        status, conflict = self.a.command(changed)
        self.assertEqual(409, status)
        self.assertEqual("IDEMPOTENCY_CONFLICT", conflict["error"]["code"])
        self.assertEqual(replies[0], self.a.request("GET", self.a.prefix + "/commands/parallel-same"))
        self.assertEqual(404, self.b.request("GET", self.b.prefix + "/commands/parallel-same")[0])
        self.assertEqual(1, self.audit()["stateVersion"])

    def test_05_compete_for_last_material(self):
        first = self.intent(self.a, {"type": "claim", "quantity": 12})
        second = self.intent(self.b, {"type": "claim", "quantity": 12})
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda pair: pair[0].command(pair[1]), [(self.a, first), (self.b, second)]))
        self.assertEqual([200, 409], sorted(status for status, _ in replies))
        loser = self.a if replies[0][0] != 200 else self.b
        self.send(loser, {"type": "claim", "quantity": 12}, expected=422)
        o = self.audit()
        self.assertEqual(0, o["depot"]["wood"])
        self.assertEqual(12, o["resourceAudit"]["inventoryWood"])

    def test_06_compete_for_build_cell(self):
        self.send(self.a, {"type": "claim", "quantity": 3})
        self.send(self.b, {"type": "claim", "quantity": 3})
        self.send(self.b, {"type": "move", "dx": 1, "dy": 0})
        action = {"type": "build", "recipeId": "platform.v1", "at": [2, 1]}
        intents = [(self.a, self.intent(self.a, action)), (self.b, self.intent(self.b, action))]
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda pair: pair[0].command(pair[1]), intents))
        self.assertEqual([200, 409], sorted(status for status, _ in replies))
        loser = self.a if replies[0][0] != 200 else self.b
        _, conflict = self.send(loser, action, expected=409)
        self.assertEqual("CELL_OCCUPIED", conflict["error"]["code"])
        o = self.audit()
        self.assertEqual(1, len(o["entities"]))
        self.assertEqual(3, loser.observe()["self"]["inventory"]["wood"])

    def test_07_identity_override_revoke_and_renew(self):
        intent = self.intent(self.a, {"type": "claim", "quantity": 1})
        for override in [{"actorId": "a2"}, {"operatorId": "someone"}, {"identity": {"actorId": "a2"}}]:
            self.assertEqual(403, self.a.command({**intent, **override})[0])
        self.assertEqual(403, self.a.command({**intent, "action": {**intent["action"], "actorId": "a2"}})[0])
        self.assertEqual(400, self.a.command({**intent, "surprise": True})[0])
        self.assertEqual(200, self.a.command(intent)[0])
        self.assertEqual(204, self.a.request("DELETE", "/v1/session")[0])
        self.assertEqual(401, self.a.command(intent)[0])
        self.assertEqual(401, self.a.request("GET", self.a.prefix + "/events?after=0")[0])
        self.world.restart()
        self.assertEqual(401, self.a.request("GET", self.a.prefix + "/observation")[0])
        renewed = self.world.issue("a1", 3600)
        status, receipt = renewed.request("GET", renewed.prefix + "/commands/" + intent["commandId"])
        self.assertEqual(200, status, receipt)
        self.assertEqual(1, self.audit(renewed)["self"]["inventory"]["wood"])
        self.assertEqual(401, self.a.request("GET", self.a.prefix + "/observation")[0])

    def test_08_expired_session(self):
        expired = self.world.issue("a2", -1)
        self.assertEqual(401, expired.request("GET", expired.prefix + "/observation")[0])
        self.assertEqual(401, self.b.request("GET", self.b.prefix + "/observation")[0])
        self.audit()

    def test_09_restart_preserves_world_and_receipts(self):
        self.send(self.a, {"type": "claim", "quantity": 4})
        intent, receipt = self.send(self.a, {"type": "build", "recipeId": "platform.v1", "at": [2, 1]})
        self.send(self.b, {"type": "move", "dx": 0, "dy": 1})
        before = self.audit()
        events = self.a.request("GET", self.a.prefix + "/events?after=0")
        self.world.restart()
        self.assertEqual(before, self.audit())
        self.assertEqual(events, self.a.request("GET", self.a.prefix + "/events?after=0"))
        self.assertEqual((200, receipt), self.a.command(intent))

    def test_10_events_are_ordered_and_paginated(self):
        for client in (self.a, self.b):
            for i in range(60):
                self.send(client, {"type": "move", "dx": 1 if i % 2 == 0 else -1, "dy": 0})
        status, first = self.a.request("GET", self.a.prefix + "/events?after=0")
        self.assertEqual(200, status)
        self.assertEqual(100, len(first["events"]))
        self.assertEqual(100, first["nextCursor"])
        status, second = self.a.request("GET", self.a.prefix + "/events?after=100")
        seq = [event["seq"] for event in first["events"] + second["events"]]
        self.assertEqual(list(range(1, 122)), seq)
        self.assertEqual(121, second["nextCursor"])
        status, empty = self.a.request("GET", self.a.prefix + "/events?after=121")
        self.assertEqual([], empty["events"])
        self.assertEqual(121, empty["nextCursor"])
        self.assertEqual(409, self.a.request("GET", self.a.prefix + "/events?after=9999")[0])
        self.assertEqual(120, self.audit()["stateVersion"])

    def test_11_exception_rolls_back_and_original_id_retries(self):
        self.send(self.a, {"type": "claim", "quantity": 4})
        before = self.audit()
        intent = self.intent(self.a, {"type": "build", "recipeId": "platform.v1", "at": [2, 1]})
        status, unavailable = self.a.request("POST", self.a.prefix + "/commands", intent, {"X-Test-Fault": "throw-after-debit"})
        self.assertEqual(503, status)
        self.assertIsNone(unavailable["error"]["mutated"], "an infrastructure error must not claim definitely unchanged")
        self.assertEqual(before, self.audit())
        self.assertEqual(404, self.a.request("GET", self.a.prefix + "/commands/" + intent["commandId"])[0])
        self.assertEqual(200, self.a.command(intent)[0])
        self.assertEqual(1, len(self.audit()["entities"]))

    def crash_case(self, point, code, committed):
        self.send(self.a, {"type": "claim", "quantity": 4})
        before = self.audit()
        intent = self.intent(self.a, {"type": "build", "recipeId": "platform.v1", "at": [2, 1]})
        try:
            self.a.request("POST", self.a.prefix + "/commands", intent, {"X-Test-Fault": point})
        except (OSError, ValueError):
            pass
        self.assertEqual(code, self.world.process.wait(timeout=10))
        self.world.restart()
        recovered = self.audit()
        if committed:
            self.assertEqual(1, len(recovered["entities"]))
        else:
            self.assertEqual(before, recovered)
        status, receipt = self.a.command(intent)
        self.assertEqual(200, status, receipt)
        self.assertEqual(1, len(self.audit()["entities"]))
        self.assertEqual(2, self.audit()["stateVersion"])
        self.assertEqual(1, self.audit()["self"]["inventory"]["wood"])

    def test_12_exit_before_commit(self):
        self.crash_case("before-commit", 81, False)

    def test_13_exit_after_commit_before_response(self):
        self.crash_case("after-commit", 82, True)

    def test_14_fault_injection_is_disabled_by_default(self):
        self.world.stop()
        self.world.env["WORLD_ENABLE_FAULTS"] = "0"
        self.world.start()
        self.send(self.a, {"type": "claim", "quantity": 4}, headers={"X-Test-Fault": "before-commit"})
        self.assertIsNone(self.world.process.poll())
        self.assertEqual(4, self.audit()["self"]["inventory"]["wood"])

    def test_15_fixed_resident_reaches_goal_without_work(self):
        result = run_resident(self.b)
        self.assertTrue(result["goalReached"])
        self.assertLessEqual(result["commands"], 100)
        self.assertEqual(0, result["modelCalls"])
        self.assertEqual([5, 1], self.b.observe()["self"]["position"])
        self.assertEqual(12, self.audit()["depot"]["wood"])
        (self.world.data / "resident-trace.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    def test_16_same_id_in_different_actor_scopes(self):
        self.send(self.a, {"type": "claim", "quantity": 4}, command_id="same-id")
        self.send(self.b, {"type": "claim", "quantity": 4}, command_id="same-id")
        self.assertEqual(8, self.audit()["resourceAudit"]["inventoryWood"])
        for client, actor in ((self.a, "a1"), (self.b, "a2")):
            status, receipt = client.request("GET", client.prefix + "/commands/same-id")
            self.assertEqual(200, status)
            self.assertEqual(actor, receipt["identity"]["actorId"])

    def test_17_separate_candidates_do_not_share_tokens_or_assets(self):
        # Added after the initial implementation: a second actual service, not an API alias.
        other = Candidate(self._testMethodName + "_other", faults=False)
        try:
            self.send(self.a, {"type": "claim", "quantity": 4})
            foreign = WorldClient(other.url, self.world.access["sessions"]["a1"]["token"])
            self.assertEqual(401, foreign.request("GET", foreign.prefix + "/observation")[0])
            untouched = other.client().observe()
            self.assertEqual(0, untouched["stateVersion"])
            self.assertEqual(12, untouched["depot"]["wood"])
            self.assertEqual(0, untouched["self"]["inventory"]["wood"])
            self.assertEqual(8, self.audit()["depot"]["wood"])
        finally:
            other.stop()


class EvidenceResult(unittest.TextTestResult):
    def startTest(self, test):
        self.started = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        failed = {str(item) for item, _ in self.failures + self.errors}
        self.records.append({"test": test.id(), "passed": str(test) not in failed, "seconds": time.monotonic() - self.started})
        super().stopTest(test)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []


if __name__ == "__main__":
    if not DLL.exists():
        raise SystemExit("Build src/World.Server first: dotnet build src/World.Server")
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FoundationAcceptance)
    if len(sys.argv) > 1:
        selected = set(sys.argv[1:])
        suite = unittest.TestSuite(test for test in suite if test._testMethodName in selected)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {"suite": "foundation-http-v1", "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "passed": result.wasSuccessful(), "testsRun": result.testsRun, "tests": result.records,
              "failures": [{"test": str(test), "detail": detail} for test, detail in result.failures + result.errors],
              "dataRoot": str(RUN_ROOT.relative_to(ROOT))}
    (RUN_ROOT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", RUN_ROOT / "results.json")
    raise SystemExit(0 if result.wasSuccessful() else 1)
