#!/usr/bin/env python3
"""Actual r7 HTTP/SQLite missions; all goal choices are explicit test doubles."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import subprocess
import sys
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate, ActivityAcceptance
from foundation_api import EvidenceResult, FoundationAcceptance, ROOT
from foundation_agent import WorldClient
from resident_mission import run_mission, _context, _public
from resident_mission_api import Choice, spec
from wilderness_api import WildernessAcceptance
from wilderness_materials import collection_plan

RUN_ROOT = ROOT / '.local/iter0013/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN_ROOT


def mission(**budgets):
    return {**spec('gather-bridge', **budgets), 'allowGather': True}


class WildernessMissionAcceptance(unittest.TestCase):
    send = FoundationAcceptance.send
    intent = ActivityAcceptance.intent
    walk = ActivityAcceptance.walk
    audit = WildernessAcceptance.audit
    gather = WildernessAcceptance.gather

    def setUp(self):
        self.world = ActivityCandidate(self._testMethodName, scenario='wilderness-v1')
        self.a, self.b = self.world.client(), self.world.client('a2')
        self.state = self.world.data / 'mission.json'
        self.choose = Choice()
        self.trace, self.reports = [], []

    def tearDown(self):
        (self.world.data / 'reports.json').write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + '\n')
        WildernessAcceptance.tearDown(self)

    def run_task(self, job=None, client=None, **kwargs):
        report = run_mission(client or self.a, job or mission(), self.state, self.choose, **kwargs)
        self.reports.append(report)
        self.assertLessEqual(report['budget']['used']['wood'], report['budget']['limits']['wood'])
        self.assertLessEqual(report['budget']['used']['commands'], report['budget']['limits']['commands'])
        return report

    def completed(self, report, gathered=6):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertEqual((True, True, gathered, 0), tuple(report['facts'][k] for k in ('goalReached', 'returned', 'woodGathered', 'woodClaimed')))
        self.assertEqual(6, report['budget']['used']['wood'])
        self.assertEqual(gathered, sum(s['action']['type'] == 'gather' and s['status'] == 'committed' for s in report['steps']))
        self.assertFalse(any(s['action']['type'] == 'claim' for s in report['steps']))
        self.assertEqual([1, 1], self.audit()['self']['position'])

    def test_01_empty_hands_build_bridge_and_later_resident_reuses_without_harvesting(self):
        before = self.audit()
        context = _context(mission(), _public(before))
        self.assertTrue(context['candidates'][0]['feasible'])
        report = self.run_task()
        self.completed(report)
        self.assertEqual(context['candidates'][0]['estimatedCommands'], report['budget']['used']['commands'])
        self.assertEqual(1, self.choose.calls)
        built = self.audit()
        self.assertEqual((6, 0, 6), tuple(built['resourceAudit'][k] for k in ('wildWood', 'inventoryWood', 'embodiedWood')))
        self.assertEqual(2, len(built['entities']))
        self.assertEqual(report, self.run_task())
        self.assertEqual(built, self.audit())
        traveler = mission(wood=0)
        traveler.update(missionId='later-resident', allowBuild=False, allowGather=False)
        traveler['goals'] = [{'id': 'far-bank', 'label': '对岸已有通路', 'target': [1, 1]}]
        self.state = self.world.data / 'traveler.json'
        reuse = self.run_task(traveler, client=self.b)
        self.assertEqual('completed', reuse['mission']['status'])
        self.assertEqual(0, reuse['facts']['woodGathered'])
        self.assertEqual(0, reuse['budget']['used']['wood'])
        self.assertTrue(all(s['action']['type'] == 'move' for s in reuse['steps']))
        self.assertEqual(built['entities'], self.audit()['entities'])
        self.assertEqual([6, 6], self.b.observe()['self']['position'])

    def test_02_absent_permission_preserves_legacy_no_gather_behavior(self):
        before = self.audit()
        report = self.run_task(spec())
        self.assertEqual(('blocked', 'natural_material_collection_required'),
                         (report['mission']['status'], report['mission']['reason']))
        self.assertEqual([], report['steps'])
        self.assertEqual(before, self.audit())

    def test_03_wood_budget_blocks_before_collecting_and_commands_survive_resume(self):
        before = self.audit()
        report = self.run_task(mission(wood=3))
        self.assertEqual(('budget_exhausted', 'wood'), (report['mission']['status'], report['mission']['reason']))
        self.assertEqual(before, self.audit())
        self.state = self.world.data / 'command-limit.json'
        job = mission(commands=2)
        self.assertEqual(1, self.run_task(job, max_steps=1)['facts']['woodGathered'])
        report = self.run_task(job)
        self.assertEqual(('budget_exhausted', 'commands'), (report['mission']['status'], report['mission']['reason']))
        self.assertEqual(2, report['facts']['woodGathered'])
        before = self.audit()
        self.run_task(job)
        self.assertEqual(before, self.audit())

    def test_04_unreachable_sources_are_not_counted_as_available_supply(self):
        self.gather(count=3)
        self.send(self.a, {'type': 'build', 'recipeId': 'platform.v1', 'at': [0, 1]})
        before = self.audit()
        self.assertEqual(9, before['resourceAudit']['wildWood'])
        report = self.run_task()
        self.assertEqual('insufficient_reachable_natural_material', report['mission']['reason'])
        self.assertEqual([], report['steps'])
        self.assertEqual(before, self.audit())

    def test_05_preexisting_inventory_only_collects_the_remaining_shortage(self):
        self.gather(count=2)
        self.completed(self.run_task(), gathered=4)

    def crash(self, point, exit_code, committed):
        class CrashClient(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                if method == 'POST' and payload.get('action', {}).get('type') == 'gather':
                    headers = {**(headers or {}), 'X-Test-Fault': point}
                return super().request(method, path, payload, headers)
        client = CrashClient(self.world.url, self.world.access['sessions']['a1']['token'])
        first = self.run_task(client=client)
        self.assertEqual('unknown', first['mission']['status'])
        self.assertEqual(exit_code, self.world.process.wait(timeout=10))
        pending = json.loads(self.state.read_text())['_state']['pending']['request']
        self.world.restart()
        self.assertEqual(int(committed), self.audit()['self']['inventory']['wood'])
        final = self.run_task()
        self.completed(final)
        self.assertEqual(pending['commandId'], final['steps'][0]['commandId'])
        self.assertEqual(1, self.choose.calls)

    def test_06_exit_after_cut_commit_recovers_original_once(self):
        self.crash('after-commit', 82, True)

    def test_07_exit_before_commit_retries_same_cut(self):
        self.crash('before-commit', 81, False)

    def test_08_wrong_node_receipt_stays_pending_until_original_is_recovered(self):
        class WrongReceipt(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                status, result = super().request(method, path, payload, headers)
                if method == 'POST' and payload['action']['type'] == 'gather':
                    result['result']['nodeId'] = 'tree-east-south'
                return status, result
        client = WrongReceipt(self.world.url, self.world.access['sessions']['a1']['token'])
        first = self.run_task(client=client)
        self.assertEqual(('unknown', 'unconfirmed_gather_receipt'),
                         (first['mission']['status'], first['mission']['reason']))
        self.assertEqual(0, first['facts']['woodGathered'])
        self.assertEqual(1, self.audit()['self']['inventory']['wood'])
        class WrongQuery(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                status, result = super().request(method, path, payload, headers)
                if method == 'GET' and '/commands/' in path:
                    mutate(result)
                return status, result
        for mutate in (
            lambda r: r.update(identity=None),
            lambda r: r['identity'].update(actorId='a2'),
            lambda r: r.update(stateVersion=r['stateVersion'] + 1),
            lambda r: r['result'].update(quantity=True),
            lambda r: r['result'].update(remainingWood=99),
            lambda r: r['result'].update(inventoryWood=99),
            lambda r: r['result'].update(position=[7, 6]),
        ):
            wrong = self.run_task(client=WrongQuery(self.world.url, self.world.access['sessions']['a1']['token']))
            self.assertEqual('unknown', wrong['mission']['status'])
            self.assertEqual(0, wrong['facts']['woodGathered'])
            self.assertEqual(1, len(wrong['steps']))
            self.assertEqual(1, self.audit()['self']['inventory']['wood'])
        final = self.run_task()
        self.completed(final)
        self.assertEqual(first['steps'][0]['commandId'], final['steps'][0]['commandId'])

    def test_09_stale_cut_replans_only_after_confirmed_rejection(self):
        peer = self.b
        class ConcurrentMove(WorldClient):
            changed = False
            def request(inner, method, path, payload=None, headers=None):
                if method == 'POST' and not inner.changed:
                    inner.changed = True
                    o = peer.observe()
                    self.assertEqual(200, peer.command({'schemaVersion': 1, 'rulesVersion': 'r7', 'commandId': 'peer-move',
                        'expectedStateVersion': o['stateVersion'], 'action': {'type': 'move', 'dx': 0, 'dy': -1}})[0])
                return super().request(method, path, payload, headers)
        client = ConcurrentMove(self.world.url, self.world.access['sessions']['a1']['token'])
        report = self.run_task(client=client)
        self.completed(report)
        self.assertEqual(('rejected', 'STALE_STATE'), (report['steps'][0]['status'], report['steps'][0]['errorCode']))

    def test_10_process_exit_after_cut_receipt_before_local_settlement(self):
        program = '''
import json,os,sys
sys.path[:0]=[sys.argv[1]+"/scripts",sys.argv[1]+"/tests"]
from wilderness_mission_api import mission
from resident_mission_api import Choice
from resident_mission import run_mission
from foundation_agent import WorldClient
class CrashClient(WorldClient):
 def request(self,method,path,payload=None,headers=None):
  response=super().request(method,path,payload,headers)
  if method=="POST" and payload["action"]["type"]=="gather" and response[0]==200:os._exit(83)
  return response
access=json.load(open(sys.argv[3]))
run_mission(CrashClient(sys.argv[2],access["sessions"]["a1"]["token"]),mission(),sys.argv[4],Choice())
'''
        process = subprocess.run([sys.executable, '-c', program, str(ROOT), self.world.url,
            str(self.world.data / 'access.json'), str(self.state)], capture_output=True, timeout=25)
        self.assertEqual(83, process.returncode, process.stderr.decode())
        self.completed(self.run_task())
        self.assertEqual(0, self.choose.calls)

    def test_11_permission_and_identity_binding_survive_pause(self):
        self.run_task(max_steps=1)
        before = self.audit()
        for job, client in [(mission(), self.b), ({**mission(), 'allowGather': False}, self.a)]:
            with self.assertRaises(ValueError):
                self.run_task(job, client=client)
        self.assertEqual(before, self.audit())
        self.world.restart()
        self.completed(self.run_task())

    def test_12_planning_is_readonly_and_untrusted_extra_fields_are_not_exposed(self):
        observed = self.audit()
        before = deepcopy(observed)
        self.assertEqual(6, sum(a['type'] == 'gather' for a in collection_plan(observed, 6)['actions']))
        self.assertEqual(before, observed)
        observed['resourceNodes'][0]['secret'] = 'do-not-export'
        context = _context(mission(), _public(observed))
        self.assertNotIn('do-not-export', json.dumps(context))
        for session in self.world.access['sessions'].values():
            self.assertNotIn(session['token'], json.dumps(context))
        for invalid in (1, 'yes', None):
            with self.assertRaises(ValueError):
                self.run_task({**mission(), 'allowGather': invalid})
        self.assertEqual(before, self.audit())

    def test_13_fixed_reference_cli_exports_actual_gather_report_without_models(self):
        output = self.world.data / 'cli-report.json'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_resident.py'),
            '--url', self.world.url, '--access-file', str(self.world.data / 'access.json'), '--actor', 'a1',
            '--fixed-reference', '--spec', str(ROOT / 'examples/wilderness/builder.json'),
            '--state', str(self.state), '--output', str(output)], capture_output=True, text=True, timeout=25)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(output.read_text())
        self.reports.append(report)
        self.completed(report)
        self.assertEqual('fixed-reference', report['decision']['provider']['kind'])
        self.assertFalse((self.world.data / 'decisions').exists())
        for token in self.world.access['sessions'].values():
            self.assertNotIn(token['token'], output.read_text())


if __name__ == '__main__':
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WildernessMissionAcceptance)
    if len(sys.argv) > 1:
        suite = unittest.TestSuite(t for t in suite if t._testMethodName in set(sys.argv[1:]))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {'suite': 'wilderness-resident-http', 'actualModelCalls': 0, 'decisionSource': 'test-double',
              'recordedAtUtc': datetime.now(timezone.utc).isoformat(), 'passed': result.wasSuccessful(),
              'testsRun': result.testsRun, 'tests': result.records,
              'failures': [{'test': str(t), 'detail': d} for t, d in result.failures + result.errors]}
    (RUN_ROOT / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN_ROOT / 'results.json')
    raise SystemExit(0 if result.wasSuccessful() else 1)
