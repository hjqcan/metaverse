#!/usr/bin/env python3
"""Instance preconditions against real HTTP/SQLite, including legacy fixtures. No models."""
from datetime import datetime, timezone
import hashlib
import http.client
import json
import sqlite3
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import ROOT
from foundation_agent import WorldBindingError, WorldClient

RUN = ROOT / '.local/world-instance/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN
PREFIX = '/v1/worlds/foundation-01'
HEADER = 'World-Instance-Id'


def raw(world, method, path, payload=None, instances=(), token=None):
    """Intentionally never observes or adds a binding on behalf of a test."""
    body = json.dumps(payload, separators=(',', ':')).encode() if payload is not None else b''
    connection = http.client.HTTPConnection('127.0.0.1', world.port, timeout=10)
    connection.putrequest(method, path)
    connection.putheader('Authorization', 'Bearer ' + (token or world.access['sessions']['a1']['token']))
    connection.putheader('Content-Type', 'application/json')
    connection.putheader('Content-Length', str(len(body)))
    for name, value in instances:
        connection.putheader(name, value)
    connection.endheaders(body)
    reply = connection.getresponse()
    content = reply.read()
    result = reply.status, json.loads(content) if content else None, reply.getheader(HEADER), content
    connection.close()
    return result


def fingerprint(world):
    with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'world_instance' ORDER BY name")]
        rows = {name: db.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall() for name in names}
        rows['user_version'] = db.execute('PRAGMA user_version').fetchone()
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


class InstanceAcceptance(unittest.TestCase):
    def setUp(self):
        self.worlds = []
        self.world = self.create('original')
        self.client = self.world.client()
        self.observed = self.client.observe()
        self.instance = self.observed['world']['instanceId']

    def create(self, name):
        world = ActivityCandidate(self._testMethodName + '-' + name, scenario='wilderness-continuous-v1')
        self.worlds.append(world)
        return world

    def tearDown(self):
        for world in self.worlds:
            world.stop()

    def intent(self):
        return dict(schemaVersion=1, rulesVersion='r8', commandId='instance_' + uuid.uuid4().hex,
                    expectedStateVersion=0, action={'type': 'gather', 'nodeId': 'tree-west-north'})

    def test_01_new_instances_restart_and_immutable_metadata(self):
        other = self.create('second')
        self.assertNotEqual(self.instance, other.client().observe()['world']['instanceId'])
        before = fingerprint(self.world)
        self.world.restart()
        self.assertEqual(self.instance, self.world.client().observe()['world']['instanceId'])
        self.assertEqual(before, fingerprint(self.world))
        with sqlite3.connect(self.world.data / 'world.db') as db:
            self.assertEqual([(1, self.instance, 1)], db.execute('SELECT * FROM world_instance').fetchall())
            self.assertEqual(8, db.execute('PRAGMA user_version').fetchone()[0])
            for statement in ('DELETE FROM world_instance', "UPDATE world_instance SET instance_id='w_' || '00000000000000000000000000000000'"):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(statement)
                db.rollback()

    def test_02_precondition_errors_have_no_business_effect(self):
        original = self.intent()
        before = fingerprint(self.world)
        cases = [([], 428, 'WORLD_INSTANCE_REQUIRED'),
                 ([(HEADER, 'w_' + '0' * 32)], 412, 'WORLD_INSTANCE_MISMATCH'),
                 ([(HEADER, '')], 400, 'INVALID_WORLD_INSTANCE'),
                 ([(HEADER, self.instance), (HEADER, self.instance)], 400, 'INVALID_WORLD_INSTANCE'),
                 ([(HEADER, self.instance + ',' + self.instance)], 400, 'INVALID_WORLD_INSTANCE'),
                 ([(HEADER, 'w_BAD')], 400, 'INVALID_WORLD_INSTANCE')]
        for headers, expected, code in cases:
            for method, path, payload in [('POST', PREFIX + '/commands', original),
                                          ('GET', PREFIX + '/commands/' + original['commandId'], None),
                                          ('DELETE', '/v1/session', None)]:
                with self.subTest(code=code, method=method, headers=headers):
                    status, body, _, _ = raw(self.world, method, path, payload, headers)
                    self.assertEqual(expected, status, body)
                    self.assertEqual(code, body['error']['code'])
                    self.assertIs(body['error']['mutated'], False)
                    self.assertNotIn('status', body)
                    self.assertEqual(before, fingerprint(self.world))
        status, _, _, _ = raw(self.world, 'POST', PREFIX + '/commands', original,
                             [(HEADER, 'bad')], token='invalid')
        self.assertEqual(401, status, 'authentication precedes instance validation')
        status, body, response_id, _ = raw(self.world, 'POST', PREFIX + '/commands', original,
                                          [(HEADER.lower(), self.instance)])
        self.assertEqual(200, status, body)
        self.assertEqual(self.instance, response_id)

    def test_03_receipt_bytes_and_historical_session_survive_rotation(self):
        original = self.intent()
        status, body, _, original_bytes = raw(self.world, 'POST', PREFIX + '/commands', original, [(HEADER, self.instance)])
        self.assertEqual(200, status, body)
        old_session = body['identity']['sessionId']
        rotated = self.world.issue('a1', 86400)
        current = rotated.observe()
        self.assertEqual(self.instance, current['world']['instanceId'])
        self.assertNotEqual(old_session, current['identity']['sessionId'])
        for method, path, payload in [('GET', PREFIX + '/commands/' + original['commandId'], None),
                                     ('POST', PREFIX + '/commands', original)]:
            status, replay, instance, content = raw(self.world, method, path, payload,
                                                   [(HEADER, self.instance)], token=rotated.token)
            self.assertEqual(200, status)
            self.assertEqual(original_bytes, content)
            self.assertEqual(old_session, replay['identity']['sessionId'])
            self.assertEqual(self.instance, instance)
        self.assertEqual(1, rotated.observe()['self']['inventory']['wood'])

    def test_04_new_database_at_same_url_cannot_accept_original(self):
        original = self.intent()
        old_token = self.client.token
        self.world.stop()
        replacement = self.create('replacement')
        replacement.stop()
        replacement.port, replacement.url = self.world.port, self.world.url
        replacement.env['WORLD_URL'] = replacement.url
        replacement.start()
        before = fingerprint(replacement)
        self.assertNotEqual(self.instance, replacement.client().observe()['world']['instanceId'])
        for method, path, payload in [('POST', PREFIX + '/commands', original),
                                     ('GET', PREFIX + '/commands/' + original['commandId'], None)]:
            status, body, _, _ = raw(replacement, method, path, payload, [(HEADER, self.instance)])
            self.assertEqual(412, status, body)
        # The transport also preserves its pinned identity after fresh B credentials.
        self.client.token = replacement.access['sessions']['a1']['token']
        with self.assertRaises(WorldBindingError):
            self.client.command(original)
        with self.assertRaises(WorldBindingError):
            self.client.observe()
        self.assertEqual(self.instance, self.client.world_instance_id)
        self.assertEqual(before, fingerprint(replacement))
        replacement.stop()
        self.world.start()
        self.client.token = old_token
        status, receipt = self.client.command(original)
        self.assertEqual(200, status, receipt)
        self.assertEqual(original['commandId'], receipt['commandId'])

    def test_05_observation_and_reads_enforce_pinned_instance(self):
        before = fingerprint(self.world)
        for path in (PREFIX + '/observation', PREFIX + '/events?after=0', PREFIX + '/mosaic-proposals'):
            status, body, _, _ = raw(self.world, 'GET', path, instances=[(HEADER, 'w_' + '0' * 32)])
            self.assertEqual(412, status, body)
        status, body, response_id, _ = raw(self.world, 'GET', PREFIX + '/observation')
        self.assertEqual(200, status)
        self.assertEqual(self.instance, response_id)
        self.assertEqual(response_id, body['world']['instanceId'])
        self.assertEqual({'version': 1, 'required': True, 'header': HEADER}, body['commandBinding'])
        self.assertEqual(before, fingerprint(self.world))

    def test_06_existing_schema8_remains_legacy_without_silent_adoption(self):
        # Exact legacy business schema: remove only newly introduced metadata from
        # this stopped disposable fixture. Never change any preview or saved user world.
        self.world.stop()
        with sqlite3.connect(self.world.data / 'world.db') as db:
            db.executescript('DROP TRIGGER immutable_world_instance_update; DROP TRIGGER immutable_world_instance_delete; DROP TABLE world_instance;')
        before = fingerprint(self.world)
        self.world.start()
        legacy = self.world.client()
        observed = legacy.observe()
        self.assertNotIn('instanceId', observed['world'])
        self.assertNotIn('commandBinding', observed)
        self.assertEqual(before, fingerprint(self.world))
        with sqlite3.connect(self.world.data / 'world.db') as db:
            self.assertEqual([], db.execute("SELECT name FROM sqlite_master WHERE name='world_instance'").fetchall())
        status, body, _, _ = raw(self.world, 'POST', PREFIX + '/commands', self.intent(), [(HEADER, self.instance)])
        self.assertEqual(428, status, body)
        self.assertEqual('WORLD_INSTANCE_UNAVAILABLE', body['error']['code'])
        status, body = legacy.command(self.intent())
        self.assertEqual(200, status, body)
        protected = self.create('protected')
        legacy.url = protected.url
        legacy.token = protected.access['sessions']['a1']['token']
        with self.assertRaises(WorldBindingError):
            legacy.observe()
        self.assertIsNone(legacy.world_instance_id, 'a legacy client must not silently adopt B')

    def test_07_corrupt_metadata_is_not_regenerated(self):
        self.world.stop()
        with sqlite3.connect(self.world.data / 'world.db') as db:
            db.execute('DROP TRIGGER immutable_world_instance_delete')
            db.execute('DELETE FROM world_instance')
        before = fingerprint(self.world)
        with self.assertRaises(RuntimeError):
            self.world.start()
        self.assertEqual(before, fingerprint(self.world))
        with sqlite3.connect(self.world.data / 'world.db') as db:
            self.assertEqual([], db.execute('SELECT * FROM world_instance').fetchall())

    def test_08_relocated_world_uses_saved_identity_and_original_receipt(self):
        original = self.intent()
        status, receipt = self.client.command(original)
        self.assertEqual(200, status)
        self.world.stop()
        # Let a new listener choose an available port without creating a new DB.
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.world.port = sock.getsockname()[1]
        self.world.url = f'http://127.0.0.1:{self.world.port}'
        self.world.env['WORLD_URL'] = self.world.url
        self.world.start()
        moved = self.world.client()
        moved.bind_instance(self.instance)
        self.assertEqual(self.instance, moved.observe()['world']['instanceId'])
        status, replay = moved.request('GET', PREFIX + '/commands/' + original['commandId'])
        self.assertEqual(200, status)
        self.assertEqual(receipt, replay)
        self.assertEqual(1, moved.observe()['self']['inventory']['wood'])


if __name__ == '__main__':
    RUN.mkdir(parents=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InstanceAcceptance))
    report = {'passed': result.wasSuccessful(), 'testsRun': result.testsRun,
              'failures': [(str(t), detail) for t, detail in result.failures + result.errors], 'actualModelCalls': 0}
    (RUN / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json')
    raise SystemExit(not result.wasSuccessful())
