#!/usr/bin/env python3
"""Builder self-check of v1/v2 material missions on actual isolated HTTP worlds.

CONTINUOUS_MATERIAL_BASELINE optionally selects a stopped two-note baseline;
otherwise the shared fixture builds it through real commands. WORLD_SERVER_DLL
selects an immutable candidate reused across isolated worlds. CONTINUOUS_MATERIAL_OLD_PYTHON
optionally selects actual previous Python scripts for pre-adoption pending files.
No world facts, production clock or resource balances are edited with SQL.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid

import foundation_api
from foundation_api import ROOT, EvidenceResult
import activities_api
import material_access_api
from material_access_api import MaterialAccessAcceptance, reserve, harvest
from continuous_material_api import baseline, Continued, rows
from foundation_agent import WorldClient
from resident_mission import run_mission
from activity_choice import choose_lowest_cost
import resident_mission
import resident_material_access as material
import resident_entity_notes as notes
import resident_construction as construction

RUN = ROOT / '.local/iter0024/python' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
SOURCE_DLL = Path(os.environ.get('WORLD_SERVER_DLL', foundation_api.DLL)).resolve()
DLL = SOURCE_DLL
OLD_PYTHON = Path(os.environ.get('CONTINUOUS_MATERIAL_OLD_PYTHON', ROOT / 'scripts')).resolve()
SOURCE = None
FILES = ['scripts/resident_material_access.py', 'scripts/resident_mission.py', 'scripts/resident_entity_notes.py',
         'tests/continuous_material_mission_api.py', 'tests/fixtures/continuous-material-platform.json']


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mission():
    return json.loads((ROOT / 'tests/fixtures/continuous-material-platform.json').read_text())


PRE_ADOPTION_RUNNER = r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from foundation_agent import WorldClient
from resident_mission import run_mission
from activity_choice import choose_lowest_cost
url,access,actor,spec,state,output,action,when=sys.argv[2:]
class Client(WorldClient):
    def request(self,method,path,payload=None,headers=None):
        target=method=='POST' and payload['action']['type']==action
        if target and when=='before': raise OSError('isolated previous-client pre-submit failure')
        result=super().request(method,path,payload,headers)
        if target and when=='after': raise OSError('isolated previous-client lost response')
        return result
token=json.loads(Path(access).read_text())['sessions'][actor]['token']
report=run_mission(Client(url,token),json.loads(Path(spec).read_text()),state,choose_lowest_cost)
Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
assert report['mission']['status']=='unknown',report['mission']
'''


class ContinuousMaterialMissionAcceptance(unittest.TestCase):
    intent = MaterialAccessAcceptance.intent
    post = MaterialAccessAcceptance.post
    send = MaterialAccessAcceptance.send
    walk = MaterialAccessAcceptance.walk
    until = MaterialAccessAcceptance.until
    active = MaterialAccessAcceptance.active
    all_worlds = []

    @classmethod
    def setUpClass(cls):
        global SOURCE
        RUN.mkdir(parents=True, exist_ok=True)
        SOURCE = baseline(RUN / 'seed', DLL)
        cls.baseline_hash = digest(SOURCE / 'world.db')
        foundation_api.DLL = material_access_api.DLL = DLL

    def setUp(self):
        self.worlds, self.trace, self.traffic, self.reports = [], [], [], []
        self.world = self.copy('world')
        self.a, self.b, self.c = [self.world.client(a) for a in ('a1', 'a2', 'a3')]
        initial = self.a.observe(); self.instance = initial['world']['instanceId']
        self.assertEqual((12, 0, 5, 2, 6), (initial['materialAccess']['generatedWood'], initial['materialAccess']['stockWood'],
                                          len(initial['entities']), initial['entityNotes']['totalCount'], initial['self']['inventory']['wood']))
        self.state = self.world.data / 'mission.json'

    def copy(self, suffix):
        world = Continued(SOURCE, RUN / (self._testMethodName + '-' + suffix), DLL)
        self.addCleanup(world.stop)
        world.original = rows(world.data)
        self.worlds.append(world); self.all_worlds.append(world)
        return world

    def fresh(self, suffix):
        activities_api.RUN_ROOT = RUN / self._testMethodName
        foundation_api.DLL = material_access_api.DLL = DLL
        world = activities_api.ActivityCandidate(suffix, scenario='wilderness-material-access-v1')
        self.addCleanup(world.stop)
        world.dll = DLL; world.adopt = lambda instance: Continued.adopt(world, instance)
        world.original = rows(world.data)
        self.worlds.append(world); self.all_worlds.append(world)
        instance = world.client('a3').observe()['world']['instanceId']; world.stop()
        result = subprocess.run(['dotnet', str(DLL), 'enable-material-source', '--instance', instance],
                                cwd=ROOT, env=world.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr); world.start()
        return world

    def adopt(self, world=None):
        world = world or self.world
        instance = world.client('a2').observe()['world']['instanceId']; world.stop()
        before = rows(world.data)
        result = world.adopt(instance)
        self.assertEqual(0, result.returncode, result.stderr)
        after = rows(world.data)
        self.assertEqual(before['material_source'], after['material_source'])
        self.trace.append({'adoption': result.stdout, 'instance': instance, 'sourceBefore': before['material_source']})
        world.start()
        observed = world.client('a2').observe()
        self.assertEqual((2, None), (observed['materialAccess']['version'], observed['materialAccess']['inputBudget']))
        self.assertTrue(material.supported(observed), observed['materialAccess'])

    def tearDown(self):
        for world in self.worlds: world.stop()
        for name, value in (('trace.json', self.trace), ('traffic.json', self.traffic), ('reports.json', self.reports)):
            (self.world.data / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        for world in self.worlds:
            current = rows(world.data)
            for table in ('entities', 'receipts', 'events', 'resource_ledger', 'entity_notes'):
                self.assertTrue(set(world.original.get(table, [])).issubset(current.get(table, [])), table)
            for table in ('resource_nodes', 'world_instance', 'entity_note_adoption'):
                self.assertEqual(world.original.get(table), current.get(table), table)
            with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
                self.assertEqual('ok', db.execute('PRAGMA integrity_check').fetchone()[0])
                self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())
                generated, stock = db.execute('SELECT generated_wood,stock_wood FROM material_source').fetchone()
                total = sum(db.execute(q).fetchone()[0] for q in ('SELECT sum(remaining_wood) FROM resource_nodes',
                            'SELECT sum(wood) FROM residents', 'SELECT coalesce(sum(embodied_wood),0) FROM entities')) + stock
                self.assertEqual(12 + generated, total)
                self.assertEqual(generated, db.execute('SELECT coalesce(sum(quantity),0) FROM material_production').fetchone()[0])
                early = next(row for row in world.original['residents'] if row[1] == 'a1')
                self.assertEqual(early, db.execute("SELECT * FROM residents WHERE actor_id='a1'").fetchone())
        self.assertEqual(self.baseline_hash, digest(SOURCE / 'world.db'))

    def saved(self): return json.loads(self.state.read_text())

    def task(self, job=None, client=None, choose=choose_lowest_cost, **kwargs):
        report = run_mission(client or self.b, job or mission(), self.state, choose, **kwargs)
        self.reports.append(report); return report

    def controlled(self, world=None, actor='a2', before=None, after=None):
        world = world or self.world; owner = self
        class Client(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                if before: headers = before(method, path, payload, headers)
                result = super().request(method, path, payload, headers)
                owner.traffic.append({'method': method, 'path': path, 'payload': deepcopy(payload), 'response': deepcopy(result)})
                return after(method, path, payload, result) if after else result
        return Client(world.url, world.access['sessions'][actor]['token'])

    def completed(self, report, actor='a2'):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['constructionBuilt'] and report['facts']['returned'] and report['facts']['goalReached'])
        self.assertEqual((3, 3, 0, 0), (report['facts']['materialWoodHarvested'], report['budget']['used']['wood'],
                                     report['facts']['woodGathered'], report['facts']['woodTransferred']))
        self.assertEqual(actor, report['facts']['construction']['ownerActorId'])
        self.assertEqual(1, sum(s['action']['type'] == 'reserve_material' for s in report['steps']))
        self.assertEqual(3, sum(s['action']['type'] == 'harvest_material' for s in report['steps']))
        self.assertEqual(2, report['world']['materialAccess']['version'])
        self.assertIsNone(report['world']['materialAccess']['inputBudget'])

    def prior_pending(self, world, action, when, actor='a3', job=None):
        job = job or mission(); self.state = world.data / 'prior-state.json'
        spec = world.data / 'prior-spec.json'; spec.write_text(json.dumps(job, ensure_ascii=False))
        output = world.data / 'prior-report.json'
        command = [sys.executable, '-c', PRE_ADOPTION_RUNNER, str(OLD_PYTHON), world.url,
                   str(world.data / 'access.json'), actor, str(spec), str(self.state), str(output), action, when]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(0, result.returncode, result.stderr)
        self.reports.append(json.loads(output.read_text()))
        self.trace.append({'priorPython': str(OLD_PYTHON), 'action': action, 'failure': when,
                           'state': str(self.state), 'stdout': result.stdout})
        return deepcopy(self.saved()['_state']['pending']['request'])

    def test_01_actual_cli_fifth_platform_and_later_production(self):
        self.adopt()
        observed = self.b.observe(); self.assertIsNone(construction.placement_issue(observed, mission()['goals'][0]))
        self.assertIsNone(material.plan(observed, mission()['goals'][0])['reason'])
        output = self.world.data / 'cli-report.json'
        command = [sys.executable, str(ROOT / 'scripts/run_resident.py'), '--url', self.world.url,
                   '--access-file', str(self.world.data / 'access.json'), '--actor', 'a2', '--fixed-reference',
                   '--spec', str(ROOT / 'tests/fixtures/continuous-material-platform.json'),
                   '--state', str(self.state), '--output', str(output)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(0, result.returncode, result.stderr)
        (self.world.data / 'cli-command.json').write_text(json.dumps({'argv': command, 'stdout': result.stdout, 'stderr': result.stderr}, indent=2))
        report = json.loads(output.read_text()); self.reports.append(report); self.completed(report)
        self.assertEqual('fixed-reference', report['decision']['provider']['kind'])
        self.assertEqual(1, report['budget']['used']['modelCalls'])
        self.assertEqual(2, report['world']['entityNotes']['totalCount'])
        after = self.b.observe(); self.assertEqual(6, len(after['entities']))
        self.assertEqual(self.instance, after['world']['instanceId'])
        self.assertGreaterEqual(after['materialAccess']['generatedWood'], 15)
        rid = self.send(self.c, reserve())['result']['reservationId']
        self.active(self.c, rid); self.walk(self.c, [28, 10]); later = self.send(self.c, harvest(rid))
        self.assertEqual(1, later['result']['quantity'])
        self.assertGreaterEqual(self.c.observe()['materialAccess']['generatedWood'], 18)
        self.world.restart(); self.assertEqual(2, self.b.observe()['entityNotes']['totalCount'])
        raw = self.state.read_bytes(); offline = self.world.client('a2')
        offline.request = lambda *_a, **_k: self.fail('completed material task requested network')
        self.assertEqual(report, self.task(client=offline)); self.assertEqual(raw, self.state.read_bytes())
        for mutate in (lambda s: s['facts']['materialHarvests'][1].update(remaining=True),
                       lambda s: s['facts']['construction'].update(woodSpent=True)):
            damaged = json.loads(raw); mutate(damaged); self.state.write_text(json.dumps(damaged))
            with self.assertRaises(ValueError): self.task(client=offline)
        self.state.write_bytes(raw)

    def test_02_first_failed_query_budgets_and_shared_note_startup(self):
        self.adopt()
        note = json.loads((ROOT / 'tests/fixtures/entity-note.json').read_text())
        note['goals'][0]['entityNote']['entityId'] = self.b.observe()['entityNotes']['target']['entityId']
        for index, job in enumerate((mission(), note)):
            self.state = self.world.data / f'startup-{index}.json'; job['budgets']['queries'] = 1
            failed = self.world.client('a2'); calls = []
            def unavailable(*_a, **_k):
                calls.append(self.saved()); return 503, {'error': {'code': 'SERVICE_UNAVAILABLE'}}
            failed.request = unavailable
            with self.assertRaises(RuntimeError): self.task(job, failed)
            original = self.saved()
            self.assertEqual(material.STARTUP if index == 0 else notes.STARTUP, original['kind'])
            self.assertEqual(1, calls[0]['used']['queries']); self.assertNotIn('mission', original)
            offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('startup budget replenished')
            with self.assertRaises(notes.StartupBudget): self.task(job, offline)
            for mutate in (lambda s: s['used'].update(queries=0), lambda s: s['queries'].clear(),
                           lambda s: s['endpoint'].update(url='http://different'), lambda s: s.pop('kind')):
                damaged = deepcopy(original); mutate(damaged); self.state.write_text(json.dumps(damaged))
                with self.assertRaises(ValueError): self.task(job, offline)
        self.state = self.world.data / 'seconds.json'; job = mission(); job['budgets']['seconds'] = 1
        with self.assertRaises(RuntimeError): self.task(job, failed)
        time.sleep(1.1)
        with self.assertRaises(notes.StartupBudget): self.task(job, offline)
        self.assertEqual(1, self.saved()['used']['queries'])
        self.state = self.world.data / 'eventually.json'; job = mission(); job['budgets']['queries'] = 3
        with self.assertRaises(RuntimeError): self.task(job, failed)
        started = self.saved()['startedEpoch']
        restored = self.task(job, max_steps=0)
        self.assertEqual(('paused', 3), (restored['mission']['status'], restored['budget']['used']['queries']))
        self.assertEqual(started, self.saved()['_state']['startedEpoch'])
        self.assertEqual('budget_exhausted', self.task(job, offline)['mission']['status'])

    def test_03_unknown_and_damaged_policy_is_not_material_authority(self):
        self.assertTrue(material.supported(self.b.observe()))
        self.adopt()
        mutations = [lambda c: c.update(version=3), lambda c: c.update(inputBudget=12), lambda c: c.pop('inputBudget'),
                     lambda c: c.pop('productionPolicy'), lambda c: c['productionPolicy'].update(id='unknown'),
                     lambda c: c['productionPolicy'].update(version=True), lambda c: c['productionPolicy'].pop('adoptedAtEventCursor'),
                     lambda c: c['productionPolicy'].update(adoptedAtEventCursor=c['productionPolicy']['adoptedAtStateVersion'] + 2),
                     lambda c: c['productionPolicy'].update(generatedWoodAtAdoption=13),
                     lambda c: c['productionPolicy'].update(adoptedAtServiceMs=10**15),
                     lambda c: c['productionPolicy'].update(productionPeriodAtAdoption=True)]
        for index, mutate in enumerate(mutations):
            self.state = self.world.data / f'policy-{index}.json'
            def corrupt(method, path, payload, response):
                if path.endswith('/observation'): mutate(response[1]['materialAccess'])
                return response
            offset = len(self.traffic)
            with self.assertRaises((ValueError, RuntimeError)): self.task(client=self.controlled(after=corrupt))
            self.assertFalse(any(t['method'] == 'POST' for t in self.traffic[offset:]))
            self.assertEqual(1, self.saved()['used']['queries'])
        self.state = self.world.data / 'original-policy.json'
        def unsent(method, path, payload, headers):
            if method == 'POST': raise OSError('isolated before submission')
            return headers
        self.task(client=self.controlled(before=unsent)); request = self.saved()['_state']['pending']['request']
        def changed(method, path, payload, response):
            if path.endswith('/observation'): response[1]['materialAccess']['productionPolicy']['adoptedAtEventCursor'] += 1
            return response
        offset = len(self.traffic); unknown = self.task(client=self.controlled(after=changed))
        self.assertEqual('unknown', unknown['mission']['status'])
        self.assertEqual(request, self.saved()['_state']['pending']['request'])
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic[offset:]))

    def test_04_confirmed_reservation_and_query_limit_coexist(self):
        for queries, actor in ((2, 'a2'), (4, 'a3')):
            world = self.world if queries == 2 else self.copy('four'); self.adopt(world)
            self.state = world.data / 'budget.json'; job = mission(); job['budgets']['queries'] = queries
            report = self.task(job, self.controlled(world, actor))
            self.assertEqual(('budget_exhausted', queries), (report['mission']['status'], report['budget']['used']['queries']))
            self.assertEqual(queries == 4, report['facts']['materialReservation'] is not None)
            pending = deepcopy(self.saved()['_state']['pending'])
            if queries == 4:
                proof = report['facts']['materialReservation']
                self.assertEqual(proof, report['steps'][0]['materialEvidence'])
                self.assertEqual('committed', report['steps'][0]['status'])
                (RUN / 'query4-confirmed-reservation-report.json').write_text(
                    json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            offline = world.client(actor); offline.request = lambda *_a, **_k: self.fail('query budget refilled')
            restored = self.task(job, offline)
            self.assertEqual(queries, restored['budget']['used']['queries'])
            self.assertEqual(pending, self.saved()['_state']['pending'])

    def test_05_permissions_and_damaged_saved_state_are_zero_io(self):
        for mutate in (lambda j: j.pop('allowMaterialAccess'), lambda j: j.update(allowBuild=False),
                       lambda j: j['goals'][0]['materialAccess'].update(quantity=6), lambda j: j['budgets'].pop('queries')):
            job = mission(); mutate(job)
            with self.assertRaises(ValueError): self.task(job, self.controlled())
        self.assertEqual([], self.traffic); self.adopt()
        def unsent(method, path, payload, headers):
            if method == 'POST': raise OSError('isolated before submission')
            return headers
        self.task(client=self.controlled(before=unsent)); original = self.saved()
        for mutate in (lambda s: s['mission'].update(allowMaterialAccess=False), lambda s: s['mission'].update(allowBuild=False),
                       lambda s: s['mission'].update(allowGather=True), lambda s: s['budget']['used'].update(queries=0),
                       lambda s: s['budget']['limits'].update(queries=5000), lambda s: s['_state']['materialAccessQueries'].pop(),
                       lambda s: s['budget']['limits'].update(queries=300.0), lambda s: s['budget']['used'].update(commands=0),
                       lambda s: s['budget']['used'].update(wood=True), lambda s: s['budget']['used'].update(modelCalls=2),
                       lambda s: s['budget']['used'].update(seconds=-1),
                       lambda s: s['_state'].pop('materialAccessTrackingVersion'),
                       lambda s: s['_state']['materialProductionPolicy'].update(adoptedAtEventCursor=0),
                       lambda s: s['_state']['initial']['materialAccess'].update(inputBudget=12),
                       lambda s: s['_state']['pending']['request']['action'].update(sourceId='another'),
                       lambda s: s['_state']['pending']['materialBefore'].update(inventoryWood=1)):
            damaged = deepcopy(original); mutate(damaged); self.state.write_text(json.dumps(damaged))
            offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('damaged state requested network')
            with self.assertRaises(ValueError): self.task(client=offline, choose=lambda _: self.fail('damaged state selected'))
        self.state.write_text(json.dumps(original))
        self.assertEqual('paused', self.task(max_steps=1)['mission']['status'])

    def test_06_old_exhausted_terminal_never_reopens_after_adoption(self):
        rejected = self.task()
        self.assertEqual(('blocked', 'command_rejected:SOURCE_BUDGET_EXHAUSTED'),
                         (rejected['mission']['status'], rejected['mission']['reason']))
        raw = self.state.read_bytes(); request_id = rejected['steps'][0]['commandId']
        original_receipt = self.b.request('GET', self.b.prefix + '/commands/' + request_id)
        self.adopt(); offline = self.world.client('a2')
        offline.request = lambda *_a, **_k: self.fail('old rejected task restarted')
        self.assertEqual(rejected, self.task(client=offline)); self.assertEqual(raw, self.state.read_bytes())
        self.assertEqual(original_receipt, self.b.request('GET', self.b.prefix + '/commands/' + request_id))

    def test_07_prior_reserve_pending_retains_original_id_across_adoption(self):
        for when in ('before', 'after'):
            world = self.world if when == 'before' else self.fresh('committed-reserve')
            original = self.prior_pending(world, 'reserve_material', when, actor='a2' if when == 'before' else 'a3')
            self.adopt(world)
            client = world.issue('a2' if when == 'before' else 'a3', 600)
            report = self.task(client=client, choose=lambda _: self.fail('old task reselected'), max_steps=1)
            self.assertEqual('paused', report['mission']['status'], report['mission'])
            self.assertEqual(original['commandId'], report['facts']['materialReservation']['requestCommandId'])
            self.assertEqual(original['action'], report['steps'][0]['action'])
            self.assertEqual(1, report['budget']['used']['commands'])

    def test_08_prior_harvest_and_build_receipts_survive_adoption(self):
        for action in ('harvest_material', 'build'):
            world = self.fresh(action)
            original = self.prior_pending(world, action, 'after')
            self.adopt(world)
            report = self.task(client=world.issue('a3', 600), choose=lambda _: self.fail('old task reselected'))
            self.completed(report, 'a3')
            facts = report['facts']['materialHarvests'] if action == 'harvest_material' else [report['facts']['construction']]
            self.assertTrue(any(f['commandId'] == original['commandId'] for f in facts))
            step = next(s for s in report['steps'] if s['commandId'] == original['commandId'])
            self.assertEqual(original['action'], step['action'])
            self.assertEqual(original['expectedStateVersion'], step['expectedStateVersion'])

    def test_09_prior_note_pending_keeps_text_reference_and_three_proofs(self):
        for when in ('before', 'after'):
            world = self.world if when == 'before' else self.copy('note-after')
            observed = world.client('a2').observe(); bridge = observed['entityNotes']['target']
            self.walk(world.client('a2'), bridge['position'])
            job = json.loads((ROOT / 'tests/fixtures/entity-note.json').read_text())
            job['goals'][0]['target'] = bridge['position']; job['goals'][0]['entityNote'] = {
                'entityId': bridge['entityId'], 'text': '保留旧世界原文与引用。', 'replyToNoteId': observed['entityNotes']['notes'][0]['noteId']}
            original = self.prior_pending(world, notes.ACTION, when, actor='a2', job=job)
            self.adopt(world)
            report = self.task(job, world.issue('a2', 600), choose=lambda _: self.fail('old note reselected'))
            self.assertEqual('completed', report['mission']['status'], report['mission'])
            note = report['facts']['entityNote']; self.assertEqual(original['commandId'], note['commandId'])
            for key in ('text', 'entityId', 'replyToNoteId'): self.assertEqual(original['action'][key], note[key])
            self.assertEqual('original_receipt_note_and_event', report['steps'][0]['evidenceSource'])
            self.assertEqual(3, report['world']['entityNotes']['totalCount'])

    def test_10_actual_process_exit_and_session_rotation_keep_reserve(self):
        for index, (fault, code) in enumerate((('before-commit', 81), ('after-commit', 82))):
            world = self.world if index == 0 else self.copy('after'); self.adopt(world)
            self.state = world.data / 'crash-state.json'
            def inject(method, path, payload, headers):
                return {**(headers or {}), 'X-Test-Fault': fault} if method == 'POST' else headers
            report = self.task(client=self.controlled(world, before=inject))
            self.assertEqual('unknown', report['mission']['status'])
            original = self.saved()['_state']['pending']['request']; self.assertEqual(code, world.process.wait(timeout=10))
            world.restart(); report = self.task(client=world.issue('a2', 600), max_steps=1)
            self.assertEqual(original['commandId'], report['facts']['materialReservation']['requestCommandId'])
            self.assertEqual(1, report['budget']['used']['commands'])


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    before = {p: digest(ROOT / p) for p in FILES}
    dll_before = digest(DLL) if DLL.exists() else None
    suite = (unittest.TestSuite(ContinuousMaterialMissionAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:]
             else unittest.defaultTestLoader.loadTestsFromTestCase(ContinuousMaterialMissionAcceptance))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    after = {p: digest(ROOT / p) for p in FILES}
    stopped = all(w.process.poll() is not None for w in ContinuousMaterialMissionAcceptance.all_worlds)
    report = {'suite': 'continuous-material-mission-http', 'validationLevel': 'builder-self-check', 'actualModelCalls': 0,
              'passed': result.wasSuccessful() and before == after and stopped and dll_before is not None and digest(DLL) == dll_before,
              'testsRun': result.testsRun,
              'tests': result.records, 'skipped': [{'test': t.id(), 'reason': reason} for t, reason in result.skipped],
              'sourceHashesBefore': before, 'sourceHashesAfter': after, 'sourceStable': before == after,
              'allStartedServicesStopped': stopped, 'baseline': str(SOURCE),
              'baselineSha256': digest(SOURCE / 'world.db') if SOURCE else None,
              'dll': str(DLL), 'dllSha256': digest(DLL) if DLL.exists() else None,
              'priorPython': str(OLD_PYTHON), 'actualPreviousPython': 'CONTINUOUS_MATERIAL_OLD_PYTHON' in os.environ,
              'priorPythonHashes': {p: digest(OLD_PYTHON / p) for p in ('resident_material_access.py', 'resident_mission.py', 'resident_entity_notes.py')},
              'failureDetails': [(str(t), detail) for t, detail in result.errors + result.failures]}
    report['runtimeMode'] = 'shared-immutable-input'
    report['temporaryRuntimeCreated'] = False
    report['dllStable'] = DLL.exists() and digest(DLL) == dll_before
    report['sourceDll'] = str(SOURCE_DLL)
    (RUN / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json', flush=True)
    raise SystemExit(not report['passed'])
