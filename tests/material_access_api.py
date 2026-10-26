#!/usr/bin/env python3
"""r10 real-clock HTTP/SQLite checks. No material or time is edited in SQL."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import signal
import sqlite3
import subprocess
import sys
import time
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate
from actor_state_api import ActorStateAcceptance, MODE
from foundation_api import DLL, ROOT, EvidenceResult
import continuous_navigation as nav

RUN = ROOT / '.local/iter0022/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN
SOURCE = 'wood-source-east'


def reserve():
    return {'type': 'reserve_material', 'sourceId': SOURCE}


def harvest(rid):
    return {'type': 'harvest_material', 'reservationId': rid}


class MaterialAccessAcceptance(unittest.TestCase):
    intent = ActorStateAcceptance.intent
    post = ActorStateAcceptance.post
    send = ActorStateAcceptance.send
    approach = ActorStateAcceptance.approach
    collect = ActorStateAcceptance.collect
    bridge = ActorStateAcceptance.bridge

    def setUp(self):
        self.worlds, self.trace, self.timings = [], [], []
        self.world = self.create('world')
        self.a, self.b, self.c = [self.world.client(a) for a in ('a1', 'a2', 'a3')]

    def create(self, name, scenario='wilderness-material-access-v1'):
        world = ActivityCandidate(self._testMethodName + '-' + name, scenario=scenario)
        self.worlds.append(world)
        return world

    def tearDown(self):
        for world in self.worlds:
            world.stop()
        (self.world.data / 'trace.json').write_text(json.dumps({'commands': self.trace, 'timings': self.timings}, ensure_ascii=False, indent=2) + '\n')
        for world in self.worlds:
            with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
                self.assertEqual('ok', db.execute('PRAGMA integrity_check').fetchone()[0])
                self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())
                r10 = db.execute('PRAGMA user_version').fetchone()[0] == 10
                generated, stock = db.execute('SELECT generated_wood,stock_wood FROM material_source').fetchone() if r10 else (0, 0)
                total = sum(db.execute(q).fetchone()[0] for q in ('SELECT sum(remaining_wood) FROM resource_nodes', 'SELECT sum(wood) FROM residents', 'SELECT coalesce(sum(embodied_wood),0) FROM entities'))
                self.assertEqual(12 + generated, total + stock)
                self.assertEqual(12 + generated, db.execute('SELECT issued_wood FROM worlds').fetchone()[0])
                version = db.execute('SELECT state_version FROM worlds').fetchone()[0]
                self.assertEqual(version + 1, db.execute('SELECT count(*) FROM events').fetchone()[0])
                balances = {}
                for source, destination, quantity in db.execute('SELECT source_account,destination_account,quantity FROM resource_ledger'):
                    balances[source] = balances.get(source, 0) - quantity
                    balances[destination] = balances.get(destination, 0) + quantity
                self.assertEqual(-12, balances.pop('initial-issuance'))
                self.assertEqual(-generated, balances.pop('ecological-input', 0))
                self.assertEqual(stock, balances.pop('source:' + SOURCE, 0))
                self.assertEqual(db.execute('SELECT sum(remaining_wood) FROM resource_nodes').fetchone()[0], balances.pop('wild-wood', 0))
                for actor, wood in db.execute('SELECT actor_id,wood FROM residents'):
                    self.assertEqual(wood, balances.pop('inventory:' + actor, 0))
                for entity, wood in db.execute('SELECT entity_id,embodied_wood FROM entities'):
                    self.assertEqual(wood, balances.pop('entity:' + entity, 0))
                self.assertEqual({}, balances)
                if r10:
                    self.assertEqual(generated, db.execute('SELECT coalesce(sum(quantity),0) FROM material_production').fetchone()[0])
                    self.assertLessEqual(db.execute("SELECT coalesce(sum(remaining),0) FROM material_reservations WHERE status='active'").fetchone()[0], stock)
                    self.assertEqual([], db.execute("SELECT operator_id FROM material_reservations WHERE status IN('active','queued') GROUP BY operator_id HAVING count(*)>1").fetchall())
                    for event, in db.execute("SELECT event_json FROM events WHERE json_extract(event_json,'$.type') IN('materialProduced','materialReservationGranted','materialReservationExpired','materialSourceEnabled')"):
                        self.assertIsNone(json.loads(event)['actorId'])

    def walk(self, client, target):
        # Tests use public geometry directly; no production client capability is mocked.
        for _ in range(260):
            observed = client.observe(); start = observed['self']['position']
            if math.dist(start, target) <= .06:
                return
            path = nav.navigation(observed).route(start, target)
            self.assertIsNotNone(path)
            point = next((p for p in path if math.dist(start, p) > .06), target)
            time.sleep(.2)
            receipt = self.send(client, {'type': 'walk', 'to': list(point)})
            self.assertFalse(receipt['result']['blocked'], receipt)
        self.fail('bounded real route did not finish')

    def admin(self, world=None, instance=None):
        world = world or self.world
        return subprocess.run(['dotnet', str(DLL), 'enable-material-source', '--instance', instance or self.a.observe()['world']['instanceId']], cwd=ROOT, env=world.env, capture_output=True, text=True, timeout=15)

    def enable(self):
        instance = self.a.observe()['world']['instanceId']
        self.world.stop()
        result = self.admin(instance=instance)
        self.assertEqual(0, result.returncode, result.stderr)
        self.world.start()

    def until(self, client, predicate, timeout=85):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            observed = client.observe()
            if predicate(observed):
                return observed
            time.sleep(.1)
        self.fail('real service clock deadline: ' + json.dumps(observed['materialAccess']))

    def active(self, client, rid):
        return self.until(client, lambda o: any(r['reservationId'] == rid and r['status'] == 'active' for r in o['materialAccess']['recentReservations']))

    def stamp(self, name, observed):
        self.timings.append({'stage': name, 'utc': datetime.now(timezone.utc).isoformat(), 'serviceMs': observed['materialAccess']['serviceMs'], 'stateVersion': observed['stateVersion']})

    def test_01_initial_identity_inactive_protocol_and_offline_activation_lock(self):
        observed = self.a.observe(); source = observed['materialAccess']
        self.assertFalse(source['active']); self.assertEqual((0, 0, 12, 6), tuple(source[k] for k in ('stockWood', 'generatedWood', 'inputBudget', 'capacity')))
        self.assertEqual({'a1': 'local-operator', 'a1_alias': 'local-operator', 'a2': 'declared-late', 'a3': 'declared-third'}, {r['actorId']: r['operatorId'] for r in source['controlRoster']})
        self.post(self.a, self.intent(self.a, reserve()), 422, 'MATERIAL_SOURCE_INACTIVE')
        self.post(self.a, self.intent(self.a, {**reserve(), 'sourceId': 'missing'}), 404, 'MATERIAL_SOURCE_NOT_FOUND')
        self.post(self.a, self.intent(self.a, {**reserve(), 'operatorId': 'fake'}), 403, 'IDENTITY_OVERRIDE')
        self.assertNotEqual(0, self.admin(instance=observed['world']['instanceId']).returncode)
        with (self.world.data / 'duplicate.log').open('w') as log:
            duplicate = subprocess.Popen(['dotnet', str(DLL)], cwd=ROOT, env=self.world.env, stdout=log, stderr=log)
            self.assertNotEqual(0, duplicate.wait(timeout=15))
        self.world.stop()
        self.assertNotEqual(0, self.admin(instance='w_' + '0' * 32).returncode)
        self.assertEqual(0, self.admin(instance=observed['world']['instanceId']).returncode)
        before = self.world.dump()
        self.assertEqual(0, self.admin(instance=observed['world']['instanceId']).returncode)
        self.assertEqual(before, self.world.dump())
        missing = self.world.data / 'missing'; missing.mkdir()
        command = subprocess.run(['dotnet', str(DLL), 'enable-material-source', '--instance', observed['world']['instanceId']], env={**self.world.env, 'WORLD_DATA_DIR': str(missing)}, capture_output=True, timeout=10)
        self.assertNotEqual(0, command.returncode); self.assertFalse((missing / 'world.db').exists())
        old = self.create('old', 'wilderness-cooperation-v1'); client = old.client()
        self.assertNotIn('materialAccess', client.observe())
        self.post(client, self.intent(client, reserve(), None), 422, 'ACTION_UNAVAILABLE')
        self.post(client, self.intent(client, reserve()), 422, 'PRECONDITION_MODE_UNAVAILABLE')

    def test_02_same_instance_refusal_then_real_reservation_harvest_and_platform(self):
        self.bridge(); self.collect(self.a, 'tree-east-north'); self.collect(self.a, 'tree-east-south')
        before = self.a.observe(); self.assertEqual((0, 6, 6), tuple(before['resourceAudit'][k] for k in ('wildWood', 'inventoryWood', 'embodiedWood')))
        original = deepcopy(self.trace[0]); original_identity = before['world']['instanceId']
        self.post(self.b, self.intent(self.b, {'type': 'build', 'recipeId': 'platform.v1', 'at': [28, 16]}), 422, 'INSUFFICIENT_RESOURCE')
        self.enable(); self.stamp('firstRequest', self.b.observe())
        request = self.intent(self.b, reserve()); receipt = self.post(self.b, request); rid = receipt['result']['reservationId']
        self.stamp('queued', self.b.observe()); granted = self.active(self.b, rid); self.stamp('granted', granted)
        self.walk(self.b, [28, 10]); self.stamp('arrived', self.b.observe())
        for _ in range(3):
            got = self.send(self.b, harvest(rid)); self.assertEqual(1, got['result']['remainingBefore'] - got['result']['remaining'])
        self.stamp('thirdHarvest', self.b.observe()); self.walk(self.b, [28, 14.3])
        built = self.send(self.b, {'type': 'build', 'recipeId': 'platform.v1', 'at': [28, 16]}); self.stamp('platformCommitted', self.b.observe())
        after = self.a.observe()
        self.assertEqual(original_identity, after['world']['instanceId']); self.assertEqual(6, after['self']['inventory']['wood'])
        self.assertTrue(all(e in after['entities'] for e in before['entities']))
        self.assertEqual('a2', next(e['ownerActorId'] for e in after['entities'] if e['entityId'] == built['result']['entityId']))
        self.assertEqual(original['receipt'], self.post(self.a, original['request']))
        self.assertEqual(receipt, self.post(self.b, request))
        self.assertEqual([], self.b.observe()['recentTransfers']['items'])
        self.world.restart(); self.assertEqual(receipt, self.post(self.b, request))
        self.assertEqual(original['receipt'], self.post(self.a, original['request']))

    def test_03_alias_one_slot_fifo_rejoin_and_original_receipt(self):
        self.enable(); alias = self.world.client('a1_alias')
        early_request = self.intent(self.a, reserve()); early = self.post(self.a, early_request)
        with ThreadPoolExecutor(max_workers=6) as pool:
            replies = list(pool.map(lambda _: self.a.command(early_request), range(6)))
        self.assertTrue(all(r == (200, early) for r in replies))
        self.post(alias, self.intent(alias, reserve()), 409, 'RESERVATION_ALREADY_ACTIVE')
        early_id = early['result']['reservationId']
        self.post(alias, self.intent(alias, harvest(early_id)), 404, 'RESERVATION_NOT_FOUND')
        self.send(self.a, {'type': 'cancel_reservation', 'reservationId': early_id})
        first = self.send(self.c, reserve())['result']['reservationId']; late = self.send(self.b, reserve())['result']['reservationId']
        self.active(self.c, first)
        for _ in range(3): self.send(self.c, harvest(first))
        self.walk(self.c, [28.5, 12]); self.send(self.c, {'type': 'build', 'recipeId': 'platform.v1', 'at': [30, 13]})
        again = self.send(self.c, reserve())['result']['reservationId']
        late_observation = self.active(self.b, late)
        late_lease = late_observation['materialAccess']['currentReservation']
        self.assertEqual('queued', self.c.observe()['materialAccess']['currentReservation']['status'])
        self.active(self.c, again)
        early_lease = self.c.observe()['materialAccess']['currentReservation']
        self.assertLess(late_lease['grantedAtMs'], early_lease['grantedAtMs'])
        self.assertEqual(early, self.post(self.a, early_request))

    def test_04_partial_harvest_restart_expiry_preserves_inventory_and_releases_only_remaining(self):
        self.enable(); rid = self.send(self.c, reserve())['result']['reservationId']
        later = self.send(self.b, reserve())['result']['reservationId']; waiting = self.send(self.a, reserve())['result']['reservationId']
        self.active(self.c, rid)
        request = self.intent(self.c, harvest(rid)); receipt = self.post(self.c, request)
        lease = self.c.observe()['materialAccess']['currentReservation']; self.assertEqual(2, lease['remaining'])
        checkpoint = self.c.observe()['materialAccess']['serviceMs']; self.world.stop(); time.sleep(1.2); self.world.start()
        resumed = self.c.observe()['materialAccess']['serviceMs']; self.assertLess(resumed - checkpoint, 700)
        self.assertEqual(receipt, self.post(self.c, request))
        self.active(self.b, later)
        self.until(self.c, lambda o: any(r['reservationId'] == rid and r['status'] == 'expired' for r in o['materialAccess']['recentReservations']))
        self.assertEqual(1, self.c.observe()['self']['inventory']['wood']); self.assertEqual(receipt, self.post(self.c, request))
        self.post(self.c, self.intent(self.c, harvest(rid)), 422, 'RESERVATION_NOT_ACTIVE')
        granted = self.active(self.a, waiting)['materialAccess']['currentReservation']
        self.assertGreaterEqual(granted['grantedAtMs'], lease['expiresAtMs'])
        self.assertEqual(60000, granted['expiresAtMs'] - granted['grantedAtMs'])
        self.assertEqual(6, self.a.observe()['materialAccess']['stockWood'])

    def test_05_budget_capacity_and_exhausted_budget_does_not_reset(self):
        self.enable()
        for index in range(4):
            rid = self.send(self.c, reserve())['result']['reservationId']; self.active(self.c, rid)
            for _ in range(3): self.send(self.c, harvest(rid))
        observed = self.c.observe(); self.assertEqual((12, 0, 12), (observed['materialAccess']['generatedWood'], observed['materialAccess']['stockWood'], observed['self']['inventory']['wood']))
        self.post(self.c, self.intent(self.c, reserve()), 422, 'SOURCE_BUDGET_EXHAUSTED')
        self.assertEqual([], self.c.observe()['materialAccess']['queue'])
        self.world.restart()
        for _ in range(50): self.assertEqual(12, self.c.observe()['materialAccess']['generatedWood'])

    def test_06_empty_and_full_plot_walkable_but_reserved_for_building(self):
        self.walk(self.c, [28, 10]); self.assertEqual([28, 10], self.c.observe()['self']['position'])
        self.post(self.c, self.intent(self.c, {'type': 'build', 'recipeId': 'platform.v1', 'at': [28, 10]}), 409, 'AREA_OCCUPIED')
        self.enable(); self.until(self.c, lambda o: o['materialAccess']['stockWood'] == 6, timeout=25)
        self.walk(self.c, [29.5, 10]); self.walk(self.c, [28, 10])
        self.post(self.c, self.intent(self.c, {'type': 'build', 'recipeId': 'platform.v1', 'at': [29.5, 10]}), 409, 'AREA_OCCUPIED')
        time.sleep(10.5); self.assertEqual(6, self.c.observe()['materialAccess']['generatedWood'])

    def test_07_harvest_transaction_faults_keep_original_id(self):
        self.enable(); rid = self.send(self.c, reserve())['result']['reservationId']; self.active(self.c, rid)
        request = self.intent(self.c, harvest(rid))
        self.post(self.c, request, 503, 'SERVICE_UNAVAILABLE', {'X-Test-Fault': 'throw-after-debit'})
        self.assertEqual(0, self.c.observe()['self']['inventory']['wood'])
        self.assertEqual(404, self.c.request('GET', self.c.prefix + '/commands/' + request['commandId'])[0])
        for fault, exit_code in [('before-commit', 81), ('after-commit', 82)]:
            request = self.intent(self.c, harvest(rid))
            with self.assertRaises((OSError, ValueError)):
                self.c.request('POST', self.c.prefix + '/commands', request, {'X-Test-Fault': fault})
            self.assertEqual(exit_code, self.world.process.wait(timeout=10)); self.world.stop(); self.world.start()
            status, old = self.c.request('GET', self.c.prefix + '/commands/' + request['commandId'])
            self.assertEqual(404 if fault == 'before-commit' else 200, status)
            committed = self.post(self.c, request)
            if fault == 'after-commit': self.assertEqual(old, committed)
        self.assertEqual(2, self.c.observe()['self']['inventory']['wood'])

    def test_08_production_crash_boundaries_and_restart(self):
        self.enable(); self.world.stop(); self.world.env['WORLD_MATERIAL_TEST_FAULT'] = 'before-commit'; self.world.start()
        self.assertEqual(83, self.world.process.wait(timeout=15)); self.world.stop()
        with sqlite3.connect(self.world.data / 'world.db') as db: self.assertEqual(0, db.execute('SELECT generated_wood FROM material_source').fetchone()[0])
        self.world.env['WORLD_MATERIAL_TEST_FAULT'] = 'after-commit'; self.world.start()
        self.assertEqual(84, self.world.process.wait(timeout=15)); self.world.stop()
        with sqlite3.connect(self.world.data / 'world.db') as db: self.assertEqual(3, db.execute('SELECT generated_wood FROM material_source').fetchone()[0])
        self.world.env.pop('WORLD_MATERIAL_TEST_FAULT'); self.world.start()
        rid = self.send(self.c, reserve())['result']['reservationId']; self.active(self.c, rid)
        self.assertEqual(3, self.c.observe()['materialAccess']['generatedWood'])
        self.send(self.c, {'type': 'cancel_reservation', 'reservationId': rid})
        # Hold only this disposable process to delay the background callback. The
        # monotonic service clock keeps elapsed process time, without a fake clock.
        os.kill(self.world.process.pid, signal.SIGSTOP)
        try: time.sleep(1.1)
        finally: os.kill(self.world.process.pid, signal.SIGCONT)
        self.assertEqual(3, self.c.observe()['materialAccess']['generatedWood'])
        fresh = self.send(self.c, reserve())['result']['reservationId']; o = self.active(self.c, fresh)
        lease = o['materialAccess']['currentReservation']
        self.assertEqual(60000, lease['expiresAtMs'] - lease['grantedAtMs'])
        self.assertLess(o['materialAccess']['serviceMs'] - lease['grantedAtMs'], 1000)


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    suite = unittest.TestSuite(MaterialAccessAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:] else unittest.defaultTestLoader.loadTestsFromTestCase(MaterialAccessAcceptance)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    evidence = {'suite': 'material-access-http-v1', 'recordedAtUtc': datetime.now(timezone.utc).isoformat(),
                'passed': result.wasSuccessful(), 'testsRun': result.testsRun, 'tests': result.records,
                'actualModelCalls': 0, 'clock': 'real monotonic service clock; no SQL time or material edits',
                'dllSha256': hashlib.sha256(DLL.read_bytes()).hexdigest(),
                'sourceSha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT / 'src/World.Server').glob('*.cs')), ROOT / 'tests/material_access_api.py']},
                'failureDetails': [(str(t), detail) for t, detail in result.failures + result.errors]}
    (RUN / 'results.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json')
    raise SystemExit(not result.wasSuccessful())
