#!/usr/bin/env python3
"""Builder self-check of fixed canvas tasks on a real isolated r10 continuation.

ENTITY_CANVAS_BASELINE must contain the original DB/WAL snapshot and access.json.
WORLD_SERVER_DLL is a frozen shared runtime. SQLite backup captures WAL changes;
neither the source world nor its resources, positions or drawings are rewritten.
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
import unittest
import uuid

import foundation_api
from foundation_api import ROOT, EvidenceResult
from continuous_material_api import rows
from entity_canvas_api import CanvasWorld, baseline
from material_access_api import MaterialAccessAcceptance
from foundation_agent import WorldClient
from resident_mission import run_mission
from activity_choice import choose_lowest_cost
import resident_entity_canvas as canvas

RUN = ROOT / '.local/iter0025/python' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
DLL = Path(os.environ.get('WORLD_SERVER_DLL', foundation_api.DLL)).resolve()
SOURCE = None
TARGET = 'e926486325c2c4e3e924610139ee26711'
INSTANCE = 'w_15ced6889f624d8da8a3d2129ba26874'
FILES = ['scripts/resident_entity_canvas.py', 'scripts/resident_mission.py', 'scripts/command_preconditions.py',
         'scripts/run_resident.py', 'tests/entity_canvas_mission_api.py',
         'tests/fixtures/entity-canvas-first.json', 'tests/fixtures/entity-canvas-second.json']


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mission(second=False):
    job = json.loads((ROOT / ('tests/fixtures/entity-canvas-' + ('second' if second else 'first') + '.json')).read_text())
    job['goals'][0]['entityCanvas']['entityId'] = TARGET
    return job


class EntityCanvasMissionAcceptance(unittest.TestCase):
    intent = MaterialAccessAcceptance.intent
    post = MaterialAccessAcceptance.post
    send = MaterialAccessAcceptance.send
    walk = MaterialAccessAcceptance.walk
    all_worlds = []

    @classmethod
    def setUpClass(cls):
        global SOURCE, TARGET, INSTANCE
        RUN.mkdir(parents=True, exist_ok=True)
        SOURCE, TARGET = baseline(RUN/'seed', DLL)
        with sqlite3.connect(f'file:{SOURCE / "world.db"}?mode=ro', uri=True) as db:
            INSTANCE = db.execute('SELECT instance_id FROM world_instance').fetchone()[0]
        if not (SOURCE / 'world.db').is_file() or not DLL.is_file():
            raise RuntimeError('Explicit original snapshot and frozen DLL are required')
        cls.source_hashes = {p.name: digest(p) for p in (SOURCE / 'world.db', SOURCE / 'world.db-wal') if p.exists()}
        foundation_api.DLL = DLL

    def setUp(self):
        self.trace, self.traffic, self.reports = [], [], []
        self.worlds = []
        self.world = self.copy('world')
        self.a, self.b = [self.world.client(a) for a in ('a1_alias', 'a2')]
        self.state = self.world.data / 'mission.json'

    def copy(self, suffix):
        world = CanvasWorld(SOURCE, RUN / (self._testMethodName + '-' + suffix), DLL, start=False)
        self.worlds.append(world); self.all_worlds.append(world); self.addCleanup(world.stop)
        world.original = rows(world.data)
        with sqlite3.connect(world.data/'world.db') as db:
            world.initial_wood = dict(db.execute('SELECT actor_id,wood FROM residents'))
        # Session renewal is an offline supported command in the private copy.
        for actor in ('a1_alias', 'a2'):
            output = world.data / ('issued-' + actor + '.json')
            result = subprocess.run(['dotnet', str(DLL), 'issue-session', '--actor', actor, '--ttl-seconds', '600',
                                     '--output', str(output)], cwd=ROOT, env=world.env, capture_output=True, text=True, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr)
            world.access['sessions'][actor]['token'] = json.loads(output.read_text())['token']
        (world.data / 'access.json').write_text(json.dumps(world.access))
        result = subprocess.run(['dotnet', str(DLL), 'adopt-entity-canvas', '--instance', INSTANCE, '--entity', TARGET],
                                cwd=ROOT, env=world.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        world.start()
        observed = world.client('a1_alias').observe()
        self.assertEqual((INSTANCE, 0, 6, 2), (observed['world']['instanceId'], observed['self']['inventory']['wood'],
                                              len(observed['entities']), observed['entityNotes']['totalCount']))
        self.assertTrue(canvas.supported(observed), observed.get('entityCanvas'))
        self.assertEqual((TARGET, [24, 7], 'a2', 3), tuple(observed['entityCanvas']['target'][k] for k in
                                                      ('entityId', 'position', 'ownerActorId', 'embodiedWood')))
        return world

    def tearDown(self):
        for world in self.worlds: world.stop()
        for name, value in (('trace.json', self.trace), ('traffic.json', self.traffic), ('reports.json', self.reports)):
            (self.world.data / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        for world in self.worlds:
            current = rows(world.data)
            for table in ('entities', 'resource_nodes', 'entity_notes', 'entity_note_adoption', 'world_instance'):
                self.assertEqual(world.original[table], current[table], table)
            for table in ('receipts', 'events', 'resource_ledger'):
                self.assertTrue(set(world.original[table]).issubset(current[table]), table)
            with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
                self.assertEqual('ok', db.execute('PRAGMA integrity_check').fetchone()[0])
                self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())
                generated, stock = db.execute('SELECT generated_wood,stock_wood FROM material_source').fetchone()
                total = stock + sum(db.execute(q).fetchone()[0] for q in ('SELECT sum(remaining_wood) FROM resource_nodes',
                    'SELECT sum(wood) FROM residents', 'SELECT coalesce(sum(embodied_wood),0) FROM entities'))
                self.assertEqual(12 + generated, total)
                self.assertEqual(generated, db.execute('SELECT coalesce(sum(quantity),0) FROM material_production').fetchone()[0])
                self.assertEqual(tuple(world.initial_wood[a] for a in ('a1_alias','a2')), tuple(db.execute('SELECT wood FROM residents WHERE actor_id=?', (a,)).fetchone()[0]
                                              for a in ('a1_alias', 'a2')))
                edits = {r[0] for r in db.execute('SELECT command_id FROM entity_canvas_edits')}
                ledger = {r[0] for r in db.execute('SELECT command_id FROM resource_ledger')}
                self.assertFalse(edits & ledger)
        self.assertEqual(self.source_hashes, {SOURCE.joinpath(n).name: digest(SOURCE / n) for n in self.source_hashes})

    def saved(self): return json.loads(self.state.read_text())

    def task(self, job=None, client=None, choose=choose_lowest_cost, **kwargs):
        report = run_mission(client or self.b, job or mission(), self.state, choose, **kwargs)
        self.reports.append(report)
        return report

    def controlled(self, *, actor='a2', before=None, after=None, world=None):
        world = world or self.world; owner = self
        class Controlled(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                owner.traffic.append({'method': method, 'path': path, 'payload': deepcopy(payload)})
                if before: headers = before(method, path, payload, headers)
                response = super().request(method, path, payload, headers)
                return after(method, path, payload, response) if after else response
        return Controlled(world.url, world.access['sessions'][actor]['token'])

    def completed(self, report, job, actor):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['entityCanvasPainted'] and report['facts']['goalReached'] and report['facts']['returned'])
        edit = report['facts']['entityCanvasEdit']; expected = job['goals'][0]['entityCanvas']
        self.assertEqual((actor, INSTANCE, TARGET, expected['expectedCanvasRevision']),
                         (edit['authorActorId'], edit['worldInstanceId'], edit['entityId'], edit['baseRevision']))
        self.assertEqual(canvas.canonical_patch(expected['patch']), edit['patch'])
        self.assertEqual((0, 0, 0), (report['budget']['used']['wood'], report['facts']['woodGathered'], report['facts']['woodTransferred']))
        self.assertTrue(all(s['action']['type'] in ('walk', canvas.ACTION) for s in report['steps']))
        self.assertEqual(1, sum(s['action']['type'] == canvas.ACTION and s['status'] == 'committed' for s in report['steps']))

    def near(self, client=None):
        self.walk(client or self.b, [24, 8])

    def drop_paint(self, *, when='after', world=None, actor='a2'):
        def before(method, path, payload, headers):
            if when == 'before' and method == 'POST' and payload['action']['type'] == canvas.ACTION:
                raise OSError('isolated pre-submit loss')
            return headers
        def after(method, path, payload, response):
            if when == 'after' and method == 'POST' and payload['action']['type'] == canvas.ACTION:
                raise OSError('isolated post-submit response loss')
            return response
        report = self.task(client=self.controlled(actor=actor, world=world, before=before, after=after))
        self.assertEqual('unknown', report['mission']['status'])
        return deepcopy(self.saved()['_state']['pending']['request'])

    def test_01_actual_cli_two_original_round_trips(self):
        first = None
        for actor, second in (('a1_alias', False), ('a2', True)):
            observed = self.world.client(actor).observe()
            job = mission(second)
            self.assertEqual(job['goals'][0]['entityCanvas']['expectedCanvasRevision'], observed['entityCanvas']['revision'])
            if first:
                self.assertEqual(first['commandId'], observed['entityCanvas']['cells'][6]['commandId'])
            spec = self.world.data / (actor + '-spec.json'); spec.write_text(json.dumps(job, ensure_ascii=False))
            output = self.world.data / (actor + '-report.json'); self.state = self.world.data / (actor + '-state.json')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_resident.py'), '--url', self.world.url,
                                     '--access-file', str(self.world.data / 'access.json'), '--actor', actor,
                                     '--spec', str(spec), '--state', str(self.state), '--output', str(output)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=180)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(output.read_text()); self.reports.append(report); self.completed(report, job, actor)
            first = report['facts']['entityCanvasEdit']
            self.assertEqual(self.world.initial_wood[actor], first['inventoryWood'])
            self.assertEqual('fixed-reference', report['decision']['provider']['kind'])
        self.assertEqual(2, self.b.observe()['entityCanvas']['revision'])

    def test_02_original_revision_conflict_is_terminal(self):
        self.near(); self.walk(self.a, [24, 7])
        report = self.task(max_steps=0); self.assertEqual('paused', report['mission']['status'])
        self.send(self.a, canvas.action(mission()['goals'][0]))
        report = self.task()
        self.assertEqual(('blocked', 'command_rejected:CANVAS_REVISION_MISMATCH'),
                         (report['mission']['status'], report['mission']['reason']))
        self.assertFalse(report['facts']['entityCanvasPainted'])
        paint = next(s for s in report['steps'] if s['action']['type'] == canvas.ACTION)
        self.assertEqual(canvas.action(mission()['goals'][0]), paint['action'])
        raw = self.state.read_bytes(); offline = self.world.client('a2')
        offline.request = lambda *_a, **_k: self.fail('terminal conflict made I/O')
        self.assertEqual(report, self.task(client=offline)); self.assertEqual(raw, self.state.read_bytes())

    def test_03_before_and_after_loss_retain_original_request(self):
        for when in ('before', 'after'):
            world = self.world if when == 'before' else self.copy('after')
            client = world.client('a2'); self.near(client); self.state = world.data / 'loss.json'
            original = self.drop_paint(when=when, world=world)
            report = self.task(client=world.client('a2'), choose=lambda _: self.fail('reselected'))
            self.completed(report, mission(), 'a2')
            self.assertEqual(original['commandId'], report['facts']['entityCanvasEdit']['commandId'])
            self.assertEqual(original, self.saved()['_state']['entityCanvasProof']['request'])

    def test_04_old_success_after_own_repaint_keeps_fact_stops_route(self):
        self.near(); original = self.drop_paint()
        repaint = canvas.action(mission()['goals'][0]); repaint['expectedCanvasRevision'] = 1
        repaint['patch'] = [{'x': 1, 'y': 1, 'color': 'blank'}]
        self.send(self.b, repaint)
        report = self.task(choose=lambda _: self.fail('reselected'))
        self.assertTrue(report['facts']['entityCanvasPainted'])
        self.assertEqual(original['commandId'], report['facts']['entityCanvasEdit']['commandId'])
        self.assertEqual(('blocked', 'command_rejected:STALE_ACTOR_STATE'),
                         (report['mission']['status'], report['mission']['reason']))
        self.assertFalse(report['facts']['returned'])
        self.assertEqual(('blank', 'a2'), tuple(report['world']['entityCanvas']['cells'][6][k] for k in ('color', 'authorActorId')))

    def test_05_older_than_recent_fifty_still_confirms_original_edit(self):
        self.near(); self.walk(self.a, [24, 7]); original = self.drop_paint()
        for revision in range(1, 52):
            request = canvas.action(mission()['goals'][0]); request['expectedCanvasRevision'] = revision
            request['patch'] = [{'x': 4, 'y': 4, 'color': 'leaf' if revision % 2 else 'sun'}]
            self.send(self.a, request)
        observed = self.b.observe(); self.assertEqual(50, len(observed['entityCanvas']['recentEdits']))
        self.assertNotIn(original['commandId'], [e['commandId'] for e in observed['entityCanvas']['recentEdits']])
        self.traffic.clear(); report = self.task(client=self.controlled())
        self.completed(report, mission(), 'a2')
        self.assertEqual(original['commandId'], report['facts']['entityCanvasEdit']['commandId'])
        self.assertTrue(any('/canvas/edits/a2/' + original['commandId'] in t['path'] for t in self.traffic))
        self.assertFalse(any(t['method'] == 'POST' and t['payload']['action']['type'] == canvas.ACTION for t in self.traffic))

    def test_06_query_failures_wrong_evidence_preserve_pending(self):
        self.near(); original = self.drop_paint()
        for failure in ('receipt503', 'edit404', 'edit503', 'wrongedit', 'wrongevent', 'oldparse'):
            def after(method, path, payload, response):
                status, body = response
                if failure == 'receipt503' and method == 'GET' and '/commands/' in path:
                    return 503, {'error': {'code': 'UNAVAILABLE'}}
                if '/canvas/edits/' in path:
                    if failure in ('edit404', 'edit503'): return (404 if failure == 'edit404' else 503), {'error': {'code': 'CANVAS_EDIT_NOT_FOUND'}}
                    if failure == 'wrongedit':
                        body = deepcopy(body); body['edit']['patch'][0]['color'] = 'ink'
                if failure == 'wrongevent' and '/events?' in path:
                    body = deepcopy(body); body['events'][0]['commandId'] = 'different'
                if failure == 'oldparse' and method == 'GET' and '/commands/' in path:
                    return 400, {'error': {'code': 'INVALID_REQUEST', 'mutated': False}}
                return status, body
            report = self.task(client=self.controlled(after=after))
            self.assertEqual('unknown', report['mission']['status'])
            self.assertFalse(report['facts']['entityCanvasPainted'])
            self.assertEqual(original, self.saved()['_state']['pending']['request'])
        self.completed(self.task(), mission(), 'a2')

    def test_07_first_failed_observation_and_query_budget_are_durable(self):
        job = mission(); job['budgets']['queries'] = 1
        client = self.controlled(before=lambda *_: (_ for _ in ()).throw(OSError('offline first read')))
        with self.assertRaises(OSError): self.task(job, client)
        self.assertEqual((1, 1), (self.saved()['used']['queries'], len(self.traffic)))
        raw = self.saved(); offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('startup refilled budget')
        from resident_entity_notes import StartupBudget
        with self.assertRaises(StartupBudget): self.task(job, offline)
        self.assertEqual(raw['queries'], self.saved()['queries'])
        self.walk(self.b, [24, 7])
        for count in (1, 2, 3, 4):
            # Separate worlds avoid reusing a different canvas base between budgets.
            world = self.world if count == 1 else self.copy('query' + str(count))
            client = world.client('a2'); self.walk(client, [24, 7])
            self.state = world.data / ('query' + str(count) + '.json'); job = mission(); job['budgets']['queries'] = count
            report = self.task(job, client); self.assertEqual(('budget_exhausted', count),
                (report['mission']['status'], report['budget']['used']['queries']))
            self.assertEqual(count == 4, report['facts']['entityCanvasPainted'])
            original = deepcopy(self.saved()['_state']['pending']); offline = world.client('a2')
            offline.request = lambda *_a, **_k: self.fail('query budget refilled')
            restored = self.task(job, offline)
            self.assertEqual(count, restored['budget']['used']['queries'])
            self.assertEqual(original, self.saved()['_state']['pending'])

    def test_08_permissions_and_damaged_saved_state_zero_io(self):
        for mutate in (lambda j: j.pop('allowEntityCanvas'), lambda j: j.update(allowBuild=True),
                       lambda j: j.update(allowGather=True), lambda j: j.update(allowEntityNotes=True),
                       lambda j: j['goals'][0]['entityCanvas'].update(expectedCanvasRevision=True),
                       lambda j: j['goals'][0]['entityCanvas']['patch'][0].update(x=1.0),
                       lambda j: j['goals'].append(deepcopy(j['goals'][0])), lambda j: j['budgets'].pop('queries')):
            job = mission(); mutate(job)
            with self.assertRaises(ValueError): self.task(job, self.controlled())
        self.assertEqual([], self.traffic)
        self.near(); self.drop_paint(when='before'); original = self.saved()
        mutations = (lambda s: s['mission'].update(allowEntityCanvas=False), lambda s: s['mission'].update(allowBuild=True),
            lambda s: s['mission'].update(origin=[1, 1]), lambda s: s['budget']['used'].update(queries=0),
            lambda s: s['budget']['limits'].update(queries=5000), lambda s: s['_state']['entityCanvasQueries'].pop(),
            lambda s: s['budget']['limits'].update(queries=800.0), lambda s: s['budget']['used'].update(commands=0),
            lambda s: s['_state']['spec']['budgets'].update(queries=800.0),
            lambda s: s['budget']['used'].update(wood=True), lambda s: s['budget']['used'].update(modelCalls=2),
            lambda s: s['budget']['used'].update(seconds=-1), lambda s: s['_state'].pop('entityCanvasBinding'),
            lambda s: s['_state'].update(entityCanvasActorStateVersion=True),
            lambda s: s['_state']['entityCanvasBinding']['adoption'].update(worldInstanceId='w_' + '0' * 32),
            lambda s: s['_state']['pending']['request']['action'].update(expectedCanvasRevision=1),
            lambda s: s['_state']['pending']['request']['action']['patch'][0].update(color='sun'),
            lambda s: s['_state']['pending']['entityCanvasBefore'].update(inventoryWood=(self.world.initial_wood['a2'] + 1) % 13))
        for mutate in mutations:
            damaged = deepcopy(original); mutate(damaged); self.state.write_text(json.dumps(damaged))
            offline = self.world.client('a2'); offline.request = lambda *_a, **_k: self.fail('damaged state made I/O')
            with self.assertRaises(ValueError): self.task(client=offline, choose=lambda _: self.fail('damaged state selected'))
        self.state.write_text(json.dumps(original)); self.completed(self.task(), mission(), 'a2')


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    before = {p: digest(ROOT / p) for p in FILES}; dll_before = digest(DLL)
    suite = (unittest.TestSuite(EntityCanvasMissionAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:]
             else unittest.defaultTestLoader.loadTestsFromTestCase(EntityCanvasMissionAcceptance))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    after = {p: digest(ROOT / p) for p in FILES}
    stopped = all(w.process is None or w.process.poll() is not None for w in EntityCanvasMissionAcceptance.all_worlds)
    report = {'suite': 'entity-canvas-mission-http', 'validationLevel': 'builder-self-check', 'actualModelCalls': 0,
              'passed': result.wasSuccessful() and before == after and stopped and digest(DLL) == dll_before,
              'testsRun': result.testsRun, 'tests': result.records, 'sourceHashesBefore': before, 'sourceHashesAfter': after,
              'sourceStable': before == after, 'allStartedServicesStopped': stopped, 'baseline': str(SOURCE),
              'baselineHashes': getattr(EntityCanvasMissionAcceptance, 'source_hashes', {}), 'dll': str(DLL), 'dllSha256': digest(DLL),
              'dllStable': digest(DLL) == dll_before, 'runtimeMode': 'shared-immutable-input', 'temporaryRuntimeCreated': False,
              'failureDetails': [(str(t), detail) for t, detail in result.errors + result.failures]}
    (RUN / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json', flush=True)
    raise SystemExit(not report['passed'])
