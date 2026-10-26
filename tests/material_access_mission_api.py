#!/usr/bin/env python3
"""Builder self-check: r10 material missions through HTTP, real time and SQLite.

WORLD_TEST_DLL selects an immutable candidate; no build or SQL world edits.
Faulted transport responses below are isolated client probes, not live failures.
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
import uuid

import foundation_api
from foundation_api import ROOT, EvidenceResult
DLL = Path(os.environ.get('WORLD_TEST_DLL', foundation_api.DLL)).resolve()
foundation_api.DLL = DLL
import activities_api
from material_access_api import MaterialAccessAcceptance, reserve, harvest
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice
from activity_choice import choose_lowest_cost
import resident_material_access as material

RUN = ROOT / '.local/iter0022/python' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN


def mission():
    return json.loads((ROOT / 'tests/fixtures/material-access-platform.json').read_text())


class MaterialMissionAcceptance(unittest.TestCase):
    create = MaterialAccessAcceptance.create
    intent = MaterialAccessAcceptance.intent
    post = MaterialAccessAcceptance.post
    send = MaterialAccessAcceptance.send
    walk = MaterialAccessAcceptance.walk
    approach = MaterialAccessAcceptance.approach
    collect = MaterialAccessAcceptance.collect
    bridge = MaterialAccessAcceptance.bridge
    enable = MaterialAccessAcceptance.enable
    admin = MaterialAccessAcceptance.admin
    until = MaterialAccessAcceptance.until
    active = MaterialAccessAcceptance.active

    def setUp(self):
        MaterialAccessAcceptance.setUp(self)
        self.state = self.world.data / 'mission.json'
        self.reports, self.traffic = [], []

    def tearDown(self):
        (self.world.data / 'reports.json').write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + '\n')
        (self.world.data / 'traffic.json').write_text(json.dumps(self.traffic, ensure_ascii=False, indent=2) + '\n')
        MaterialAccessAcceptance.tearDown(self)

    def task(self, job=None, client=None, choose=choose_lowest_cost, **kwargs):
        report = run_mission(client or self.c, job or mission(), self.state, choose, **kwargs)
        self.reports.append(report)
        return report

    def controlled(self, *, before=None, after=None, actor='a3'):
        owner = self
        class Controlled(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                if before:
                    headers = before(method, path, payload, headers)
                status, body = super().request(method, path, payload, headers)
                owner.traffic.append({'method': method, 'path': path, 'payload': deepcopy(payload),
                                      'status': status, 'body': deepcopy(body)})
                return after(method, path, payload, (status, body)) if after else (status, body)
        return Controlled(self.world.url, self.world.access['sessions'][actor]['token'])

    def saved(self):
        return json.loads(self.state.read_text())

    def completed(self, report, actor='a3'):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['returned'] and report['facts']['goalReached'] and report['facts']['constructionBuilt'])
        self.assertEqual((3, 3, 0, 0), (report['facts']['materialWoodHarvested'], report['budget']['used']['wood'],
                                     report['facts']['woodGathered'], report['facts']['woodTransferred']))
        self.assertEqual(actor, report['facts']['construction']['ownerActorId'])
        reservation = report['facts']['materialReservation']
        self.assertEqual((actor, material.ROSTER[actor], report['mission']['worldInstanceId']),
                         (reservation['actorId'], reservation['operatorId'], reservation['worldInstanceId']))
        self.assertEqual(1, sum(s['action']['type'] == 'reserve_material' for s in report['steps']))
        self.assertEqual(3, sum(s['action']['type'] == 'harvest_material' for s in report['steps']))
        self.assertEqual([3, 2, 1], [r['remainingBefore'] for r in report['facts']['materialHarvests']])
        self.assertTrue(all(r['reservationId'] == reservation['reservationId'] for r in report['facts']['materialHarvests']))
        self.assertLessEqual(report['budget']['used']['queries'], report['budget']['limits']['queries'])

    def test_01_same_instance_refusal_cli_platform_and_restart(self):
        self.bridge(); self.collect(self.a, 'tree-east-north'); self.collect(self.a, 'tree-east-south')
        original = self.a.observe(); first = deepcopy(self.trace[0])
        self.assertEqual((0, 6, 6), tuple(original['resourceAudit'][k] for k in ('wildWood', 'inventoryWood', 'embodiedWood')))
        self.enable()
        output = self.world.data / 'cli-report.json'
        command = [sys.executable, str(ROOT / 'scripts/run_resident.py'), '--url', self.world.url,
                   '--access-file', str(self.world.data / 'access.json'), '--actor', 'a2', '--fixed-reference',
                   '--spec', str(ROOT / 'tests/fixtures/material-access-platform.json'), '--state', str(self.state), '--output', str(output)]
        first_run = subprocess.run([*command, '--max-steps', '1'], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, first_run.returncode, first_run.stderr)
        paused = json.loads(output.read_text()); self.reports.append(paused)
        self.assertEqual('paused', paused['mission']['status'])
        original_reservation = deepcopy(paused['facts']['materialReservation'])
        started = self.saved()['_state']['startedEpoch']
        self.world.restart()
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, done.returncode, done.stderr)
        report = json.loads(output.read_text()); self.reports.append(report); self.completed(report, 'a2')
        self.assertEqual(original_reservation, report['facts']['materialReservation'])
        self.assertEqual(started, self.saved()['_state']['startedEpoch'])
        self.assertGreater(report['budget']['used']['queries'], paused['budget']['used']['queries'])
        self.assertEqual('fixed-reference', report['decision']['provider']['kind'])
        after = self.a.observe()
        self.assertEqual(original['world']['instanceId'], after['world']['instanceId'])
        self.assertEqual(6, after['self']['inventory']['wood'])
        self.assertTrue(all(e in after['entities'] for e in original['entities']))
        self.assertEqual(first['receipt'], self.post(self.a, first['request']))
        self.assertEqual([], after['recentTransfers']['items'])
        snapshot = self.state.read_bytes()
        offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('completed task requested network')
        self.assertEqual(report, run_mission(offline, mission(), self.state, choose_lowest_cost))
        self.assertEqual(snapshot, self.state.read_bytes())

    def test_02_permission_query_wood_budgets_and_reserved_plot(self):
        for mutate in (lambda j: j.pop('allowMaterialAccess'), lambda j: j.update(allowMaterialAccess=False),
                       lambda j: j['budgets'].pop('queries'), lambda j: j['goals'][0]['materialAccess'].update(quantity=True),
                       lambda j: j['goals'][0]['materialAccess'].update(sourceId='other'), lambda j: j.update(allowBuild=False)):
            job = mission(); mutate(job)
            with self.assertRaises(ValueError): self.task(job, self.controlled())
        self.assertEqual([], self.traffic); self.assertFalse(self.state.exists())
        self.enable()
        for index, (change, reason) in enumerate(((lambda j: j['budgets'].update(queries=1), 'queries'),
                                                (lambda j: j['budgets'].update(wood=2), 'wood'))):
            self.state = self.world.data / f'budget-{index}.json'
            job = mission(); change(job)
            report = self.task(job, self.controlled(), choose=Choice('platform'))
            self.assertEqual(('budget_exhausted', reason, 0), (report['mission']['status'], report['mission']['reason'], report['budget']['used']['commands']))
        self.state = self.world.data / 'exclusion.json'
        job = mission(); job['goals'][0]['target'] = [28, 10]
        report = self.task(job, choose=Choice('platform'))
        self.assertEqual('construction_material_source_reserved', report['mission']['reason'])
        self.assertEqual(0, report['budget']['used']['commands'])

    def test_03_reserve_event_binding_corruption_unknown_query_and_new_session(self):
        self.enable()
        def corrupt(method, path, payload, response):
            status, body = response
            if isinstance(body, dict) and body.get('result', {}).get('action') == 'reserve_material':
                body['result']['reservationId'] = 'm' + '0' * 32
            return status, body
        first = self.task(client=self.controlled(after=corrupt))
        self.assertEqual('unknown', first['mission']['status']); self.assertIsNone(first['facts']['materialReservation'])
        original = self.saved()['_state']['pending']['request']; used = first['budget']['used']['queries']
        def unavailable(method, path, payload, response):
            if '/commands/' in path: return 503, {'error': {'code': 'SERVICE_UNAVAILABLE'}}
            return response
        second = self.task(client=self.controlled(after=unavailable))
        self.assertEqual('unknown', second['mission']['status'])
        self.assertEqual(original, self.saved()['_state']['pending']['request'])
        self.assertEqual(1, second['budget']['used']['commands']); self.assertGreater(second['budget']['used']['queries'], used)
        fresh = self.world.issue('a3', 600)
        final = self.task(client=fresh); self.completed(final)
        self.assertEqual(original['commandId'], final['facts']['materialReservation']['requestCommandId'])

    def test_04_lost_harvest_recovery_checks_original_remaining_not_source_stock(self):
        self.enable()
        def lost(method, path, payload, response):
            if method == 'POST' and payload['action']['type'] == 'harvest_material': raise OSError('isolated lost response')
            return response
        first = self.task(client=self.controlled(after=lost))
        self.assertEqual('unknown', first['mission']['status']); self.assertEqual(0, first['facts']['materialWoodHarvested'])
        original = self.saved()['_state']['pending']['request']
        self.until(self.c, lambda o: o['materialAccess']['generatedWood'] >= 6, timeout=25)
        self.world.restart()
        final = self.task(); self.completed(final)
        self.assertEqual(original['commandId'], final['facts']['materialHarvests'][0]['commandId'])

    def test_05_cancelled_original_stops_without_new_reservation(self):
        self.enable(); paused = self.task(max_steps=1)
        rid = paused['facts']['materialReservation']['reservationId']
        self.send(self.c, {'type': 'cancel_reservation', 'reservationId': rid})
        stopped = self.task()
        self.assertEqual(('blocked', 'material_reservation_cancelled'), (stopped['mission']['status'], stopped['mission']['reason']))
        saved = self.state.read_bytes(); offline = self.world.client('a3')
        offline.request = lambda *_a, **_k: self.fail('cancelled task requested network')
        self.assertEqual(stopped, self.task(client=offline)); self.assertEqual(saved, self.state.read_bytes())

    def test_06_unsent_harvest_expiry_keeps_original_id_and_never_requeues(self):
        self.enable()
        def unsent(method, path, payload, headers):
            if method == 'POST' and payload['action']['type'] == 'harvest_material': raise OSError('isolated pre-submit failure')
            return headers
        first = self.task(client=self.controlled(before=unsent))
        self.assertEqual('unknown', first['mission']['status'])
        original = self.saved()['_state']['pending']['request']
        rid = first['facts']['materialReservation']['reservationId']
        self.until(self.c, lambda o: any(r['reservationId'] == rid and r['status'] == 'expired'
                                       for r in o['materialAccess']['recentReservations']), timeout=70)
        final = self.task()
        self.assertEqual(('blocked', 'command_rejected:RESERVATION_NOT_ACTIVE'), (final['mission']['status'], final['mission']['reason']))
        self.assertEqual(original['commandId'], final['steps'][-1]['commandId'])
        self.assertEqual(2, final['budget']['used']['commands']); self.assertEqual(0, final['facts']['materialWoodHarvested'])
        self.assertEqual(1, len(self.c.observe()['materialAccess']['recentReservations']))

    def test_07_damaged_saved_authority_and_query_budget_make_no_requests(self):
        self.enable()
        def offline(method, path, payload, headers):
            if method == 'POST': raise OSError('isolated pre-submit failure')
            return headers
        self.task(client=self.controlled(before=offline)); baseline = self.saved()
        variants = (lambda s: s['mission'].update(allowMaterialAccess=False),
                    lambda s: s['mission'].update(allowBuild=False),
                    lambda s: s['mission'].update(allowGather=True),
                    lambda s: s['budget']['limits'].update(queries=5000),
                    lambda s: s['budget']['used'].update(queries=True),
                    lambda s: s['_state']['pending'].pop('materialBefore'),
                    lambda s: s['_state']['pending']['materialBefore'].update(actorId='a1'),
                    lambda s: s['_state']['pending']['request']['action'].update(sourceId='other'),
                    lambda s: s['_state']['pending']['materialBefore'].update(inventoryWood=1))
        for mutate in variants:
            damaged = deepcopy(baseline); mutate(damaged); self.state.write_text(json.dumps(damaged))
            client = self.world.client('a3'); client.request = lambda *_a, **_k: self.fail('damaged task requested network')
            with self.assertRaises(ValueError): self.task(client=client)
        self.state.write_text(json.dumps(baseline))
        self.assertEqual('paused', self.task(max_steps=1)['mission']['status'])

    def test_08_alias_cannot_adopt_group_reservation_or_unknown_actor_session(self):
        self.enable(); rid = self.send(self.a, reserve())['result']['reservationId']
        alias = self.world.client('a1_alias')
        report = self.task(client=alias, choose=Choice('platform'))
        self.assertEqual(('blocked', 'material_reservation_already_exists'), (report['mission']['status'], report['mission']['reason']))
        self.assertEqual(0, report['budget']['used']['commands'])
        self.assertEqual(rid, alias.observe()['materialAccess']['currentReservation']['reservationId'])
        missing = self.world.data / 'missing-access.json'; missing.write_text('{"sessions": {}}')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_resident.py'), '--url', self.world.url,
                                 '--access-file', str(missing), '--actor', 'a3', '--fixed-reference',
                                 '--spec', str(ROOT / 'tests/fixtures/material-access-platform.json'),
                                 '--state', str(self.world.data / 'never.json'), '--output', str(self.world.data / 'never-report.json')],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(2, result.returncode); self.assertFalse((self.world.data / 'never.json').exists())

    def test_09_reserve_recovers_original_event_beyond_recent_twenty(self):
        self.enable()
        def lost(method, path, payload, response):
            if method == 'POST': raise OSError('isolated lost reserve response')
            return response
        first = self.task(client=self.controlled(after=lost))
        original = self.saved()['_state']['pending']['request']
        rid = self.c.observe()['materialAccess']['currentReservation']['reservationId']
        self.send(self.c, {'type': 'cancel_reservation', 'reservationId': rid})
        for _ in range(21):
            other = self.send(self.c, reserve())['result']['reservationId']
            self.send(self.c, {'type': 'cancel_reservation', 'reservationId': other})
        self.assertNotIn(rid, [r['reservationId'] for r in self.c.observe()['materialAccess']['recentReservations']])
        restored = self.task(client=self.controlled())
        self.assertEqual(('blocked', 'material_reservation_unavailable'), (restored['mission']['status'], restored['mission']['reason']))
        self.assertEqual(rid, restored['facts']['materialReservation']['reservationId'])
        self.assertEqual(original['commandId'], restored['facts']['materialReservation']['requestCommandId'])
        self.assertEqual(1, restored['budget']['used']['commands'])
        self.assertTrue(any('/events?after=' in t['path'] for t in self.traffic))

    def test_10_query_exhaustion_after_commit_retains_pending_without_budget_refill(self):
        self.enable(); job = mission(); job['budgets']['queries'] = 2
        first = self.task(job, self.controlled())
        self.assertEqual(('budget_exhausted', 'queries_pending_retained'), (first['mission']['status'], first['mission']['reason']))
        original = self.saved()['_state']['pending']['request']
        self.assertEqual((1, 2), (first['budget']['used']['commands'], first['budget']['used']['queries']))
        self.assertEqual(2, sum(t['method'] == 'GET' for t in self.traffic))
        self.assertIsNone(first['facts']['materialReservation'])
        offline = self.world.client('a3'); offline.request = lambda *_a, **_k: self.fail('exhausted query budget requested network')
        second = self.task(job, offline)
        self.assertEqual(('budget_exhausted', 'queries'), (second['mission']['status'], second['mission']['reason']))
        self.assertEqual(original, self.saved()['_state']['pending']['request'])
        self.assertEqual((1, 2), (second['budget']['used']['commands'], second['budget']['used']['queries']))
        expanded = deepcopy(job); expanded['budgets']['queries'] = 300
        with self.assertRaises(ValueError): self.task(expanded, offline)
        self.assertEqual(1, len(self.c.observe()['materialAccess']['recentReservations']))

    def test_11_corrupt_harvest_receipts_and_pending_reservation_are_not_facts(self):
        self.enable()
        def unsent(method, path, payload, headers):
            if method == 'POST' and payload['action']['type'] == 'harvest_material': raise OSError('isolated pre-submit failure')
            return headers
        first = self.task(client=self.controlled(before=unsent)); baseline = self.saved()
        original = deepcopy(baseline['_state']['pending']['request'])
        for mutate in (lambda s: s['_state']['pending']['request']['action'].update(reservationId='m' + '0' * 32),
                       lambda s: s['_state']['pending']['materialBefore']['reservation'].update(remaining=2),
                       lambda s: s['facts']['materialReservation'].update(actorId='a1')):
            damaged = deepcopy(baseline); mutate(damaged); self.state.write_text(json.dumps(damaged))
            offline = self.world.client('a3'); offline.request = lambda *_a, **_k: self.fail('damaged harvest requested network')
            with self.assertRaises(ValueError): self.task(client=offline)
        self.state.write_text(json.dumps(baseline))
        mutations = (lambda r: r['result'].update(remainingBefore=2), lambda r: r['result'].update(remaining=True),
                     lambda r: r['result'].update(inventoryWoodBefore=1), lambda r: r['result'].update(quantity=True),
                     lambda r: r['result'].update(sourceId='other'), lambda r: r.update(eventCursor=True),
                     lambda r: r['identity'].update(operatorId='local-operator'),
                     lambda r: r['result'].update(reservationId='m' + '0' * 32))
        for mutate in mutations:
            def corrupt(method, path, payload, response):
                status, body = response
                if isinstance(body, dict) and body.get('result', {}).get('action') == 'harvest_material': mutate(body)
                return status, body
            report = self.task(client=self.controlled(after=corrupt))
            self.assertEqual('unknown', report['mission']['status'])
            self.assertEqual(original, self.saved()['_state']['pending']['request'])
            self.assertEqual(0, report['facts']['materialWoodHarvested'])
        completed = self.task(); self.completed(completed)
        self.assertEqual(original['commandId'], completed['facts']['materialHarvests'][0]['commandId'])


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    files = [*ROOT.glob('scripts/*.py'), Path(__file__), ROOT / 'tests/fixtures/material-access-platform.json']
    before_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    selected = sys.argv[1:]
    suite = (unittest.defaultTestLoader.loadTestsFromNames(selected, sys.modules[__name__]) if selected
             else unittest.defaultTestLoader.loadTestsFromTestCase(MaterialMissionAcceptance))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    after_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    report = {'suite': 'material-access-mission-http', 'validationLevel': 'builder-self-check',
              'actualModelCalls': 0, 'clock': 'real service monotonic time; no time injection',
              'dll': str(DLL), 'dllSha256': hashlib.sha256(DLL.read_bytes()).hexdigest(),
              'sourceSha256': after_hashes, 'sourceSha256Before': before_hashes,
              'sourceStable': before_hashes == after_hashes,
              'tests': result.testsRun, 'testResults': result.records,
              'successful': result.wasSuccessful() and before_hashes == after_hashes,
              'failures': [str(t) + '\n' + e for t, e in result.failures],
              'errors': [str(t) + '\n' + e for t, e in result.errors]}
    (RUN / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json', flush=True)
    raise SystemExit(not report['successful'])
