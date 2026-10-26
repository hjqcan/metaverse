#!/usr/bin/env python3
"""Explicit policy adoption in the real exhausted, two-note original world.

CONTINUOUS_MATERIAL_BASELINE optionally selects a stopped baseline. Without it,
the baseline is built with actual r10 commands, including both original notes.
All running worlds are isolated copies; the supplied binary is shared read-only.
No time or wood is seeded.
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
import uuid

import foundation_api
from foundation_api import ROOT, Candidate, EvidenceResult
from foundation_agent import WorldClient
import activities_api
import entity_notes_api
import material_access_api
from material_access_api import MaterialAccessAcceptance, reserve, harvest

RUN = ROOT / '.local/iter0024/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
SOURCE_DLL = Path(os.environ.get('WORLD_SERVER_DLL', foundation_api.DLL))
DLL = SOURCE_DLL.resolve()
OLD_DLL = Path(os.environ['CONTINUOUS_MATERIAL_OLD_DLL']) if os.environ.get('CONTINUOUS_MATERIAL_OLD_DLL') else None


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline(output=None, dll=None):
    """Reusable fixture for the CLI and native tests; returns a stopped directory."""
    if os.environ.get('CONTINUOUS_MATERIAL_BASELINE'):
        return Path(os.environ['CONTINUOUS_MATERIAL_BASELINE']).resolve()
    output = Path(output or RUN/'seed')
    chosen = Path(dll or DLL)
    foundation_api.DLL = chosen
    material_access_api.DLL = chosen
    entity_notes_api.DLL = chosen
    entity_notes_api.RUN = output
    previous = os.environ.pop('ENTITY_NOTES_BASELINE', None)
    try:
        exhausted = entity_notes_api.baseline()
    finally:
        if previous is not None: os.environ['ENTITY_NOTES_BASELINE'] = previous
    prep = entity_notes_api.EntityNotesAcceptance('test_01_same_instance_two_authors_reference_return_and_old_facts')
    prep.source = exhausted
    prep.setUp()
    try:
        prep.test_01_same_instance_two_authors_reference_return_and_old_facts()
        return prep.world.data
    finally:
        prep.tearDown()
        prep.doCleanups()


class Continued(Candidate):
    def __init__(self, source, output, dll=None, start=True):
        self.data = Path(output); self.data.mkdir(parents=True, mode=0o700)
        with sqlite3.connect(f'file:{Path(source)/"world.db"}?mode=ro', uri=True) as src, sqlite3.connect(self.data/'world.db') as dst:
            src.backup(dst)
        shutil.copy2(Path(source)/'access.json', self.data/'access.json')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.env = {**os.environ, 'WORLD_URL': self.url, 'WORLD_DATA_DIR': str(self.data), 'WORLD_ENABLE_FAULTS': '1'}
        for key in ('WORLD_SCENARIO','WORLD_MATERIAL_TEST_FAULT','WORLD_CONTINUOUS_ADOPTION_TEST_FAULT'):
            self.env.pop(key, None)
        self.dll = Path(dll or DLL)
        self.process = self.log = None
        self.access = json.loads((self.data/'access.json').read_text())
        if start: self.start()

    def start(self):
        self.log = (self.data/'server.log').open('a')
        self.process = subprocess.Popen(['dotnet', str(self.dll)], cwd=ROOT, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f'Candidate exited {self.process.returncode}; see {self.data / "server.log"}')
                try:
                    if WorldClient(self.url, '').request('GET','/healthz')[0] == 200: return
                except (OSError, ValueError): pass
                time.sleep(.05)
            raise RuntimeError('Candidate startup timed out')
        except BaseException:
            self.stop(); raise

    def adopt(self, instance, fault=None, dll=None):
        env = dict(self.env)
        if fault: env['WORLD_CONTINUOUS_ADOPTION_TEST_FAULT'] = fault
        return subprocess.run(['dotnet',str(dll or self.dll),'adopt-continuous-material-source','--instance',instance],
                              cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)


def rows(data):
    with sqlite3.connect(f'file:{Path(data)/"world.db"}?mode=ro', uri=True) as db:
        return {name: db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()}


class ContinuousMaterialAcceptance(unittest.TestCase):
    intent = MaterialAccessAcceptance.intent
    post = MaterialAccessAcceptance.post
    send = MaterialAccessAcceptance.send
    walk = MaterialAccessAcceptance.walk
    until = MaterialAccessAcceptance.until
    active = MaterialAccessAcceptance.active

    @classmethod
    def setUpClass(cls):
        RUN.mkdir(parents=True,exist_ok=True)
        (RUN/'binary-location.json').write_text(json.dumps({'path':str(DLL),'sha256':digest(DLL)},indent=2)+'\n')
        cls.source = baseline()

    def setUp(self):
        self.worlds = []
        self.world = self.copy('world')
        self.a,self.b,self.c = [self.world.client(a) for a in ('a1','a2','a3')]
        observed = self.a.observe()
        self.instance = observed['world']['instanceId']
        self.original = rows(self.world.data)
        self.trace = []
        self.assertEqual((12,0), tuple(observed['materialAccess'][k] for k in ('generatedWood','stockWood')))
        self.assertEqual((5,2,6), (len(observed['entities']),observed['entityNotes']['totalCount'],observed['self']['inventory']['wood']))

    def copy(self, name, start=True):
        world = Continued(self.source,RUN/self._testMethodName/name,start=start)
        self.worlds.append(world)
        return world

    def tearDown(self):
        for w in self.worlds: w.stop()
        (self.world.data/'trace.json').write_text(json.dumps(self.trace,ensure_ascii=False,indent=2)+'\n')
        for w in self.worlds:
            if getattr(w,'intentionally_corrupted',False): continue
            with sqlite3.connect(w.data/'world.db') as db:
                self.assertEqual('ok',db.execute('PRAGMA integrity_check').fetchone()[0])
                self.assertEqual([],db.execute('PRAGMA foreign_key_check').fetchall())
                issued, = db.execute('SELECT issued_wood FROM worlds').fetchone()
                generated,stock = db.execute('SELECT generated_wood,stock_wood FROM material_source').fetchone()
                total = sum(db.execute(sql).fetchone()[0] for sql in (
                    'SELECT coalesce(sum(wood),0) FROM residents','SELECT coalesce(sum(remaining_wood),0) FROM resource_nodes',
                    'SELECT coalesce(sum(embodied_wood),0) FROM entities'))
                self.assertEqual(12+generated,issued); self.assertEqual(total+stock,issued)
                self.assertEqual(generated,db.execute('SELECT coalesce(sum(quantity),0) FROM material_production').fetchone()[0])
                balances = {}
                for src,dst,q in db.execute('SELECT source_account,destination_account,quantity FROM resource_ledger'):
                    balances[src]=balances.get(src,0)-q;balances[dst]=balances.get(dst,0)+q
                self.assertEqual(-12,balances.pop('initial-issuance'))
                self.assertEqual(-generated,balances.pop('ecological-input'))
                self.assertEqual(stock,balances.pop('source:wood-source-east',0))
                self.assertEqual(db.execute('SELECT coalesce(sum(remaining_wood),0) FROM resource_nodes').fetchone()[0],balances.pop('wild-wood',0))
                for actor,wood in db.execute('SELECT actor_id,wood FROM residents'): self.assertEqual(wood,balances.pop('inventory:'+actor,0))
                for entity,wood in db.execute('SELECT entity_id,embodied_wood FROM entities'): self.assertEqual(wood,balances.pop('entity:'+entity,0))
                self.assertFalse(balances)

    def adopt(self):
        self.world.stop()
        result = self.world.adopt(self.instance)
        self.assertEqual(0,result.returncode,result.stderr)
        self.world.start()

    def preserved(self):
        current = rows(self.world.data)
        for name in ('entities','receipts','events','resource_ledger','entity_notes','entity_note_adoption','recipes','resource_nodes','world_instance'):
            self.assertTrue(set(self.original[name]).issubset(set(current[name])),name)
        self.assertEqual(6,self.a.observe()['self']['inventory']['wood'])
        self.assertEqual(self.instance,self.b.observe()['world']['instanceId'])

    def test_01_explicit_offline_adoption_preserves_phase_rows_and_is_idempotent(self):
        self.assertNotEqual(0,self.world.adopt(self.instance).returncode)
        self.world.stop(); before=rows(self.world.data)
        self.assertNotEqual(0,self.world.adopt('w_'+'0'*32).returncode)
        self.assertEqual(before,rows(self.world.data))
        self.assertEqual(0,self.world.adopt(self.instance).returncode)
        after=rows(self.world.data)
        for name in before:
            if name not in ('worlds','events','sqlite_sequence'): self.assertEqual(before[name],after[name],name)
        self.assertEqual(len(before['events'])+1,len(after['events']))
        self.assertEqual(0,self.world.adopt(self.instance).returncode)
        self.assertEqual(after,rows(self.world.data))
        self.world.start(); source=self.b.observe()['materialAccess']
        self.assertEqual(2,source['version']);self.assertIsNone(source['inputBudget'])
        self.assertEqual('continuous-service-time-v1',source['productionPolicy']['id'])
        self.assertEqual(12,source['productionPolicy']['generatedWoodAtAdoption'])
        self.assertEqual(before['material_source'][0][6:],(source['generatedWood'],source['stockWood']))

    def test_02_original_world_late_platform_and_production_beyond_another_twelve(self):
        denied=self.intent(self.b,reserve());self.post(self.b,denied,422,'SOURCE_BUDGET_EXHAUSTED')
        self.adopt();self.post(self.b,denied,422,'SOURCE_BUDGET_EXHAUSTED')
        rid=self.send(self.b,reserve())['result']['reservationId'];self.active(self.b,rid)
        self.walk(self.b,[28,10])
        for _ in range(3):self.send(self.b,harvest(rid))
        self.walk(self.b,[24,16])
        built=self.send(self.b,{'type':'build','recipeId':'platform.v1','at':[24,16]})
        self.assertEqual('a2',next(e['ownerActorId'] for e in self.b.observe()['entities'] if e['entityId']==built['result']['entityId']))
        # Four later original requests consume another twelve; generated > 24
        # proves this is neither one extra grant nor another lifetime twelve.
        self.walk(self.c,[28,10])
        for _ in range(4):
            rid=self.send(self.c,reserve())['result']['reservationId'];self.active(self.c,rid)
            for _ in range(3):self.send(self.c,harvest(rid))
        final=self.b.observe()
        self.assertGreaterEqual(final['materialAccess']['generatedWood'],27)
        self.assertEqual(6,len(final['entities']));self.assertEqual(2,final['entityNotes']['totalCount'])
        self.world.restart();self.preserved()
        (self.world.data/'natural-final.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n')

    def test_03_adoption_crash_rolls_back_or_commits_once(self):
        for fault,code,version in [('before-commit',85,10),('after-commit',86,11)]:
            w=self.copy(fault,start=False);before=rows(w.data)
            self.assertEqual(code,w.adopt(self.instance,fault).returncode)
            with sqlite3.connect(w.data/'world.db') as db:self.assertEqual(version,db.execute('PRAGMA user_version').fetchone()[0])
            if version==10:self.assertEqual(before,rows(w.data))
            self.assertEqual(0,w.adopt(self.instance).returncode)
            after=rows(w.data);self.assertEqual(len(before['events'])+1,len(after['events']))
            self.assertEqual(before['material_source'],after['material_source'])
            w.start();self.assertEqual(2,w.client().observe()['materialAccess']['version'])

    def test_04_old_binary_cold_start_refuses_and_new_restarts(self):
        if OLD_DLL is None:self.skipTest('CONTINUOUS_MATERIAL_OLD_DLL not provided; no old-binary claim')
        self.adopt();self.world.stop();before=rows(self.world.data)
        run=subprocess.run(['dotnet',str(OLD_DLL)],cwd=ROOT,env=self.world.env,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(0,run.returncode);self.assertEqual(before,rows(self.world.data))
        self.world.start();self.assertEqual(2,self.a.observe()['materialAccess']['version'])

    def test_05_original_committed_and_404_intents_survive_adoption(self):
        original=self.intent(self.c,{'type':'walk','to':[27,10]})
        committed=self.post(self.c,original)
        pending=self.intent(self.b,reserve());body=json.dumps(pending,separators=(',',':'))
        self.assertEqual(404,self.b.request('GET',self.b.prefix+'/commands/'+pending['commandId'])[0])
        self.adopt()
        self.assertEqual(committed,self.post(self.c,original))
        self.assertEqual(404,self.b.request('GET',self.b.prefix+'/commands/'+pending['commandId'])[0])
        self.assertEqual(body,json.dumps(pending,separators=(',',':')))
        queued=self.post(self.b,pending)
        self.assertEqual(queued,self.post(self.b,pending))
        self.assertEqual(queued,self.b.request('GET',self.b.prefix+'/commands/'+pending['commandId'])[1])
        self.preserved()

    def test_06_full_capacity_skips_without_debt_and_offline_time_does_not_produce(self):
        self.adopt();full=self.until(self.c,lambda o:o['materialAccess']['stockWood']==6)
        source=full['materialAccess'];self.world.stop()
        stopped=rows(self.world.data)['material_source'];time.sleep(1.2)
        self.assertEqual(stopped,rows(self.world.data)['material_source'])
        self.world.start();restarted=self.c.observe()['materialAccess']
        self.assertEqual(source['generatedWood'],restarted['generatedWood'])
        self.assertLess(restarted['serviceMs']-stopped[0][2],1000)
        # Let a real full period pass. It advances the phase, never the input.
        skipped=self.until(self.c,lambda o:o['materialAccess']['serviceMs']>=source['nextProductionAtMs']+300)
        self.assertEqual(source['generatedWood'],skipped['materialAccess']['generatedWood'])
        rid=self.send(self.c,reserve())['result']['reservationId'];self.active(self.c,rid)
        self.send(self.c,harvest(rid))
        after=self.c.observe()['materialAccess']
        self.assertEqual(5,after['stockWood']);self.assertEqual(source['generatedWood'],after['generatedWood'])
        produced=self.until(self.c,lambda o:o['materialAccess']['generatedWood']>source['generatedWood'])['materialAccess']
        self.assertEqual(source['generatedWood']+1,produced['generatedWood']);self.assertEqual(6,produced['stockWood'])

    def test_07_production_crash_preserves_exact_period_and_ledger(self):
        for fault,code,expected in [('before-commit',83,12),('after-commit',84,15)]:
            w=self.copy(fault,start=False);self.assertEqual(0,w.adopt(self.instance).returncode)
            w.env['WORLD_MATERIAL_TEST_FAULT']=fault;w.start()
            self.assertEqual(code,w.process.wait(timeout=15));w.stop()
            with sqlite3.connect(w.data/'world.db') as db:self.assertEqual(expected,db.execute('SELECT generated_wood FROM material_source').fetchone()[0])
            w.env.pop('WORLD_MATERIAL_TEST_FAULT');w.start();client=w.client('a3')
            self.until(client,lambda o:o['materialAccess']['generatedWood']>=15,timeout=15)
            w.stop()
            with sqlite3.connect(w.data/'world.db') as db:
                self.assertEqual(15,db.execute('SELECT generated_wood FROM material_source').fetchone()[0])
                self.assertEqual(5,db.execute('SELECT count(*) FROM material_production').fetchone()[0])

    def test_08_policy_damage_refuses_instead_of_falling_back_to_old_budget(self):
        self.adopt();self.world.stop();self.world.intentionally_corrupted=True
        with sqlite3.connect(self.world.data/'world.db') as db:db.execute('DROP TABLE material_source_policy')
        before=rows(self.world.data)
        run=subprocess.run(['dotnet',str(DLL)],cwd=ROOT,env=self.world.env,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(0,run.returncode);self.assertEqual(before,rows(self.world.data))

    def test_09_incomplete_old_production_event_cannot_be_adopted(self):
        for field in ('type','quantity','productionPeriod','serviceMs','sourceId','actorId','commandId'):
            with self.subTest(field=field):
                w=self.copy('missing-'+field,start=False);w.intentionally_corrupted=True
                with sqlite3.connect(w.data/'world.db') as db:
                    db.execute('DROP TRIGGER immutable_event_update')
                    db.execute("UPDATE events SET event_json=json_remove(event_json,?) WHERE seq=(SELECT min(event_seq) FROM material_production)",('$.'+field,))
                before=rows(w.data)
                self.assertNotEqual(0,w.adopt(self.instance).returncode)
                self.assertEqual(before,rows(w.data))

    def test_10_missing_policy_constraint_or_trigger_refuses_startup(self):
        for kind in ('source-constraint','policy-trigger'):
            w=self.copy(kind,start=False);self.assertEqual(0,w.adopt(self.instance).returncode);w.intentionally_corrupted=True
            with sqlite3.connect(w.data/'world.db') as db:
                if kind=='policy-trigger':db.execute('DROP TRIGGER immutable_material_policy_update')
                else:
                    # Deliberately corrupt only an isolated fixture schema.
                    db.execute('PRAGMA writable_schema=ON')
                    db.execute("UPDATE sqlite_master SET sql=replace(sql,'stock_wood BETWEEN 0 AND 6','stock_wood>=0') WHERE name='material_source'")
                    db.execute('PRAGMA writable_schema=OFF')
            before=rows(w.data)
            run=subprocess.run(['dotnet',str(DLL)],cwd=ROOT,env=w.env,capture_output=True,text=True,timeout=15)
            self.assertNotEqual(0,run.returncode);self.assertEqual(before,rows(w.data))

    def test_11_partial_active_and_fifo_queue_keep_original_lease_across_adoption(self):
        activities_api.RUN_ROOT=RUN/self._testMethodName
        foundation_api.DLL=DLL
        w=activities_api.ActivityCandidate('unexhausted-branch',scenario='wilderness-material-access-v1');self.worlds.append(w)
        a,b,c=[w.client(actor) for actor in ('a1','a2','a3')]
        instance=a.observe()['world']['instanceId'];w.stop()
        enabled=subprocess.run(['dotnet',str(DLL),'enable-material-source','--instance',instance],env=w.env,capture_output=True,text=True)
        self.assertEqual(0,enabled.returncode,enabled.stderr);w.start()
        rid=self.send(c,reserve())['result']['reservationId'];self.active(c,rid)
        self.send(c,harvest(rid))
        early=self.send(a,reserve())['result']['reservationId']
        late=self.send(b,reserve())['result']['reservationId']
        alias=w.client('a1_alias')
        self.post(alias,self.intent(alias,reserve()),409,'RESERVATION_ALREADY_ACTIVE')
        w.stop();before=rows(w.data)
        adopted=subprocess.run(['dotnet',str(DLL),'adopt-continuous-material-source','--instance',instance],env=w.env,capture_output=True,text=True)
        self.assertEqual(0,adopted.returncode,adopted.stderr)
        after=rows(w.data)
        self.assertEqual(before['material_reservations'],after['material_reservations'])
        self.assertEqual(before['material_source'],after['material_source'])
        self.assertEqual(before['residents'],after['residents'])
        w.start();current=c.observe()['materialAccess']['currentReservation']
        self.assertEqual((rid,'active',2),(current['reservationId'],current['status'],current['remaining']))
        granted=self.active(a,early)['materialAccess']['currentReservation']
        self.assertEqual('queued',b.observe()['materialAccess']['currentReservation']['status'])
        self.send(c,{'type':'cancel_reservation','reservationId':rid})
        later=self.active(b,late)['materialAccess']['currentReservation']
        self.assertLess(granted['queueSequence'],later['queueSequence'])
        self.assertEqual(1,c.observe()['self']['inventory']['wood'])

    def test_12_null_phase_and_fractional_source_cannot_be_adopted(self):
        activities_api.RUN_ROOT=RUN/self._testMethodName
        foundation_api.DLL=DLL
        for kind in ('null-phase','fractional-generated'):
            w=activities_api.ActivityCandidate(kind,scenario='wilderness-material-access-v1');self.worlds.append(w)
            instance=w.client().observe()['world']['instanceId'];w.stop();w.intentionally_corrupted=True
            enabled=subprocess.run(['dotnet',str(DLL),'enable-material-source','--instance',instance],env=w.env,capture_output=True,text=True)
            self.assertEqual(0,enabled.returncode)
            with sqlite3.connect(w.data/'world.db') as db:
                if kind=='null-phase':db.execute('UPDATE material_source SET enabled_at_ms=NULL,next_production_ms=NULL')
                else:db.execute('UPDATE material_source SET generated_wood=0.25')
            before=rows(w.data)
            result=subprocess.run(['dotnet',str(DLL),'adopt-continuous-material-source','--instance',instance],env=w.env,capture_output=True,text=True)
            self.assertNotEqual(0,result.returncode);self.assertEqual(before,rows(w.data))

    def test_13_fractional_policy_anchors_refuse_without_truncation(self):
        for field in ('adopted_service_ms','state_version','event_seq','generated_at_adoption','production_period_at_adoption'):
            with self.subTest(field=field):
                w=self.copy('fractional-'+field,start=False)
                self.assertEqual(0,w.adopt(self.instance).returncode)
                w.intentionally_corrupted=True
                with sqlite3.connect(w.data/'world.db') as db:
                    trigger=db.execute("SELECT sql FROM sqlite_master WHERE name='immutable_material_policy_update'").fetchone()[0]
                    db.execute('DROP TRIGGER immutable_material_policy_update')
                    delta='-0.5' if field=='generated_at_adoption' else '+0.5'
                    db.execute(f'UPDATE material_source_policy SET {field}={field}{delta}')
                    db.execute(trigger)
                    self.assertEqual('real',db.execute(f'SELECT typeof({field}) FROM material_source_policy').fetchone()[0])
                before=rows(w.data)
                for args in ([],['adopt-continuous-material-source','--instance',self.instance]):
                    run=subprocess.run(['dotnet',str(DLL),*args],cwd=ROOT,env=w.env,capture_output=True,text=True,timeout=15)
                    self.assertNotEqual(0,run.returncode)
                    if not args: self.assertIn('持续材料政策字段类型不匹配',run.stdout+run.stderr)
                    self.assertEqual(before,rows(w.data))
                self.trace.append({'fractionalPolicyField':field,'startupAndRepeatedAdoptionRejected':True,'allRowsUnchanged':True})


if __name__ == '__main__':
    RUN.mkdir(parents=True,exist_ok=True)
    suite=unittest.TestSuite(ContinuousMaterialAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:] else unittest.defaultTestLoader.loadTestsFromTestCase(ContinuousMaterialAcceptance)
    result=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(suite)
    evidence={'suite':'continuous-material-http-v1','passed':result.wasSuccessful(),'testsRun':result.testsRun,'tests':result.records,
              'actualModelCalls':0,'dllSha256':digest(DLL),'baseline':str(getattr(ContinuousMaterialAcceptance,'source','')),
              'clock':'real Stopwatch in natural operation; isolated damage cases deliberately alter invalid rows/schema, never to fund success',
              'failureDetails':[(str(t),d) for t,d in result.failures+result.errors]}
    (RUN/'results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print('Evidence:',RUN/'results.json')
    raise SystemExit(not result.wasSuccessful())
