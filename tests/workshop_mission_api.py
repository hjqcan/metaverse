#!/usr/bin/env python3
"""Actual fixed workshop CLI and recovery on a private copy of original history.

WORKSHOP_BASELINE and WORLD_SERVER_DLL must explicitly name a stopped original
snapshot and frozen candidate. Setup never grants wood or changes positions in
SQL. The source stays read-only; owned databases/tokens are removed after checks.
"""
from copy import deepcopy
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
sys.path.insert(0, str(ROOT/'scripts'))
import workshop_api as api
from foundation_agent import WorldClient
from resident_mission import run_mission
import resident_workshop as workshop
import continuous_navigation as nav

RUN = ROOT/'.local/iter0027/python'/ (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
SOURCE = Path(os.environ['WORKSHOP_BASELINE']).resolve() if os.environ.get('WORKSHOP_BASELINE') else None
DLL = Path(os.environ['WORLD_SERVER_DLL']).resolve() if os.environ.get('WORLD_SERVER_DLL') else None
FILES = ['scripts/'+n+'.py' for n in ('resident_workshop', 'resident_mission', 'run_resident', 'foundation_agent',
         'continuous_navigation', 'command_preconditions', 'resident_construction')]+['tests/workshop_mission_api.py']


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spec(instance, action, *, actor='a2', target=None, returns=True):
    return dict(missionId='workshop-'+uuid.uuid4().hex[:12], objective='执行明确指定的工坊动作并核对原三方证据。',
        goals=[dict(id='fixed', label='明确工坊目标', target=target or action.get('at'),
                    workshop=dict(worldInstanceId=instance, actorId=actor, action=deepcopy(action), returnToOrigin=returns))],
        allowBuild=False, **{p: p == workshop.PERMISSIONS[action['type']] for p in workshop.PERMISSIONS.values()},
        budgets=dict(commands=250, queries=1000, wood=workshop.action_cost(action), woodMoved=workshop.movement_cost(action),
                     seconds=600, modelCalls=0))


class WorkshopMissionAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SOURCE is None or DLL is None or not (SOURCE/'world.db').is_file() or not DLL.is_file():
            raise RuntimeError('Explicit WORKSHOP_BASELINE and WORLD_SERVER_DLL are required')
        api.DLL = DLL
        RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
        cls.original_hashes = {p.name: digest(p) for p in SOURCE.glob('world.db*')}
        cls.code_hashes = {p: digest(ROOT/p) for p in FILES}
        cls.outcomes = []
        save(RUN/'candidate.json', dict(dll=str(DLL), dllSha256=digest(DLL), source=str(SOURCE),
                                       sourceHashes=cls.original_hashes, codeHashes=cls.code_hashes, actualModelCalls=0))

    def setUp(self):
        self.directory = RUN/self._testMethodName
        self.directory.mkdir()
        self.world = api.World(self.directory/'runtime', SOURCE)
        self.addCleanup(self.dispose)
        self.initial = api.snapshot(self.world.data)
        with sqlite3.connect(f'file:{self.world.data/"world.db"}?mode=ro', uri=True) as db:
            self.world.instance = db.execute('SELECT instance_id FROM world_instance').fetchone()[0]
            self.start_wood = dict(db.execute('SELECT actor_id,wood FROM residents'))
        for actor in ('a1_alias', 'a2', 'a3'):
            output = self.world.data/('issued-'+actor+'.json')
            issue = subprocess.run(['dotnet', str(DLL), 'issue-session', '--actor', actor, '--ttl-seconds', '1800',
                                    '--output', str(output)], cwd=ROOT, env=self.world.env, capture_output=True, text=True, timeout=15)
            self.assertEqual(0, issue.returncode, issue.stderr)
            self.world.access['sessions'][actor]['token'] = json.loads(output.read_text())['token']
            output.unlink()
        save(self.world.data/'access.json', self.world.access)
        adopted = self.world.admin('adopt-workshop')
        self.assertEqual(0, adopted.returncode, adopted.stderr)
        self.world.start()
        self.client = self.new_client()
        self.job = spec(self.world.instance, api.build())
        self.state = self.directory/'state.json'
        self.reports, self.traffic = [], []
        self.assertTrue(workshop.supported(self.client.observe()))

    def new_client(self, actor='a2'):
        return WorldClient(self.world.env['WORLD_URL'], self.world.access['sessions'][actor]['token'])

    def dispose(self):
        self.world.stop()
        if hasattr(self, 'reports'):
            save(self.directory/'reports.json', self.reports)
            save(self.directory/'traffic.json', self.traffic)
        save(self.directory/'setup-requests.json', self.world.trace)
        current = api.snapshot(self.world.data)
        retained = {}
        for table in ('entities', 'resource_nodes', 'entity_notes', 'entity_note_adoption', 'world_instance',
                      'entity_canvas_adoption', 'entity_canvas_cells', 'entity_canvas_edits', 'receipts', 'events', 'resource_ledger'):
            if table in self.initial:
                retained[table] = set(self.initial[table]).issubset(current[table])
        with sqlite3.connect(f'file:{self.world.data/"world.db"}?mode=ro', uri=True) as db:
            generated, stock = db.execute('SELECT generated_wood,stock_wood FROM material_source').fetchone()
            audit = {}
            for name, query in {
                'natural': 'SELECT coalesce(sum(remaining_wood),0) FROM resource_nodes',
                'residents': 'SELECT coalesce(sum(wood),0) FROM residents',
                'structures': 'SELECT coalesce(sum(embodied_wood),0) FROM entities',
                'tools': 'SELECT count(*) FROM workshop_tools',
                'stored': 'SELECT coalesce(sum(wood),0) FROM workshop_chests'}.items():
                audit[name] = db.execute(query).fetchone()[0]
            audit.update(stock=stock, generated=generated, issued=12+generated)
            audit['accounted'] = sum(audit[k] for k in ('natural', 'residents', 'structures', 'tools', 'stored', 'stock'))
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            foreign_keys = db.execute('PRAGMA foreign_key_check').fetchall()
        clean = dict(processExited=self.world.process.poll() is not None,
                     originalHistoryRetained=retained, audit=audit, integrity=integrity, foreignKeys=foreign_keys)
        save(self.directory/'audit.json', clean)
        shutil.copyfile(self.world.data/'server.log', self.directory/'server.log')
        shutil.rmtree(self.world.data)
        clean['runtimeRemoved'] = not self.world.data.exists()
        save(self.directory/'audit.json', clean)
        self.assertTrue(all(retained.values()), retained)
        self.assertEqual(audit['issued'], audit['accounted'], audit)
        self.assertEqual(('ok', []), (integrity, foreign_keys))
        self.assertEqual(self.original_hashes, {p.name: digest(p) for p in SOURCE.glob('world.db*')})
        self.outcomes.append(dict(test=self._testMethodName, cleanup=clean))

    def task(self, client=None, **kwargs):
        def forbidden(*args, **opts): raise AssertionError('Fixed workshop tasks called a selector')
        report = run_mission(client or self.client, self.job, self.state, forbidden, **kwargs)
        self.reports.append(report)
        workshop.validate_saved(json.loads(self.state.read_text()), self.job,
                                dict(url=self.client.url, prefix=self.client.prefix))
        return report

    def controlled(self, *, before=None, after=None):
        owner = self
        class Controlled(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                owner.traffic.append(dict(method=method, path=path, payload=deepcopy(payload)))
                if before: before(method, path, payload)
                result = super().request(method, path, payload, headers)
                return after(method, path, payload, result) if after else result
        return Controlled(self.client.url, self.world.access['sessions']['a2']['token'])

    def complete(self, report):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['workshopCompleted'])
        self.assertEqual(0, report['budget']['used']['modelCalls'])
        if self.job['goals'][0]['workshop']['returnToOrigin']:
            self.assertTrue(report['facts']['returned'])
        return report['facts']['workshopAction']

    def cli(self, action, *, actor='a2', target=None, returns=True, name=None):
        self.job = spec(self.world.instance, action, actor=actor, target=target, returns=returns)
        name = name or self.job['missionId']
        spec_path, output = self.directory/(name+'-spec.json'), self.directory/(name+'-report.json')
        self.state = self.directory/(name+'-state.json')
        save(spec_path, self.job)
        run = subprocess.run([sys.executable, str(ROOT/'scripts/run_resident.py'), '--url', self.client.url,
                '--access-file', str(self.world.data/'access.json'), '--actor', actor, '--spec', str(spec_path),
                '--state', str(self.state), '--output', str(output)], cwd=ROOT, capture_output=True, text=True, timeout=180)
        save(self.directory/(name+'-cli.json'), dict(returncode=run.returncode, stdout=run.stdout, stderr=run.stderr))
        self.assertEqual(0, run.returncode, run.stderr)
        report = json.loads(output.read_text()); self.reports.append(report)
        workshop.validate_saved(json.loads(self.state.read_text()), self.job, dict(url=self.client.url, prefix=self.client.prefix))
        return self.complete(report)

    def navigate(self, target, actor='a2'):
        client = self.new_client(actor)
        for _ in range(300):
            observed = client.observe()
            if nav.near(observed['self']['position'], target): return
            route = nav.navigation(observed).route(observed['self']['position'], target)
            self.assertIsNotNone(route, (observed['self']['position'], target))
            time.sleep(.205)
            self.world.send(dict(type='walk', to=list(route[0])), actor)
        self.fail('Setup navigation did not reach its explicit target')

    def test_01_actual_cli_chain_restart_storage_and_reuse(self):
        self.assertEqual(9, self.start_wood['a2'])
        bench = self.cli(api.build(), name='build-bench')['entity']
        mallet = self.cli(api.craft(bench['entityId']), target=bench['position'], name='craft-mallet')['tool']
        chest = self.cli(api.build('wooden_chest.v1', (29, 20), mallet['toolId']), name='build-chest')['entity']
        self.assertEqual(2, self.client.observe()['self']['inventory']['wood'])
        self.navigate([28, 10]); self.world.fill('a2', 12)
        self.navigate([30, 18])
        self.cli(api.storage('deposit_wood', chest['entityId'], 3), target=chest['position'], name='deposit-three')
        self.assertEqual(9, self.client.observe()['self']['inventory']['wood'])
        self.navigate([28, 10]); self.world.fill('a2', 12)
        filled = self.client.observe()
        self.assertEqual((12, 3), (filled['self']['inventory']['wood'], filled['workshop']['chests'][0]['storedWood']))
        save(self.directory/'capacity-use.json', filled)
        # Spend three carried units, then stop the same database and retrieve the stored three.
        self.navigate([30, 22]); self.world.send(dict(type='build', recipeId='platform.v1', at=[31, 22]))
        self.world.restart(); self.client = self.new_client()
        self.cli(api.storage('withdraw_wood', chest['entityId'], 3), target=chest['position'], name='withdraw-after-restart')
        self.assertEqual(12, self.client.observe()['self']['inventory']['wood'])
        self.navigate([24, 22]); self.world.send(dict(type='build', recipeId='platform.v1', at=[24, 22]))
        final = self.client.observe()
        self.assertEqual((9, 0), (final['self']['inventory']['wood'], final['workshop']['chests'][0]['storedWood']))
        save(self.directory/'chain-summary.json', dict(instance=self.world.instance, initialInventory=9,
            workshopRecipeWood=7, actualHarvested=13, storedThenWithdrawn=3, postStoragePlatformWood=6,
            finalInventory=9, bench=bench, mallet=mallet, chest=chest, actualModelCalls=0,
            limitation='Original historical branch, fixed CLI tasks; not the original live head or independent people'))

    def test_02_dropped_success_restores_original_without_post(self):
        def lost(method, path, payload, result):
            if method == 'POST' and payload['action']['type'] == 'build_workshop': raise OSError('lost original response')
            return result
        report = self.task(self.controlled(after=lost))
        self.assertEqual('unknown', report['mission']['status'])
        pending = json.loads(self.state.read_text())['_state']['pending']['request']
        self.world.restart(); self.client = self.new_client(); self.traffic.clear()
        self.complete(self.task(self.controlled()))
        self.assertFalse(any(t['method'] == 'POST' and t['payload']['action']['type'] == 'build_workshop' for t in self.traffic))
        self.assertEqual(pending['commandId'], self.reports[-1]['facts']['workshopAction']['commandId'])

    def test_03_unsubmitted_pending_404_resends_exact_original(self):
        def lost(method, path, payload):
            if method == 'POST' and payload['action']['type'] == 'build_workshop': raise OSError('pre-submit disconnect')
        self.task(self.controlled(before=lost))
        pending = json.loads(self.state.read_text())['_state']['pending']['request']; self.traffic.clear()
        self.complete(self.task(self.controlled()))
        sent = [t['payload'] for t in self.traffic if t['method'] == 'POST' and t['payload']['action']['type'] == 'build_workshop']
        self.assertEqual([pending], sent)

    def test_04_partial_three_records_keep_pending(self):
        def hidden(method, path, payload, result):
            if '/workshop/actions/' in path: return 503, {'error': {'code': 'TEMPORARY'}}
            return result
        report = self.task(self.controlled(after=hidden))
        self.assertEqual('unknown', report['mission']['status'])
        self.assertFalse(report['facts']['workshopCompleted'])
        self.assertIsNotNone(json.loads(self.state.read_text())['_state']['pending'])
        self.complete(self.task())

    def test_05_query_failure_cost_survives_restart(self):
        self.job['budgets']['queries'] = 2
        def fail(method, path, payload):
            if path.endswith('/observation'): raise OSError('lost observation')
        with self.assertRaises(OSError): self.task(self.controlled(before=fail))
        self.assertEqual(1, json.loads(self.state.read_text())['used']['queries'])
        with self.assertRaises(OSError): self.task(self.controlled(before=fail))
        before = len(self.traffic)
        with self.assertRaises(workshop.QueryBudget): self.task(self.controlled(before=fail))
        self.assertEqual(before, len(self.traffic))

    def test_06_permissions_and_forged_journal_rejected_before_io(self):
        def no_io(*args): raise AssertionError('Malformed authority reached transport')
        for field in workshop.PERMISSIONS.values():
            damaged = deepcopy(self.job); damaged[field] = not damaged[field]
            with self.assertRaises(ValueError): run_mission(self.controlled(before=no_io), damaged, self.state, no_io)
        self.task(max_steps=0); original = self.state.read_bytes()
        for mutate in (lambda s: s['budget']['used'].update(queries=0),
                       lambda s: s['mission'].update(allowCraftTool=True),
                       lambda s: s['_state']['binding'].update(instanceId='w_'+'0'*32),
                       lambda s: s['facts'].update(workshopCompleted=True),
                       lambda s: s['_state'].update(confirmedInventoryWood=12)):
            damaged = json.loads(original); mutate(damaged); save(self.state, damaged)
            with self.assertRaises(ValueError): self.task(self.controlled(before=no_io))
        self.state.write_bytes(original)

    def test_07_unknown_capability_and_recipe_budget_stop(self):
        def unknown(method, path, payload, result):
            if path.endswith('/observation') and result[0] == 200:
                result[1]['workshop']['version'] = 2
            return result
        with self.assertRaises(ValueError): self.task(self.controlled(after=unknown))
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))
        self.state = self.directory/'budget-state.json'; self.job['budgets']['wood'] = 2
        result = self.task(self.controlled())
        self.assertEqual(('budget_exhausted', 'wood'), (result['mission']['status'], result['mission']['reason']))
        self.assertFalse(result['facts']['workshopCompleted'])

    def test_08_changed_actor_aba_original_state_rejects(self):
        self.task(max_steps=0)
        original = self.client.observe()['self']['position']
        self.navigate([26, 16]); self.navigate(original)
        result = self.task()
        self.assertEqual('blocked', result['mission']['status'])
        self.assertEqual('command_rejected:STALE_ACTOR_STATE', result['mission']['reason'])
        self.assertFalse(result['facts']['workshopCompleted'])

    def test_09_workshop_success_without_required_return_is_separate(self):
        self.job['goals'][0]['workshop']['action']['at'] = [26, 22]
        self.job['goals'][0]['target'] = [26, 22]
        self.job['goals'][0]['workshop']['returnToOrigin'] = False
        result = self.task(); self.complete(result)
        self.assertFalse(result['facts']['returned'])
        def no_io(*args): raise AssertionError('Completed task replay touched transport')
        self.complete(self.task(self.controlled(before=no_io)))

    def test_10_furniture_geometry_and_only_target_exclusion(self):
        bench = self.cli(api.build(), name='geometry-bench')['entity']
        observed = self.client.observe(); geometry = nav.navigation(observed)
        self.assertFalse(geometry.walkable(bench['position']))
        self.assertFalse(geometry.clear([24.5, 20], [27.5, 20]))
        ray = nav.navigation(observed, interaction_target=bench['entityId'])
        self.assertTrue(ray.clear([26, 18.5], bench['position']))
        self.assertFalse(geometry.clear([26, 18.5], bench['position']))
        self.assertIsNotNone(geometry.route([24.5, 20], [27.5, 20]))

    def visitor_chain(self, reuse):
        actor = 'a3'
        self.assertEqual(3, self.start_wood[actor])
        bench = None
        if reuse: bench = self.cli(api.build(), returns=False, name='existing-public-bench')['entity']
        self.world.fill(actor, 4 if reuse else 7)
        if not reuse:
            bench = self.cli(api.build(), actor=actor, returns=False, name='own-workbench')['entity']
        mallet = self.cli(api.craft(bench['entityId']), actor=actor, target=bench['position'],
                          returns=False, name='visitor-mallet')['tool']
        chest = self.cli(api.build('wooden_chest.v1', (29, 20), mallet['toolId']), actor=actor,
                         returns=False, name='visitor-chest')['entity']
        observed = self.new_client(actor).observe()
        self.assertEqual(0, observed['self']['inventory']['wood'])
        self.assertEqual(actor, mallet['ownerActorId']); self.assertEqual(actor, chest['ownerActorId'])
        self.assertEqual('a2' if reuse else actor, bench['ownerActorId'])
        harvested = [e for e in self.world.trace if e['method'] == 'POST' and e['actor'] == actor
                     and e.get('request', {}).get('action', {}).get('type') == 'harvest_material' and e['status'] == 200]
        self.assertEqual(1 if reuse else 4, len(harvested))
        save(self.directory/'visitor-summary.json', dict(actor=actor, instance=self.world.instance,
            originalInventory=3, actuallyHarvested=len(harvested), consumedWood=4 if reuse else 7, finalInventory=0,
            workbenchOwner=bench['ownerActorId'], mallet=mallet, chest=chest,
            actualModelCalls=0, returnRequired=False,
            limitation='Same declared actor and initial inventory on separate original-history branches; no timing or independent-person claim'))

    def test_11_same_initial_resident_reuses_public_bench(self):
        self.visitor_chain(True)

    def test_12_same_initial_resident_builds_own_bench(self):
        self.visitor_chain(False)

    def test_13_storage_budget_and_other_owner_stay_separate(self):
        bench = self.cli(api.build(), name='owner-bench')['entity']
        tool = self.cli(api.craft(bench['entityId']), target=bench['position'], name='owner-mallet')['tool']
        chest = self.cli(api.build('wooden_chest.v1', (29, 20), tool['toolId']), name='owner-chest')['entity']
        self.state = self.directory/'movement-budget.json'
        self.job = spec(self.world.instance, api.storage('deposit_wood', chest['entityId'], 2), target=chest['position'])
        self.job['budgets']['woodMoved'] = 1
        report = self.task(self.controlled())
        self.assertEqual(('budget_exhausted', 'woodMoved'), (report['mission']['status'], report['mission']['reason']))
        self.assertFalse(report['facts']['workshopCompleted'])
        self.assertFalse(any(t['method'] == 'POST' and t['payload']['action']['type'] == 'deposit_wood' for t in self.traffic))
        self.state = self.directory/'other-owner.json'
        self.job = spec(self.world.instance, api.storage('withdraw_wood', chest['entityId'], 1), actor='a3', target=chest['position'])
        with self.assertRaisesRegex(ValueError, 'another resident'):
            run_mission(self.new_client('a3'), self.job, self.state, None)

    def test_14_unauthorized_and_server_errors_preserve_exact_pending(self):
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

    def test_15_missing_proof_query_budget_retains_original(self):
        self.job['budgets']['queries'] = 3
        report = self.task()
        self.assertEqual(('budget_exhausted', 'queries_pending_retained'), (report['mission']['status'], report['mission']['reason']))
        original = json.loads(self.state.read_text())['_state']['pending']
        self.assertIsNotNone(original)
        self.assertFalse(report['facts']['workshopCompleted'])
        self.traffic.clear(); self.task(self.controlled())
        self.assertEqual([], self.traffic)
        self.assertEqual(original, json.loads(self.state.read_text())['_state']['pending'])

    def test_16_issued_success_then_altered_detail_stays_unknown(self):
        def changed(method, path, payload, result):
            if '/workshop/actions/' in path and result[0] == 200:
                result[1]['workshopAction']['inventoryWood'] += 1
            return result
        report = self.task(self.controlled(after=changed))
        self.assertEqual('unknown', report['mission']['status'])
        self.assertFalse(report['facts']['workshopCompleted'])
        self.assertIsNotNone(json.loads(self.state.read_text())['_state']['pending'])
        self.complete(self.task())

    def test_17_concurrent_storage_rejects_original_without_new_id(self):
        bench = self.cli(api.build(), name='concurrent-bench')['entity']
        mallet = self.cli(api.craft(bench['entityId']), target=bench['position'], name='concurrent-mallet')['tool']
        chest = self.cli(api.build('wooden_chest.v1', (29, 20), mallet['toolId']), name='concurrent-chest')['entity']
        self.job = spec(self.world.instance, api.storage('deposit_wood', chest['entityId'], 2), target=chest['position'])
        self.state = self.directory/'concurrent-state.json'
        interfered = []
        def competing(method, path, payload):
            if method == 'POST' and payload['action']['type'] == 'deposit_wood' and not interfered:
                interfered.append(self.world.send(api.storage('deposit_wood', chest['entityId'], 1))[0])
        result = self.task(self.controlled(before=competing))
        self.assertEqual(('blocked', 'command_rejected:STALE_ACTOR_STATE'), (result['mission']['status'], result['mission']['reason']))
        self.assertEqual((False, 0), (result['facts']['workshopCompleted'], result['facts']['woodDeposited']))
        self.assertEqual(1, self.client.observe()['workshop']['chests'][0]['storedWood'])
        self.traffic.clear(); self.task(self.controlled())
        self.assertEqual([], self.traffic)

    def test_18_expired_time_does_not_resend_missing_pending(self):
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

    def test_19_expired_time_can_verify_already_committed_original(self):
        self.job['budgets']['seconds'] = 1
        def lost(method, path, payload, result):
            if method == 'POST': raise OSError('committed response lost')
            return result
        result = self.task(self.controlled(after=lost))
        self.assertEqual('unknown', result['mission']['status'])
        time.sleep(1.05); self.traffic.clear()
        self.complete(self.task(self.controlled()))
        self.assertFalse(any(t['method'] == 'POST' for t in self.traffic))

    def test_20_newer_actual_position_does_not_claim_original_return(self):
        self.task(max_steps=0)
        self.navigate([26, 16])
        result = self.task()
        self.assertEqual(('blocked', 'workshop_actor_changed_outside_task'), (result['mission']['status'], result['mission']['reason']))
        self.assertFalse(result['facts']['returned'])
        self.assertEqual([26, 16], result['world']['observedSelf']['position'])
        self.traffic.clear(); self.task(self.controlled())
        self.assertEqual([], self.traffic)

    def test_21_delayed_observation_crosses_deadline_no_fresh_post(self):
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
        self.assertFalse(result['facts']['workshopCompleted'])

    def test_22_delayed_capability_observation_does_not_resend_pending(self):
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

    def test_23_crash_after_rejection_settlement_restores_terminal(self):
        """Fault fixture: stop immediately after the rejected receipt is persisted."""
        import resident_mission
        self.task(max_steps=0)
        self.navigate([26, 16]); self.navigate([26, 17])
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

    def test_24_last_fresh_save_crosses_deadline_preserves_pending(self):
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

    def test_25_last_resend_save_crosses_deadline_preserves_original(self):
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


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkshopMissionAcceptance) if len(sys.argv) == 1 else unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:], sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if RUN.exists():
        save(RUN/'summary.json', dict(success=result.wasSuccessful(), testsRun=result.testsRun,
            failures=[dict(test=str(t), detail=e) for t,e in result.failures+result.errors],
            outcomes=WorkshopMissionAcceptance.outcomes,
            finalCodeHashes={p: digest(ROOT/p) for p in FILES}, actualModelCalls=0))
        print('Evidence: '+str(RUN))
    raise SystemExit(0 if result.wasSuccessful() else 1)
