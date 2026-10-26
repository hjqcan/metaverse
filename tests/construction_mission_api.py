#!/usr/bin/env python3
"""Explicit construction missions against actual r8 HTTP/SQLite; no model calls."""
from datetime import datetime, timezone
import json
import subprocess
import sys
import time
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import EvidenceResult, ROOT
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice
from wilderness_api import WildernessAcceptance
from continuous_navigation import distance, ARRIVAL_TOLERANCE

RUN_ROOT = ROOT / '.local/iter0017/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN_ROOT


def mission(recipe='platform.v1', target=None):
    return {'missionId': 'construction-' + recipe.split('.')[0], 'objective': '在指定地点建造公共设施，走到设施中心后返回起点。',
            'goals': [{'id': 'construction', 'label': '公共平台' if recipe == 'platform.v1' else '跨河木桥',
                       'target': target or ([8.2, 10.4] if recipe == 'platform.v1' else [16.4, 8]), 'buildRecipeId': recipe}],
            'allowBuild': True, 'allowGather': True,
            'budgets': {'commands': 250, 'wood': 3 if recipe == 'platform.v1' else 6, 'seconds': 600, 'modelCalls': 1}}


class ConstructionAcceptance(unittest.TestCase):
    def setUp(self):
        self.world = ActivityCandidate(self._testMethodName, scenario='wilderness-continuous-v1')
        self.a, self.b = self.world.client(), self.world.client('a2')
        self.state = self.world.data / 'mission.json'
        self.choose = Choice('construction')
        self.trace, self.reports = [], []

    def tearDown(self):
        (self.world.data / 'reports.json').write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + '\n')
        WildernessAcceptance.tearDown(self)

    def task(self, job=None, client=None, **kwargs):
        report = run_mission(client or self.a, job or mission(), self.state, self.choose, **kwargs)
        self.reports.append(report)
        return report

    def client(self, cls):
        return cls(self.world.url, self.world.access['sessions']['a1']['token'])

    def completed(self, report, client=None):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['constructionBuilt'])
        self.assertTrue(report['facts']['goalReached'])
        self.assertTrue(report['facts']['returned'])
        goal, fact = report['mission']['goal'], report['facts']['construction']
        self.assertEqual(goal['buildRecipeId'], fact['recipeId'])
        self.assertEqual(goal['target'], fact['position'])
        step = next(s for s in report['steps'] if s['commandId'] == fact['commandId'])
        self.assertEqual(('committed', 'build', fact['entityId'], goal['target']),
                         (step['status'], step['action']['type'], step['entityId'], step['action']['at']))
        observed = (client or self.a).observe()
        entity = next(e for e in observed['entities'] if e['entityId'] == fact['entityId'])
        self.assertEqual((fact['ownerActorId'], fact['position'], fact['woodSpent']),
                         (entity['ownerActorId'], entity['position'], entity['embodiedWood']))
        self.assertLessEqual(distance(observed['self']['position'], report['mission']['origin']), ARRIVAL_TOLERANCE)
        self.assertEqual(1, sum(s['status'] == 'committed' and s['action']['type'] == 'build' for s in report['steps']))

    def test_01_platform_is_built_with_actual_material_and_return(self):
        report = self.task(); self.completed(report)
        self.assertEqual((3, 3, 0), (report['facts']['woodGathered'], report['budget']['used']['wood'], report['facts']['woodClaimed']))
        before = self.a.observe()
        self.assertEqual(report, self.task()); self.assertEqual(before, self.a.observe()); self.assertEqual(1, self.choose.calls)

    def test_02_explicit_bridge_then_later_platform_and_free_visit(self):
        bridge = self.task(mission('bridge.v1')); self.completed(bridge)
        self.state = self.world.data / 'platform.json'
        platform = self.task(mission(target=[26.4, 14.5]), client=self.b); self.completed(platform, self.b)
        self.assertEqual(('a1','a2'),(bridge['mission']['actorId'],platform['mission']['actorId']))
        self.assertEqual(('a1','a2'),(bridge['facts']['construction']['ownerActorId'],platform['facts']['construction']['ownerActorId']))
        self.assertEqual(bridge['mission']['worldInstanceId'],platform['mission']['worldInstanceId'])
        self.state = self.world.data / 'visit.json'
        visit = mission(target=[26.4, 14.5]); visit['missionId'] = 'later-visitor'; visit['goals'][0].pop('buildRecipeId')
        visit.update(allowBuild=False, allowGather=False); visit['budgets']['wood'] = 0
        report = self.task(visit)
        self.assertEqual('a1',report['mission']['actorId'])
        self.assertEqual(bridge['mission']['worldInstanceId'],report['mission']['worldInstanceId'])
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertEqual((0, 0, []), (report['facts']['woodGathered'], report['budget']['used']['wood'], report['facts']['createdEntityIds']))
        self.assertFalse(report['facts']['constructionBuilt'])
        self.assertEqual(2, len(self.a.observe()['entities']))

    def test_03_lost_build_response_restores_same_entity_once(self):
        class Drop(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                response = super().request(method, path, payload, headers)
                if method == 'POST' and payload['action']['type'] == 'build': raise OSError('lost committed build reply')
                return response
        report = self.task(client=Drop(self.world.url, self.world.access['sessions']['a1']['token']))
        self.assertEqual('unknown', report['mission']['status']); self.assertFalse(report['facts']['constructionBuilt'])
        original = report['steps'][-1]['commandId']; entities = self.a.observe()['entities']
        self.assertEqual(1, len(entities)); self.world.restart()
        final = self.task(); self.completed(final)
        self.assertEqual(original, final['facts']['construction']['commandId'])
        self.assertEqual(entities, self.a.observe()['entities']); self.assertEqual(1, self.choose.calls)

    def test_04_server_exit_before_commit_retries_original_build(self):
        class Crash(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                if method == 'POST' and payload['action']['type'] == 'build':
                    headers = {**(headers or {}), 'X-Test-Fault': 'before-commit'}
                return super().request(method, path, payload, headers)
        first = self.task(client=self.client(Crash))
        self.assertEqual('unknown', first['mission']['status'])
        self.assertEqual(81, self.world.process.wait(timeout=10)); self.world.restart()
        self.assertEqual([], self.a.observe()['entities']); self.assertEqual(3, self.a.observe()['self']['inventory']['wood'])
        original = json.loads(self.state.read_text())['_state']['pending']['request']
        final = self.task(); self.completed(final)
        self.assertEqual(original['commandId'], final['facts']['construction']['commandId'])
        self.assertEqual(3, final['budget']['used']['wood'])

    def test_05_client_process_exit_after_commit_restores_original_build(self):
        jobfile = self.world.data / 'job.json'; jobfile.write_text(json.dumps(mission()))
        program = '''
import json,os,sys
sys.path[:0]=[sys.argv[1]+"/scripts",sys.argv[1]+"/tests"]
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice
class Crash(WorldClient):
 def request(self,method,path,payload=None,headers=None):
  result=super().request(method,path,payload,headers)
  if method=="POST" and payload["action"]["type"]=="build" and result[0]==200:os._exit(83)
  return result
access=json.load(open(sys.argv[3])); spec=json.load(open(sys.argv[4]))
run_mission(Crash(sys.argv[2],access["sessions"]["a1"]["token"]),spec,sys.argv[5],Choice("construction"))
'''
        child = subprocess.run([sys.executable, '-c', program, str(ROOT), self.world.url,
            str(self.world.data / 'access.json'), str(jobfile), str(self.state)], capture_output=True, text=True, timeout=60)
        self.assertEqual(83, child.returncode, child.stderr)
        saved = json.loads(self.state.read_text()); original = saved['_state']['pending']['request']['commandId']
        self.assertFalse(saved['facts']['constructionBuilt']); self.assertEqual(0, saved['budget']['used']['wood'])
        self.assertEqual(1, len(self.a.observe()['entities']))
        final = self.task(); self.completed(final)
        self.assertEqual(original, final['facts']['construction']['commandId']); self.assertEqual(0, self.choose.calls)

    def test_06_mismatched_receipt_and_absent_entity_keep_original_pending(self):
        class Wrong(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                status, result = super().request(method, path, payload, headers)
                if isinstance(result.get('result'), dict) and result['result'].get('action') == 'build': mutate(result)
                return status, result
        mutate = lambda r: r['result'].update(position=[8.3, 10.4])
        first = self.task(client=self.client(Wrong)); original = first['steps'][-1]['commandId']
        count = len(first['steps'])
        for mutate in (lambda r: r.update(commandId='other-command'), lambda r: r.update(identity=None),
                       lambda r: r['identity'].update(actorId='a2'), lambda r: r.update(stateVersion=r['stateVersion']+1),
                       lambda r: r['result'].update(inventoryWood=3), lambda r: r['result'].update(entityId='old-entity'),
                       lambda r: r['result'].update(position=[True, 10.4])):
            report = self.task(client=self.client(Wrong))
            self.assertEqual('unknown', report['mission']['status']); self.assertFalse(report['facts']['constructionBuilt'])
            self.assertEqual((0, count), (report['budget']['used']['wood'], len(report['steps'])))
            self.assertEqual(original, json.loads(self.state.read_text())['_state']['pending']['request']['commandId'])
        class Hidden(WorldClient):
            def observe(inner):
                observed = super().observe(); observed['entities'] = []; return observed
        report = self.task(client=self.client(Hidden))
        self.assertEqual('unconfirmed_construction_receipt', report['mission']['reason'])
        self.assertFalse(report['facts']['constructionBuilt']); self.assertEqual(0, report['budget']['used']['wood'])
        self.completed(self.task()); self.assertEqual(1, self.choose.calls)

    def test_07_permissions_material_budget_and_geometry_prevent_actions(self):
        invalid = mission(); invalid['allowBuild'] = False
        with self.assertRaises(ValueError): self.task(invalid)
        self.assertEqual(0, self.choose.calls); self.assertFalse(self.state.exists())
        cases = [({**mission(), 'allowGather': False}, 'blocked', 'natural_material_collection_required')]
        cheap = mission(); cheap['budgets']['wood'] = 2; cases.append((cheap, 'budget_exhausted', 'wood'))
        for target, reason in (([16.4,8], 'platform_requires_land'), ([11.7,8.5], 'construction_site_occupied'),
                               ([.5,7], 'construction_outside_world'), ([26.4,14.5], 'construction_site_unreachable')):
            cases.append((mission(target=target), 'blocked', reason))
        cases.append((mission('bridge.v1', [16.8,8]), 'blocked', 'bridge_alignment_required'))
        for index, (job, status, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                self.state = self.world.data / f'boundary-{index}.json'
                report = self.task(job)
                self.assertEqual((status, reason), (report['mission']['status'], report['mission']['reason']))
                self.assertEqual([], report['steps']); self.assertEqual(0, self.a.observe()['stateVersion'])
        self.state = self.world.data / 'commands.json'; job = mission(); job['budgets']['commands'] = 3
        report = self.task(job)
        self.assertEqual(('budget_exhausted', 'commands'), (report['mission']['status'], report['mission']['reason']))
        self.assertEqual(3, report['facts']['woodGathered']); self.assertFalse(report['facts']['constructionBuilt'])
        self.assertEqual([], self.a.observe()['entities'])

    def test_08_existing_facility_is_not_this_tasks_construction(self):
        self.completed(self.task()); before = self.a.observe()
        self.state = self.world.data / 'another.json'; job = mission(); job['missionId'] = 'another-platform'
        report = self.task(job)
        self.assertEqual(('blocked', 'construction_site_occupied'), (report['mission']['status'], report['mission']['reason']))
        self.assertFalse(report['facts']['constructionBuilt']); self.assertEqual([], report['steps'])
        self.assertEqual(before, self.a.observe())

    def test_09_pause_freezes_recipe_target_actor_and_permissions(self):
        self.task(max_steps=1); original = self.state.read_bytes()
        changes = [mission('bridge.v1'), mission(target=[8.2,10.6]), {**mission(), 'allowGather': False}]
        for job, client in [(job, self.a) for job in changes] + [(mission(), self.b)]:
            with self.assertRaises(ValueError): self.task(job, client=client)
            self.assertEqual(original, self.state.read_bytes())
        self.completed(self.task()); self.assertEqual(1, self.choose.calls)

    def test_10_stale_build_requires_original_rejection_then_new_attempt(self):
        peer = self.b
        class Stale(WorldClient):
            changed = False
            def observe(inner):
                observed = super().observe()
                observed.pop('commandConcurrency', None)  # Keep this original strict-mode regression.
                return observed
            def request(inner, method, path, payload=None, headers=None):
                if method == 'POST' and payload['action']['type'] == 'build' and not inner.changed:
                    inner.changed = True; observed = peer.observe()
                    self.assertEqual(200, peer.command({'schemaVersion':1, 'rulesVersion':'r8', 'commandId':'peer-walk',
                        'expectedStateVersion':observed['stateVersion'], 'action':{'type':'walk','to':[26,16.5]}})[0])
                return super().request(method, path, payload, headers)
        report = self.task(client=self.client(Stale)); self.completed(report)
        steps = [s for s in report['steps'] if s['action']['type'] == 'build']
        self.assertEqual(2, len(steps)); self.assertEqual(('rejected','STALE_STATE'), (steps[0]['status'],steps[0]['errorCode']))
        self.assertNotEqual(steps[0]['commandId'], steps[1]['commandId']); self.assertEqual(3, report['budget']['used']['wood'])

    def test_11_fixed_reference_cli_exports_construction_facts(self):
        output, spec = self.world.data / 'cli-report.json', self.world.data / 'spec.json'
        spec.write_text(json.dumps(mission()))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_resident.py'), '--url', self.world.url,
            '--access-file', str(self.world.data / 'access.json'), '--actor', 'a1', '--fixed-reference',
            '--spec', str(spec), '--state', str(self.state), '--output', str(output)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(output.read_text()); self.reports.append(report); self.completed(report)
        self.assertEqual('fixed-reference', report['decision']['provider']['kind']); self.assertNotIn('_state', report)
        for session in self.world.access['sessions'].values(): self.assertNotIn(session['token'], output.read_text())

    def test_12_visit_before_build_does_not_replace_visiting_completed_facility(self):
        self.task(max_steps=3)  # Actual inventory gathered, no build yet.
        def walk(target):
            while distance(self.a.observe()['self']['position'], target) > ARRIVAL_TOLERANCE:
                time.sleep(.205); observed = self.a.observe()
                status, receipt = self.a.command({'schemaVersion':1,'rulesVersion':'r8','commandId':uuid.uuid4().hex,
                    'expectedStateVersion':observed['stateVersion'],'action':{'type':'walk','to':target}})
                self.assertEqual(200,status); self.assertFalse(receipt['result']['blocked'])
        walk(mission()['goals'][0]['target'])
        before = self.task(max_steps=0)
        self.assertTrue(before['facts']['goalReached']); self.assertFalse(before['facts']['constructionBuilt'])
        walk([6.1,8.2])  # Manual activity while the original mission is paused.
        final = self.task(); self.completed(final)
        index = next(i for i,s in enumerate(final['steps']) if s['action']['type']=='build')
        self.assertTrue(any(s['status']=='committed' and s['action']['type']=='walk'
            and distance(s['position'],final['mission']['goal']['target']) <= ARRIVAL_TOLERANCE
            for s in final['steps'][index+1:]))
        self.assertEqual(1,self.choose.calls)

    def test_13_observation_failure_after_confirmation_keeps_built_fact(self):
        class FailAfterConfirmation(WorldClient):
            built = False
            confirmed_observations = 0
            def request(inner, method, path, payload=None, headers=None):
                response = super().request(method,path,payload,headers)
                if method=='POST' and payload['action']['type']=='build': inner.built=True
                return response
            def observe(inner):
                if inner.built:
                    inner.confirmed_observations += 1
                    if inner.confirmed_observations > 1: raise OSError('offline after confirmed construction')
                return super().observe()
        report=self.task(client=self.client(FailAfterConfirmation))
        self.assertEqual('unknown',report['mission']['status']); self.assertTrue(report['facts']['constructionBuilt'])
        fact=report['facts']['construction']
        self.assertTrue(any(e['entityId']==fact['entityId'] for e in report['world']['entities']))
        self.assertEqual(3,report['budget']['used']['wood'])
        self.assertIsNone(json.loads(self.state.read_text())['_state']['pending'])
        final=self.task(); self.completed(final)
        self.assertEqual(fact,final['facts']['construction']); self.assertEqual(1,self.choose.calls)


if __name__ == '__main__':
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ConstructionAcceptance)
    if len(sys.argv) > 1: suite = unittest.TestSuite(t for t in suite if t._testMethodName in set(sys.argv[1:]))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    (RUN_ROOT / 'results.json').write_text(json.dumps({'suite': 'construction-mission-http', 'actualModelCalls': 0,
        'decisionSource': 'test-double', 'passed': result.wasSuccessful(), 'testsRun': result.testsRun,
        'tests': result.records, 'failures': [{'test': str(t), 'detail': d} for t, d in result.failures + result.errors]}, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN_ROOT / 'results.json')
    raise SystemExit(0 if result.wasSuccessful() else 1)
