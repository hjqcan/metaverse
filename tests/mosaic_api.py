#!/usr/bin/env python3
"""Independent mosaic acceptance: real HTTP/SQLite, explicitly labelled model doubles."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import socket
import sqlite3
import sys
import unittest
import uuid

from foundation_api import Candidate, EvidenceResult, FoundationAcceptance, ROOT
from activities_api import ActivityAcceptance
from postcards_api import PostcardChoice, postcard_mission
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice

RUN_ROOT = ROOT / ".local/iter0006/api" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])
PATCH = [{"x": 1, "y": 2, "color": "river"}, {"x": 2, "y": 2, "color": "river"}]


class MosaicCandidate(Candidate):
    def __init__(self, name, scenario="mosaic-v1", fixture=None):
        self.data = RUN_ROOT / name
        self.data.mkdir(parents=True, mode=0o700)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); self.port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, "WORLD_URL": self.url, "WORLD_DATA_DIR": str(self.data), "WORLD_ENABLE_FAULTS": "1"}
        self.env.pop("WORLD_SCENARIO", None)
        if scenario: self.env["WORLD_SCENARIO"] = scenario
        if fixture:
            with sqlite3.connect(self.data / "world.db") as db:
                db.executescript((ROOT / "tests/fixtures" / fixture).read_text())
            (self.data / "access.json").write_text(json.dumps({"sessions": {a: {"token": "fixture-r4-" + a} for a in ["a1", "a2"]}}))
            self.fixture_before = self.dump()
        self.process = self.log = None
        self.start()
        self.access = json.loads((self.data / "access.json").read_text())

    def dump(self):
        with sqlite3.connect(f"file:{self.data / 'world.db'}?mode=ro", uri=True) as db:
            return (db.execute("PRAGMA user_version").fetchone()[0], "\n".join(db.iterdump()))


def mosaic_mission(name="mosaic-test", commands=20):
    spec = json.loads((ROOT / "examples/mosaic/first.json").read_text())
    spec["missionId"] = name; spec["budgets"]["commands"] = commands
    return spec


class MosaicChoice(Choice):
    def __init__(self, patch=None):
        super().__init__("garden"); self.patch = deepcopy(patch if patch is not None else PATCH)

    def __call__(self, context):
        return {**super().__call__(context), "mosaicPatch": deepcopy(self.patch)}


class MosaicAcceptance(unittest.TestCase):
    audit = FoundationAcceptance.audit
    send = FoundationAcceptance.send
    intent = ActivityAcceptance.intent
    walk = ActivityAcceptance.walk

    def setUp(self):
        self.world = MosaicCandidate(self._testMethodName)
        self.a, self.b = self.world.client(), self.world.client("a2")
        self.trace, self.reports = [], []
        self.state = self.world.data / "mission.json"
        self.choice = MosaicChoice()

    def tearDown(self):
        (self.world.data / "reports.json").write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + "\n")
        before = self.a.observe() if self.world.process.poll() is None else None
        FoundationAcceptance.tearDown(self)
        with sqlite3.connect(f"file:{self.world.data / 'world.db'}?mode=ro", uri=True) as db:
            self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
            edits = [json.loads(row[0]) for row in db.execute("SELECT event_json FROM events ORDER BY state_version")]
            edits = [e for e in edits if e["type"] == "mosaic_painted"]
            self.assertEqual(len(edits), db.execute("SELECT count(*) FROM mosaic_edits").fetchone()[0])
            board = [{"x": i % 5, "y": i // 5, "color": "blank", "authorActorId": None, "commandId": None, "stateVersion": None} for i in range(25)]
            for revision, edit in enumerate(edits, 1):
                self.assertEqual((revision - 1, revision), (edit["baseRevision"], edit["revision"]))
                self.assertEqual(edit["actorId"], edit["authorActorId"])
                receipt = json.loads(db.execute("SELECT result_json FROM receipts WHERE actor_id=? AND command_id=?", (edit["authorActorId"], edit["commandId"])).fetchone()[0])
                self.assertEqual("committed", receipt["status"])
                for key in ["activityId", "authorActorId", "commandId", "visitCommandId", "baseRevision", "revision", "patch", "stateVersion", "paintedAtUtc", "position"]:
                    self.assertEqual(edit[key], receipt["result"][key])
                visit = db.execute("SELECT activity_id,x,y,state_version FROM visits WHERE actor_id=? AND command_id=?", (edit["authorActorId"], edit["visitCommandId"])).fetchone()
                self.assertEqual(("garden", 1, 6), visit[:3]); self.assertLess(visit[3], edit["stateVersion"])
                self.assertEqual(0, db.execute("SELECT count(*) FROM resource_ledger WHERE command_id=?", (edit["commandId"],)).fetchone()[0])
                for c in edit["patch"]:
                    self.assertNotEqual(board[c["y"] * 5 + c["x"]]["color"], c["color"])
                    board[c["y"] * 5 + c["x"]] = {**c, "authorActorId": edit["authorActorId"], "commandId": edit["commandId"], "stateVersion": edit["stateVersion"]}
            if before:
                self.assertEqual(len(edits), before["mosaic"]["revision"])
                self.assertEqual(board, before["mosaic"]["cells"])

    def visit(self, client=None):
        client = client or self.a; self.walk(client, (1, 6))
        intent, _ = self.send(client, {"type": "visit", "activityId": "garden"})
        return intent["commandId"]

    def action(self, visit, patch=None, revision=None):
        return {"type": "mosaic", "activityId": "garden", "visitCommandId": visit,
                "expectedMosaicRevision": self.a.observe()["mosaic"]["revision"] if revision is None else revision,
                "patch": deepcopy(PATCH if patch is None else patch)}

    def task(self, spec=None, client=None, choose=None, **kwargs):
        r = run_mission(client or self.a, spec or mosaic_mission(), self.state, choose or self.choice, **kwargs)
        self.reports.append(r); return r

    def test_01_public_tiles_authorship_restart_and_immutable_history(self):
        o = self.audit(); self.assertEqual("r5", o["rulesVersion"])
        self.assertEqual(25, len(o["mosaic"]["cells"])); self.assertEqual(0, o["mosaic"]["revision"])
        self.assertEqual({"blank"}, {c["color"] for c in o["mosaic"]["cells"]})
        visit = self.visit(); intent, reply = self.send(self.a, self.action(visit))
        own, peer = self.a.observe(), self.b.observe()
        self.assertEqual(own["mosaic"], peer["mosaic"]); self.assertEqual(own["mosaicEdits"], peer["mosaicEdits"])
        self.assertEqual([], peer["self"]["mosaicEdits"])
        self.assertEqual(intent["commandId"], own["mosaic"]["cells"][11]["commandId"])
        self.assertEqual("a1", own["mosaic"]["cells"][11]["authorActorId"])
        self.assertEqual(reply["result"]["revision"], 1)
        self.world.restart(); self.assertEqual(own, self.a.observe())
        with sqlite3.connect(self.world.data / "world.db") as db:
            with self.assertRaises(sqlite3.DatabaseError): db.execute("DELETE FROM mosaic_edits")
            with self.assertRaises(sqlite3.DatabaseError): db.execute("UPDATE mosaic_edits SET revision=99")

    def test_02_location_identity_visit_and_independent_postcard_slots(self):
        for extra, expected, code in [({}, 422, "NOT_AT_ACTIVITY"), ({"activityId": "riverwalk"}, 422, "MOSAIC_LOCATION_UNAVAILABLE"), ({"actorId": "a2"}, 403, "IDENTITY_OVERRIDE")]:
            _, r = self.send(self.a, {**self.action("missing"), **extra}, expected=expected); self.assertEqual(code, r["error"]["code"])
        other = self.visit(self.b); self.walk(self.a, (1, 6))
        for visit in ["missing", other]:
            _, r = self.send(self.a, self.action(visit), expected=422); self.assertEqual("VISIT_REQUIRED", r["error"]["code"])
        own = self.visit(); self.send(self.a, {"type": "postcard", "activityId": "garden", "visitCommandId": own, "text": "同一次到访，也可以给画作留一句话。"})
        self.send(self.a, self.action(own)); self.assertEqual(1, len(self.a.observe()["postcards"]))

    def test_03_original_id_patch_order_and_one_edit_per_visit(self):
        visit = self.visit(); original, reply = self.send(self.a, self.action(visit))
        same = deepcopy(original); same["action"]["patch"].reverse()
        before = self.audit(); self.assertEqual((200, reply), self.a.command(same))
        changed = deepcopy(original); changed["action"]["patch"][0]["color"] = "leaf"
        self.assertEqual("IDEMPOTENCY_CONFLICT", self.a.command(changed)[1]["error"]["code"])
        _, r = self.send(self.a, self.action(visit, [{"x": 0, "y": 0, "color": "leaf"}]), expected=409)
        self.assertEqual("VISIT_ALREADY_PAINTED", r["error"]["code"]); self.assertEqual(before, self.audit())

    def test_04_parallel_duplicate_and_two_authors_cannot_lose_update(self):
        one = self.visit(); two = self.visit(self.b)
        original = self.intent(self.a, self.action(one))
        with ThreadPoolExecutor(max_workers=2) as pool: replies = list(pool.map(lambda _: self.a.command(original), range(2)))
        self.assertEqual(replies[0], replies[1]); self.assertEqual(1, self.a.observe()["mosaic"]["revision"])
        _, r = self.send(self.b, self.action(two, [{"x": 0, "y": 0, "color": "leaf"}], revision=0), expected=409)
        self.assertEqual("MOSAIC_CHANGED", r["error"]["code"])
        self.send(self.b, self.action(two, [{"x": 0, "y": 0, "color": "leaf"}]))
        self.assertEqual(2, self.audit()["mosaic"]["revision"])

    def test_05_atomic_batch_strict_shape_and_same_color_reject(self):
        visit = self.visit(); before = self.audit()
        bad = [[], PATCH * 2, [{"x": 0, "y": 0, "color": "url(evil)"}], [{"x": True, "y": 0, "color": "river"}],
               [{"x": 5, "y": 0, "color": "river"}], [{"x": 0, "y": 0, "color": "river", "html": "x"}],
               [{"x": i % 5, "y": i // 5, "color": "river"} for i in range(9)]]
        for patch in bad: self.send(self.a, self.action(visit, patch), expected=400)
        self.send(self.a, self.action(visit, PATCH + [{"x": 0, "y": 0, "color": "blank"}]), expected=422)
        self.assertEqual(before, self.audit())
        eight = [{"x": i % 5, "y": i // 5, "color": "sun"} for i in range(8)]
        self.send(self.a, self.action(visit, eight)); self.assertEqual(8, sum(c["color"] != "blank" for c in self.audit()["mosaic"]["cells"]))
        visit = self.visit(); self.send(self.a, self.action(visit, [{"x": 0, "y": 0, "color": "blank"}]))
        self.assertEqual("a1", self.audit()["mosaic"]["cells"][0]["authorActorId"])

    def crash(self, stage, code, committed):
        visit = self.visit(); original = self.intent(self.a, self.action(visit)); before = self.audit()
        with self.assertRaises((OSError, ValueError)): self.a.request("POST", self.a.prefix + "/commands", original, {"X-Test-Fault": stage})
        self.assertEqual(code, self.world.process.wait(timeout=10)); self.world.restart()
        observed = self.audit(); self.assertEqual(int(committed), observed["mosaic"]["revision"])
        self.assertEqual(before["stateVersion"] + int(committed), observed["stateVersion"])
        self.assertEqual(200, self.a.command(original)[0]); self.assertEqual(1, self.audit()["mosaic"]["revision"])

    def test_06_before_commit_exit_rolls_back_entire_patch(self): self.crash("before-commit", 81, False)
    def test_07_after_commit_exit_retains_entire_patch(self): self.crash("after-commit", 82, True)

    def test_08_budget_stops_after_visit_before_paint(self):
        r = self.task(mosaic_mission(commands=6)); self.assertEqual("budget_exhausted", r["mission"]["status"])
        self.assertTrue(r["facts"]["activityCompleted"]); self.assertFalse(r["facts"]["mosaicPainted"])
        self.assertEqual(0, self.audit()["mosaic"]["revision"])

    def test_09_pause_resume_uses_one_decision_and_completed_is_noop(self):
        first = self.task(max_steps=6); self.assertTrue(first["facts"]["activityCompleted"])
        self.assertFalse(first["facts"]["mosaicPainted"])
        final = self.task(); self.assertEqual("completed", final["mission"]["status"])
        self.assertTrue(final["facts"]["mosaicPainted"] and final["facts"]["returned"])
        self.assertEqual(12, final["budget"]["used"]["commands"])
        before = self.audit(); data = self.state.read_bytes(); self.task(); self.assertEqual(data, self.state.read_bytes()); self.assertEqual(before, self.audit())
        self.assertEqual(1, self.choice.calls)

    def test_10_after_commit_exit_task_recovers_original_edit(self):
        class Crash(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                if method == "POST" and payload.get("action", {}).get("type") == "mosaic": headers = {"X-Test-Fault": "after-commit"}
                return super().request(method, path, payload, headers)
        first = self.task(client=Crash(self.world.url, self.world.access["sessions"]["a1"]["token"]))
        self.assertEqual("unknown", first["mission"]["status"]); original = first["steps"][-1]["commandId"]
        self.assertEqual(82, self.world.process.wait(timeout=10)); self.world.restart()
        final = self.task(); self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(original, final["facts"]["mosaicEdit"]["commandId"]); self.assertEqual(1, self.audit()["mosaic"]["revision"])

    def test_11_old_edit_never_completes_new_task(self):
        old = self.visit(); self.send(self.a, self.action(old, [{"x": 0, "y": 0, "color": "leaf"}]))
        self.walk(self.a, (1, 1)); first = self.task(max_steps=6)
        self.assertFalse(first["facts"]["mosaicPainted"]); final = self.task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertNotEqual(old, final["facts"]["mosaicEdit"]["visitCommandId"])
        self.assertEqual(2, self.audit()["mosaic"]["revision"])

    def test_12_wrong_evidence_and_query_failure_keep_original_pending(self):
        class Wrong(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                status, result = super().request(method, path, payload, headers)
                if method == "POST" and payload.get("action", {}).get("type") == "mosaic" and status == 200: result["result"]["patch"][0]["color"] = "rose"
                return status, result
        first = self.task(client=Wrong(self.world.url, self.world.access["sessions"]["a1"]["token"]))
        self.assertEqual("unknown", first["mission"]["status"]); self.assertFalse(first["facts"]["mosaicPainted"])
        original = first["steps"][-1]["commandId"]
        class BadQuery(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                if method == "GET" and "/commands/" in path: path = self.prefix + "/commands/invalid!"
                status, result = super().request(method, path, payload, headers)
                if method == "GET" and path.endswith("/observation") and status == 200: result["self"]["mosaicEdits"] = []
                return status, result
        second = self.task(client=BadQuery(self.world.url, self.world.access["sessions"]["a1"]["token"]))
        self.assertEqual("unknown", second["mission"]["status"])
        self.assertEqual(original, json.loads(self.state.read_text())["_state"]["pending"]["request"]["commandId"])
        final = self.task(); self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(original, final["facts"]["mosaicEdit"]["commandId"])

    def test_13_changed_board_stops_frozen_draft_without_overwrite(self):
        self.task(max_steps=6); other = self.visit(self.b)
        self.send(self.b, self.action(other, [{"x": 0, "y": 0, "color": "leaf"}]))
        r = self.task(); self.assertEqual("blocked", r["mission"]["status"])
        self.assertIn("MOSAIC_CHANGED", r["mission"]["reason"])
        self.assertEqual(0, r["decision"]["mosaicBaseRevision"]); self.assertFalse(r["facts"]["mosaicPainted"])
        before = self.audit(); self.task(); self.assertEqual(before, self.audit()); self.assertEqual(1, self.choice.calls)
        self.assertEqual(1, before["mosaic"]["revision"])

    def test_14_capabilities_bad_goals_and_invalid_draft_fail_before_actions(self):
        bad = mosaic_mission(); bad["goals"][0]["activityId"] = "riverwalk"
        before = self.audit()
        with self.assertRaises(ValueError): self.task(bad)
        self.assertEqual(0, self.choice.calls)
        r = self.task(choose=Choice("garden")); self.assertEqual("decision_failed", r["mission"]["status"])
        self.assertEqual(before, self.audit())
        self.state = self.world.data / "same-color.json"
        r = self.task(choose=MosaicChoice([{"x": 0, "y": 0, "color": "blank"}]))
        self.assertEqual("decision_failed", r["mission"]["status"]); self.assertEqual(before, self.audit())
        old = MosaicCandidate(self._testMethodName + "-r4", "postcards-v1")
        try:
            self.state = self.world.data / "old-rules.json"
            with self.assertRaises(ValueError): self.task(client=old.client())
            self.assertEqual(0, self.choice.calls); self.assertEqual(0, old.client().observe()["stateVersion"])
        finally: old.stop()

    def test_15_populated_r4_unchanged_and_postcards_still_work_on_r5(self):
        old = MosaicCandidate(self._testMethodName + "-fixture", None, "postcards-v4-populated.sql")
        try:
            observed = old.client().observe(); self.assertEqual("r4", observed["rulesVersion"])
            self.assertEqual(2, len(observed["postcards"])); self.assertIsNone(observed["mosaic"])
            self.assertEqual([], observed["mosaicEdits"]); old.stop(); self.assertEqual(old.fixture_before, old.dump())
        finally: old.stop()
        r = self.task(postcard_mission(), choose=PostcardChoice())
        self.assertEqual("completed", r["mission"]["status"]); self.assertTrue(r["facts"]["postcardShared"])
        self.assertEqual(0, self.audit()["mosaic"]["revision"])

    def test_16_bounded_public_own_history_and_public_model_context(self):
        ids = []
        for i in range(103):
            visit = self.visit(); intent, _ = self.send(self.a, self.action(visit, [{"x": 0, "y": 0, "color": "leaf" if i % 2 == 0 else "river"}]))
            ids.append(intent["commandId"])
        observed = self.audit(); self.assertEqual(ids[-50:], [e["commandId"] for e in observed["mosaicEdits"]])
        self.assertEqual(ids[-100:], [e["commandId"] for e in observed["self"]["mosaicEdits"]])
        self.assertEqual([], self.b.observe()["self"]["mosaicEdits"])
        self.walk(self.a, (1, 1)); self.task(max_steps=0)
        context = self.choice.contexts[0]; self.assertTrue(context["mosaicPainting"])
        self.assertEqual(observed["mosaic"], context["observation"]["mosaic"])
        self.assertEqual(12, context["candidates"][0]["estimatedCommands"])
        def keys(v):
            if isinstance(v, dict):
                for k, x in v.items(): yield k; yield from keys(x)
            elif isinstance(v, list):
                for x in v: yield from keys(x)
        self.assertTrue(set(keys(context)).isdisjoint({"sessionId", "token", "authorization", "password"}))

    def test_17_committed_edit_remains_true_after_later_overwrite(self):
        class Lost(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                result = super().request(method, path, payload, headers)
                if method == "POST" and payload.get("action", {}).get("type") == "mosaic": raise OSError("test loses committed response")
                return result
        first = self.task(client=Lost(self.world.url, self.world.access["sessions"]["a1"]["token"]))
        self.assertEqual("unknown", first["mission"]["status"]); original = first["steps"][-1]["commandId"]
        other = self.visit(self.b); self.send(self.b, self.action(other, [{"x": 1, "y": 2, "color": "leaf"}]))
        final = self.task(); self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(original, final["facts"]["mosaicEdit"]["commandId"])
        self.assertEqual("river", final["facts"]["mosaicEdit"]["patch"][0]["color"])
        self.assertEqual("leaf", final["world"]["mosaic"]["cells"][11]["color"])
        self.assertEqual(2, self.audit()["mosaic"]["revision"])


if __name__ == "__main__":
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MosaicAcceptance)
    if len(sys.argv) > 1:
        names = set(sys.argv[1:]); suite = unittest.TestSuite(t for t in suite if t._testMethodName in names)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {"suite": "mosaic-http-v1", "decisionSource": "explicit-test-double", "actualModelCalls": 0,
              "recordedAtUtc": datetime.now(timezone.utc).isoformat(), "passed": result.wasSuccessful(), "testsRun": result.testsRun,
              "tests": result.records, "dataRoot": str(RUN_ROOT.relative_to(ROOT)),
              "failures": [{"test": str(t), "detail": d} for t, d in result.failures + result.errors]}
    (RUN_ROOT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", RUN_ROOT / "results.json")
    raise SystemExit(0 if result.wasSuccessful() else 1)
