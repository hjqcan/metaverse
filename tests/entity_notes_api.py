#!/usr/bin/env python3
"""Same-instance notes after real material exhaustion; never seed world facts with SQL."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import unittest
import uuid

import activities_api
import foundation_api
from foundation_api import Candidate, ROOT, EvidenceResult
from material_access_api import MaterialAccessAcceptance, reserve, harvest

DLL = Path(os.environ.get('WORLD_SERVER_DLL', foundation_api.DLL))
foundation_api.DLL = DLL
RUN = ROOT / '.local/iter0023/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])


def baseline():
    if os.environ.get('ENTITY_NOTES_BASELINE'):
        return Path(os.environ['ENTITY_NOTES_BASELINE'])
    activities_api.RUN_ROOT = RUN
    prep = MaterialAccessAcceptance('test_05_budget_capacity_and_exhausted_budget_does_not_reset')
    prep.setUp()
    try:
        prep.bridge()
        prep.collect(prep.a, 'tree-east-north'); prep.collect(prep.a, 'tree-east-south')
        prep.enable(); prep.walk(prep.c, [28, 10])
        for point in ([30,14], [30,17], [27,14], [27,17]):
            rid = prep.send(prep.c, reserve())['result']['reservationId']; prep.active(prep.c, rid)
            for _ in range(3): prep.send(prep.c, harvest(rid))
            prep.walk(prep.c, [point[0], point[1] - 2])
            prep.send(prep.c, {'type': 'build', 'recipeId': 'platform.v1', 'at': point})
            prep.walk(prep.c, [28,10])
        return prep.world.data
    finally:
        prep.tearDown()


class ContinuedCandidate(Candidate):
    def __init__(self, source, output):
        self.data = Path(output); self.data.mkdir(parents=True, mode=0o700)
        with sqlite3.connect(f'file:{source / "world.db"}?mode=ro', uri=True) as src, sqlite3.connect(self.data/'world.db') as dst:
            src.backup(dst)
        shutil.copy2(source/'access.json', self.data/'access.json')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.env = {**os.environ, 'WORLD_URL': self.url, 'WORLD_DATA_DIR': str(self.data), 'WORLD_ENABLE_FAULTS': '1'}
        self.env.pop('WORLD_SCENARIO', None)
        self.process = self.log = None
        self.access = json.loads((self.data/'access.json').read_text())
        self.start()


def facts(world):
    with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
        return {name: db.execute(sql).fetchall() for name, sql in {
            'entities': 'SELECT * FROM entities ORDER BY entity_id',
            'wood': 'SELECT actor_id,wood FROM residents ORDER BY actor_id',
            'trees': 'SELECT * FROM resource_nodes ORDER BY node_id',
            'ledger': 'SELECT * FROM resource_ledger ORDER BY rowid',
            'receipts': 'SELECT actor_id,command_id,result_json FROM receipts ORDER BY actor_id,command_id',
            'source': 'SELECT generated_wood,stock_wood FROM material_source',
        }.items()}


class EntityNotesAcceptance(unittest.TestCase):
    intent = MaterialAccessAcceptance.intent
    post = MaterialAccessAcceptance.post
    send = MaterialAccessAcceptance.send
    walk = MaterialAccessAcceptance.walk

    @classmethod
    def setUpClass(cls): cls.source = baseline()

    def setUp(self):
        self.world = ContinuedCandidate(self.source, RUN/self._testMethodName)
        self.addCleanup(self.world.stop)
        self.a, self.b, self.c = [self.world.client(a) for a in ('a1','a2','a3')]
        observed = self.a.observe(); self.instance = observed['world']['instanceId']
        self.target = next(e for e in observed['entities'] if e['definitionId'] == 'bridge')
        self.trace = []; self.before = facts(self.world)
        self.assertEqual([(12,0)], self.before['source'])
        self.assertEqual(6, observed['self']['inventory']['wood'])
        self.assertEqual(5, len(self.before['entities']))
        self.assertTrue(all(n['remainingWood'] == 0 for n in observed['resourceNodes']))

    def tearDown(self):
        self.world.stop()
        (self.world.data/'trace.json').write_text(json.dumps(self.trace, ensure_ascii=False, indent=2)+'\n')
        after = facts(self.world)
        for field in ('entities','wood','trees','ledger','source'): self.assertEqual(self.before[field], after[field], field)
        self.assertTrue(set(self.before['receipts']).issubset(set(after['receipts'])))
        with sqlite3.connect(self.world.data/'world.db') as db:
            self.assertEqual('ok', db.execute('PRAGMA integrity_check').fetchone()[0])
            self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())

    def adopt(self):
        self.world.stop()
        result = subprocess.run(['dotnet', str(DLL), 'adopt-entity-notes', '--instance', self.instance,
                                 '--entity', self.target['entityId']], cwd=ROOT, env=self.world.env, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.world.start()

    def note(self, text='桥连接了两岸。', reply=None):
        return {'type':'append_entity_note', 'entityId':self.target['entityId'], 'text':text, 'replyToNoteId':reply}

    def test_01_same_instance_two_authors_reference_return_and_old_facts(self):
        self.assertNotIn('entityNotes', self.b.observe())
        rejected = self.intent(self.b, self.note()); self.post(self.b, rejected, 422, 'ENTITY_NOTES_UNAVAILABLE')
        self.adopt()
        self.assertEqual(self.instance, self.b.observe()['world']['instanceId'])
        self.post(self.b, rejected, 422, 'ENTITY_NOTES_UNAVAILABLE')
        originals = [self.b.observe()['self']['position'], self.c.observe()['self']['position']]
        first = None
        for client, origin in zip((self.b,self.c), originals):
            if first is not None: self.assertEqual(first, client.observe()['entityNotes']['notes'][0])
            self.walk(client, self.target['position'])
            request = self.intent(client, self.note('这座桥让我们不用重新开路。' if first is None else '我从另一岸来到这里，读到了前一位居民的话。', None if first is None else first['noteId']))
            receipt = self.post(client, request); self.assertEqual(receipt, self.post(client, request))
            record = client.observe()['entityNotes']['notes'][-1]
            self.assertEqual({k:v for k,v in receipt['result'].items() if k != 'action'}, record)
            status, stream = client.request('GET', client.prefix+'/events?after='+str(record['eventCursor']-1))
            self.assertEqual(200,status)
            for key,value in record.items(): self.assertEqual(value, stream['events'][0][key])
            if first is None: first=record
            self.walk(client, origin)
        self.world.restart(); self.assertEqual(2, self.a.observe()['entityNotes']['totalCount'])
        self.assertEqual(first, self.a.observe()['entityNotes']['notes'][0])

    def test_02_frozen_text_reference_quota_and_original_receipt(self):
        self.adopt(); self.walk(self.b, self.target['position'])
        action = self.note('😀'*160); request = self.intent(self.b, action)
        first = self.post(self.b, request); changed = deepcopy(request); changed['action']['text'] = 'changed'
        self.post(self.b, changed, 409, 'IDEMPOTENCY_CONFLICT')
        self.post(self.b, self.intent(self.b, self.note('missing', 'n'+'0'*32)), 404, 'NOTE_REFERENCE_NOT_FOUND')
        self.send(self.b, self.note('<b>纯文本</b>', first['result']['noteId']))
        self.post(self.b, self.intent(self.b, self.note('第三条')), 422, 'NOTE_LIMIT_REACHED')
        self.assertEqual(first, self.post(self.b, request))
        self.world.restart(); self.assertEqual(2, self.b.observe()['entityNotes']['selfCount'])


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    suite = unittest.TestSuite(EntityNotesAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:] else unittest.defaultTestLoader.loadTestsFromTestCase(EntityNotesAcceptance)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    evidence = {'suite':'entity-notes-http-v1', 'passed':result.wasSuccessful(), 'testsRun':result.testsRun, 'tests':result.records,
                'actualModelCalls':0, 'dllSha256':hashlib.sha256(DLL.read_bytes()).hexdigest(),
                'failureDetails':[(str(t),d) for t,d in result.failures+result.errors]}
    (RUN/'results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print('Evidence:',RUN/'results.json')
    raise SystemExit(not result.wasSuccessful())
