#!/usr/bin/env python3
"""Real protected-r8 missions under interference and recovery; no model calls."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import unittest
import uuid

import foundation_api
from foundation_api import EvidenceResult, ROOT
import activities_api
from activities_api import ActivityCandidate
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice
from construction_mission_api import mission, ConstructionAcceptance
from wilderness_api import WildernessAcceptance
import continuous_navigation as nav

if os.environ.get('ACTOR_TEST_DLL'):
    foundation_api.DLL = Path(os.environ['ACTOR_TEST_DLL']).resolve(strict=True)
RUN_ROOT = ROOT / '.local/iter0019/python' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN_ROOT
MODE = 'actor-state-v1'
SOURCES = ['scripts/command_preconditions.py', 'scripts/resident_mission.py', 'scripts/continuous_navigation.py',
           'scripts/wilderness_materials.py', 'scripts/resident_construction.py', 'scripts/foundation_agent.py',
           'src/World.Server/wwwroot/resident.js', 'tests/actor_mission_api.py']


def source_hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}


def walking():
    job = mission(target=[8.25, 7.35])
    job['missionId'] = 'actor-walk'
    job['goals'][0].pop('buildRecipeId')
    job.update(allowBuild=False, allowGather=False)
    job['budgets']['wood'] = 0
    return job


class ActorMissionAcceptance(unittest.TestCase):
    worlds = []
    task = ConstructionAcceptance.task
    completed = ConstructionAcceptance.completed

    def setUp(self):
        self.world = ActivityCandidate(self._testMethodName, scenario='wilderness-continuous-v1')
        self.addCleanup(self.world.stop)
        self.worlds.append(self.world)
        self.a, self.b = self.world.client(), self.world.client('a2')
        self.state = self.world.data / 'mission.json'
        self.choose = Choice('construction')
        self.trace, self.reports = [], []
        self.assertEqual({'version': 1, 'supportedModes': [MODE]}, self.a.observe().get('commandConcurrency'),
                         'This suite requires the ITER-0019 core candidate, not a simulated capability.')

    def tearDown(self):
        (self.world.data / 'reports.json').write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + '\n')
        WildernessAcceptance.tearDown(self)

    def client(self, *, before=None, after=None, observation=None):
        owner = self
        class Controlled(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                if method == 'POST' and before is not None:
                    headers = before(payload, headers)
                response = super().request(method, path, payload, headers)
                if method == 'POST' or '/commands/' in path:
                    owner.trace.append({'method': method, 'path': path, 'request': deepcopy(payload),
                                        'status': response[0], 'response': deepcopy(response[1])})
                return after(method, path, payload, response) if after is not None else response

            def observe(inner):
                result = super().observe()
                if observation is not None:
                    observation(result)
                return result
        return Controlled(self.world.url, self.world.access['sessions']['a1']['token'])

    def send(self, client, action):
        observed = client.observe()
        intent = {'schemaVersion': 1, 'rulesVersion': 'r8', 'commandId': uuid.uuid4().hex,
                  'expectedStateVersion': observed['stateVersion'], 'action': action}
        status, receipt = client.command(intent)
        self.trace.append({'request': intent, 'status': status, 'response': receipt})
        self.assertEqual(200, status, receipt)
        return receipt

    def peer_walk(self):
        position = self.b.observe()['self']['position']
        target = [26, 16.8 if position[1] > 16.9 else 17]
        time.sleep(.025)
        receipt = self.send(self.b, {'type': 'walk', 'to': target})
        self.assertFalse(receipt['result']['blocked'])
        self.assertGreater(nav.distance(position, receipt['result']['position']), 0)

    def interfere(self, intent, headers):
        self.peer_walk()
        return headers

    def pending(self):
        return json.loads(self.state.read_text())['_state']['pending']['request']

    def walk_to(self, client, target):
        for _ in range(300):
            observed = client.observe()
            if nav.near(observed['self']['position'], target):
                return
            route = nav.navigation(observed).route(observed['self']['position'], target)
            self.assertTrue(route, (observed['self']['position'], target))
            time.sleep(.205)
            receipt = self.send(client, {'type': 'walk', 'to': route[0]})
            self.assertFalse(receipt['result']['blocked'])
        self.fail('Real participant travel did not finish within its bounded command allowance')

    def test_01_real_interference_all_actions_finish_one_platform(self):
        report = self.task(mission(target=[9.2, 12.4]), client=self.client(before=self.interfere))
        self.completed(report)
        self.assertGreaterEqual(len(report['steps']), 20)
        self.assertEqual({'walk', 'gather', 'build'}, {s['action']['type'] for s in report['steps']})
        self.assertEqual(MODE, report['mission']['preconditionMode'])
        for step in report['steps']:
            self.assertEqual('committed', step['status'])
            self.assertEqual(step['expectedStateVersion'] + 1, step['execution']['appliedOnStateVersion'])
            self.assertEqual(step['expectedStateVersion'] + 2, step['stateVersion'])
        self.assertEqual((3, 3, 1), (report['facts']['woodGathered'], report['budget']['used']['wood'], self.choose.calls))
        (self.world.data / 'actual-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    def test_02_same_actor_aba_stops_original_task_after_rejection(self):
        def offline(intent, headers):
            raise OSError('before original transport')
        first = self.task(client=self.client(before=offline))
        self.assertEqual('unknown', first['mission']['status'])
        original = self.pending()
        self.send(self.a, {'type': 'walk', 'to': [5.1, 7]})
        time.sleep(.205)
        self.send(self.a, {'type': 'walk', 'to': [5, 7]})
        self.assertEqual([5, 7], self.a.observe()['self']['position'])
        final = self.task()
        self.assertEqual(('blocked', 'command_rejected:STALE_ACTOR_STATE'),
                         (final['mission']['status'], final['mission']['reason']))
        first_step = final['steps'][0]
        self.assertEqual((original['commandId'], 'rejected', 'STALE_ACTOR_STATE'),
                         (first_step['commandId'], first_step['status'], first_step['errorCode']))
        self.assertEqual(2, first_step['execution']['appliedOnStateVersion'])
        self.assertEqual(409, self.a.command(original)[0])
        self.assertEqual((1, 1, 0), (len(final['steps']), final['budget']['used']['commands'], final['facts']['woodGathered']))
        self.assertIsNone(json.loads(self.state.read_text())['_state']['pending'])
        saved_bytes = self.state.read_bytes()
        offline = self.world.client()
        def no_network(*args, **kwargs):
            raise AssertionError('The stopped task must not resume an old target')
        offline.request = no_network
        self.assertEqual(final, self.task(client=offline))
        self.assertEqual(saved_bytes, self.state.read_bytes())
        self.assertEqual(1, self.choose.calls)

    def test_03_other_resident_takes_one_wood_before_the_same_gather(self):
        # Reach the same tree by actual gathering, bridge construction and walking.
        bridge = run_mission(self.b, mission('bridge.v1'), self.world.data / 'peer-bridge.json', Choice('construction'))
        self.reports.append(bridge)
        self.assertEqual('completed', bridge['mission']['status'], bridge['mission'])
        self.walk_to(self.b, [5, 7])
        def compete(intent, headers):
            self.assertEqual('gather', intent['action']['type'])
            self.send(self.b, intent['action'])
            return headers
        report = self.task(client=self.client(before=compete), max_steps=1)
        self.assertEqual(('paused', 1), (report['mission']['status'], report['facts']['woodGathered']))
        step = report['steps'][0]
        receipt = self.a.request('GET', self.a.prefix + '/commands/' + step['commandId'])[1]
        self.assertEqual((2, 1, 1), (receipt['result']['remainingWoodBefore'], receipt['result']['remainingWood'],
                                   receipt['result']['inventoryWood']))
        self.assertEqual(step['expectedStateVersion'] + 2, step['stateVersion'])
        self.assertIsNone(json.loads(self.state.read_text())['_state']['pending'])

    def crash_build(self, fault, code):
        def crash(intent, headers):
            self.peer_walk()
            if intent['action']['type'] == 'build':
                return {**(headers or {}), 'X-Test-Fault': fault}
            return headers
        first = self.task(client=self.client(before=crash))
        self.assertEqual('unknown', first['mission']['status'])
        self.assertEqual(code, self.world.process.wait(timeout=10))
        original, count = self.pending(), len(first['steps'])
        self.world.restart()
        self.peer_walk()
        final = self.task()
        self.completed(final)
        self.assertEqual(original['commandId'], final['facts']['construction']['commandId'])
        self.assertEqual(3, final['budget']['used']['wood'])
        self.assertEqual(1, len(self.a.observe()['entities']))
        self.assertEqual(1, self.choose.calls)
        self.assertEqual(count, next(s['index'] for s in final['steps'] if s['action']['type'] == 'build'))
        return final

    def test_04_before_commit_exit_retries_same_mode_body_and_id(self):
        self.crash_build('before-commit', 81)

    def test_05_after_commit_exit_keeps_execution_and_completed_offline_read(self):
        final = self.crash_build('after-commit', 82)
        state_bytes = self.state.read_bytes()
        def no_network(*args, **kwargs):
            raise AssertionError('A completed task must not contact the world')
        offline = self.world.client()
        offline.request = no_network
        self.assertEqual(final, self.task(client=offline))
        self.assertEqual(state_bytes, self.state.read_bytes())

    def false_execution(self, action, job):
        mutation = lambda r: r.pop('execution')
        def alter(method, path, payload, response):
            status, receipt = response
            if isinstance(receipt.get('result'), dict) and receipt['result'].get('action') == action:
                mutation(receipt)
            return status, receipt
        first = self.task(job, client=self.client(after=alter))
        self.assertEqual(('unknown', 'unconfirmed_execution'), (first['mission']['status'], first['mission']['reason']))
        original, count = self.pending(), len(first['steps'])
        self.world.restart()
        for mutation in (
                lambda r: r.update(execution=None),
                lambda r: r['execution'].update(preconditionMode='other-mode'),
                lambda r: r['execution'].update(observedStateVersion=True),
                lambda r: r['execution'].update(observedStateVersion=r['execution']['observedStateVersion'] + 1),
                lambda r: r['execution'].update(appliedOnStateVersion=-1),
                lambda r: r['execution'].update(appliedOnStateVersion=r['execution']['appliedOnStateVersion'] + 1),
                lambda r: r.update(stateVersion=r['stateVersion'] + 1)):
            report = self.task(job, client=self.client(after=alter))
            self.assertEqual('unknown', report['mission']['status'])
            self.assertEqual(original, self.pending())
            self.assertEqual(count, report['budget']['used']['commands'])
            self.assertIsNone(report['steps'][-1]['execution'])
        final = self.task(job)
        self.assertEqual('completed', final['mission']['status'], final['mission'])
        if action == 'build':
            self.completed(final)
        self.assertEqual(1, self.choose.calls)

    def test_06_false_walk_execution_retains_pending(self):
        self.false_execution('walk', walking())

    def test_07_false_gather_execution_retains_pending(self):
        self.false_execution('gather', mission())

    def test_08_false_build_execution_retains_pending(self):
        self.false_execution('build', mission())

    def test_09_false_gather_transaction_quantities_retain_pending(self):
        mutation = lambda r: r['result'].pop('remainingWoodBefore')
        def alter(method, path, payload, response):
            status, receipt = response
            if isinstance(receipt.get('result'), dict) and receipt['result'].get('action') == 'gather':
                mutation(receipt)
            return status, receipt
        first = self.task(client=self.client(after=alter))
        self.assertEqual('unconfirmed_gather_receipt', first['mission']['reason'])
        original = self.pending()
        for mutation in (
                lambda r: r['result'].update(remainingWoodBefore=True),
                lambda r: r['result'].update(remainingWoodBefore=0),
                lambda r: r['result'].update(remainingWoodBefore=4),
                lambda r: r['result'].update(remainingWoodBefore=2),
                lambda r: r['result'].update(quantity=2),
                lambda r: r['result'].update(inventoryWood=2),
                lambda r: r['result'].update(nodeId='another-node')):
            report = self.task(client=self.client(after=alter))
            self.assertEqual('unknown', report['mission']['status'])
            self.assertEqual(original, self.pending())
            self.assertEqual((1, 0), (report['budget']['used']['commands'], report['facts']['woodGathered']))
        self.completed(self.task())

    def test_10_legacy_and_new_strict_tasks_do_not_upgrade_on_resume(self):
        hide = lambda r: r.pop('commandConcurrency', None)
        self.task(walking(), client=self.client(observation=hide), max_steps=1)
        saved = json.loads(self.state.read_text())
        saved['_state']['binding'].pop('preconditionBindingVersion')
        saved['_state']['binding'].pop('preconditionMode')
        saved['mission'].pop('preconditionMode')
        self.state.write_text(json.dumps(saved))  # Reproduce the actual pre-ITER19 local format.
        changed = False
        def once(intent, headers):
            nonlocal changed
            self.assertNotIn('preconditionMode', intent)
            if not changed:
                changed = True
                self.peer_walk()
            return headers
        report = self.task(walking(), client=self.client(before=once), max_steps=2)
        self.assertEqual(('rejected', 'STALE_STATE'), (report['steps'][1]['status'], report['steps'][1]['errorCode']))
        self.assertEqual(3, report['budget']['used']['commands'])
        self.assertEqual(1, self.choose.calls)
        self.assertNotIn('preconditionMode', json.loads(self.state.read_text())['mission'])
        self.state = self.world.data / 'new-strict.json'
        self.task(walking(), client=self.client(observation=hide), max_steps=0)
        report = self.task(walking(), max_steps=1)
        saved = json.loads(self.state.read_text())
        self.assertEqual(1, saved['_state']['binding']['preconditionBindingVersion'])
        self.assertIsNone(report['mission']['preconditionMode'])
        self.assertNotIn('execution', report['steps'][0])

    def test_11_mode_and_before_record_corruption_never_contacts_world(self):
        def offline(intent, headers):
            raise OSError('not submitted')
        self.task(client=self.client(before=offline))
        saved = json.loads(self.state.read_text())
        for mutate in (
                lambda s: s['_state']['binding'].pop('preconditionBindingVersion'),
                lambda s: s['_state']['binding'].pop('preconditionMode'),
                lambda s: s['mission'].pop('preconditionMode'),
                lambda s: s['_state']['binding'].update(preconditionMode=None),
                lambda s: s['_state']['pending']['request'].pop('preconditionMode'),
                lambda s: s['_state']['pending']['request'].update(preconditionMode=None),
                lambda s: s['steps'][-1].pop('preconditionMode'),
                lambda s: s['steps'][-1].update(expectedStateVersion=999),
                lambda s: s['_state']['pending'].pop('gatherBefore'),
                lambda s: s['_state']['pending']['gatherBefore'].update(remainingWood=True),
                lambda s: s['_state']['pending']['gatherBefore'].update(inventoryWood=-1),
                lambda s: s['_state']['pending']['gatherBefore'].update(position=None)):
            corrupt = deepcopy(saved); mutate(corrupt)
            self.state.write_text(json.dumps(corrupt))
            before = self.state.read_bytes()
            spy = self.world.client()
            def no_network(*args, **kwargs):
                raise AssertionError('Corrupt local binding must fail before network access')
            spy.request = no_network
            with self.assertRaises(ValueError):
                self.task(client=spy)
            self.assertEqual(before, self.state.read_bytes())
        self.state.write_text(json.dumps(saved))
        # Removing a current advertisement cannot rewrite a previously chosen mode.
        final = self.task(client=self.client(observation=lambda r: r.pop('commandConcurrency', None)))
        self.completed(final)
        self.assertEqual(MODE, final['mission']['preconditionMode'])
        self.assertEqual(saved['_state']['pending']['request']['commandId'], final['steps'][0]['commandId'])

    def test_12_rejected_execution_must_match_before_pending_is_cleared(self):
        def offline(intent, headers):
            raise OSError('not submitted')
        self.task(client=self.client(before=offline))
        original = self.pending()
        self.send(self.a, {'type': 'walk', 'to': [5.1, 7]})
        def alter(method, path, payload, response):
            status, receipt = response
            if receipt.get('status') == 'rejected':
                receipt['execution']['appliedOnStateVersion'] += 1
            return status, receipt
        first = self.task(client=self.client(after=alter))
        self.assertEqual('unconfirmed_execution', first['mission']['reason'])
        self.assertEqual(original, self.pending())
        final = self.task()
        self.assertEqual(('blocked', 'command_rejected:STALE_ACTOR_STATE'),
                         (final['mission']['status'], final['mission']['reason']))
        self.assertEqual((1, 0, 0), (len(final['steps']), final['facts']['woodGathered'], final['budget']['used']['wood']))
        self.assertEqual('STALE_ACTOR_STATE', final['steps'][0]['errorCode'])
        self.assertEqual(final['steps'][0]['stateVersion'], final['steps'][0]['execution']['appliedOnStateVersion'])


if __name__ == '__main__':
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    before = source_hashes()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ActorMissionAcceptance)
    if len(sys.argv) > 1:
        suite = unittest.TestSuite(t for t in suite if t._testMethodName in set(sys.argv[1:]))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    after = source_hashes()
    stopped = all(w.process.poll() is not None for w in ActorMissionAcceptance.worlds)
    summary = {'suite': 'actor-mission-http', 'actualModelCalls': 0, 'decisionSource': 'test-double',
               'passed': result.wasSuccessful() and before == after and stopped, 'testsRun': result.testsRun,
               'tests': result.records, 'sourceHashesBefore': before, 'sourceHashesAfter': after,
               'sourceStable': before == after, 'allStartedServicesStopped': stopped,
               'serverDllSha256': hashlib.sha256(foundation_api.DLL.read_bytes()).hexdigest(),
               'failures': [{'test': str(t), 'detail': d} for t, d in result.failures + result.errors]}
    (RUN_ROOT / 'results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN_ROOT / 'results.json')
    raise SystemExit(0 if summary['passed'] else 1)
