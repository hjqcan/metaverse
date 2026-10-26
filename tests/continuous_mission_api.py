#!/usr/bin/env python3
"""Continuous resident acceptance on real r8 HTTP/SQLite. No model calls."""
from datetime import datetime, timezone
import json
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import EvidenceResult, ROOT
from foundation_agent import WorldClient
from resident_mission import run_mission, _route_info
from resident_mission_api import Choice
from wilderness_api import WildernessAcceptance
from continuous_navigation import distance, ARRIVAL_TOLERANCE

RUN_ROOT = ROOT / '.local/iter0015/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN_ROOT


def mission(build=False):
    return {'missionId': 'continuous-builder' if build else 'continuous-walker',
            'objective': '沿自然地形到目标后返回，有权限时采集木材并造桥。',
            'goals': [{'id': 'destination', 'label': '连续坐标目标', 'target': [26.2, 7.4] if build else [8.25, 7.35]}],
            'allowBuild': build, 'allowGather': build,
            'budgets': {'commands': 200, 'wood': 6 if build else 0, 'seconds': 600, 'modelCalls': 1}}


class ContinuousMissionAcceptance(unittest.TestCase):
    def setUp(self):
        self.world = ActivityCandidate(self._testMethodName, scenario='wilderness-continuous-v1')
        self.a = self.world.client()
        self.state = self.world.data / 'mission.json'
        self.choose = Choice('destination')
        self.trace, self.reports = [], []

    def tearDown(self):
        (self.world.data / 'reports.json').write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + '\n')
        WildernessAcceptance.tearDown(self)

    def task(self, job=None, client=None, **kwargs):
        report = run_mission(client or self.a, job or mission(), self.state, self.choose, **kwargs)
        self.reports.append(report)
        return report

    def completed(self, report):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['goalReached'])
        self.assertTrue(report['facts']['returned'])
        self.assertLessEqual(distance(self.a.observe()['self']['position'], report['mission']['origin']), ARRIVAL_TOLERANCE)
        self.assertFalse(any(s['action']['type'] == 'move' for s in report['steps']))
        previous = report['mission']['origin']
        for step in report['steps']:
            if step['action']['type'] == 'walk' and step['status'] == 'committed':
                self.assertLessEqual(distance(previous, step['position']), .600001)
            if step['status'] == 'committed':
                previous = step['position']

    def test_01_fractional_target_obstacle_detour_and_return(self):
        report = self.task()
        self.completed(report)
        self.assertTrue(any(any(type(n) is float and n != int(n) for n in s['position']) for s in report['steps']))
        self.assertEqual(0, report['facts']['woodGathered'])
        self.assertEqual('continuous-xz', report['world']['coordinateSystem'])
        self.assertNotIn('blocked', report['world'])
        self.assertEqual([8.25, 7.35], report['mission']['goal']['target'])
        self.assertEqual(report, self.task())
        self.assertEqual(1, self.choose.calls)

    def test_02_lost_walk_response_recovers_original_position_once(self):
        class Drop(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                result = super().request(method, path, payload, headers)
                if method == 'POST':
                    raise OSError('lost reply after actual commit')
                return result
        first = self.task(client=Drop(self.world.url, self.world.access['sessions']['a1']['token']))
        self.assertEqual('unknown', first['mission']['status'])
        original = first['steps'][0]['commandId']
        self.world.restart()
        final = self.task()
        self.completed(final)
        self.assertEqual(original, final['steps'][0]['commandId'])
        self.assertEqual(1, self.choose.calls)

    def test_03_wrong_walk_receipt_cannot_confirm_a_teleport(self):
        class Wrong(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                status, reply = super().request(method, path, payload, headers)
                if method == 'POST':
                    reply['result']['position'] = [26.2, 7.4]
                return status, reply
        first = self.task(client=Wrong(self.world.url, self.world.access['sessions']['a1']['token']))
        self.assertEqual(('unknown', 'unconfirmed_walk_receipt'), (first['mission']['status'], first['mission']['reason']))
        self.assertFalse(first['facts']['goalReached'])
        self.completed(self.task())

    def test_04_actual_gather_bridge_crossing_and_later_resident_reuse(self):
        builder = self.task(mission(True))
        self.completed(builder)
        self.assertEqual((6, 6, 1), (builder['facts']['woodGathered'], builder['budget']['used']['wood'], len(builder['facts']['createdEntityIds'])))
        built = self.a.observe()['entities']
        self.a = self.world.client('a2')
        self.state = self.world.data / 'traveler.json'
        job = mission(); job['missionId'] = 'continuous-traveler'; job['goals'][0]['target'] = [5.1, 7.2]
        traveler = self.task(job)
        self.completed(traveler)
        self.assertEqual(0, traveler['facts']['woodGathered'])
        self.assertEqual(0, traveler['budget']['used']['wood'])
        self.assertEqual(built, self.a.observe()['entities'])

    def test_05_budget_and_gather_permission_prevent_material_actions(self):
        job = mission(True); job['allowGather'] = False
        report = self.task(job)
        self.assertEqual('blocked', report['mission']['status'])
        self.assertEqual([], report['steps'])
        self.assertEqual(0, report['facts']['woodGathered'])
        self.state = self.world.data / 'budget.json'
        job = mission(True); job['budgets']['wood'] = 5
        report = self.task(job)
        self.assertEqual(('budget_exhausted', 'wood'), (report['mission']['status'], report['mission']['reason']))
        self.assertEqual([], report['steps'])
        self.assertEqual(0, self.a.observe()['stateVersion'])

    def test_06_pause_preserves_identity_permissions_and_command_budget(self):
        first = self.task(max_steps=1)
        self.assertEqual('paused', first['mission']['status'])
        for job, client in [(mission(), self.world.client('a2')), ({**mission(), 'allowGather': True}, self.a)]:
            with self.assertRaises(ValueError): self.task(job, client=client)
        self.completed(self.task())
        self.assertEqual(1, self.choose.calls)
        self.state = self.world.data / 'one-command.json'
        job = mission(); job['budgets']['commands'] = 1
        report = self.task(job)
        self.assertEqual(('budget_exhausted', 'commands'), (report['mission']['status'], report['mission']['reason']))
        self.assertEqual(1, len(report['steps']))

    def test_07_query_identity_version_and_collision_evidence(self):
        class Drop(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                response = super().request(method, path, payload, headers)
                if method == 'POST': raise OSError('lost committed response')
                return response
        first = self.task(client=Drop(self.world.url, self.world.access['sessions']['a1']['token']))
        self.assertEqual('unknown', first['mission']['status'])
        class WrongQuery(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                status, result = super().request(method, path, payload, headers)
                if method == 'GET' and '/commands/' in path: mutate(result)
                return status, result
        for mutate in (lambda r: r.update(identity=None), lambda r: r['identity'].update(actorId='a2'),
                       lambda r: r.update(stateVersion=r['stateVersion']+1), lambda r: r['result'].update(blocked=1)):
            report = self.task(client=WrongQuery(self.world.url, self.world.access['sessions']['a1']['token']))
            self.assertEqual('unknown', report['mission']['status'])
            self.assertEqual(1, len(report['steps']))
        self.completed(self.task())

    def test_08_fixed_reference_cli_exports_fractional_report(self):
        output, spec = self.world.data / 'cli-report.json', self.world.data / 'spec.json'
        spec.write_text(json.dumps(mission()))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_resident.py'), '--url', self.world.url,
            '--access-file', str(self.world.data / 'access.json'), '--actor', 'a1', '--fixed-reference',
            '--spec', str(spec), '--state', str(self.state), '--output', str(output)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(output.read_text()); self.reports.append(report); self.completed(report)
        self.assertEqual('fixed-reference', report['decision']['provider']['kind'])
        self.assertFalse((self.world.data / 'decisions').exists())
        self.assertNotIn('_state', report)
        for session in self.world.access['sessions'].values(): self.assertNotIn(session['token'], output.read_text())

    def test_09_actual_collision_receipt_stops_without_claiming_arrival(self):
        class IncompleteTerrain(WorldClient):
            def observe(inner):
                observed = super().observe()
                observed['terrain']['obstacles'] = []  # Only the test observation omits rocks.
                return observed
        job = mission(); job['goals'][0]['target'] = [11.7, 8.5]
        report = self.task(job, client=IncompleteTerrain(self.world.url, self.world.access['sessions']['a1']['token']))
        self.assertEqual(('blocked', 'movement_collision'), (report['mission']['status'], report['mission']['reason']))
        self.assertFalse(report['facts']['goalReached'])
        self.assertEqual(True, report['steps'][-1]['blocked'])
        self.assertEqual('committed', report['steps'][-1]['status'])
        self.assertIsNone(json.loads(self.state.read_text())['_state']['pending'])
        self.assertEqual(self.a.observe()['self']['position'], report['steps'][-1]['position'])

    def test_10_stale_walk_replans_after_authoritative_rejection(self):
        peer = self.world.client('a2')
        class Stale(WorldClient):
            changed = False
            def request(inner, method, path, payload=None, headers=None):
                if method == 'POST' and not inner.changed:
                    inner.changed = True; observed = peer.observe()
                    self.assertEqual(200, peer.command({'schemaVersion': 1, 'rulesVersion': 'r8',
                        'commandId': 'peer-walk', 'expectedStateVersion': observed['stateVersion'],
                        'action': {'type': 'walk', 'to': [26, 16.5]}})[0])
                return super().request(method, path, payload, headers)
        report = self.task(client=Stale(self.world.url, self.world.access['sessions']['a1']['token']))
        self.completed(report)
        self.assertEqual(('rejected', 'STALE_STATE'), (report['steps'][0]['status'], report['steps'][0]['errorCode']))
        self.assertNotEqual(report['steps'][0]['commandId'], report['steps'][1]['commandId'])

    def test_11_planning_time_counts_before_any_material_mutation(self):
        calls, elapsed = 0, 0
        def planning(*args, **kwargs):
            nonlocal calls, elapsed
            result = _route_info(*args, **kwargs)
            calls += 1
            if calls == 2: elapsed = 601  # Deterministic expiry during runtime planning.
            return result
        clock = SimpleNamespace(time=lambda: time.time() + elapsed, sleep=time.sleep)
        with patch('resident_mission._route_info', side_effect=planning), patch('resident_mission.time', clock):
            report = self.task()
        self.assertEqual(('budget_exhausted', 'seconds'), (report['mission']['status'], report['mission']['reason']))
        self.assertEqual(2, calls)
        self.assertEqual([], report['steps'])
        self.assertEqual(0, self.a.observe()['stateVersion'])


if __name__ == '__main__':
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContinuousMissionAcceptance)
    if len(sys.argv) > 1:
        suite = unittest.TestSuite(t for t in suite if t._testMethodName in set(sys.argv[1:]))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    (RUN_ROOT / 'results.json').write_text(json.dumps({'suite': 'continuous-mission-http', 'actualModelCalls': 0,
        'decisionSource': 'test-double', 'passed': result.wasSuccessful(), 'testsRun': result.testsRun,
        'tests': result.records, 'failures': [{'test': str(t), 'detail': d} for t, d in result.failures + result.errors]}, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN_ROOT / 'results.json')
    raise SystemExit(0 if result.wasSuccessful() else 1)
