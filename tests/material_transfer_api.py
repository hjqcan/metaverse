#!/usr/bin/env python3
"""Actual r9 HTTP transactions; every material fixture is produced by legal HTTP actions."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import shutil
import sqlite3
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate
from actor_state_api import ActorStateAcceptance, MODE
from foundation_api import DLL, ROOT, EvidenceResult

RUN = ROOT / '.local/iter0020/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN


def gift(recipient='a2', quantity=3):
    return {'type': 'transfer', 'recipientActorId': recipient, 'resource': 'wood', 'quantity': quantity}


class TransferAcceptance(unittest.TestCase):
    # Share HTTP/navigation/audit helpers only, not the parent's r8 test cases.
    tearDown = ActorStateAcceptance.tearDown
    intent = ActorStateAcceptance.intent
    post = ActorStateAcceptance.post
    send = ActorStateAcceptance.send
    walk = ActorStateAcceptance.walk
    approach = ActorStateAcceptance.approach
    collect = ActorStateAcceptance.collect
    bridge = ActorStateAcceptance.bridge
    raw = ActorStateAcceptance.raw
    meeting_source = None

    def setUp(self):
        self.worlds, self.trace = [], []
        self.world = self.create('world')
        self.a, self.b = self.world.client(), self.world.client('a2')

    def create(self, name, scenario='wilderness-cooperation-v1', fixture=None):
        world = ActivityCandidate(self._testMethodName + '-' + name, scenario=scenario, fixture=fixture)
        self.worlds.append(world)
        return world

    def meeting(self):
        """Cold copies save repeated walking. No SQL state edits, issuance, or live clones."""
        if TransferAcceptance.meeting_source is None:
            self.bridge()
            self.collect(self.a, 'tree-east-north')
            self.collect(self.a, 'tree-east-south')
            self.walk(self.a, [26, 16])
            self.walk(self.b, [26.7, 16])
            self.world.stop()
            source = self.world.data.parent / 'natural-meeting-fixture'
            source.mkdir()
            for name in ('world.db', 'access.json'):
                shutil.copy2(self.world.data / name, source / name)
            (source / 'creation-trace.json').write_text(json.dumps(self.trace, ensure_ascii=False, indent=2) + '\n')
            TransferAcceptance.meeting_source = source
            self.world.start()
        else:
            self.world.stop()
            for name in ('world.db', 'access.json'):
                shutil.copy2(TransferAcceptance.meeting_source / name, self.world.data / name)
            self.world.access = json.loads((self.world.data / 'access.json').read_text())
            self.world.start()
            self.a, self.b = self.world.client(), self.world.client('a2')
        a, b = self.a.observe(), self.b.observe()
        self.assertEqual((0, 6, 0, 6), (a['resourceAudit']['wildWood'], a['self']['inventory']['wood'], b['self']['inventory']['wood'], a['resourceAudit']['embodiedWood']))
        self.assertLess(math.dist(a['self']['position'], b['self']['position']), 1.6)

    def test_01_cooperation_real_materials_received_then_built_and_original_receipt(self):
        self.meeting()
        observed = self.a.observe()
        self.assertEqual('wilderness-cooperation-v1', observed['world']['scenarioId'])
        self.assertEqual({'version': 1, 'resource': 'wood', 'maxQuantity': 12, 'reach': 1.6, 'recipientConfirmation': False}, observed['materialTransfer'])
        request = self.intent(self.a, gift())
        receipt = self.post(self.a, request)
        self.assertEqual({'action': 'transfer', 'resource': 'wood', 'quantity': 3, 'senderActorId': 'a1', 'recipientActorId': 'a2', 'inventoryWood': 3}, receipt['result'])
        incoming = self.b.observe()['recentTransfers']['items']
        self.assertEqual(1, len(incoming))
        self.assertEqual((request['commandId'], 'a1', 'a2', 3, receipt['stateVersion']), tuple(incoming[0][k] for k in ('commandId', 'actorId', 'recipientActorId', 'quantity', 'stateVersion')))
        self.assertEqual(404, self.b.request('GET', self.b.prefix + '/commands/' + request['commandId'])[0])
        built = self.send(self.b, {'type': 'build', 'recipeId': 'platform.v1', 'at': [28, 16]})
        self.assertEqual(0, built['result']['inventoryWood'])
        self.assertEqual((200, receipt), self.a.request('GET', self.a.prefix + '/commands/' + request['commandId']))
        self.assertEqual(receipt, self.post(self.a, request))
        self.world.restart()
        self.assertEqual(receipt, self.post(self.a, request))
        now = self.a.observe()
        self.assertEqual((3, 9), (now['resourceAudit']['inventoryWood'], now['resourceAudit']['embodiedWood']))
        self.assertEqual('a2', next(e for e in now['entities'] if e['entityId'] == built['result']['entityId'])['ownerActorId'])

    def test_02_refusal_control_can_cross_but_cannot_build(self):
        self.meeting()
        self.walk(self.b, [15, 12])
        request = self.intent(self.b, {'type': 'build', 'recipeId': 'platform.v1', 'at': [14, 12]})
        denied = self.post(self.b, request, 422, 'INSUFFICIENT_RESOURCE')
        self.send(self.a, {'type': 'walk', 'to': [26.1, 16]})
        self.assertEqual((422, denied), self.b.command(request))
        self.assertEqual([], self.b.observe()['recentTransfers']['items'])
        self.assertEqual((6, 0), (self.a.observe()['self']['inventory']['wood'], self.b.observe()['self']['inventory']['wood']))

    def test_03_protocol_invalid_and_old_worlds_remain_unavailable(self):
        before = self.a.observe()
        for field, values in [('quantity', [0, -1, 13, 1.1, True, '3']), ('resource', ['stone', None]), ('recipientActorId', ['', 'has space', True])]:
            for value in values:
                action = gift(); action[field] = value
                self.post(self.a, self.intent(self.a, action), 400, 'INVALID_REQUEST')
        for field, code in [('actorId', 'IDENTITY_OVERRIDE'), ('senderActorId', 'INVALID_REQUEST')]:
            self.post(self.a, self.intent(self.a, {**gift(), field: 'a2'}), 403 if field == 'actorId' else 400, code)
        for action, status, code in [(gift('a1'), 422, 'SELF_TRANSFER'), (gift('missing'), 404, 'RESIDENT_NOT_FOUND'), (gift(), 422, 'TRANSFER_UNREACHABLE')]:
            request = self.intent(self.a, action)
            denied = self.post(self.a, request, status, code)
            self.assertEqual((status, denied), self.a.command(request))
        self.assertEqual(before, self.a.observe())
        old = self.create('old-r8', scenario='wilderness-continuous-v1'); client = old.client()
        self.assertNotIn('materialTransfer', client.observe())
        self.post(client, self.intent(client, gift(), None), 422, 'ACTION_UNAVAILABLE')
        self.post(client, self.intent(client, gift()), 422, 'PRECONDITION_MODE_UNAVAILABLE')

    def test_04_same_id_changes_conflict_and_different_actors_do_not_share_receipts(self):
        self.meeting()
        request = self.intent(self.a, gift(quantity=1))
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: self.a.command(request), range(4)))
        self.assertTrue(all(reply == replies[0] for reply in replies))
        for change in ({'action': gift(quantity=2)}, {'action': gift('a1', 1)}, {'expectedStateVersion': request['expectedStateVersion'] + 1}):
            self.post(self.a, {**request, **change}, 409, 'IDEMPOTENCY_CONFLICT')
        strict = deepcopy(request); strict.pop('preconditionMode')
        self.post(self.a, strict, 409, 'IDEMPOTENCY_CONFLICT')
        opposite = self.intent(self.b, gift('a1', 1)); opposite['commandId'] = request['commandId']
        returned = self.post(self.b, opposite)
        self.assertEqual('a2', returned['result']['senderActorId'])
        self.assertEqual((6, 0), (self.a.observe()['self']['inventory']['wood'], self.b.observe()['self']['inventory']['wood']))
        self.assertEqual(replies[0], self.a.command(request))

    def test_05_incoming_transfer_invalidates_all_four_actions_and_aba(self):
        self.meeting()
        actions = [{'type': 'walk', 'to': [26.8, 16]}, {'type': 'gather', 'nodeId': 'tree-east-south'},
                   {'type': 'build', 'recipeId': 'platform.v1', 'at': [28, 16]}, gift('a1', 1)]
        old = [self.intent(self.b, action) for action in actions]
        strict = self.intent(self.b, actions[0], None)
        self.send(self.a, gift(quantity=3))
        for request in old:
            self.post(self.b, request, 409, 'STALE_ACTOR_STATE')
        self.post(self.b, strict, 409, 'STALE_STATE')
        aba = self.intent(self.b, {'type': 'walk', 'to': [26.8, 16]})
        self.send(self.b, gift('a1', 3))
        self.send(self.a, gift(quantity=3))
        self.post(self.b, aba, 409, 'STALE_ACTOR_STATE')
        self.send(self.b, {'type': 'build', 'recipeId': 'platform.v1', 'at': [28, 16]})

    def test_06_sender_stable_receiver_movement_rechecked_and_obstacle_blocks(self):
        self.meeting()
        request = self.intent(self.a, gift(quantity=1))
        self.send(self.b, {'type': 'walk', 'to': [26.8, 16]})
        self.post(self.a, request)
        request = self.intent(self.a, gift(quantity=1))
        self.walk(self.b, [28, 16])
        self.post(self.a, request, 422, 'TRANSFER_UNREACHABLE')
        radius, angle = 1.55, .45
        self.walk(self.a, [23 + radius * math.cos(angle), 12.5 - radius * math.sin(angle)])
        self.walk(self.b, [23 + radius * math.cos(angle), 12.5 + radius * math.sin(angle)])
        self.assertLess(math.dist(self.a.observe()['self']['position'], self.b.observe()['self']['position']), 1.6)
        self.post(self.a, self.intent(self.a, gift(quantity=1)), 422, 'TRANSFER_UNREACHABLE')

    def test_07_competing_build_and_gift_do_not_double_spend(self):
        self.meeting()
        self.send(self.a, gift(quantity=3))
        requests = [self.intent(self.a, gift(quantity=3)), self.intent(self.a, {'type': 'build', 'recipeId': 'platform.v1', 'at': [28, 16]})]
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(self.a.command, requests))
        self.assertEqual([200, 409], sorted(status for status, _ in replies))
        self.assertEqual('STALE_ACTOR_STATE', next(reply['error']['code'] for status, reply in replies if status == 409))
        self.assertEqual(0, self.a.observe()['self']['inventory']['wood'])
        self.post(self.a, self.intent(self.a, gift(quantity=1)), 422, 'INSUFFICIENT_RESOURCE')

    def test_08_debit_rollback_and_both_process_exit_points_recover_once(self):
        self.meeting()
        request = self.intent(self.a, gift(quantity=1)); before = self.a.observe()
        self.post(self.a, request, 503, 'SERVICE_UNAVAILABLE', {'X-Test-Fault': 'throw-after-debit'})
        self.assertEqual(before, self.a.observe())
        self.assertEqual(404, self.a.request('GET', self.a.prefix + '/commands/' + request['commandId'])[0])
        for index, fault in enumerate(('before-commit', 'after-commit')):
            request = self.intent(self.a, gift(quantity=1))
            with self.assertRaises((OSError, RuntimeError, ValueError)):
                self.a.request('POST', self.a.prefix + '/commands', request, {'X-Test-Fault': fault})
            self.assertEqual(81 if index == 0 else 82, self.world.process.wait(timeout=10))
            self.world.restart()
            self.assertEqual(404 if index == 0 else 200, self.a.request('GET', self.a.prefix + '/commands/' + request['commandId'])[0])
            receipt = self.post(self.a, request)
            self.assertEqual(receipt, self.post(self.a, request))
            self.assertEqual(index + 1, self.b.observe()['self']['inventory']['wood'])

    def test_09_recent_history_is_bounded_but_public_events_remain_complete(self):
        self.meeting()
        for index in range(22):
            self.send(self.a if index % 2 == 0 else self.b, gift('a2' if index % 2 == 0 else 'a1', 1))
        recent = self.b.observe()['recentTransfers']
        self.assertEqual((20, True), (len(recent['items']), recent['truncated']))
        cursor, all_events = 0, []
        while True:
            status, result = self.b.request('GET', self.b.prefix + '/events?after=' + str(cursor))
            self.assertEqual(200, status); all_events.extend(result['events'])
            if result['nextCursor'] == result['eventCursor']: break
            self.assertGreater(result['nextCursor'], cursor); cursor = result['nextCursor']
        transfers = [e for e in all_events if e['type'] == 'woodTransferred']
        self.assertEqual(22, len(transfers)); self.assertEqual(transfers[-20:], recent['items'])


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(TransferAcceptance))
    evidence = {'suite': 'material-transfer-http-v1', 'recordedAtUtc': datetime.now(timezone.utc).isoformat(),
                'passed': result.wasSuccessful(), 'testsRun': result.testsRun, 'tests': result.records, 'actualModelCalls': 0,
                'fixture': 'cold isolated copies of an actual HTTP-created world; creation-trace.json retained',
                'dllSha256': hashlib.sha256(DLL.read_bytes()).hexdigest(),
                'sourceSha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [*sorted((ROOT / 'src/World.Server').glob('*.cs')), ROOT / 'tests/material_transfer_api.py']},
                'failureDetails': [(str(t), detail) for t, detail in result.failures + result.errors]}
    (RUN / 'results.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json')
    raise SystemExit(not result.wasSuccessful())
