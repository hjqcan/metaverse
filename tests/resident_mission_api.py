#!/usr/bin/env python3
"""Durable mission acceptance: actual world HTTP, explicitly labelled decision doubles."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
import uuid

import passage_api
from foundation_api import EvidenceResult, FoundationAcceptance, ROOT
from foundation_agent import WorldClient
from resident_mission import run_mission

RUN_ROOT = ROOT / ".local/iter0003/api" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])
passage_api.RUN_ROOT = RUN_ROOT


def spec(mission="mission-test", **budgets):
    return {"missionId": mission, "objective": "优先连通彼岸供他人使用，完成后回到原始起点。",
            "goals": [{"id": "far-bank", "label": "彼岸", "target": [6, 1]},
                      {"id": "nearby", "label": "本岸探索", "target": [1, 6]}],
            "allowBuild": True, "budgets": {"commands": 50, "wood": 6, "seconds": 600, "modelCalls": 1, **budgets}}


class Choice:
    def __init__(self, goal="far-bank"):
        self.goal, self.calls, self.contexts = goal, 0, []

    def __call__(self, context):
        self.calls += 1
        self.contexts.append(context)
        return {"goalId": self.goal, "reason": "测试替身选择，不能计为模型推理。",
                "provider": {"kind": "test-double", "model": "none", "usage": {}}}


class MissionAcceptance(unittest.TestCase):
    audit = FoundationAcceptance.audit

    def setUp(self):
        self.world = passage_api.PassageCandidate(self._testMethodName)
        self.a, self.b = self.world.client(), self.world.client("a2")
        self.state = self.world.data / "mission.json"
        self.choose = Choice()
        self.reports = []
        self.trace = []

    def tearDown(self):
        (self.world.data / "reports.json").write_text(json.dumps(self.reports, ensure_ascii=False, indent=2))
        FoundationAcceptance.tearDown(self)

    def run_task(self, job=None, client=None, choose=None, **kwargs):
        report = run_mission(client or self.a, job or spec(), self.state, choose or self.choose, **kwargs)
        self.reports.append(report)
        self.assertEqual("resident-mission-report", report["kind"])
        self.assertLessEqual(report["budget"]["used"]["wood"], report["budget"]["limits"]["wood"])
        self.assertLessEqual(report["budget"]["used"]["commands"], report["budget"]["limits"]["commands"])
        self.assertLessEqual(report["budget"]["used"]["modelCalls"], 1)
        return report

    def test_01_builder_verified_and_completed_resume_is_noop(self):
        report = self.run_task()
        self.assertEqual("completed", report["mission"]["status"])
        self.assertTrue(report["facts"]["goalReached"])
        self.assertTrue(report["facts"]["returned"])
        self.assertEqual(6, report["budget"]["used"]["wood"])
        self.assertEqual(2, len(report["facts"]["createdEntityIds"]))
        before = self.audit()
        self.run_task()
        self.assertEqual(before, self.audit())
        self.assertEqual(1, self.choose.calls)
        self.assertEqual([1, 1], before["self"]["position"])

    def test_02_pause_resume_retains_full_task_and_cumulative_budget(self):
        first = self.run_task(max_steps=4)
        self.assertEqual("paused", first["mission"]["status"])
        self.assertEqual(4, first["budget"]["used"]["commands"])
        second = self.run_task(max_steps=2)
        self.assertEqual(6, second["budget"]["used"]["commands"])
        self.world.restart()
        final = self.run_task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual([1, 1], final["mission"]["origin"])
        self.assertEqual(1, self.choose.calls)
        self.assertEqual(21, final["budget"]["used"]["commands"])
        self.assertEqual(21, len({s["commandId"] for s in final["steps"]}))

    def test_03_command_budget_never_resets_on_resume(self):
        job = spec(commands=2)
        first = self.run_task(job, max_steps=1)
        self.assertEqual(1, first["budget"]["used"]["commands"])
        second = self.run_task(job)
        self.assertEqual("budget_exhausted", second["mission"]["status"])
        self.assertEqual(2, second["budget"]["used"]["commands"])
        before = self.audit()
        self.run_task(job)
        self.assertEqual(before, self.audit())
        self.assertEqual(1, self.choose.calls)

    def test_04_material_budget_is_not_bypassed_by_existing_inventory(self):
        o = self.a.observe()
        self.assertEqual(200, self.a.command({"schemaVersion": 1, "rulesVersion": "r2", "commandId": "preexisting-wood",
                                             "expectedStateVersion": o["stateVersion"], "action": {"type": "claim", "quantity": 6}})[0])
        report = self.run_task(spec(wood=3))
        self.assertIn(report["mission"]["status"], ("blocked", "budget_exhausted"))
        self.assertFalse(report["facts"]["goalReached"])
        self.assertLessEqual(self.audit()["resourceAudit"]["embodiedWood"], 3)

    def test_05_unlisted_goal_is_rejected_before_any_world_action(self):
        before = self.audit()
        report = self.run_task(choose=Choice("invented-admin-goal"))
        self.assertEqual("decision_failed", report["mission"]["status"])
        self.assertEqual(before, self.audit())
        self.assertEqual(0, report["budget"]["used"]["commands"])

    def test_06_model_failure_does_not_retry_or_change_world(self):
        calls = []
        def fail(context):
            calls.append(context)
            raise RuntimeError("deliberate model transport failure")
        report = self.run_task(choose=fail)
        self.assertEqual("decision_failed", report["mission"]["status"])
        self.assertEqual(1, report["budget"]["used"]["modelCalls"])
        before = self.audit()
        self.run_task(choose=fail)
        self.assertEqual(1, len(calls))
        self.assertEqual(before, self.audit())

    def test_07_invalid_spec_boolean_budget_and_duplicate_goals(self):
        before = self.audit()
        invalid = [spec(commands=True), spec(wood=-1), spec(seconds=601)]
        duplicate = spec(); duplicate["goals"][1]["id"] = "far-bank"; invalid.append(duplicate)
        for job in invalid:
            with self.assertRaises((ValueError, RuntimeError)):
                self.run_task(job)
        self.assertEqual(0, self.choose.calls)
        self.assertEqual(before, self.audit())

    def test_08_bridge_commit_then_service_exit_recovers_original_id(self):
        class CrashClient(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                if method == "POST" and payload.get("action", {}).get("type") == "build":
                    headers = {**(headers or {}), "X-Test-Fault": "after-commit"}
                return super().request(method, path, payload, headers)
        client = CrashClient(self.world.url, self.world.access["sessions"]["a1"]["token"])
        first = self.run_task(client=client)
        self.assertEqual("unknown", first["mission"]["status"])
        self.assertEqual(82, self.world.process.wait(timeout=10))
        self.world.restart()
        final = self.run_task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(1, self.choose.calls)
        self.assertEqual(6, final["budget"]["used"]["wood"])
        self.assertEqual(21, final["budget"]["used"]["commands"])
        self.assertEqual([1, 1], self.audit()["self"]["position"])
        self.assertEqual(2, len(self.audit()["entities"]))

    def test_09_process_exit_after_receipt_before_local_settlement(self):
        # Exact dedicated child dies after a real bridge POST has returned 200.
        program = '''
import json,os,sys
sys.path[:0]=[sys.argv[1]+"/scripts",sys.argv[1]+"/tests"]
from resident_mission_api import spec,Choice
from resident_mission import run_mission
from foundation_agent import WorldClient
class CrashClient(WorldClient):
 def request(self,method,path,payload=None,headers=None):
  result=super().request(method,path,payload,headers)
  if method=="POST" and payload.get("action",{}).get("type")=="build" and result[0]==200:os._exit(83)
  return result
access=json.load(open(sys.argv[3]))
run_mission(CrashClient(sys.argv[2],access["sessions"]["a1"]["token"]),spec(),sys.argv[4],Choice())
'''
        p = subprocess.run([sys.executable, "-c", program, str(ROOT), self.world.url,
                            str(self.world.data / "access.json"), str(self.state)], timeout=25, capture_output=True)
        self.assertEqual(83, p.returncode, p.stderr.decode())
        self.assertEqual(1, len(self.audit()["entities"]))
        final = self.run_task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(0, self.choose.calls, "saved choice must be reused")
        self.assertEqual(21, final["budget"]["used"]["commands"])
        self.assertEqual(6, final["budget"]["used"]["wood"])
        self.assertEqual(2, len(self.audit()["entities"]))

    def test_10_identity_and_spec_binding_cannot_be_replaced(self):
        self.run_task(max_steps=1)
        before = self.audit()
        with self.assertRaises((ValueError, RuntimeError)):
            self.run_task(client=self.b)
        changed = spec(); changed["budgets"]["wood"] = 12
        with self.assertRaises((ValueError, RuntimeError)):
            self.run_task(changed)
        self.assertEqual(before, self.audit())

    def test_11_same_state_file_is_mutually_exclusive_across_processes(self):
        marker = self.world.data / "choosing.marker"
        program = '''
import json,sys,time
from pathlib import Path
sys.path[:0]=[sys.argv[1]+"/scripts",sys.argv[1]+"/tests"]
from resident_mission_api import spec,Choice
from resident_mission import run_mission
from foundation_agent import WorldClient
def choose(context):
 Path(sys.argv[5]).write_text("ready")
 time.sleep(2)
 return Choice()(context)
access=json.load(open(sys.argv[3]))
run_mission(WorldClient(sys.argv[2],access["sessions"]["a1"]["token"]),spec(),sys.argv[4],choose,max_steps=1)
'''
        child = subprocess.Popen([sys.executable, "-c", program, str(ROOT), self.world.url,
                                  str(self.world.data / "access.json"), str(self.state), str(marker)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(marker.exists())
            with self.assertRaises((ValueError, RuntimeError, BlockingIOError)):
                self.run_task()
            _, error = child.communicate(timeout=10)
            self.assertEqual(0, child.returncode, error.decode())
            final = self.run_task()
            self.assertEqual("completed", final["mission"]["status"])
            self.assertEqual(0, self.choose.calls)
        finally:
            if child.poll() is None:
                child.terminate(); child.wait(timeout=5)

    def test_12_elapsed_budget_survives_pause(self):
        job = spec(seconds=1)
        first = self.run_task(job, max_steps=1)
        self.assertEqual("paused", first["mission"]["status"])
        before = self.audit()
        time.sleep(1.1)
        final = self.run_task(job)
        self.assertEqual("budget_exhausted", final["mission"]["status"])
        self.assertEqual(before, self.audit())

    def test_13_context_has_no_credentials_and_free_traveler_uses_public_work(self):
        self.run_task()
        serialized = json.dumps(self.choose.contexts)
        for session in self.world.access["sessions"].values():
            self.assertNotIn(session["token"], serialized)
            self.assertNotIn(session["sessionId"], serialized)
        self.assertNotIn("operatorId", serialized)
        self.state = self.world.data / "traveler.json"
        job = spec("traveler", wood=0); job["allowBuild"] = False
        report = self.run_task(job, client=self.b, choose=Choice())
        self.assertEqual("completed", report["mission"]["status"])
        self.assertEqual(0, report["budget"]["used"]["wood"])
        self.assertEqual(0, report["facts"]["woodClaimed"])
        self.assertTrue(all(step["action"]["type"] == "move" for step in report["steps"]))
        self.assertEqual(6, self.audit()["depot"]["wood"])

    def test_14_query_routing_error_cannot_reject_original_pending_command(self):
        class DropPost(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                if method == "POST":
                    raise OSError("simulated request not delivered")
                return super().request(method, path, payload, headers)
        class MisrouteQuery(WorldClient):
            def request(self, method, path, payload=None, headers=None):
                if method == "GET" and "/commands/" in path:
                    path = self.prefix + "/commands/invalid.id"
                return super().request(method, path, payload, headers)
        token = self.world.access["sessions"]["a1"]["token"]
        first = self.run_task(client=DropPost(self.world.url, token))
        self.assertEqual("unknown", first["mission"]["status"])
        command_id = first["steps"][0]["commandId"]
        second = self.run_task(client=MisrouteQuery(self.world.url, token))
        self.assertEqual("unknown", second["mission"]["status"], "GET format error is not the original command receipt")
        self.assertEqual(0, self.audit()["stateVersion"])
        final = self.run_task()
        self.assertEqual("completed", final["mission"]["status"])
        self.assertEqual(command_id, final["steps"][0]["commandId"])
        self.assertEqual(21, final["budget"]["used"]["commands"])


if __name__ == "__main__":
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MissionAcceptance)
    if len(sys.argv) > 1:
        names = set(sys.argv[1:]); suite = unittest.TestSuite(t for t in suite if t._testMethodName in names)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {"suite": "resident-mission-http-v1", "decisionSource": "test-double", "realModelCalls": 0,
              "recordedAtUtc": datetime.now(timezone.utc).isoformat(), "passed": result.wasSuccessful(),
              "testsRun": result.testsRun, "tests": result.records, "dataRoot": str(RUN_ROOT.relative_to(ROOT)),
              "failures": [{"test": str(t), "detail": d} for t, d in result.failures + result.errors]}
    (RUN_ROOT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    print("Evidence:", RUN_ROOT / "results.json")
    raise SystemExit(0 if result.wasSuccessful() else 1)
