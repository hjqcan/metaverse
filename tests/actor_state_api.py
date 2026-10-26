#!/usr/bin/env python3
"""Explicit actor-state preconditions through actual HTTP, SQLite and process failures."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import sqlite3
import time
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import EvidenceResult, ROOT
import continuous_navigation as nav

MODE = 'actor-state-v1'
RUN = ROOT / '.local/iter0019/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN


class ActorStateAcceptance(unittest.TestCase):
    def setUp(self):
        self.worlds, self.trace = [], []
        self.world = self.create('world')
        self.a, self.b = self.world.client(), self.world.client('a2')

    def create(self, name, scenario='wilderness-continuous-v1', fixture=None):
        world = ActivityCandidate(self._testMethodName + '-' + name, scenario=scenario, fixture=fixture)
        self.worlds.append(world)
        return world

    def tearDown(self):
        for world in self.worlds:
            world.stop()
        (self.world.data / 'trace.json').write_text(json.dumps(self.trace, ensure_ascii=False, indent=2) + '\n')
        for world in self.worlds:
            with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
                self.assertEqual('ok', db.execute('PRAGMA integrity_check').fetchone()[0])
                self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())
                total = sum(db.execute(q).fetchone()[0] for q in (
                    'SELECT coalesce(sum(remaining_wood),0) FROM resource_nodes',
                    'SELECT sum(wood) FROM residents', 'SELECT coalesce(sum(embodied_wood),0) FROM entities'))
                self.assertEqual(12, total)
                version = db.execute('SELECT state_version FROM worlds').fetchone()[0]
                self.assertEqual(version + 1, db.execute('SELECT count(*) FROM events').fetchone()[0])
                self.assertEqual(version, db.execute("SELECT count(*) FROM receipts WHERE json_extract(result_json,'$.status')='committed'").fetchone()[0])
                balances = {}
                for source, target, quantity in db.execute('SELECT source_account,destination_account,quantity FROM resource_ledger'):
                    balances[source] = balances.get(source, 0) - quantity
                    balances[target] = balances.get(target, 0) + quantity
                self.assertEqual(-12, balances.pop('initial-issuance'))
                self.assertEqual(db.execute('SELECT sum(remaining_wood) FROM resource_nodes').fetchone()[0], balances.pop('wild-wood', 0))
                for actor, wood in db.execute('SELECT actor_id,wood FROM residents'):
                    self.assertEqual(wood, balances.pop('inventory:' + actor, 0))
                for entity, wood in db.execute('SELECT entity_id,embodied_wood FROM entities'):
                    self.assertEqual(wood, balances.pop('entity:' + entity, 0))
                self.assertEqual({}, balances)

    def intent(self, client, action, mode=MODE):
        observed = client.observe()
        request = {'schemaVersion': 1, 'rulesVersion': observed['rulesVersion'], 'commandId': uuid.uuid4().hex,
                   'expectedStateVersion': observed['stateVersion'], 'action': action}
        if mode is not None:
            request['preconditionMode'] = mode
        return request

    def post(self, client, request, status=200, code=None, headers=None):
        actual, receipt = client.request('POST', client.prefix + '/commands', request, headers)
        self.trace.append({'request': deepcopy(request), 'status': actual, 'receipt': receipt})
        self.assertEqual(status, actual, receipt)
        if code is not None:
            self.assertEqual(code, receipt['error']['code'])
        if receipt.get('status') in ('committed', 'rejected'):
            if request.get('preconditionMode') == MODE:
                evidence = receipt['execution']
                self.assertEqual(MODE, evidence['preconditionMode'])
                self.assertEqual(request['expectedStateVersion'], evidence['observedStateVersion'])
                self.assertEqual(receipt['stateVersion'], evidence['appliedOnStateVersion'] + int(receipt['status'] == 'committed'))
                if receipt['status'] == 'committed':
                    self.assertGreaterEqual(evidence['appliedOnStateVersion'], request['expectedStateVersion'])
            else:
                self.assertNotIn('execution', receipt)
        return receipt

    def send(self, client, action, mode=MODE):
        return self.post(client, self.intent(client, action, mode))

    def walk(self, client, target):
        for _ in range(250):
            observed = client.observe()
            if math.dist(observed['self']['position'], target) <= .06:
                return
            route = nav.route_info(observed, target, False, False)
            self.assertIsNone(route['reason'], route)
            time.sleep(observed['movement']['maxStepDistance'] / observed['movement']['speed'])
            receipt = self.send(client, route['nextAction'])
            self.assertFalse(receipt['result']['blocked'], receipt)
        self.fail('bounded route did not finish')

    def approach(self, client, node_id):
        observed = client.observe()
        target = next(n['position'] for n in observed['resourceNodes'] if n['nodeId'] == node_id)
        start = observed['self']['position']
        if math.dist(start, target) <= 1.5:
            return
        geometry = nav.navigation(observed)
        points = []
        for index in range(24):
            angle = index * math.tau / 24
            point = [target[0] + 1.2 * math.cos(angle), target[1] + 1.2 * math.sin(angle)]
            route = geometry.route(start, point)
            if route is not None:
                points.append((nav.path_length(start, route), point))
        self.assertTrue(points)
        self.walk(client, min(points)[1])

    def collect(self, client, node_id, count=3):
        self.approach(client, node_id)
        for _ in range(count):
            self.send(client, {'type': 'gather', 'nodeId': node_id})

    def bridge(self):
        self.collect(self.a, 'tree-west-north')
        self.collect(self.a, 'tree-west-south')
        self.walk(self.a, [15.7, 12])
        self.send(self.a, {'type': 'build', 'recipeId': 'bridge.v1', 'at': [18, 12]})
        self.walk(self.a, [20.7, 12])

    def raw(self, body, instance=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.world.port, timeout=10)
        headers = {'Authorization': 'Bearer ' + self.a.token, 'Content-Type': 'application/json'}
        if instance is not None:
            headers['World-Instance-Id'] = instance
        conn.request('POST', self.a.prefix + '/commands', body, headers)
        reply = conn.getresponse()
        result = reply.status, json.loads(reply.read())
        conn.close()
        return result

    def test_01_capability_legacy_and_existing_strict_receipt(self):
        self.assertEqual({'version': 1, 'supportedModes': [MODE]}, self.a.observe()['commandConcurrency'])
        old = self.create('strict-fixture', fixture='strict-r8-populated.sql')
        client = old.client()
        client.observe()
        with sqlite3.connect(old.data / 'world.db') as db:
            original = db.execute("SELECT result_json FROM receipts WHERE command_id='legacy_strict_gather'").fetchone()[0]
        request = {'schemaVersion': 1, 'rulesVersion': 'r8', 'commandId': 'legacy_strict_gather',
                   'expectedStateVersion': 0, 'action': {'type': 'gather', 'nodeId': 'tree-west-north'}}
        before = old.dump()
        self.assertEqual(json.loads(original), self.post(client, request))
        self.assertEqual(before, old.dump())
        with sqlite3.connect(old.data / 'world.db') as db:
            self.assertEqual(original, db.execute("SELECT result_json FROM receipts WHERE command_id='legacy_strict_gather'").fetchone()[0])
        legacy = self.create('legacy')
        legacy.stop()
        with sqlite3.connect(legacy.data / 'world.db') as db:
            db.executescript('DROP TRIGGER immutable_world_instance_update; DROP TRIGGER immutable_world_instance_delete; DROP TABLE world_instance;')
        before = legacy.dump()
        legacy.start()
        lc = legacy.client()
        self.assertNotIn('commandConcurrency', lc.observe())
        self.assertEqual(before, legacy.dump(), 'upgrade does not add metadata to legacy')
        self.post(lc, self.intent(lc, {'type': 'gather', 'nodeId': 'tree-west-north'}), 422, 'PRECONDITION_MODE_UNAVAILABLE')
        self.send(lc, {'type': 'gather', 'nodeId': 'tree-west-north'}, None)

    def test_02_twenty_unrelated_moves_allow_actual_progress(self):
        start = self.b.observe()['self']['position']
        for index in range(20):
            time.sleep(.02)  # Let the real 3 m/s budget cover each 5 cm step, even on fast hosts.
            request = self.intent(self.b, {'type': 'walk', 'to': [26 + .05 * (index + 1), 17]})
            self.send(self.a, {'type': 'walk', 'to': [5 + .02 * (index + 1), 7]})
            receipt = self.post(self.b, request)
            self.assertEqual(request['expectedStateVersion'] + 1, receipt['execution']['appliedOnStateVersion'])
            self.assertFalse(receipt['result']['blocked'])
        self.assertGreater(math.dist(start, self.b.observe()['self']['position']), .8)
        strict = self.intent(self.b, {'type': 'walk', 'to': [27.1, 17]}, None)
        self.send(self.a, {'type': 'walk', 'to': [5.41, 7]})
        self.post(self.b, strict, 409, 'STALE_STATE')

    def test_03_unrelated_walk_does_not_block_gather_or_build(self):
        for index in range(3):
            request = self.intent(self.a, {'type': 'gather', 'nodeId': 'tree-west-north'})
            self.send(self.b, {'type': 'walk', 'to': [26 + .02 * index, 17]})
            receipt = self.post(self.a, request)
            self.assertEqual((3 - index, 2 - index, index + 1), tuple(receipt['result'][k] for k in ('remainingWoodBefore', 'remainingWood', 'inventoryWood')))
        request = self.intent(self.a, {'type': 'build', 'recipeId': 'platform.v1', 'at': [4, 7]})
        self.send(self.b, {'type': 'walk', 'to': [26.1, 17]})
        receipt = self.post(self.a, request)
        entity = self.a.observe()['entities'][0]
        self.assertEqual((receipt['result']['entityId'], 'a1', [4, 7], 3), tuple(entity[k] for k in ('entityId', 'ownerActorId', 'position', 'embodiedWood')))

    def test_04_same_actor_concurrency_and_ABA_remain_rejected(self):
        left = self.intent(self.a, {'type': 'walk', 'to': [4.95, 7]})
        right = {**left, 'commandId': uuid.uuid4().hex, 'action': {'type': 'walk', 'to': [5.05, 7]}}
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(self.a.command, [left, right]))
        self.assertEqual([200, 409], sorted(r[0] for r in replies))
        self.assertEqual(['STALE_ACTOR_STATE'], [r[1]['error']['code'] for r in replies if r[0] == 409])
        origin = self.a.observe()['self']['position']
        old = self.intent(self.a, {'type': 'walk', 'to': [origin[0] - .1, origin[1]]})
        self.send(self.a, {'type': 'walk', 'to': [origin[0] + .05, origin[1]]})
        self.send(self.a, {'type': 'walk', 'to': origin})
        self.assertEqual(origin, self.a.observe()['self']['position'])
        self.post(self.a, old, 409, 'STALE_ACTOR_STATE')

    def test_05_partial_and_final_resource_competition(self):
        self.bridge()
        node = 'tree-east-north'
        self.approach(self.a, node)
        self.approach(self.b, node)
        older = self.intent(self.b, {'type': 'gather', 'nodeId': node})
        self.send(self.a, older['action'])
        shared = self.post(self.b, older)
        self.assertEqual((2, 1, 1), tuple(shared['result'][k] for k in ('remainingWoodBefore', 'remainingWood', 'inventoryWood')))
        requests = [self.intent(c, older['action']) for c in (self.a, self.b)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda pair: pair[0].command(pair[1]), zip((self.a, self.b), requests)))
        self.assertEqual([200, 422], sorted(r[0] for r in replies))
        self.assertEqual(['RESOURCE_DEPLETED'], [r[1]['error']['code'] for r in replies if r[0] == 422])
        for client, request, reply in zip((self.a, self.b), requests, replies):
            self.assertEqual(reply, client.command(request))
        self.assertEqual(3, sum(c.observe()['self']['inventory']['wood'] for c in (self.a, self.b)))

    def test_06_same_build_space_is_revalidated_without_double_debit(self):
        self.bridge()
        self.collect(self.a, 'tree-east-north')
        self.collect(self.b, 'tree-east-south')
        for client in (self.a, self.b):
            self.walk(client, [26.4, 16])
        action = {'type': 'build', 'recipeId': 'platform.v1', 'at': [26.4, 14.5]}
        left, right = self.intent(self.a, action), self.intent(self.b, action)
        first = self.post(self.a, left)
        loser = self.post(self.b, right, 409, 'AREA_OCCUPIED')
        self.assertEqual(3, self.b.observe()['self']['inventory']['wood'])
        self.assertEqual(2, len(self.a.observe()['entities']))
        self.assertEqual(first['stateVersion'], loser['execution']['appliedOnStateVersion'])

    def test_07_walk_rechecks_new_bridge_and_keeps_speed_limit(self):
        self.collect(self.b, 'tree-east-north')
        self.collect(self.b, 'tree-east-south')
        self.walk(self.b, [20.7, 12])
        self.walk(self.a, [16.2, 12])
        before = self.a.observe()['self']['position']
        request = self.intent(self.a, {'type': 'walk', 'to': [20.7, 12]})
        self.send(self.b, {'type': 'build', 'recipeId': 'bridge.v1', 'at': [18, 12]})
        receipt = self.post(self.a, request)
        self.assertFalse(receipt['result']['blocked'])
        self.assertGreater(receipt['result']['position'][0], 16.32)
        self.assertLessEqual(math.dist(before, receipt['result']['position']), .600001)

    def test_08_same_id_mode_changes_conflict_and_replays_keep_original_execution(self):
        strict = self.intent(self.a, {'type': 'gather', 'nodeId': 'tree-west-north'}, None)
        old = self.post(self.a, strict)
        self.post(self.a, {**strict, 'preconditionMode': MODE}, 409, 'IDEMPOTENCY_CONFLICT')
        request = self.intent(self.a, strict['action'])
        self.send(self.b, {'type': 'walk', 'to': [26.1, 17]})
        receipt = self.post(self.a, request)
        changed = {k: v for k, v in request.items() if k != 'preconditionMode'}
        self.post(self.a, changed, 409, 'IDEMPOTENCY_CONFLICT')
        self.send(self.a, {'type': 'walk', 'to': [4.9, 7]})
        renewed = self.world.issue('a1', 86400)
        renewed.observe()
        self.assertEqual((200, receipt), renewed.command(request))
        self.assertEqual((200, receipt), renewed.request('GET', renewed.prefix + '/commands/' + request['commandId']))
        self.assertEqual((200, old), renewed.command(strict))
        self.assertNotEqual(receipt['identity']['sessionId'], renewed.observe()['identity']['sessionId'])

    def test_09_invalid_modes_future_anchor_and_instance_errors_do_not_execute(self):
        request = self.intent(self.a, {'type': 'gather', 'nodeId': 'tree-west-north'})
        instance = self.a.observe()['world']['instanceId']
        before = self.world.dump()
        for invalid in [None, '', 'actor-state-v2', 1, False]:
            status, reply = self.raw(json.dumps({**request, 'preconditionMode': invalid}), instance)
            self.assertEqual((400, 'INVALID_REQUEST'), (status, reply['error']['code']))
        body = json.dumps(request).replace('"preconditionMode": "actor-state-v1"', '"preconditionMode":"actor-state-v1","preconditionMode":"actor-state-v1"')
        self.assertEqual(400, self.raw(body, instance)[0])
        self.assertEqual(before, self.world.dump())
        for value, status in [(None, 428), ('w_' + '0' * 32, 412)]:
            self.assertEqual(status, self.raw(json.dumps(request), value)[0])
        self.assertEqual(before, self.world.dump())
        future = {**request, 'expectedStateVersion': 10}
        denied = self.post(self.a, future, 409, 'STATE_VERSION_AHEAD')
        self.assertEqual({'preconditionMode': MODE, 'observedStateVersion': 10, 'appliedOnStateVersion': 0}, denied['execution'])
        self.assertEqual((409, denied), self.a.command(future))
        self.assertEqual(0, self.a.observe()['stateVersion'])

    def test_10_before_and_after_commit_crashes_recover_original_mode(self):
        for index, fault in enumerate(['before-commit', 'after-commit']):
            request = self.intent(self.a, {'type': 'gather', 'nodeId': 'tree-west-north'})
            self.send(self.b, {'type': 'walk', 'to': [26 + .05 * index, 17]})
            with self.assertRaises((OSError, RuntimeError, ValueError)):
                self.a.request('POST', self.a.prefix + '/commands', request, {'X-Test-Fault': fault})
            self.assertEqual(81 if index == 0 else 82, self.world.process.wait(timeout=10))
            self.world.restart()
            status, receipt = self.a.request('GET', self.a.prefix + '/commands/' + request['commandId'])
            self.assertEqual(404 if index == 0 else 200, status)
            original = deepcopy(request)
            restored = self.post(self.a, request)
            self.assertEqual(original, request)
            if index:
                self.assertEqual(receipt, restored)
            self.assertEqual(index + 1, self.a.observe()['self']['inventory']['wood'])


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActorStateAcceptance))
    evidence = {'suite': 'actor-state-http-v1', 'recordedAtUtc': datetime.now(timezone.utc).isoformat(),
                'passed': result.wasSuccessful(), 'testsRun': result.testsRun, 'tests': result.records,
                'actualModelCalls': 0, 'sourceSha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [ROOT / 'src/World.Server/Protocol.cs', ROOT / 'src/World.Server/WorldService.cs', ROOT / 'tests/actor_state_api.py']},
                'failureDetails': [(str(t), detail) for t, detail in result.failures + result.errors]}
    (RUN / 'results.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json')
    raise SystemExit(not result.wasSuccessful())
