#!/usr/bin/env python3
"""Fixed forestry CLI/recovery on an explicit original-history snapshot.

FORESTRY_BASELINE names the cold v1352/storage13 history; WORLD_SERVER_DLL must
name a frozen candidate. All material comes from actual HTTP operations and
elapsed service time. No SQL grants, state rewrites or copied runtime libraries.
"""
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import workshop_api as api
import continuous_navigation as nav
import resident_forestry as forestry
from foundation_agent import WorldClient, SUPPORTED_CAPABILITIES
from resident_mission import run_mission

RUN = ROOT / '.local/iter0028/python' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
SOURCE = Path(os.environ['FORESTRY_BASELINE']).resolve() if os.environ.get('FORESTRY_BASELINE') else None
DLL = Path(os.environ['WORLD_SERVER_DLL']).resolve() if os.environ.get('WORLD_SERVER_DLL') else None
READY_SOURCE = Path(os.environ['FORESTRY_READY_BASELINE']).resolve() if os.environ.get('FORESTRY_READY_BASELINE') else None
FILES = ['scripts/' + n + '.py' for n in ('resident_forestry', 'resident_mission', 'run_resident', 'foundation_agent',
         'continuous_navigation', 'command_preconditions')] + ['tests/forestry_mission_api.py']


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy_snapshot(source, destination):
    source = Path(source)
    destination = Path(destination)
    destination.mkdir(parents=True, mode=0o700, exist_ok=True)
    staging = destination.parent / (destination.name + '-source-files')
    staging.mkdir(mode=0o700)
    before = {p.name: digest(p) for p in source.glob('world.db*')}
    try:
        # Opening a WAL database even with mode=ro may create SHM/WAL sidecars.
        # Copy cold files first and open only this owned staging directory.
        for name in ('world.db', 'world.db-wal', 'world.db-journal'):
            if (source / name).exists():
                shutil.copy2(source / name, staging / name)
        if before != {p.name: digest(p) for p in source.glob('world.db*')}:
            raise RuntimeError('The cold source changed while copying its files')
        with closing(sqlite3.connect(staging / 'world.db')) as src, closing(sqlite3.connect(destination / 'world.db')) as dst:
            src.backup(dst)
        shutil.copy2(source / 'access.json', destination / 'access.json')
    finally:
        shutil.rmtree(staging)


def snapshot(data):
    # sqlite3.Connection.__exit__ only commits/rolls back. Explicit close keeps
    # no Python connection alive across a server stop, restart or file backup.
    with closing(sqlite3.connect(f'file:{Path(data) / "world.db"}?mode=ro', uri=True)) as db:
        result = {name: db.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall()
                  for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()}
        result['user_version'] = db.execute('PRAGMA user_version').fetchone()
        return result


def spec(instance, action, *, actor='a3', target=None, returns=True, waiting=True):
    return dict(missionId='forestry-' + uuid.uuid4().hex[:12], objective='执行明确的原林业动作，核对原三方证据。',
        goals=[dict(id='fixed', label='明确林业目标', target=target,
                    forestry=dict(worldInstanceId=instance, actorId=actor, action=deepcopy(action), waitForReady=waiting, returnToOrigin=returns))],
        allowBuild=False, **{p: kind == action['type'] for kind, p in forestry.PERMISSIONS.items()},
        budgets=dict(commands=250, queries=1000, **forestry.costs(action), seconds=600, modelCalls=0))


def action(kind, **fields):
    return dict(type=kind, capabilityVersion=1, **fields)


class World(api.World):
    def __init__(self, path, source):
        super().__init__(path, source=None)
        copy_snapshot(source, self.data)
        self.env.pop('WORLD_SCENARIO', None)
        self.access = json.loads((self.data / 'access.json').read_text())

    def request(self, method, path, payload=None, actor='a3', capability=SUPPORTED_CAPABILITIES, **kwargs):
        return super().request(method, path, payload, actor=actor, capability=capability, **kwargs)


class ForestryMissionAcceptance(unittest.TestCase):
    READY_TESTS = {'test_21_original_tree_and_nursery_collision',
                   'test_22_old_harvest_pending_recovers_after_next_generation_planted',
                   'test_23_wood_and_seed_budgets_are_independent',
                   'test_24_growing_without_waiting_and_cancel_after_plant_stop',
                   'test_26_expired_mature_handoff_preserves_tree_and_capacity_stops'}
    @classmethod
    def setUpClass(cls):
        if SOURCE is None or DLL is None or not (SOURCE / 'world.db').is_file() or not DLL.is_file():
            raise RuntimeError('Explicit FORESTRY_BASELINE and frozen WORLD_SERVER_DLL are required')
        api.DLL = DLL
        RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
        cls.origin_hashes = {p.name: digest(p) for p in SOURCE.glob('world.db*')}
        cls.baseline = RUN / 'baseline'
        cls.addClassCleanup(cls.cleanup_baseline)
        copy_snapshot(SOURCE, cls.baseline)
        with closing(sqlite3.connect(f'file:{cls.baseline / "world.db"}?mode=ro', uri=True)) as db:
            version = db.execute('SELECT state_version FROM worlds').fetchone()[0]
            storage = db.execute('PRAGMA user_version').fetchone()[0]
        if (version, storage) != (1352, 13):
            raise RuntimeError(f'The supplied history is not the original v1352/storage13: {(version, storage)}')
        if cls.origin_hashes != {p.name: digest(p) for p in SOURCE.glob('world.db*')}:
            raise RuntimeError('The original source changed during its read-only backup')
        cls.baseline_hash = digest(cls.baseline / 'world.db')
        cls.ready_baseline = READY_SOURCE
        cls.outcomes = []
        save(RUN / 'candidate.json', dict(dll=str(DLL), dllSha256=digest(DLL), originalSource=str(SOURCE),
            originalSourceHashes=cls.origin_hashes, sourceUnchangedDuringBackup=True, isolatedBaselineSha256=cls.baseline_hash,
            codeHashes={p: digest(ROOT / p) for p in FILES}, actualModelCalls=0))

    @classmethod
    def cleanup_baseline(cls):
        if hasattr(cls, 'baseline') and cls.baseline.exists():
            unchanged = digest(cls.baseline / 'world.db') == cls.baseline_hash if hasattr(cls, 'baseline_hash') else None
            shutil.rmtree(cls.baseline)
            save(RUN / 'baseline-cleanup.json', dict(isolatedBaselineDatabaseBytesUnchanged=unchanged, removed=not cls.baseline.exists()))
            if unchanged is False:
                raise AssertionError('A test changed the frozen private source baseline')

    def setUp(self):
        self.directory = RUN / self._testMethodName
        self.directory.mkdir()
        source = self.ready_baseline if self._testMethodName in self.READY_TESTS else self.baseline
        if source is None:
            raise RuntimeError('A real matured baseline is required; run the actual CLI chain first')
        self.world = World(self.directory / 'runtime', source)
        self.reports, self.traffic = [], []
        self.addCleanup(self.dispose)
        self.initial = snapshot(self.world.data)
        with closing(sqlite3.connect(f'file:{self.world.data / "world.db"}?mode=ro', uri=True)) as db:
            self.world.instance = db.execute('SELECT instance_id FROM world_instance').fetchone()[0]
        for actor in ('a1_alias', 'a2', 'a3'):
            issued = self.world.data / ('issued-' + actor + '.json')
            result = subprocess.run(['dotnet', str(DLL), 'issue-session', '--actor', actor, '--ttl-seconds', '1800',
                                     '--output', str(issued)], cwd=ROOT, env=self.world.env, capture_output=True, text=True, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr)
            self.world.access['sessions'][actor]['token'] = json.loads(issued.read_text())['token']
            issued.unlink()
        save(self.world.data / 'access.json', self.world.access)
        adopted = self.world.admin('adopt-forestry')
        self.assertEqual(0, adopted.returncode, adopted.stderr)
        self.world.start()
        self.client = self.new_client()
        observed = self.client.observe()
        save(self.directory / 'initial-observation.json', observed)
        self.assertTrue(forestry.supported(observed), 'Initial forestry schema or geometry is unsupported')
        self.job = spec(self.world.instance, action('reserve_forest'))
        self.state = self.directory / 'state.json'

    def new_client(self, actor='a3'):
        return WorldClient(self.world.env['WORLD_URL'], self.world.access['sessions'][actor]['token'])

    def dispose(self):
        if not hasattr(self, 'world'):
            return
        failure = None
        try:
            if self.world.process is not None and self.world.process.poll() is None:
                final = self.new_client().observe()
                save(self.directory / 'final-observation.json', final)
                self.database_checkpoint('final-before-stop')
            self.world.stop()
            self.database_checkpoint('final-after-stop')
            current = snapshot(self.world.data)
            retained = {table: set(self.initial[table]).issubset(current[table]) for table in
                        ('entities', 'resource_nodes', 'entity_notes', 'entity_note_adoption', 'world_instance',
                         'entity_canvas_adoption', 'entity_canvas_cells', 'entity_canvas_edits', 'workshop_tools',
                         'workshop_chests', 'receipts', 'events', 'resource_ledger') if table in self.initial}
            with closing(sqlite3.connect(f'file:{self.world.data / "world.db"}?mode=ro', uri=True)) as db:
                integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
                foreign_keys = db.execute('PRAGMA foreign_key_check').fetchall()
            cleanup = dict(processExited=self.world.process is None or self.world.process.poll() is not None,
                           originalHistoryRetained=retained, integrity=integrity, foreignKeys=foreign_keys)
            if 'final' in locals():
                cleanup.update(resourceAudit=final.get('resourceAudit'), seedAudit=final.get('seedAudit'))
                self.assertTrue(final.get('resourceAudit', {}).get('conserved'), final.get('resourceAudit'))
                self.assertTrue(final.get('seedAudit', {}).get('conserved'), final.get('seedAudit'))
            self.assertTrue(all(retained.values()), retained)
            self.assertEqual(('ok', []), (integrity, foreign_keys))
        except BaseException as error:
            failure = error
            cleanup = dict(error=repr(error), processExited=self.world.process is None or self.world.process.poll() is not None)
        finally:
            self.world.stop()
            save(self.directory / 'reports.json', self.reports)
            save(self.directory / 'traffic.json', self.traffic)
            save(self.directory / 'setup-requests.json', self.world.trace)
            if (self.world.data / 'server.log').exists():
                shutil.copyfile(self.world.data / 'server.log', self.directory / 'server.log')
            if failure is None:
                shutil.rmtree(self.world.data)
            else:
                cleanup['retainedForImmediateDiagnosis'] = str(self.world.data)
            cleanup['runtimeRemoved'] = not self.world.data.exists()
            save(self.directory / 'audit.json', cleanup)
            self.outcomes.append(dict(test=self._testMethodName, cleanup=cleanup))
        if failure:
            raise failure

    def database_checkpoint(self, phase):
        with closing(sqlite3.connect(f'file:{self.world.data / "world.db"}?mode=ro', uri=True)) as db:
            db.execute('BEGIN')
            entry = dict(phase=phase, integrity=db.execute('PRAGMA integrity_check').fetchall(),
                         foreignKeys=db.execute('PRAGMA foreign_key_check').fetchall(),
                         stateVersion=db.execute('SELECT state_version FROM worlds').fetchone()[0])
        path = self.directory / 'database-checkpoints.json'
        entries = json.loads(path.read_text()) if path.exists() else []
        entries.append(entry); save(path, entries)
        self.assertEqual([('ok',)], entry['integrity'])
        self.assertEqual([], entry['foreignKeys'])

    def task(self, client=None, **kwargs):
        def forbidden(*args, **opts): raise AssertionError('Fixed forestry task called a selector')
        report = run_mission(client or self.client, self.job, self.state, forbidden, **kwargs)
        self.reports.append(report)
        forestry.validate_saved(json.loads(self.state.read_text()), self.job, dict(url=self.client.url, prefix=self.client.prefix))
        return report

    def controlled(self, *, before=None, after=None, actor='a3'):
        owner = self
        class Controlled(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                owner.traffic.append(dict(method=method, path=path, payload=deepcopy(payload)))
                if before: before(method, path, payload)
                result = super().request(method, path, payload, headers)
                return after(method, path, payload, result) if after else result
        return Controlled(self.client.url, self.world.access['sessions'][actor]['token'])

    def complete(self, report):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['forestryCompleted'])
        self.assertEqual(0, report['budget']['used']['modelCalls'])
        if self.job['goals'][0]['forestry']['returnToOrigin']:
            self.assertTrue(report['facts']['returned'])
        return report['facts']['forestryAction']

    def cli(self, operation, *, actor='a3', target=None, returns=True, waiting=True, name=None):
        self.job = spec(self.world.instance, operation, actor=actor, target=target, returns=returns, waiting=waiting)
        name = name or self.job['missionId']
        spec_path, output = self.directory / (name + '-spec.json'), self.directory / (name + '-report.json')
        self.state = self.directory / (name + '-state.json')
        save(spec_path, self.job)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_resident.py'), '--url', self.client.url,
            '--access-file', str(self.world.data / 'access.json'), '--actor', actor, '--spec', str(spec_path),
            '--state', str(self.state), '--output', str(output)], cwd=ROOT, capture_output=True, text=True, timeout=650,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        save(self.directory / (name + '-cli.json'), dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(output.read_text())
        self.reports.append(report)
        forestry.validate_saved(json.loads(self.state.read_text()), self.job, dict(url=self.client.url, prefix=self.client.prefix))
        return self.complete(report)

    def navigate(self, target, actor='a3'):
        client = self.new_client(actor)
        for _ in range(300):
            observed = client.observe()
            position = observed['self']['position']
            if nav.near(position, target):
                return
            route = nav.navigation(observed).route(position, target)
            self.assertIsNotNone(route, (position, target))
            next_point = list(route[0])
            distance = nav.distance(position, next_point)
            step = min(distance, observed['movement']['maxStepDistance'])
            next_point = [a + (b - a) * step / distance for a, b in zip(position, next_point)]
            time.sleep(step / observed['movement']['speed'] + .005)
            _, response = self.world.send(dict(type='walk', to=next_point), actor)
            self.assertFalse(response[1]['result']['blocked'], response[1])
        self.fail('Explicit setup navigation did not finish')

    def wait_reservation(self, reservation_id, actor='a3', timeout=70):
        client = self.new_client(actor)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            observed = client.observe()
            current = next((r for r in observed['forestry']['reservations'] if r['reservationId'] == reservation_id), None)
            self.assertIsNotNone(current, 'Original reservation disappeared')
            if current['status'] != 'queued':
                return current
            time.sleep(.5)
        self.fail('Original reservation did not receive its real allocation')

    def ready_harvest(self, *, returns=False):
        observed = self.client.observe()
        reservation = next(r for r in observed['forestry']['reservations'] if r['actorId'] == 'a3')
        plant = next(p for p in observed['forestry']['plants'] if p['plantId'] == reservation['plantId'])
        tool = observed['forestry']['tools'][0]
        self.job = spec(self.world.instance, action('harvest_tree', plantId=plant['plantId'],
                        reservationId=reservation['reservationId'], toolId=tool['toolId']),
                        target=forestry.PLOTS[plant['plotId']], returns=returns)
        return plant, reservation, tool

    def test_01_actual_cli_two_generations_restart_and_wood_use(self):
        initial = self.client.observe()
        self.assertEqual(2, initial['self']['inventory']['wood'])
        self.assertEqual((0, 0), (initial['forestry']['seeds'], initial['forestry']['nursery']['stockSeeds']))
        bench = next(e for e in initial['entities'] if e['definitionId'] == 'workbench' and e['ownerActorId'] == 'a2')
        tool = self.cli(action('craft_forestry_tool', entityId=bench['entityId'], recipeId='wooden_axe.v1'),
                        target=bench['position'], name='craft-owned-axe')['tool']
        first_reservation = self.cli(action('reserve_forest'), name='reserve-first')['reservation']['reservationId']
        self.cli(action('collect_seed', sourceId='nursery-west', reservationId=first_reservation),
                 target=[7, 6], returns=False, name='collect-first-seed')
        granted = self.wait_reservation(first_reservation)
        first_plot = granted['plotId']
        self.assertEqual('forest-west-north', first_plot)
        first_plant = self.cli(action('plant_tree', plotId=first_plot, reservationId=first_reservation),
                               target=forestry.PLOTS[first_plot], returns=False, name='plant-first')['plant']
        before_restart = self.client.observe()
        self.assertEqual('growing', next(p for p in before_restart['forestry']['plants'] if p['plantId'] == first_plant['plantId'])['state'])
        self.database_checkpoint('growing-before-stop')
        self.world.stop()
        self.database_checkpoint('growing-after-stop')
        with closing(sqlite3.connect(f'file:{self.world.data / "world.db"}?mode=ro', uri=True)) as db:
            stopped_service = db.execute('SELECT service_ms FROM material_source').fetchone()[0]
        stopped_at = time.monotonic()
        time.sleep(1.25)
        with closing(sqlite3.connect(f'file:{self.world.data / "world.db"}?mode=ro', uri=True)) as db:
            self.assertEqual(stopped_service, db.execute('SELECT service_ms FROM material_source').fetchone()[0])
        offline_ms = (time.monotonic() - stopped_at) * 1000
        self.world.start()
        self.client = self.new_client()
        after_restart = self.client.observe()
        service_delta = after_restart['forestry']['nursery']['serviceMs'] - stopped_service
        self.assertLess(service_delta, offline_ms, 'Restart incorrectly accumulated the stopped interval')
        save(self.directory / 'growing-restart.json', dict(plantId=first_plant['plantId'], stoppedServiceMs=stopped_service,
             offlineElapsedMs=offline_ms, serviceDeltaAfterRestart=service_delta, originalHistorySameDatabase=True))
        growth = []
        deadline = time.monotonic() + 135
        while time.monotonic() < deadline:
            observed = self.client.observe()
            plant = next(p for p in observed['forestry']['plants'] if p['plantId'] == first_plant['plantId'])
            growth.append(dict(serviceMs=observed['forestry']['nursery']['serviceMs'], state=plant['state'], standingWood=plant['standingWood']))
            if plant['state'] == 'mature':
                break
            time.sleep(1)
        else:
            self.fail('The original first plant did not mature on actual service time')
        save(self.directory / 'first-growth-observations.json', growth)
        self.database_checkpoint('mature-before-stop')
        self.world.stop()
        self.database_checkpoint('mature-after-stop-before-copy')
        cache = ROOT / '.local/iter0028' / ('python-ready-' + RUN.name)
        copy_snapshot(self.world.data, cache)
        save(cache / 'provenance.json', dict(originalBaselineSha256=self.baseline_hash, producingRun=str(RUN),
             producingTest=self._testMethodName, actualCommands=True, noSqlMaterialOrLifecycleWrites=True,
             plant=plant, reservationId=first_reservation, tool=tool, serviceMs=observed['forestry']['nursery']['serviceMs'],
             databaseSha256=digest(cache / 'world.db'), dllSha256=digest(DLL), pendingCleanupAfterReuse=True))
        type(self).ready_baseline = cache
        save(self.directory / 'ready-baseline.json', dict(path=str(cache), sha256=digest(cache / 'world.db')))
        self.database_checkpoint('mature-after-copy-before-restart')
        self.world.start()
        self.client = self.new_client()
        first_harvest = self.cli(action('harvest_tree', plantId=first_plant['plantId'], reservationId=first_reservation,
                              toolId=tool['toolId']), target=forestry.PLOTS[first_plot], returns=False, name='harvest-first')
        first_state = json.loads(self.state.read_text())
        first_intent = next(s['request'] for s in first_state['steps'] if s['action']['type'] == 'harvest_tree')
        first_original_receipt = self.world.request('GET', api.PREFIX + '/commands/' + first_intent['commandId'], actor='a3')
        second_reservation = self.cli(action('reserve_forest'), name='reserve-second')['reservation']['reservationId']
        second_grant = self.wait_reservation(second_reservation)
        self.assertEqual(0, second_grant['reservedSeed'], 'The second generation must use the first harvest seed')
        self.assertEqual(first_plot, second_grant['plotId'])
        second_plant = self.cli(action('plant_tree', plotId=second_grant['plotId'], reservationId=second_reservation),
                               target=forestry.PLOTS[second_grant['plotId']], returns=False, name='plant-second')['plant']
        self.assertNotEqual(first_plant['plantId'], second_plant['plantId'])
        before_replay = self.client.observe()
        replay = self.world.request('POST', api.PREFIX + '/commands', first_intent, actor='a3')
        self.assertEqual((200, first_original_receipt[2]), (replay[0], replay[2]))
        after_replay = self.client.observe()
        self.assertEqual(before_replay['self'], after_replay['self'])
        self.assertEqual(before_replay['forestry']['seeds'], after_replay['forestry']['seeds'])
        self.assertEqual('growing', next(p for p in after_replay['forestry']['plants'] if p['plantId'] == second_plant['plantId'])['state'])
        save(self.directory / 'old-generation-replay.json', dict(originalRequest=first_intent, originalReceipt=first_original_receipt[1],
             replayReceipt=replay[1], sameOriginalBytes=True, secondPlantId=second_plant['plantId'],
             secondPlantUnaffected=True, inventoryUnaffected=True))
        second_harvest = self.cli(action('harvest_tree', plantId=second_plant['plantId'], reservationId=second_reservation,
                               toolId=tool['toolId']), target=forestry.PLOTS[second_grant['plotId']], name='harvest-second-waiting')
        self.assertEqual((6, 1), (second_harvest['inventoryWood'], second_harvest['seeds']))
        self.navigate([25, 5.7])
        construction, result = self.world.send(dict(type='build', recipeId='platform.v1', at=[25, 4]), 'a3')
        final = self.client.observe()
        self.assertEqual((3, 1), (final['self']['inventory']['wood'], final['forestry']['seeds']))
        self.assertTrue(any(e['ownerActorId'] == 'a3' and e['position'] == [25, 4] for e in final['entities']))
        self.assertEqual(6, final['resourceAudit']['forestGeneratedWood'])
        self.assertEqual(0, final['resourceAudit']['standingForestWood'])
        save(self.directory / 'chain-summary.json', dict(instance=self.world.instance, initialInventoryWood=2,
             recipeWood=2, harvestedWood=6, collectedSeeds=1, plantedSeeds=2, harvestGeneratedSeeds=2,
             finalInventoryWood=3, finalOwnedSeeds=1, firstPlant=first_plant, secondPlant=second_plant,
             originalAxe=tool, firstHarvest=first_harvest, secondHarvest=second_harvest,
             actualWoodUseCommand=construction, actualWoodUseReceipt=result[1], resourceAudit=final['resourceAudit'],
             seedAudit=final['seedAudit'], actualModelCalls=0,
             scope='Actual fixed CLI tasks and real service time on an isolated branch of the original v1352 history'))

    def test_02_reserve_original_queue_fact_and_cancel(self):
        first = self.cli(action('reserve_forest'), name='reserve-original')
        self.assertEqual('queued', first['reservation']['status'])
        self.assertIsNone(first['plant'])
        rid = first['reservation']['reservationId']
        self.cli(action('cancel_forest_reservation', reservationId=rid), name='cancel-original')
        self.assertEqual(0, self.client.observe()['forestry']['seeds'])


    def test_03_dropped_success_restores_original_without_post(self):
        def lost(method, path, payload, result):
            if method == 'POST' and payload['action']['type'] == 'reserve_forest': raise OSError('lost original response')
            return result
        report = self.task(self.controlled(after=lost))
        self.assertEqual('unknown', report['mission']['status'])
        pending = json.loads(self.state.read_text())['_state']['pending']['request']
        self.world.restart(); self.client = self.new_client(); self.traffic.clear()
        self.complete(self.task(self.controlled()))
        self.assertFalse(any(t['method'] == 'POST' and t['payload']['action']['type'] == 'reserve_forest' for t in self.traffic))
        self.assertEqual(pending['commandId'], self.reports[-1]['facts']['forestryAction']['commandId'])

    def test_04_missing_proof_query_budget_preserves_pending(self):
        self.job['budgets']['queries'] = 3
        report = self.task()
        self.assertEqual(('budget_exhausted', 'queries_pending_retained'), (report['mission']['status'], report['mission']['reason']))
        original = json.loads(self.state.read_text())['_state']['pending']
        self.assertIsNotNone(original)
        self.assertFalse(report['facts']['forestryCompleted'])
        self.traffic.clear(); self.task(self.controlled())
        self.assertEqual([], self.traffic)
        self.assertEqual(original, json.loads(self.state.read_text())['_state']['pending'])

    def test_05_unsubmitted_pending_404_resends_exact_original(self):
        def lost(method, path, payload):
            if method == 'POST' and payload['action']['type'] == 'reserve_forest': raise OSError('pre-submit disconnect')
        self.task(self.controlled(before=lost))
        pending = json.loads(self.state.read_text())['_state']['pending']['request']; self.traffic.clear()
        self.complete(self.task(self.controlled()))
        sent = [t['payload'] for t in self.traffic if t['method'] == 'POST' and t['payload']['action']['type'] == 'reserve_forest']
        self.assertEqual([pending], sent)

    def test_06_partial_three_records_keep_pending(self):
        def hidden(method, path, payload, result):
            if '/forestry/actions/' in path: return 503, {'error': {'code': 'TEMPORARY'}}
            return result
        report = self.task(self.controlled(after=hidden))
        self.assertEqual('unknown', report['mission']['status'])
        self.assertFalse(report['facts']['forestryCompleted'])
        self.assertIsNotNone(json.loads(self.state.read_text())['_state']['pending'])
        self.complete(self.task())

    def test_07_query_failure_cost_survives_restart(self):
        self.job['budgets']['queries'] = 2
        def fail(method, path, payload):
            if path.endswith('/observation'): raise OSError('lost observation')
        with self.assertRaises(OSError): self.task(self.controlled(before=fail))
        self.assertEqual(1, json.loads(self.state.read_text())['used']['queries'])
        with self.assertRaises(OSError): self.task(self.controlled(before=fail))
        before = len(self.traffic)
        with self.assertRaises(forestry.QueryBudget): self.task(self.controlled(before=fail))
        self.assertEqual(before, len(self.traffic))

    def test_08_permissions_and_forged_journal_rejected_before_io(self):
        def no_io(*args): raise AssertionError('Malformed authority reached transport')
        for field in forestry.PERMISSIONS.values():
            damaged = deepcopy(self.job); damaged[field] = not damaged[field]
            with self.assertRaises(ValueError): run_mission(self.controlled(before=no_io), damaged, self.state, no_io)
        self.task(max_steps=0); original = self.state.read_bytes()
        for mutate in (lambda s: s['budget']['used'].update(queries=0),
                       lambda s: s['mission'].update(allowCraftForestryTool=True),
                       lambda s: s['_state']['binding'].update(instanceId='w_'+'0'*32),
                       lambda s: s['facts'].update(forestryCompleted=True),
                       lambda s: s['_state'].update(confirmedInventoryWood=12)):
            damaged = json.loads(original); mutate(damaged); save(self.state, damaged)
            with self.assertRaises(ValueError): self.task(self.controlled(before=no_io))
        self.state.write_bytes(original)

    def test_09_changed_actor_aba_original_state_rejects(self):
        self.task(max_steps=0)
        original = self.client.observe()['self']['position']
        self.navigate([25, 21.4]); self.navigate(original)
        result = self.task()
        self.assertEqual('blocked', result['mission']['status'])
        self.assertEqual('command_rejected:STALE_ACTOR_STATE', result['mission']['reason'])
        self.assertFalse(result['facts']['forestryCompleted'])

    def test_10_unauthorized_and_server_errors_preserve_exact_pending(self):
        def drop(method, path, payload):
            if method == 'POST': raise OSError('pre-send disconnect')
        report = self.task(self.controlled(before=drop))
        original = json.loads(self.state.read_text())['_state']['pending']
        self.assertEqual('unknown', report['mission']['status'])
        for status in (401, 500):
            def refusal(method, path, payload, result):
                if '/commands/' in path: return status, {'error': {'code': 'UNAVAILABLE'}}
                return result
            self.traffic.clear()
            report = self.task(self.controlled(after=refusal))
            self.assertEqual('unknown', report['mission']['status'])
            self.assertEqual(original, json.loads(self.state.read_text())['_state']['pending'])
            self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.complete(self.task())

    def test_11_issued_success_then_altered_detail_stays_unknown(self):
        def changed(method, path, payload, result):
            if '/forestry/actions/' in path and result[0] == 200:
                result[1]['forestryAction']['inventoryWood'] += 1
            return result
        report = self.task(self.controlled(after=changed))
        self.assertEqual('unknown', report['mission']['status'])
        self.assertFalse(report['facts']['forestryCompleted'])
        self.assertIsNotNone(json.loads(self.state.read_text())['_state']['pending'])
        self.complete(self.task())

    def test_12_expired_time_does_not_resend_missing_pending(self):
        self.job['budgets']['seconds'] = 1
        def missing(method, path, payload):
            if method == 'POST': raise OSError('not submitted')
        self.task(self.controlled(before=missing))
        original = json.loads(self.state.read_text())['_state']['pending']
        time.sleep(1.05); self.traffic.clear()
        result = self.task(self.controlled())
        self.assertEqual('budget_exhausted', result['mission']['status'])
        self.assertEqual(original, json.loads(self.state.read_text())['_state']['pending'])
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))

    def test_13_expired_time_can_verify_already_committed_original(self):
        self.job['budgets']['seconds'] = 1
        def lost(method, path, payload, result):
            if method == 'POST': raise OSError('committed response lost')
            return result
        result = self.task(self.controlled(after=lost))
        self.assertEqual('unknown', result['mission']['status'])
        time.sleep(1.05); self.traffic.clear()
        self.complete(self.task(self.controlled()))
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))

    def test_14_newer_actual_position_does_not_claim_original_return(self):
        self.task(max_steps=0)
        self.navigate([25, 21.4])
        result = self.task()
        self.assertEqual(('blocked', 'forestry_actor_changed_outside_task'), (result['mission']['status'], result['mission']['reason']))
        self.assertFalse(result['facts']['returned'])
        self.assertEqual([25, 21.4], result['world']['observedSelf']['position'])
        self.traffic.clear(); self.task(self.controlled())
        self.assertEqual([], self.traffic)

    def test_15_delayed_observation_crosses_deadline_no_fresh_post(self):
        """Fault fixture: delay a real HTTP observation past the one-second limit."""
        self.job['budgets']['seconds'] = 1
        observations = []
        def delayed(method, path, payload, result):
            if path.endswith('/observation'):
                observations.append(path)
                if len(observations) == 2: time.sleep(1.05)
            return result
        result = self.task(self.controlled(after=delayed))
        self.assertEqual('budget_exhausted', result['mission']['status'])
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.assertIsNone(json.loads(self.state.read_text())['_state']['pending'])
        self.assertFalse(result['facts']['forestryCompleted'])

    def test_16_delayed_capability_observation_does_not_resend_pending(self):
        """Fault fixture: capability read after explicit 404 crosses the deadline."""
        self.job['budgets']['seconds'] = 1
        def missing(method, path, payload):
            if method == 'POST': raise OSError('pre-send loss')
        self.task(self.controlled(before=missing))
        original = json.loads(self.state.read_text())['_state']['pending']
        self.traffic.clear()
        def delayed(method, path, payload, result):
            if path.endswith('/observation'): time.sleep(1.05)
            return result
        result = self.task(self.controlled(after=delayed))
        self.assertEqual('budget_exhausted', result['mission']['status'])
        self.assertEqual(original, json.loads(self.state.read_text())['_state']['pending'])
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))

    def test_17_crash_after_rejection_settlement_restores_terminal(self):
        """Fault fixture: stop immediately after the rejected receipt is persisted."""
        import resident_mission
        self.task(max_steps=0)
        self.navigate([25, 21.4]); self.navigate([25, 22])
        original_save = resident_mission._save
        class SimulatedCrash(BaseException): pass
        def crash_after_save(path, value):
            original_save(path, value)
            if value.get('steps') and value['steps'][-1]['status'] == 'rejected' and value['_state']['pending'] is None:
                raise SimulatedCrash('durable receipt saved; process cut before next instruction')
        with patch.object(resident_mission, '_save', crash_after_save):
            with self.assertRaises(SimulatedCrash): self.task()
        self.traffic.clear()
        result = self.task(self.controlled())
        self.assertEqual(('blocked', 'command_rejected:STALE_ACTOR_STATE'), (result['mission']['status'], result['mission']['reason']))
        self.assertEqual([], self.traffic)

    def test_18_last_fresh_save_crosses_deadline_preserves_pending(self):
        """Fault fixture: the final durable save returns after the time limit."""
        import resident_mission
        self.job['budgets']['seconds'] = 1
        original_save, pending_writes, delays = resident_mission._save, [], []
        def delayed_save(path, value):
            original_save(path, value)
            pending = value.get('_state', {}).get('pending')
            if pending is not None:
                pending_writes.append(pending['request']['commandId'])
                if len(pending_writes) == 2:
                    delay = dict(path='fresh-final-save', cachedSeconds=value['budget']['used']['seconds'],
                                 elapsedBefore=time.time()-value['_state']['startedEpoch'], pending=deepcopy(pending))
                    time.sleep(1.05)
                    delay['elapsedAfter'] = time.time()-value['_state']['startedEpoch']; delays.append(delay)
        with patch.object(resident_mission, '_save', delayed_save):
            result = self.task(self.controlled())
        save(self.directory/'write-delay-fixture.json', delays)
        self.assertEqual(1, len(delays))
        self.assertLess(delays[0]['cachedSeconds'], 1); self.assertGreaterEqual(delays[0]['elapsedAfter'], 1)
        self.assertEqual('budget_exhausted', result['mission']['status'])
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.assertEqual(delays[0]['pending'], json.loads(self.state.read_text())['_state']['pending'])

    def test_19_last_resend_save_crosses_deadline_preserves_original(self):
        """Fault fixture: final save after 404 and capability read crosses time."""
        import resident_mission
        self.job['budgets']['seconds'] = 1
        def missing(method, path, payload):
            if method == 'POST': raise OSError('pre-send loss')
        self.task(self.controlled(before=missing))
        original = json.loads(self.state.read_text())['_state']['pending']; self.traffic.clear()
        original_save, observation_writes, delays = resident_mission._save, [], []
        def delayed_save(path, value):
            original_save(path, value)
            pending = value.get('_state', {}).get('pending')
            if pending is not None and value['_state']['queries'][-1]['kind'] == 'observation':
                observation_writes.append(pending['request']['commandId'])
                if len(observation_writes) == 3:
                    delay = dict(path='404-capability-final-save', cachedSeconds=value['budget']['used']['seconds'],
                                 elapsedBefore=time.time()-value['_state']['startedEpoch'], pending=deepcopy(pending))
                    time.sleep(1.05)
                    delay['elapsedAfter'] = time.time()-value['_state']['startedEpoch']; delays.append(delay)
        with patch.object(resident_mission, '_save', delayed_save):
            result = self.task(self.controlled())
        save(self.directory/'write-delay-fixture.json', delays)
        self.assertEqual(1, len(delays))
        self.assertLess(delays[0]['cachedSeconds'], 1); self.assertGreaterEqual(delays[0]['elapsedAfter'], 1)
        self.assertEqual('budget_exhausted', result['mission']['status'])
        self.assertEqual(original, json.loads(self.state.read_text())['_state']['pending'])
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))

    def test_20_unknown_capability_geometry_and_wrong_instance_stop(self):
        for name, mutate in (
                ('version', lambda o: o['forestry'].update(version=2)),
                ('geometry', lambda o: o['terrain']['obstacles'].pop()),
                ('integer', lambda o: o['forestry'].update(seeds=2**53)),
                ('boolean', lambda o: o['forestry']['policy'].update(groupLimit=True))):
            self.state = self.directory / (name + '.json')
            def changed(method, path, payload, result):
                if path.endswith('/observation') and result[0] == 200: mutate(result[1])
                return result
            with self.assertRaises(ValueError): self.task(self.controlled(after=changed))
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.state = self.directory / 'wrong-instance.json'
        self.job['goals'][0]['forestry']['worldInstanceId'] = 'w_' + '0' * 32
        with self.assertRaises((ValueError, RuntimeError)): self.task(self.controlled())
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))

    def test_21_original_tree_and_nursery_collision(self):
        observed = self.client.observe()
        plant = observed['forestry']['plants'][0]
        center = forestry.PLOTS[plant['plotId']]
        geometry = nav.navigation(observed)
        self.assertFalse(geometry.walkable([7, 6]))
        self.assertFalse(geometry.walkable(center))
        start = [center[0], center[1] - 1.5]
        self.assertFalse(geometry.clear(start, center))
        ray = nav.navigation(observed, interaction_obstacle=plant['plantId'])
        self.assertTrue(ray.clear(start, center))
        self.assertFalse(ray.clear([7, 4.5], [7, 6]))
        self.assertFalse(geometry.clear([center[0] - 1.5, center[1]], [center[0] + 1.5, center[1]]))
        with self.assertRaises(ValueError): nav.navigation(observed, interaction_obstacle='other-generation')
        damaged = deepcopy(observed)
        damaged['forestry']['version'] = 2
        with self.assertRaises(ValueError): nav.navigation(damaged)
        save(self.directory / 'geometry-summary.json', dict(plantId=plant['plantId'], originalCenter=center,
             normalWalkBlocksTreeAndNursery=True, interactionRayOmitsOnlyItsOriginalTree=True))

    def test_22_old_harvest_pending_recovers_after_next_generation_planted(self):
        plant, reservation, tool = self.ready_harvest()
        def lost(method, path, payload, result):
            if method == 'POST' and payload['action']['type'] == 'harvest_tree':
                raise OSError('original harvest committed; response lost')
            return result
        report = self.task(self.controlled(after=lost))
        self.assertEqual('unknown', report['mission']['status'])
        pending = json.loads(self.state.read_text())['_state']['pending']
        _, queued = self.world.send(action('reserve_forest'), 'a3')
        rid = queued[1]['result']['forestryAction']['reservation']['reservationId']
        granted = self.wait_reservation(rid)
        self.assertEqual(0, granted['reservedSeed'])
        _, planted = self.world.send(action('plant_tree', plotId=granted['plotId'], reservationId=rid), 'a3')
        next_plant = planted[1]['result']['forestryAction']['plant']
        self.assertNotEqual(plant['plantId'], next_plant['plantId'])
        before = self.client.observe()
        self.world.restart(); self.client = self.new_client(); self.traffic.clear()
        original = self.complete(self.task(self.controlled()))
        after = self.client.observe()
        self.assertEqual(pending['request']['commandId'], original['commandId'])
        self.assertEqual(plant['plantId'], original['plant']['plantId'])
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.assertEqual(before['self'], after['self'])
        self.assertEqual(before['forestry']['seeds'], after['forestry']['seeds'])
        self.assertEqual('growing', next(p for p in after['forestry']['plants'] if p['plantId'] == next_plant['plantId'])['state'])
        save(self.directory / 'generation-recovery.json', dict(originalPending=pending, originalResult=original,
             nextPlant=next_plant, nextGenerationUntouched=True, noRecoveryPost=True))

    def test_23_wood_and_seed_budgets_are_independent(self):
        self.ready_harvest()
        original = deepcopy(self.job)
        for key, limit in (('woodHarvested', 2), ('seedsHarvested', 0)):
            self.job = deepcopy(original); self.job['missionId'] += '-' + key
            self.job['budgets'][key] = limit
            self.state = self.directory / (key + '.json'); self.traffic.clear()
            report = self.task(self.controlled())
            self.assertEqual(('budget_exhausted', key), (report['mission']['status'], report['mission']['reason']))
            self.assertFalse(report['facts']['forestryCompleted'])
            self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.job = deepcopy(original); self.state = self.directory / 'actual-original-harvest.json'
        self.complete(self.task())

    def test_24_growing_without_waiting_and_cancel_after_plant_stop(self):
        plant, reservation, tool = self.ready_harvest()
        self.complete(self.task())
        _, queued = self.world.send(action('reserve_forest'), 'a3')
        rid = queued[1]['result']['forestryAction']['reservation']['reservationId']
        granted = self.wait_reservation(rid)
        _, planted = self.world.send(action('plant_tree', plotId=granted['plotId'], reservationId=rid), 'a3')
        next_plant = planted[1]['result']['forestryAction']['plant']
        operations = [
            (action('harvest_tree', plantId=next_plant['plantId'], reservationId=rid, toolId=tool['toolId']),
             forestry.PLOTS[granted['plotId']], 'forestry_wait_not_authorized'),
            (action('cancel_forest_reservation', reservationId=rid), None, 'forestry_original_reservation_not_cancellable')]
        for index, (operation, target, reason) in enumerate(operations):
            self.job = spec(self.world.instance, operation, target=target, returns=False, waiting=False)
            self.state = self.directory / ('stopped-' + str(index) + '.json'); self.traffic.clear()
            report = self.task(self.controlled())
            self.assertEqual(('blocked', reason), (report['mission']['status'], report['mission']['reason']))
            self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.assertEqual('growing', self.client.observe()['forestry']['plants'][0]['state'])

    def test_25_issued_original_with_wrong_instance_header_stays_pending(self):
        owner = self
        class WrongHeader(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                owner.traffic.append(dict(method=method, path=path, payload=deepcopy(payload)))
                result = super().request(method, path, payload, headers)
                if '/forestry/actions/' in path:
                    inner.response_instance_id = 'w_' + '0' * 32
                return result
        report = self.task(WrongHeader(self.client.url, self.world.access['sessions']['a3']['token']))
        self.assertEqual('unknown', report['mission']['status'])
        pending = json.loads(self.state.read_text())['_state']['pending']
        self.assertFalse(report['facts']['forestryCompleted'])
        self.traffic.clear(); original = self.complete(self.task(self.controlled()))
        self.assertEqual(pending['request']['commandId'], original['commandId'])
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))

    def test_26_expired_mature_handoff_preserves_tree_and_capacity_stops(self):
        observed = self.new_client('a2').observe()
        self.assertEqual(12, observed['self']['inventory']['wood'])
        original = self.client.observe()['forestry']['plants'][0]
        bench = next(e for e in observed['entities'] if e['definitionId'] == 'workbench' and e['ownerActorId'] == 'a2')
        tool = self.cli(action('craft_forestry_tool', entityId=bench['entityId'], recipeId='wooden_axe.v1'),
                        actor='a2', target=bench['position'], returns=False, name='later-owned-axe')['tool']
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            current = self.client.observe()
            if not any(r['plantId'] == original['plantId'] for r in current['forestry']['reservations']):
                break
            time.sleep(.5)
        else:
            self.fail('Original priority lease did not expire on actual service time')
        queued = self.cli(action('reserve_forest'), actor='a2', returns=False, name='later-original-queue')['reservation']
        granted = self.wait_reservation(queued['reservationId'], actor='a2', timeout=75)
        self.assertEqual(('harvesting', original['plantId'], 0), (granted['status'], granted['plantId'], granted['reservedSeed']))
        self.client = self.new_client('a2')
        self.job = spec(self.world.instance, action('harvest_tree', plantId=original['plantId'],
                        reservationId=granted['reservationId'], toolId=tool['toolId']), actor='a2',
                        target=forestry.PLOTS[original['plotId']], returns=False)
        self.state = self.directory / 'capacity-stop.json'; self.traffic.clear()
        report = self.task(self.controlled(actor='a2'))
        self.assertEqual(('blocked', 'forestry_harvest_inventory_capacity'), (report['mission']['status'], report['mission']['reason']))
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        final = self.client.observe()
        self.assertEqual((10, 0), (final['self']['inventory']['wood'], final['forestry']['seeds']))
        self.assertEqual(original, final['forestry']['plants'][0])
        save(self.directory / 'handoff-capacity.json', dict(originalPlant=original, originalQueue=queued,
             assignedSameMaturePlant=granted, reservedNoSeed=True, capacityStopWithoutPost=True,
             inventoryWood=10, seeds=0, actualServiceTime=True))


if __name__ == '__main__':
    started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:], module=sys.modules[__name__]) if len(sys.argv) > 1 else unittest.defaultTestLoader.loadTestsFromTestCase(ForestryMissionAcceptance)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    RUN.mkdir(parents=True, exist_ok=True)
    save(RUN / 'summary.json', dict(testsRun=result.testsRun, failures=[str(x) for x in result.failures], errors=[str(x) for x in result.errors],
        success=result.wasSuccessful(), elapsedSeconds=time.monotonic() - started,
        outcomes=ForestryMissionAcceptance.outcomes if hasattr(ForestryMissionAcceptance, 'outcomes') else [],
        sourceCodeHashes={p: digest(ROOT / p) for p in FILES}, actualModelCalls=0))
    print('FORESTRY_EVIDENCE=' + str(RUN), flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
