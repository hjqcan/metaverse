#!/usr/bin/env python3
"""Independent postcard acceptance against real HTTP/SQLite; decision doubles only."""
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
from activities_api import ActivityAcceptance, mission
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice

RUN_ROOT = ROOT / ".local/iter0005/api" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])


class PostcardCandidate(Candidate):
    def __init__(self, name, scenario="postcards-v1", fixture=None):
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
            (self.data / "access.json").write_text(json.dumps({"sessions": {a: {"token": "fixture-r3-" + a} for a in ("a1", "a2")}}))
            self.fixture_before = self.dump()
        self.process = self.log = None
        self.start()
        self.access = json.loads((self.data / "access.json").read_text())

    def dump(self):
        with sqlite3.connect(f"file:{self.data / 'world.db'}?mode=ro", uri=True) as db:
            return (db.execute("PRAGMA user_version").fetchone()[0], "\n".join(db.iterdump()))


def postcard_mission(name="postcard-test", commands=20):
    job = mission(name, commands=commands, wood=0)
    job["allowBuild"] = False
    job["sharePostcard"] = True
    return job


class PostcardChoice(Choice):
    def __init__(self, text="愿后来的人也能在花园里慢下来。"):
        super().__init__("garden")
        self.text = text

    def __call__(self, context):
        return {**super().__call__(context), "postcardText": self.text}


class PostcardAcceptance(unittest.TestCase):
    audit = FoundationAcceptance.audit
    send = FoundationAcceptance.send
    intent = ActivityAcceptance.intent
    walk = ActivityAcceptance.walk

    def setUp(self):
        self.world = PostcardCandidate(self._testMethodName)
        self.a, self.b = self.world.client(), self.world.client("a2")
        self.trace, self.reports = [], []
        self.state = self.world.data / "mission.json"
        self.choice = PostcardChoice()

    def tearDown(self):
        (self.world.data / "reports.json").write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + "\n")
        # Preserve deliberately invalid surrogate inputs as JSON escapes, not invalid UTF-8.
        trace_json = json.dumps(self.trace, ensure_ascii=True, indent=2) + "\n"
        self.trace = []
        try:
            FoundationAcceptance.tearDown(self)
        finally:
            (self.world.data / "http-trace.json").write_text(trace_json)
        with sqlite3.connect(f"file:{self.world.data / 'world.db'}?mode=ro", uri=True) as db:
            self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
            for actor, command, visit, activity, text, version, x, y in db.execute(
                    "SELECT author_actor_id,command_id,visit_command_id,activity_id,text,state_version,x,y FROM postcards"):
                receipt = json.loads(db.execute("SELECT result_json FROM receipts WHERE actor_id=? AND command_id=?", (actor, command)).fetchone()[0])
                event = json.loads(db.execute("SELECT event_json FROM events WHERE state_version=?", (version,)).fetchone()[0])
                self.assertEqual(("committed", "postcard", actor, command, visit, activity, text, version, [x, y]),
                                 (receipt["status"], receipt["result"]["action"], receipt["result"]["authorActorId"], receipt["result"]["commandId"],
                                  receipt["result"]["visitCommandId"], receipt["result"]["activityId"], receipt["result"]["text"], receipt["result"]["stateVersion"], receipt["result"]["position"]))
                self.assertEqual(("postcard_shared", actor, command, visit, text),
                                 (event["type"], event["actorId"], event["commandId"], event["visitCommandId"], event["text"]))
                old = db.execute("SELECT activity_id,x,y,state_version FROM visits WHERE actor_id=? AND command_id=?", (actor, visit)).fetchone()
                self.assertEqual((activity, x, y), old[:3]); self.assertLess(old[3], version)
                self.assertEqual(0, db.execute("SELECT count(*) FROM resource_ledger WHERE command_id=?", (command,)).fetchone()[0])

    def visit(self, client=None, activity="garden", target=(1, 6)):
        client = client or self.a
        self.walk(client, target)
        intent, _ = self.send(client, {"type": "visit", "activityId": activity})
        return intent["commandId"]

    def action(self, visit, text="留一句话，给后来的人。", activity="garden"):
        return {"type": "postcard", "activityId": activity, "visitCommandId": visit, "text": text}

    def task(self, job=None, client=None, choose=None, **kwargs):
        report = run_mission(client or self.a, job or postcard_mission(), self.state, choose or self.choice, **kwargs)
        self.reports.append(report)
        return report

    def test_01_author_public_read_and_restart(self):
        self.assertEqual("r4", self.audit()["rulesVersion"])
        visit = self.visit(); before = self.audit()["resourceAudit"]
        intent, result = self.send(self.a, self.action(visit))
        card = self.audit()["postcards"][0]
        self.assertEqual(intent["commandId"], card["commandId"])
        self.assertEqual("a1", card["authorActorId"])
        self.assertEqual(card, {k: v for k, v in result["result"].items() if k != "action"})
        self.assertEqual([card], self.b.observe()["postcards"])
        self.assertEqual([], self.b.observe()["self"]["postcards"])
        self.assertEqual(404, self.b.request("GET", self.b.prefix + "/commands/" + intent["commandId"])[0])
        self.world.restart()
        self.assertEqual([card], self.audit()["postcards"])
        self.assertEqual(before, self.audit()["resourceAudit"])

    def test_02_location_visit_and_identity_constraints(self):
        for action, code in [(self.action("missing"), "NOT_AT_ACTIVITY"), (self.action("missing", activity="unknown"), "ACTIVITY_NOT_FOUND")]:
            before = self.audit(); _, r = self.send(self.a, action, expected=422)
            self.assertEqual(code, r["error"]["code"]); self.assertEqual(before, self.audit())
        foreign = self.visit(self.b); self.walk(self.a, (1, 6))
        for reference in ["missing", foreign]:
            before = self.audit(); _, r = self.send(self.a, self.action(reference), expected=422)
            self.assertEqual("VISIT_REQUIRED", r["error"]["code"]); self.assertEqual(before, self.audit())
        own = self.visit(); before = self.audit()
        self.send(self.a, {**self.action(own), "authorActorId": "a2"}, expected=400)
        self.send(self.a, {**self.action(own), "actorId": "a2"}, expected=403)
        self.assertEqual(before, self.audit())
        self.walk(self.a, (2, 5))
        _, r = self.send(self.a, self.action(own, activity="riverwalk"), expected=422)
        self.assertEqual("VISIT_REQUIRED", r["error"]["code"])

    def test_03_original_id_and_one_share_per_visit(self):
        visit = self.visit(); intent, result = self.send(self.a, self.action(visit))
        before = self.audit()
        self.assertEqual((200, result), self.a.command(intent))
        changed = deepcopy(intent); changed["action"]["text"] += "!"
        self.assertEqual("IDEMPOTENCY_CONFLICT", self.a.command(changed)[1]["error"]["code"])
        _, denied = self.send(self.a, self.action(visit), expected=409)
        self.assertEqual("VISIT_ALREADY_SHARED", denied["error"]["code"])
        self.assertEqual(before, self.audit())
        new_visit = self.visit(); self.send(self.a, self.action(new_visit))
        self.assertEqual(2, len(self.audit()["postcards"]))

    def test_04_concurrent_original_id_commits_once(self):
        visit = self.visit(); intent = self.intent(self.a, self.action(visit)); version = self.audit()["stateVersion"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.a.command(intent), range(2)))
        self.assertEqual(results[0], results[1]); self.assertEqual(200, results[0][0])
        self.assertEqual(version + 1, self.audit()["stateVersion"])
        self.assertEqual(1, len(self.audit()["postcards"]))

    def crash_share(self, fault, code, committed):
        visit = self.visit(); before = self.audit()
        intent = self.intent(self.a, self.action(visit))
        with self.assertRaises((OSError, RuntimeError, ValueError)):
            self.a.request("POST", self.a.prefix + "/commands", intent, {"X-Test-Fault": fault})
        self.assertEqual(code, self.world.process.wait(timeout=10)); self.world.restart()
        self.assertEqual(before["stateVersion"] + int(committed), self.audit()["stateVersion"])
        self.assertEqual(200 if committed else 404, self.a.request("GET", self.a.prefix + "/commands/" + intent["commandId"])[0])
        self.assertEqual(200, self.a.command(intent)[0])
        self.assertEqual(1, len(self.audit()["postcards"]))
        self.assertEqual(before["stateVersion"] + 1, self.audit()["stateVersion"])

    def test_05_before_commit_exit_rolls_back(self): self.crash_share("before-commit", 81, False)
    def test_06_after_commit_exit_preserves_original(self): self.crash_share("after-commit", 82, True)

    def test_07_unicode_scalars_and_invalid_content(self):
        visit = self.visit(); before = self.audit()
        for text in ["", "   ", "🌱" * 161, "hello\nworld", "a\t", "a\x00", "a\x85", "\ud800", "\udfff"]:
            _, r = self.send(self.a, self.action(visit, text), expected=400)
            self.assertEqual("INVALID_REQUEST", r["error"]["code"])
        self.assertEqual(before, self.audit())
        text = "🌱" * 160
        self.send(self.a, self.action(visit, text))
        self.assertEqual(text, self.audit()["postcards"][0]["text"])

    def test_08_task_budget_stops_after_visit_before_share(self):
        report = self.task(postcard_mission(commands=6))
        self.assertEqual("budget_exhausted", report["mission"]["status"])
        self.assertTrue(report["facts"]["activityCompleted"])
        self.assertFalse(report["facts"]["postcardShared"])
        self.assertFalse(report["facts"]["returned"])
        self.assertEqual([], self.audit()["postcards"])

    def test_09_pause_share_and_complete_resume_noop(self):
        first = self.task(max_steps=6)
        self.assertTrue(first["facts"]["activityCompleted"]); self.assertFalse(first["facts"]["postcardShared"])
        final = self.task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertTrue(final["mission"]["sharePostcard"] and final["facts"]["postcardShared"] and final["facts"]["returned"])
        self.assertEqual(12, final["budget"]["used"]["commands"])
        self.assertEqual(final["facts"]["activityVisit"]["commandId"], final["facts"]["postcard"]["visitCommandId"])
        before = self.audit(); self.task(); self.assertEqual(before, self.audit())
        self.assertEqual(1, self.choice.calls)

    def test_10_task_after_commit_exit_recovers_same_share(self):
        class Crash(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                if method == "POST" and payload.get("action", {}).get("type") == "postcard": headers = {"X-Test-Fault": "after-commit"}
                return super().request(method, path, payload, headers)
        first = self.task(client=Crash(self.world.url, self.world.access["sessions"]["a1"]["token"]))
        self.assertEqual("unknown", first["mission"]["status"])
        original = first["steps"][-1]["commandId"]
        self.assertEqual(82, self.world.process.wait(timeout=10)); self.world.restart()
        final = self.task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(original, final["facts"]["postcard"]["commandId"])
        self.assertEqual(12, final["budget"]["used"]["commands"])
        self.assertEqual(1, len(self.audit()["postcards"]))

    def test_11_previous_share_cannot_complete_new_task(self):
        old = self.visit(); self.send(self.a, self.action(old)); self.walk(self.a, (1, 1))
        first = self.task(max_steps=6)
        self.assertFalse(first["facts"]["postcardShared"])
        final = self.task()
        self.assertNotEqual(old, final["facts"]["postcard"]["visitCommandId"])
        self.assertEqual(2, len(self.audit()["postcards"]))

    def test_12_unmatched_share_evidence_keeps_pending(self):
        class WrongText(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                status, result = super().request(method, path, payload, headers)
                if method == "POST" and payload.get("action", {}).get("type") == "postcard" and status == 200:
                    result["result"]["text"] = "这是不匹配的文字。"
                return status, result
        first = self.task(client=WrongText(self.world.url, self.world.access["sessions"]["a1"]["token"]))
        self.assertEqual("unknown", first["mission"]["status"])
        self.assertFalse(first["facts"]["postcardShared"])
        original = first["steps"][-1]["commandId"]
        final = self.task()
        self.assertEqual(original, final["facts"]["postcard"]["commandId"])
        self.assertEqual(1, len(self.audit()["postcards"]))

    def test_13_query_failure_is_not_original_rejection(self):
        class LoseResponse(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                status, result = super().request(method, path, payload, headers)
                if method == "POST" and payload.get("action", {}).get("type") == "postcard": raise OSError("test drops committed response")
                return status, result
        first = self.task(client=LoseResponse(self.world.url, self.world.access["sessions"]["a1"]["token"]))
        original = first["steps"][-1]["commandId"]
        class QueryFailure(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                # Hide the alternative observation evidence and obtain an actual HTTP 400 query response.
                if method == "GET" and "/commands/" in path: path = self.prefix + "/commands/invalid!"
                status, result = super().request(method, path, payload, headers)
                if method == "GET" and path.endswith("/observation") and status == 200: result["self"]["postcards"] = []
                return status, result
        second = self.task(client=QueryFailure(self.world.url, self.world.access["sessions"]["a1"]["token"]))
        self.assertEqual("unknown", second["mission"]["status"])
        self.assertEqual(original, json.loads(self.state.read_text())["_state"]["pending"]["request"]["commandId"])
        final = self.task(); self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(original, final["facts"]["postcard"]["commandId"])

    def test_14_capability_and_goal_validation_before_model(self):
        job = postcard_mission(); job["goals"][0].pop("activityId")
        before = self.audit()
        with self.assertRaises(ValueError): self.task(job)
        self.assertEqual(0, self.choice.calls); self.assertEqual(before, self.audit())
        old = PostcardCandidate(self._testMethodName + "-r3", "activities-v1")
        try:
            with self.assertRaises(ValueError): self.task(client=old.client())
            self.assertEqual(0, self.choice.calls); self.assertEqual(0, old.client().observe()["stateVersion"])
        finally: old.stop()

    def test_15_missing_draft_fails_without_world_action_and_old_spec_still_runs(self):
        before = self.audit()
        bad = self.task(choose=Choice("garden"))
        self.assertEqual("decision_failed", bad["mission"]["status"])
        self.assertEqual(before, self.audit())
        self.state = self.world.data / "legacy.json"
        old = self.task(mission(), choose=self.choice)
        self.assertEqual("completed", old["mission"]["status"])
        self.assertFalse(old["facts"].get("postcardShared", False))
        self.assertEqual([], self.audit()["postcards"])

    def test_16_existing_populated_schema3_world_is_unchanged(self):
        old = PostcardCandidate(self._testMethodName + "-fixture", None, "activities-v3-populated.sql")
        try:
            self.assertEqual(old.fixture_before, old.dump())
            a = old.client(); before = a.observe()
            self.assertEqual("r3", before["rulesVersion"])
            self.assertEqual(1, len(before["self"]["visits"]))
            self.assertEqual(2, len(before["entities"]))
            _, denied = self.send(a, self.action("not-needed"), expected=422)
            self.assertEqual("POSTCARD_UNAVAILABLE", denied["error"]["code"])
            self.assertEqual(before, a.observe())
            old.stop(); dump = old.dump(); old.start(); self.assertEqual(dump, old.dump())
        finally: old.stop()

    def test_17_recent_feeds_and_model_context_are_bounded(self):
        self.walk(self.b, (1, 6)); ids = []
        for i in range(101):
            visit = self.visit(self.b)
            intent, _ = self.send(self.b, self.action(visit, f"第{i+1}篇 🌱")); ids.append(intent["commandId"])
        observed = self.audit()
        self.assertEqual(ids[-50:], [p["commandId"] for p in observed["postcards"]])
        self.assertEqual([], observed["self"]["postcards"])
        self.assertEqual(ids[-100:], [p["commandId"] for p in self.b.observe()["self"]["postcards"]])
        self.task(max_steps=0)
        context = self.choice.contexts[0]
        public = context["observation"]
        self.assertTrue(context["postcardSharing"])
        self.assertEqual(ids[-5:], [p["commandId"] for p in public["postcards"]])
        self.assertEqual(12, next(c for c in context["candidates"] if c["id"] == "garden")["estimatedCommands"])
        keys = []
        def collect(value):
            if isinstance(value, dict):
                keys.extend(value)
                for v in value.values(): collect(v)
            elif isinstance(value, list):
                for v in value: collect(v)
        collect(context)
        self.assertTrue(set(keys).isdisjoint({"sessionId", "token", "authorization", "password"}))
        self.assertEqual(12, self.audit()["resourceAudit"]["depotWood"])


if __name__ == "__main__":
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PostcardAcceptance)
    if len(sys.argv) > 1:
        names = set(sys.argv[1:]); suite = unittest.TestSuite(t for t in suite if t._testMethodName in names)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {"suite": "postcards-http-v1", "decisionSource": "explicit-test-double", "actualModelCalls": 0,
              "recordedAtUtc": datetime.now(timezone.utc).isoformat(), "passed": result.wasSuccessful(), "testsRun": result.testsRun,
              "tests": result.records, "dataRoot": str(RUN_ROOT.relative_to(ROOT)),
              "failures": [{"test": str(t), "detail": d} for t, d in result.failures + result.errors]}
    (RUN_ROOT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", RUN_ROOT / "results.json")
    raise SystemExit(0 if result.wasSuccessful() else 1)
