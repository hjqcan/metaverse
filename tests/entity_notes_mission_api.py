#!/usr/bin/env python3
"""Builder self-check: explicit notes on an actual exhausted r10 continuation.

ENTITY_NOTES_BASELINE may name a stopped, read-only exhaustion snapshot; otherwise
the shared HTTP fixture constructs one through real world commands.
WORLD_SERVER_DLL selects a frozen new service; ENTITY_NOTES_OLD_DLL selects the
previous service for compatibility checks. Both binaries are copied per run.
"""
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
import time
import unittest
from unittest.mock import patch
import uuid

import foundation_api
from foundation_api import ROOT, Candidate, EvidenceResult
from foundation_agent import WorldClient
from resident_mission import run_mission
from activity_choice import choose_lowest_cost
from resident_mission_api import Choice
from material_access_api import MaterialAccessAcceptance
import resident_entity_notes as notes
import resident_mission

RUN = ROOT / '.local/iter0023/python' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
SOURCE = None
NEW_SOURCE = Path(os.environ.get('WORLD_SERVER_DLL', foundation_api.DLL))
OLD_SOURCE = Path(os.environ['ENTITY_NOTES_OLD_DLL']) if os.environ.get('ENTITY_NOTES_OLD_DLL') else None
DLL, OLD_DLL = RUN / 'bin/World.Server.dll', RUN / 'old-bin/World.Server.dll'
FILES = ['scripts/resident_entity_notes.py', 'scripts/resident_mission.py', 'scripts/command_preconditions.py',
         'scripts/run_resident.py', 'tests/entity_notes_mission_api.py', 'tests/fixtures/entity-note.json']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def facts(data):
    with sqlite3.connect(f'file:{Path(data) / "world.db"}?mode=ro', uri=True) as db:
        return {name: db.execute(sql).fetchall() for name, sql in {
            'entities': 'SELECT * FROM entities ORDER BY entity_id',
            'wood': 'SELECT actor_id,wood FROM residents ORDER BY actor_id',
            'trees': 'SELECT * FROM resource_nodes ORDER BY node_id',
            'ledger': 'SELECT * FROM resource_ledger ORDER BY rowid',
            'receipts': 'SELECT actor_id,command_id,result_json FROM receipts ORDER BY actor_id,command_id',
            'source': 'SELECT generated_wood,stock_wood FROM material_source',
            'instance': 'SELECT instance_id FROM world_instance',
        }.items()}


class Continued(Candidate):
    def __init__(self, name):
        self.data = RUN / name; self.data.mkdir(parents=True, mode=0o700)
        with sqlite3.connect(f'file:{SOURCE / "world.db"}?mode=ro&immutable=1', uri=True) as src, sqlite3.connect(self.data / 'world.db') as dst:
            src.backup(dst)
        shutil.copy2(SOURCE / 'access.json', self.data / 'access.json')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.env = {**os.environ, 'WORLD_URL': self.url, 'WORLD_DATA_DIR': str(self.data), 'WORLD_ENABLE_FAULTS': '1'}
        self.env.pop('WORLD_SCENARIO', None)
        self.process = self.log = None
        self.access = json.loads((self.data / 'access.json').read_text())
        self.initial = facts(self.data)
        foundation_api.DLL = DLL
        self.start()


class EntityNoteMissionAcceptance(unittest.TestCase):
    intent = MaterialAccessAcceptance.intent
    post = MaterialAccessAcceptance.post
    send = MaterialAccessAcceptance.send
    walk = MaterialAccessAcceptance.walk
    all_worlds = []

    @classmethod
    def setUpClass(cls):
        global SOURCE
        RUN.mkdir(parents=True, exist_ok=True)
        if not DLL.exists(): shutil.copytree(NEW_SOURCE.parent, DLL.parent)
        if OLD_SOURCE is not None and not OLD_DLL.exists(): shutil.copytree(OLD_SOURCE.parent, OLD_DLL.parent)
        from entity_notes_api import baseline
        foundation_api.DLL = DLL
        SOURCE = baseline()
        cls.baseline_hash = digest(SOURCE / 'world.db')
        foundation_api.DLL = DLL

    def setUp(self):
        self.worlds, self.trace, self.reports, self.traffic = [], [], [], []
        self.world = self.create('world')
        self.a, self.b, self.c = [self.world.client(a) for a in ('a1', 'a2', 'a3')]
        observed = self.b.observe()
        self.target = next(e for e in observed['entities'] if e['definitionId'] == 'bridge')
        self.instance = observed['world']['instanceId']
        self.assertEqual([(12, 0)], self.world.initial['source'])
        self.assertEqual(5, len(self.world.initial['entities']))
        self.assertEqual(6, dict(self.world.initial['wood'])['a1'])
        self.assertTrue(self.world.initial['receipts'])
        self.state = self.world.data / 'mission.json'
        self.adopt(self.world)

    def create(self, suffix):
        world = Continued(self._testMethodName + '-' + suffix)
        self.worlds.append(world); self.all_worlds.append(world)
        return world

    def adopt(self, world):
        observed = world.client('a2').observe()
        target = next(e for e in observed['entities'] if e['definitionId'] == 'bridge')
        world.stop()
        result = subprocess.run(['dotnet', str(DLL), 'adopt-entity-notes', '--instance', observed['world']['instanceId'],
                                 '--entity', target['entityId']], cwd=ROOT, env=world.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        foundation_api.DLL = DLL; world.start()

    def tearDown(self):
        for world in self.worlds: world.stop()
        foundation_api.DLL = DLL
        for name, value in (('reports.json', self.reports), ('traffic.json', self.traffic), ('trace.json', self.trace)):
            (self.world.data / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        for world in self.worlds:
            after = facts(world.data)
            for key in ('entities', 'wood', 'trees', 'ledger', 'source', 'instance'):
                self.assertEqual(world.initial[key], after[key], key)
            self.assertTrue(set(world.initial['receipts']).issubset(after['receipts']))
            with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
                self.assertEqual('ok', db.execute('PRAGMA integrity_check').fetchone()[0])
                self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())
                self.assertEqual(0, db.execute("SELECT count(*) FROM resource_ledger WHERE command_id IN (SELECT command_id FROM entity_notes)").fetchone()[0])
        self.assertEqual(self.baseline_hash, digest(SOURCE / 'world.db'))

    def mission(self, text=None, reply=None):
        job = json.loads((ROOT / 'tests/fixtures/entity-note.json').read_text())
        goal = job['goals'][0]; goal['target'] = deepcopy(self.target['position'])
        goal['entityNote']['entityId'] = self.target['entityId']
        if text is not None: goal['entityNote']['text'] = text
        goal['entityNote']['replyToNoteId'] = reply
        return job

    def task(self, job=None, client=None, choose=choose_lowest_cost, **kwargs):
        report = run_mission(client or self.b, job or self.mission(), self.state, choose, **kwargs)
        self.reports.append(report)
        return report

    def controlled(self, *, actor='a2', before=None, after=None, world=None):
        world = world or self.world; owner = self
        class Controlled(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                if before: headers = before(method, path, payload, headers)
                response = super().request(method, path, payload, headers)
                owner.traffic.append({'method': method, 'path': path, 'payload': deepcopy(payload), 'response': deepcopy(response)})
                return after(method, path, payload, response) if after else response
        return Controlled(world.url, world.access['sessions'][actor]['token'])

    def saved(self): return json.loads(self.state.read_text())

    def completed(self, report, job=None, actor='a2'):
        job = job or self.mission()
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['entityNoteShared'] and report['facts']['goalReached'] and report['facts']['returned'])
        note = report['facts']['entityNote']
        for key in ('text', 'entityId', 'replyToNoteId'): self.assertEqual(job['goals'][0]['entityNote'][key], note[key])
        self.assertEqual((actor, self.instance, 0), (note['authorActorId'], note['worldInstanceId'], note['inventoryWood']))
        self.assertEqual((0, 0, 0), (report['budget']['used']['wood'], report['facts']['woodGathered'], report['facts']['woodTransferred']))
        committed = [s for s in report['steps'] if s['action']['type'] == notes.ACTION and s['status'] == 'committed']
        self.assertEqual(1, len(committed)); self.assertEqual(note, committed[0]['entityNoteEvidence'])

    def test_01_actual_cli_first_note_and_original_reference_reply(self):
        first = None
        for actor in ('a2', 'a3'):
            job = self.mission('这座旧桥连接两岸。😀' if first is None else '我读到了原手记，再从这里返回。', first['noteId'] if first else None)
            spec = self.world.data / (actor + '-spec.json'); spec.write_text(json.dumps(job, ensure_ascii=False))
            self.state = self.world.data / (actor + '-state.json'); output = self.world.data / (actor + '-report.json')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_resident.py'), '--url', self.world.url,
                                     '--access-file', str(self.world.data / 'access.json'), '--actor', actor,
                                     '--spec', str(spec), '--state', str(self.state), '--output', str(output)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(output.read_text()); self.reports.append(report); self.completed(report, job, actor)
            self.assertEqual('fixed-reference', report['decision']['provider']['kind'])
            self.assertEqual(1, report['budget']['used']['modelCalls'])
            if first is None: first = report['facts']['entityNote']
            else: self.assertEqual(first['noteId'], self.saved()['_state']['entityNoteProof']['before']['reference']['noteId'])
        self.world.restart(); self.assertEqual(2, self.b.observe()['entityNotes']['totalCount'])
        raw = self.state.read_bytes(); offline = self.world.client('a3')
        offline.request = lambda *_a, **_k: self.fail('completed note requested network')
        self.assertEqual(report, self.task(job, offline)); self.assertEqual(raw, self.state.read_bytes())

    def test_02_before_and_after_commit_process_exit_and_session_rotation(self):
        for index, (fault, exit_code) in enumerate((('before-commit', 81), ('after-commit', 82))):
            world = self.world if index == 0 else self.create('after')
            if index: self.adopt(world)
            client = world.client('a2'); self.walk(client, self.target['position'])
            self.state = world.data / 'fault-state.json'
            def inject(method, path, payload, headers):
                return {**(headers or {}), 'X-Test-Fault': fault} if method == 'POST' and payload['action']['type'] == notes.ACTION else headers
            first = self.task(client=self.controlled(world=world, before=inject))
            self.assertEqual('unknown', first['mission']['status'])
            original = self.saved()['_state']['pending']['request']
            self.assertEqual(exit_code, world.process.wait(timeout=10)); world.restart()
            fresh = world.issue('a2', 600)
            final = self.task(client=fresh); self.completed(final)
            self.assertEqual(original['commandId'], final['facts']['entityNote']['commandId'])
            self.assertEqual(1, final['budget']['used']['commands'])

    def test_03_false_receipt_full_note_event_and_instance_keep_pending(self):
        self.walk(self.b, self.target['position'])
        mutations = [
            ('receipt', lambda r: r['result'].update(text='不是原文')),
            ('receipt', lambda r: r['result'].update(authorActorId='a1')),
            ('receipt', lambda r: r['result'].update(replyToNoteId='n' + '0' * 32)),
            ('receipt', lambda r: r['result'].update(noteId='n' + '0' * 32)),
            ('receipt', lambda r: r['result'].update(inventoryWood=True)),
            ('receipt', lambda r: r['identity'].update(operatorId='local-operator')),
            ('observation', lambda r: r['entityNotes']['notes'][0].update(text='伪造观察')),
            ('observation', lambda r: r['entityNotes']['target'].update(ownerActorId='a3')),
            ('observation', lambda r: r['identity'].update(operatorId='another-operator')),
            ('observation', lambda r: r['world'].update(instanceId='w_' + '0' * 32)),
            ('event', lambda r: r['events'][0].update(actorId='a1')),
            ('event', lambda r: r['events'][0].update(text='伪造事件')),
            ('event', lambda r: r['events'][0].update(seq=True)),
        ]
        original = None
        for kind, mutate in mutations:
            def corrupt(method, path, payload, response):
                status, body = response
                if isinstance(body, dict):
                    if kind == 'receipt' and body.get('result', {}).get('action') == notes.ACTION: mutate(body)
                    if kind == 'observation' and path.endswith('/observation') and body.get('entityNotes', {}).get('notes'): mutate(body)
                    if kind == 'event' and '/events?' in path and body.get('events'): mutate(body)
                return status, body
            report = self.task(client=self.controlled(after=corrupt))
            self.assertEqual('unknown', report['mission']['status'], (kind, report['mission']))
            self.assertFalse(report['facts']['entityNoteShared'])
            original = original or self.saved()['_state']['pending']['request']
            self.assertEqual(original, self.saved()['_state']['pending']['request'])
            self.assertEqual(1, report['budget']['used']['commands'])
        self.completed(self.task()); self.assertEqual(1, self.b.observe()['entityNotes']['totalCount'])

    def test_04_query_exhaustion_after_commit_and_cumulative_command_seconds(self):
        self.walk(self.b, self.target['position'])
        job = self.mission(); job['budgets']['queries'] = 3
        first = self.task(job, self.controlled())
        self.assertEqual(('budget_exhausted', 'queries_pending_retained'), (first['mission']['status'], first['mission']['reason']))
        pending = self.saved()['_state']['pending']['request']
        self.assertEqual((1, 3), (first['budget']['used']['commands'], first['budget']['used']['queries']))
        offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('query budget refilled')
        again = self.task(job, offline)
        self.assertEqual(pending, self.saved()['_state']['pending']['request']); self.assertEqual(3, again['budget']['used']['queries'])
        changed = deepcopy(job); changed['budgets']['queries'] = 300
        with self.assertRaises(ValueError): self.task(changed, offline)
        self.state = self.world.data / 'commands.json'; job = self.mission(); job['budgets']['commands'] = 1
        limited = self.task(job, self.c, choose=Choice('note'))
        self.assertEqual(('budget_exhausted', 'commands', 1), (limited['mission']['status'], limited['mission']['reason'], limited['budget']['used']['commands']))
        self.assertEqual(1, self.task(job, self.c, choose=Choice('note'))['budget']['used']['commands'])
        self.state = self.world.data / 'seconds.json'; job = self.mission('时间预算'); job['budgets']['seconds'] = 1
        self.task(job, max_steps=0); time.sleep(1.1)
        elapsed = self.task(job)
        self.assertEqual(('budget_exhausted', 'seconds', 0), (elapsed['mission']['status'], elapsed['mission']['reason'], elapsed['budget']['used']['commands']))

    def test_05_damaged_saved_binding_body_permission_and_facts_are_zero_io(self):
        self.walk(self.b, self.target['position'])
        def unsent(method, path, payload, headers):
            if method == 'POST': raise OSError('isolated pre-submit failure')
            return headers
        self.task(client=self.controlled(before=unsent)); baseline = self.saved()
        changes = [lambda s: s['mission'].update(allowEntityNotes=False),
                   lambda s: s['mission'].update(allowBuild=True),
                   lambda s: s['mission'].update(worldInstanceId='w_' + '0' * 32),
                   lambda s: s['_state']['entityNotesBinding'].update(operatorId='other'),
                   lambda s: s['_state']['binding'].update(actorId='a3'),
                   lambda s: s['budget']['limits'].update(queries=5000),
                   lambda s: s['budget']['used'].update(commands=0),
                   lambda s: s['budget']['used'].update(queries=0),
                   lambda s: s['_state']['entityNoteQueries'].pop(),
                   lambda s: s['_state']['pending']['request']['action'].update(text='被换的正文'),
                   lambda s: s['_state']['pending']['request']['action'].update(replyToNoteId='n' + '0' * 32),
                   lambda s: s['_state']['pending']['entityNoteBefore'].update(inventoryWood=1),
                   lambda s: s['_state']['pending']['entityNoteBefore']['target'].update(ownerActorId='a3'),
                   lambda s: s['facts'].update(entityNoteShared=True)]
        for mutate in changes:
            damaged = deepcopy(baseline); mutate(damaged); self.state.write_text(json.dumps(damaged))
            offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('damaged note requested network')
            with self.assertRaises(ValueError): self.task(client=offline, choose=lambda _: self.fail('damaged note chose again'))
        self.state.write_text(json.dumps(baseline)); self.completed(self.task())
        completed = self.saved(); completed['facts']['entityNote']['text'] = '损坏的完成报告'
        self.state.write_text(json.dumps(completed))
        with self.assertRaises(ValueError): self.task(client=offline)

    def test_06_later_self_action_stops_original_note_without_rewriting(self):
        self.walk(self.b, self.target['position'])
        def unsent(method, path, payload, headers):
            if method == 'POST': raise OSError('isolated pre-submit failure')
            return headers
        self.task(client=self.controlled(before=unsent)); original = self.saved()['_state']['pending']['request']
        time.sleep(.21); self.send(self.b, {'type': 'walk', 'to': [18.4, 12]})
        final = self.task()
        self.assertEqual(('blocked', 'command_rejected:STALE_ACTOR_STATE'), (final['mission']['status'], final['mission']['reason']))
        self.assertEqual(original['commandId'], final['steps'][-1]['commandId'])
        self.assertEqual(0, self.b.observe()['entityNotes']['totalCount'])
        offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('stopped note requested network')
        raw = self.state.read_bytes(); self.assertEqual(final, self.task(client=offline)); self.assertEqual(raw, self.state.read_bytes())

    def test_07_old_service_with_and_without_original_receipt_never_blindly_posts(self):
        if OLD_SOURCE is None:
            self.skipTest('ENTITY_NOTES_OLD_DLL is required for the actual old-service probe')
        for committed in (False, True):
            world = self.world if not committed else self.create('committed')
            if committed: self.adopt(world)
            self.walk(world.client('a2'), self.target['position']); self.state = world.data / 'compat.json'
            def unsent(method, path, payload, headers):
                if method == 'POST': raise OSError('isolated before send')
                return headers
            def lost(method, path, payload, response):
                if method == 'POST': raise OSError('isolated lost response')
                return response
            self.task(client=self.controlled(world=world, before=None if committed else unsent, after=lost if committed else None))
            original = self.saved()['_state']['pending']['request']
            world.stop(); foundation_api.DLL = OLD_DLL; world.start(); offset = len(self.traffic)
            old = self.task(client=self.controlled(world=world))
            self.assertEqual('unknown', old['mission']['status']); self.assertFalse(old['facts']['entityNoteShared'])
            self.assertEqual(original, self.saved()['_state']['pending']['request'])
            attempted = self.traffic[offset:]
            self.assertTrue(any('/commands/' in t['path'] for t in attempted))
            self.assertFalse(any(t['method'] == 'POST' for t in attempted))
            world.stop(); foundation_api.DLL = DLL; world.start()
            final = self.task(client=world.client('a2')); self.completed(final)
            self.assertEqual(original['commandId'], final['facts']['entityNote']['commandId'])
            self.assertEqual(1, final['budget']['used']['commands'])

    def test_08_unknown_queries_and_parse_rejections_do_not_settle_original(self):
        self.walk(self.b, self.target['position'])
        def lost(method, path, payload, response):
            if method == 'POST': raise OSError('isolated lost response')
            return response
        self.task(client=self.controlled(after=lost)); original = self.saved()['_state']['pending']['request']
        for status, code in ((503, 'SERVICE_UNAVAILABLE'), (400, 'INVALID_REQUEST'), (404, 'NOT_FOUND')):
            def proxy(method, path, payload, response):
                return (status, {'error': {'code': code, 'mutated': False}}) if '/commands/' in path else response
            report = self.task(client=self.controlled(after=proxy))
            self.assertEqual('unknown', report['mission']['status']); self.assertEqual(original, self.saved()['_state']['pending']['request'])
        self.completed(self.task())

    def test_09_permissions_reference_and_unused_flags(self):
        for mutate in (lambda j: j.pop('allowEntityNotes'), lambda j: j.update(allowEntityNotes=False),
                       lambda j: j['budgets'].pop('queries'), lambda j: j['goals'][0]['entityNote'].update(text='\ud800'),
                       lambda j: j['goals'][0].update(buildRecipeId='bridge.v1')):
            job = self.mission(); mutate(job)
            with self.assertRaises(ValueError): self.task(job, self.controlled())
        self.assertEqual([], self.traffic)
        job = self.mission(reply='n' + '0' * 32)
        with self.assertRaises(ValueError): self.task(job)
        self.assertEqual((notes.STARTUP, 1), (self.saved()['kind'], self.saved()['used']['queries']))
        self.state = self.world.data / 'ordinary.json'
        job = self.mission(); job['goals'][0].pop('entityNote'); job['goals'][0]['target'] = self.b.observe()['self']['position']
        job['budgets'].pop('queries'); job['allowMaterialAccess'] = True
        ordinary = self.task(job)
        self.assertEqual('completed', ordinary['mission']['status']); self.assertNotIn('queries', ordinary['budget']['used'])
        self.assertFalse(ordinary['facts']['entityNoteShared'])

    def test_10_existing_material_task_recovery_regression(self):
        import activities_api
        os.environ['WORLD_TEST_DLL'] = str(DLL)
        import material_access_mission_api as legacy
        activities_api.RUN_ROOT = RUN / 'legacy-material'
        for name in ('test_03_reserve_event_binding_corruption_unknown_query_and_new_session',
                     'test_10_query_exhaustion_after_commit_retains_pending_without_budget_refill'):
            case = legacy.MaterialMissionAcceptance(name); result = unittest.TestResult(); case.run(result)
            self.assertEqual([], result.errors + result.failures, result.errors + result.failures)

    def test_11_first_failed_observation_is_durable_and_cannot_refill(self):
        job = self.mission(); job['budgets']['queries'] = 1
        attempts = []
        failed = self.world.client('a2')
        def unavailable(method, path, *_args, **_kwargs):
            attempts.append(self.saved())
            return 503, {'error': {'code': 'SERVICE_UNAVAILABLE'}}
        failed.request = unavailable
        with self.assertRaises(RuntimeError): self.task(job, failed)
        initial = self.saved()
        self.assertEqual((notes.STARTUP, 1), (initial['kind'], initial['used']['queries']))
        self.assertEqual(initial['used']['queries'], attempts[0]['used']['queries'])
        self.assertNotIn('mission', initial); self.assertNotIn('world', initial)
        offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('startup refilled its budget')
        with self.assertRaises(notes.StartupBudget): self.task(job, offline)
        self.assertEqual(1, len(attempts))
        for mutate in (lambda s: s['used'].update(queries=0), lambda s: s['endpoint'].update(url='http://different'),
                       lambda s: s.update(kind='damaged'), lambda s: s.pop('kind'),
                       lambda s: s.update(startedEpoch=False), lambda s: s['queries'].clear()):
            damaged = deepcopy(initial); mutate(damaged); self.state.write_text(json.dumps(damaged))
            with self.assertRaises(ValueError): self.task(job, offline)
        self.state.write_text(json.dumps(initial))
        changed = deepcopy(job); changed['budgets']['queries'] = 2
        with self.assertRaises(ValueError): self.task(changed, offline)
        self.state = self.world.data / 'startup-seconds.json'; job = self.mission(); job['budgets']['seconds'] = 1
        with self.assertRaises(RuntimeError): self.task(job, failed)
        time.sleep(1.1)
        with self.assertRaises(notes.StartupBudget): self.task(job, offline)
        self.assertEqual(1, self.saved()['used']['queries'])
        self.state = self.world.data / 'startup-recovered.json'; job = self.mission(); job['budgets']['queries'] = 3
        with self.assertRaises(RuntimeError): self.task(job, failed)
        original = self.saved(); time.sleep(.02)
        recovered = self.task(job, max_steps=0)
        self.assertEqual(('paused', 3, 0), (recovered['mission']['status'], recovered['budget']['used']['queries'], recovered['budget']['used']['commands']))
        self.assertEqual(original['startedEpoch'], self.saved()['_state']['startedEpoch'])
        self.assertGreaterEqual(recovered['budget']['used']['seconds'], .02)
        exhausted = self.task(job, offline)
        self.assertEqual(('budget_exhausted', 3), (exhausted['mission']['status'], exhausted['budget']['used']['queries']))
        self.trace.append({'bootstrapAttempts': attempts, 'recovered': recovered})

    def test_12_four_queries_project_confirmed_note_atomically(self):
        self.walk(self.b, self.target['position'])
        job = self.mission(); job['budgets']['queries'] = 4
        writes, save = [], resident_mission._save
        def capture(path, state):
            writes.append(deepcopy(state)); save(path, state)
        with patch.object(resident_mission, '_save', capture):
            report = self.task(job, self.controlled())
        self.assertEqual(('budget_exhausted', 'queries', 4),
                         (report['mission']['status'], report['mission']['reason'], report['budget']['used']['queries']))
        note = report['facts']['entityNote']; self.assertTrue(report['facts']['entityNoteShared'])
        self.assertEqual(note['stateVersion'], report['facts']['endStateVersion'])
        self.assertIsNone(self.saved()['_state']['pending'])
        raw_note = {k: v for k, v in note.items() if k != 'worldInstanceId'}
        confirmed_writes = [s for s in writes if s.get('facts', {}).get('entityNoteShared')]
        self.assertTrue(confirmed_writes)
        for state in confirmed_writes:
            self.assertIsNone(state['_state']['pending'])
            self.assertEqual('committed', state['steps'][-1]['status'])
            self.assertEqual(raw_note, state['world']['entityNotes']['notes'][0])
            self.assertEqual(note['stateVersion'], state['facts']['endStateVersion'])
        self.assertEqual(4, len([t for t in self.traffic if t['method'] == 'GET']))
        offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('confirmed projection performed extra GET')
        self.assertTrue(self.task(job, offline)['facts']['entityNoteShared'])
        self.trace.append({'atomicWrites': writes})

    def test_13_original_reference_body_cannot_change_between_observations(self):
        self.walk(self.c, self.target['position'])
        original = self.send(self.c, {'type': notes.ACTION, 'entityId': self.target['entityId'],
                                     'text': '原桥原文', 'replyToNoteId': None})['result']
        self.walk(self.b, self.target['position'])
        job = self.mission('引用原文', original['noteId']); observations = 0
        def altered(method, path, payload, response):
            nonlocal observations
            if path.endswith('/observation'):
                observations += 1
                if observations > 1: response[1]['entityNotes']['notes'][0]['text'] = '另一个正文'
            return response
        report = self.task(job, self.controlled(after=altered))
        self.assertEqual(('unknown', 0), (report['mission']['status'], report['budget']['used']['commands']))
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.assertEqual(original['text'], self.saved()['_state']['initial']['entityNotes']['notes'][0]['text'])
        self.completed(self.task(job), job)


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    before = {p: digest(ROOT / p) for p in FILES}
    suite = (unittest.TestSuite(EntityNoteMissionAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:]
             else unittest.defaultTestLoader.loadTestsFromTestCase(EntityNoteMissionAcceptance))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    for test, reason in result.skipped:
        for record in result.records:
            if record['test'] == test.id(): record.update(passed=None, skipped=True, reason=reason)
    after = {p: digest(ROOT / p) for p in FILES}
    stopped = all(w.process.poll() is not None for w in EntityNoteMissionAcceptance.all_worlds)
    report = {'suite': 'entity-note-mission-http', 'validationLevel': 'builder-self-check', 'actualModelCalls': 0,
              'passed': result.wasSuccessful() and before == after and stopped,
              'testsRun': result.testsRun, 'tests': result.records,
              'skipped': [{'test': t.id(), 'reason': why} for t, why in result.skipped],
              'sourceHashesBefore': before, 'sourceHashesAfter': after,
              'sourceStable': before == after, 'allStartedServicesStopped': stopped,
              'baseline': str(SOURCE), 'baselineSha256': digest(SOURCE / 'world.db') if SOURCE else None,
              'dll': str(DLL), 'dllSha256': digest(DLL) if DLL.exists() else None,
              'oldDllSha256': digest(OLD_DLL) if OLD_DLL.exists() else None,
              'failureDetails': [(str(t), d) for t, d in result.failures + result.errors]}
    (RUN / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json', flush=True)
    raise SystemExit(not report['passed'])
