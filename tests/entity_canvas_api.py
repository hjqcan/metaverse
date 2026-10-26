#!/usr/bin/env python3
"""Actual HTTP/SQLite platform canvas acceptance; shared immutable DLL, isolated DBs."""
from concurrent.futures import ThreadPoolExecutor
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
import uuid

import foundation_api
from foundation_api import ROOT, EvidenceResult
from continuous_material_api import Continued, rows
import continuous_material_api as continuous
from material_access_api import MaterialAccessAcceptance, reserve, harvest

RUN = ROOT / '.local/iter0025/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
DLL = Path(os.environ.get('WORLD_SERVER_DLL', foundation_api.DLL)).resolve()
OLD_DLL = Path(os.environ['ENTITY_CANVAS_OLD_DLL']).resolve() if os.environ.get('ENTITY_CANVAS_OLD_DLL') else None


def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def copy_world(source, destination):
    """Copy a stopped DB together with its WAL; never checkpoint the source."""
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    names = [n for n in ('world.db', 'world.db-wal', 'world.db-shm', 'access.json') if (source/n).exists()]
    before = {n: digest(source/n) for n in names}
    for n in names: shutil.copy2(source/n, destination/n)
    with sqlite3.connect(destination/'world.db') as c:
        c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    if before != {n: digest(source/n) for n in names}: raise RuntimeError('Stopped baseline changed during copy')
    return before


class CanvasWorld(Continued):
    def __init__(self, source, output, dll=None, start=True):
        # Normalize a private copy before the shared process helper opens it.
        staging = Path(output).with_name(Path(output).name + '-copied-baseline')
        self.source_hashes = copy_world(source, staging)
        super().__init__(staging, output, dll=dll or DLL, start=start)
        shutil.rmtree(staging)
        self.env.pop('WORLD_CANVAS_ADOPTION_TEST_FAULT', None)

    def adopt_canvas(self, instance, entity, fault=None, dll=None):
        env = dict(self.env)
        if fault: env['WORLD_CANVAS_ADOPTION_TEST_FAULT'] = fault
        return subprocess.run(['dotnet', str(dll or self.dll), 'adopt-entity-canvas', '--instance', instance, '--entity', entity],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)


def baseline(output=None, dll=None):
    """External real continuation or a reproducible actual-command prior fixture."""
    if os.environ.get('ENTITY_CANVAS_BASELINE'):
        source = Path(os.environ['ENTITY_CANVAS_BASELINE']).resolve()
        target = os.environ.get('ENTITY_CANVAS_ENTITY_ID')
        if not target: raise ValueError('ENTITY_CANVAS_ENTITY_ID must name the actual original platform')
        return source, target
    output = Path(output or RUN/'seed'); chosen = Path(dll or DLL)
    prior = continuous.baseline(output/'prior', chosen)
    w = CanvasWorld(prior, output/'continued', chosen)
    harness = unittest.TestCase(); harness.trace = []
    for name in ('intent', 'post', 'send', 'walk', 'until', 'active'):
        setattr(harness, name, getattr(MaterialAccessAcceptance, name).__get__(harness))
    try:
        client = w.client('a2'); instance = client.observe()['world']['instanceId']; w.stop()
        result = w.adopt(instance); assert result.returncode == 0, result.stderr
        w.start(); rid = harness.send(client, reserve())['result']['reservationId']; harness.active(client, rid)
        harness.walk(client, [28, 10])
        for _ in range(3): harness.send(client, harvest(rid))
        harness.walk(client, [24, 7])
        built = harness.send(client, {'type':'build','recipeId':'platform.v1','at':[24,7]})
        entity = built['result']['entityId']
        harness.walk(client, [26,17])
        (w.data/'target-build.json').write_text(json.dumps(built, ensure_ascii=False, indent=2)+'\n')
        (w.data/'baseline-trace.json').write_text(json.dumps(harness.trace, ensure_ascii=False, indent=2)+'\n')
        return w.data, entity
    finally: w.stop()


def paint(entity, revision=0, patch=None):
    return {'type':'paint_entity_canvas','entityId':entity,'capabilityVersion':1,'expectedCanvasRevision':revision,
            'patch':patch or [{'x':1,'y':1,'color':'river'}]}


class EntityCanvasAcceptance(unittest.TestCase):
    intent = MaterialAccessAcceptance.intent
    post = MaterialAccessAcceptance.post
    send = MaterialAccessAcceptance.send
    walk = MaterialAccessAcceptance.walk

    @classmethod
    def setUpClass(cls):
        RUN.mkdir(parents=True, exist_ok=True); cls.source, cls.target = baseline()

    def setUp(self):
        self.worlds, self.trace = [], []
        self.world = self.copy('world'); self.a, self.b, self.c, self.z = [self.world.client(a) for a in ('a1','a2','a3','a1_alias')]
        first = self.a.observe(); self.instance = first['world']['instanceId']
        self.position = next(e['position'] for e in first['entities'] if e['entityId'] == self.target)
        self.original = rows(self.world.data)
        self.assertEqual((6,2,6), (len(first['entities']),first['entityNotes']['totalCount'],first['self']['inventory']['wood']))

    def copy(self, name, start=True):
        w = CanvasWorld(self.source, RUN/self._testMethodName/name, start=start)
        w.original=rows(w.data); self.worlds.append(w); self.addCleanup(w.stop); return w

    def adopt(self, w=None):
        w = w or self.world; w.stop(); p = w.adopt_canvas(self.instance,self.target)
        self.assertEqual(0,p.returncode,p.stderr); w.start()

    def detail(self, client, author, command):
        return client.request('GET', client.prefix + '/entities/' + self.target + '/canvas/edits/' + author + '/' + command)

    def tearDown(self):
        for w in self.worlds: w.stop()
        (self.world.data/'trace.json').write_text(json.dumps(self.trace,ensure_ascii=False,indent=2)+'\n')
        for w in self.worlds:
            if getattr(w,'corrupted',False): continue
            current = rows(w.data)
            for table in ('entities','receipts','events','resource_ledger','entity_notes'):
                self.assertTrue(set(w.original[table]).issubset(current[table]),table)
            for table in ('world_instance','resource_nodes','recipes','entity_note_adoption','material_source_policy'):
                self.assertEqual(w.original[table],current[table],table)
            with sqlite3.connect(w.data/'world.db') as c:
                self.assertEqual('ok',c.execute('PRAGMA integrity_check').fetchone()[0]);self.assertEqual([],c.execute('PRAGMA foreign_key_check').fetchall())
                issued = c.execute('SELECT issued_wood FROM worlds').fetchone()[0]
                generated, stock = c.execute('SELECT generated_wood,stock_wood FROM material_source').fetchone()
                total = sum(c.execute(q).fetchone()[0] for q in ('SELECT sum(wood) FROM residents','SELECT sum(remaining_wood) FROM resource_nodes','SELECT sum(embodied_wood) FROM entities')) + stock
                self.assertEqual((issued,issued),(12+generated,total))

    def test_01_same_original_platform_two_residents_paint_and_return(self):
        self.adopt(); initial=self.z.observe(); origin_z=initial['self']['position']; origin_b=self.b.observe()['self']['position']
        self.assertEqual(0,initial['self']['inventory']['wood']);self.assertEqual(0,initial['entityCanvas']['revision'])
        self.walk(self.z,self.position)
        first=self.send(self.z,paint(self.target,0,[{'x':2,'y':2,'color':'river'},{'x':1,'y':1,'color':'river'}]))
        self.assertEqual('a1_alias',first['result']['authorActorId']);self.assertEqual(0,first['result']['inventoryWood'])
        self.walk(self.z,origin_z)
        seen=self.b.observe();self.assertEqual(1,seen['entityCanvas']['revision'])
        self.assertEqual('a1_alias',seen['entityCanvas']['cells'][6]['authorActorId'])
        self.walk(self.b,self.position);second=self.send(self.b,paint(self.target,1,[{'x':3,'y':2,'color':'sun'}]));self.walk(self.b,origin_b)
        status,edit=self.detail(self.b,'a1_alias',first['commandId']);self.assertEqual(200,status)
        self.assertEqual({k:v for k,v in first['result'].items() if k!='action'},edit['edit'])
        final=self.b.observe();self.assertEqual(2,final['entityCanvas']['revision']);self.assertEqual(2,final['entityCanvas']['editCount'])
        self.assertEqual(0,self.z.observe()['self']['inventory']['wood']);self.assertEqual(origin_b,final['self']['position'])
        self.assertEqual(6,len(final['entities']));self.assertEqual(2,final['entityNotes']['totalCount'])
        for receipt in (first,second):
            self.assertEqual(receipt['execution']['appliedOnStateVersion']+1,receipt['stateVersion'])
            status,event=self.b.request('GET',self.b.prefix+'/events?after='+str(receipt['eventCursor']-1));self.assertEqual(200,status)
            self.assertEqual('entityCanvasPainted',event['events'][0]['type'])
        self.world.restart();self.assertEqual(final['entityCanvas'],self.b.observe()['entityCanvas'])
        (self.world.data/'natural-final.json').write_text(json.dumps({'initial':initial,'first':first,'second':second,'final':final},ensure_ascii=False,indent=2)+'\n')

    def test_02_explicit_adoption_lock_atomicity_and_legacy_policy_idempotence(self):
        self.assertNotEqual(0,self.world.adopt_canvas(self.instance,self.target).returncode)
        request=self.intent(self.b,paint(self.target));self.post(self.b,request,422,'ENTITY_CANVAS_UNAVAILABLE')
        self.world.stop();before=rows(self.world.data)
        for instance,entity in [('w_'+'0'*32,self.target),(self.instance,'missing')]:
            self.assertNotEqual(0,self.world.adopt_canvas(instance,entity).returncode);self.assertEqual(before,rows(self.world.data))
        self.assertEqual(0,self.world.adopt_canvas(self.instance,self.target).returncode);after=rows(self.world.data)
        self.assertEqual(len(before['events'])+1,len(after['events']))
        for name in before:
            if name not in ('worlds','events','sqlite_sequence'):self.assertEqual(before[name],after[name],name)
        self.assertEqual(0,self.world.adopt_canvas(self.instance,self.target).returncode);self.assertEqual(after,rows(self.world.data))
        self.assertEqual(0,self.world.adopt(self.instance).returncode);self.assertEqual(after,rows(self.world.data))
        self.world.start();self.post(self.b,request,422,'ENTITY_CANVAS_UNAVAILABLE')
        for fault,code,schema in [('before-commit',87,11),('after-commit',88,12)]:
            w=self.copy(fault,False);old=rows(w.data);self.assertEqual(code,w.adopt_canvas(self.instance,self.target,fault).returncode)
            with sqlite3.connect(w.data/'world.db') as c:self.assertEqual(schema,c.execute('PRAGMA user_version').fetchone()[0])
            if schema==11:self.assertEqual(old,rows(w.data))
            self.assertEqual(0,w.adopt_canvas(self.instance,self.target).returncode);self.assertEqual(len(old['events'])+1,len(rows(w.data)['events']))

    def test_03_author_permissions_blank_and_whole_batch_rejection(self):
        self.adopt();self.post(self.b,self.intent(self.b,paint(self.target)),422,'UNREACHABLE')
        self.walk(self.z,self.position);self.send(self.z,paint(self.target))
        self.send(self.z,paint(self.target,1,[{'x':1,'y':1,'color':'blank'}]))
        self.walk(self.a,self.position);before=self.a.observe()['entityCanvas']
        self.post(self.a,self.intent(self.a,paint(self.target,2,[{'x':1,'y':1,'color':'sun'},{'x':2,'y':1,'color':'sun'}])),409,'CANVAS_CONSENT_REQUIRED')
        self.assertEqual(before,self.a.observe()['entityCanvas']);self.assertEqual('a1_alias',before['cells'][6]['authorActorId'])
        self.walk(self.b,self.position);self.post(self.b,self.intent(self.b,paint(self.target,2)),409,'CANVAS_CONSENT_REQUIRED')
        self.post(self.z,self.intent(self.z,paint(self.target,2,[{'x':1,'y':1,'color':'blank'}])),422,'CANVAS_UNCHANGED')
        self.post(self.b,self.intent(self.b,paint(self.target,1,[{'x':2,'y':1,'color':'sun'}])),409,'CANVAS_REVISION_MISMATCH')

    def test_04_same_revision_concurrency_has_one_atomic_winner(self):
        self.adopt();self.walk(self.b,self.position);self.walk(self.c,self.position)
        one=self.intent(self.b,paint(self.target,0,[{'x':0,'y':0,'color':'river'}]))
        two=self.intent(self.c,paint(self.target,0,[{'x':4,'y':4,'color':'sun'}]))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(client.request,'POST',client.prefix+'/commands',request) for client,request in [(self.b,one),(self.c,two)]]
            results=[f.result() for f in futures]
        self.assertEqual([200,409],sorted(s for s,_ in results));self.assertEqual('CANVAS_REVISION_MISMATCH',next(r for s,r in results if s==409)['error']['code'])
        canvas=self.b.observe()['entityCanvas'];self.assertEqual((1,1),(canvas['revision'],canvas['editCount']))
        self.assertEqual(1,sum(c['authorActorId'] is not None for c in canvas['cells']))
        self.trace.append({'concurrentRequests':[one,two],'results':results})

    def test_05_before_and_after_commit_replay_original_id_once(self):
        self.adopt();self.walk(self.b,self.position)
        for fault,code in [('before-commit',81),('after-commit',82)]:
            observation=self.b.observe();request=self.intent(self.b,paint(self.target,observation['entityCanvas']['revision'],[{'x':0,'y':0,'color':'leaf' if fault=='before-commit' else 'sun'}]))
            try:self.b.request('POST',self.b.prefix+'/commands',request,{'X-Test-Fault':fault})
            except OSError:pass
            self.assertEqual(code,self.world.process.wait(timeout=10));self.world.stop();self.world.start()
            status,old=self.b.request('GET',self.b.prefix+'/commands/'+request['commandId'])
            self.assertEqual(404 if fault=='before-commit' else 200,status)
            reply=self.post(self.b,request);self.assertEqual(reply,self.post(self.b,request))
            self.assertEqual(reply['result']['revision'],self.b.observe()['entityCanvas']['revision'])

    def test_06_exact_history_survives_later_repaint_and_recent_window(self):
        self.adopt();self.walk(self.b,self.position);first_request=self.intent(self.b,paint(self.target));first=self.post(self.b,first_request)
        for i in range(1,53):self.send(self.b,paint(self.target,i,[{'x':1,'y':1,'color':'leaf' if i%2 else 'river'}]))
        observed=self.b.observe();self.assertEqual((53,50),(observed['entityCanvas']['editCount'],len(observed['entityCanvas']['recentEdits'])))
        self.assertFalse(any(e['commandId']==first_request['commandId'] for e in observed['entityCanvas']['recentEdits']))
        self.assertEqual(first,self.post(self.b,first_request));status,detail=self.detail(self.z,'a2',first_request['commandId'])
        self.assertEqual(200,status);self.assertEqual({k:v for k,v in first['result'].items() if k!='action'},detail['edit'])
        self.assertEqual(404,self.detail(self.b,'a2','missing')[0]);self.world.restart();self.assertEqual(observed['entityCanvas'],self.b.observe()['entityCanvas'])
        (self.world.data/'original-edit.json').write_text(json.dumps({'request':first_request,'receipt':first,'detail':detail},ensure_ascii=False,indent=2)+'\n')

    def test_07_strict_patch_parser_and_damaged_storage_reject(self):
        self.adopt();original=paint(self.target)
        changes=[lambda a:a.update(capabilityVersion=True),lambda a:a.update(expectedCanvasRevision=0.5),lambda a:a.update(extra=1),
                 lambda a:a.update(patch=[]),lambda a:a.update(patch=[{'x':True,'y':1,'color':'river'}]),
                 lambda a:a.update(patch=[{'x':5,'y':1,'color':'river'}]),lambda a:a.update(patch=[{'x':1,'y':1,'color':'unknown'}]),
                 lambda a:a.update(patch=[{'x':1,'y':1,'color':'river'}]*2)]
        for mutate in changes:
            a=deepcopy(original);mutate(a);request=self.intent(self.b,a);status,_=self.b.request('POST',self.b.prefix+'/commands',request)
            self.assertEqual(400,status)
        self.assertEqual(0,self.b.observe()['entityCanvas']['revision'])
        self.world.stop()
        corruptions=["DROP TRIGGER immutable_canvas_edit_update", "DELETE FROM entity_canvas_cells WHERE x=0 AND y=0",
                     "UPDATE entity_canvas_cells SET color='river' WHERE x=0 AND y=0", "PRAGMA user_version=11"]
        for i,sql in enumerate(corruptions):
            w=CanvasWorld(self.world.data,RUN/self._testMethodName/('damage-'+str(i)),start=False);self.worlds.append(w);self.addCleanup(w.stop);w.corrupted=True
            with sqlite3.connect(w.data/'world.db') as c:
                if i==2:c.execute('PRAGMA ignore_check_constraints=ON')
                c.execute(sql)
            before=rows(w.data);result=subprocess.run(['dotnet',str(DLL)],cwd=ROOT,env=w.env,capture_output=True,text=True,timeout=15)
            self.assertNotEqual(0,result.returncode);self.assertNotEqual(0,w.adopt_canvas(self.instance,self.target).returncode);self.assertEqual(before,rows(w.data))
        self.world.start()

    def test_08_old_binary_refuses_new_storage_old_requests_remain_exact(self):
        if OLD_DLL is None:self.skipTest('ENTITY_CANVAS_OLD_DLL required for actual old service check')
        request=self.intent(self.b,{'type':'walk','to':self.b.observe()['self']['position']});old=self.post(self.b,request)
        unsent=self.intent(self.c,{'type':'walk','to':self.c.observe()['self']['position']})
        self.adopt();self.assertEqual(old,self.post(self.b,request));self.post(self.c,unsent)
        self.world.stop();before=rows(self.world.data)
        process=subprocess.run(['dotnet',str(OLD_DLL)],cwd=ROOT,env=self.world.env,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(0,process.returncode);self.assertEqual(before,rows(self.world.data));self.world.start()

    def test_09_real_sqlite_numbers_cannot_be_truncated_to_canvas_facts(self):
        self.adopt();self.walk(self.z,self.position);self.send(self.z,paint(self.target));self.world.stop()
        cases = [('entity_canvas_edits',name) for name in ('base_revision','revision','state_version','event_seq','inventory_wood')]
        cases += [('entity_canvas_cells',name) for name in ('x','y','state_version')]
        cases += [('entity_canvas',name) for name in ('version','state_version','event_seq','revision')]
        for table,column in cases:
            with self.subTest(table=table,column=column):
                w=CanvasWorld(self.world.data,RUN/self._testMethodName/(table+'-'+column),start=False)
                self.worlds.append(w);self.addCleanup(w.stop);w.corrupted=True
                with sqlite3.connect(w.data/'world.db') as c:
                    c.execute('PRAGMA ignore_check_constraints=ON')
                    triggers=c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",(table,)).fetchall()
                    for name,_ in triggers:c.execute('DROP TRIGGER '+name)
                    where="author_actor_id IS NOT NULL" if table=='entity_canvas_cells' else '1=1'
                    c.execute(f'UPDATE {table} SET {column}={column}+0.5 WHERE {where}')
                    for _,sql in triggers:c.execute(sql)
                    self.assertTrue(c.execute(f"SELECT count(*) FROM {table} WHERE typeof({column})='real'").fetchone()[0])
                before=rows(w.data)
                self.assertNotEqual(0,w.adopt_canvas(self.instance,self.target).returncode)
                process=subprocess.run(['dotnet',str(DLL)],cwd=ROOT,env=w.env,capture_output=True,text=True,timeout=15)
                self.assertNotEqual(0,process.returncode)
                self.assertEqual(before,rows(w.data))


if __name__=='__main__':
    RUN.mkdir(parents=True,exist_ok=True);dll_before=digest(DLL)
    suite=(unittest.TestSuite(EntityCanvasAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:] else unittest.defaultTestLoader.loadTestsFromTestCase(EntityCanvasAcceptance))
    result=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(suite)
    report={'passed':result.wasSuccessful(),'testsRun':result.testsRun,'tests':result.records,'failures':[str(e) for _,e in result.failures+result.errors],
            'skipped':result.skipped,'actualModelCalls':0,'sourceDll':str(DLL),'dllSha256':dll_before,'dllStable':digest(DLL)==dll_before,
            'baseline':str(getattr(EntityCanvasAcceptance,'source','')),'target':getattr(EntityCanvasAcceptance,'target',None)}
    (RUN/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Evidence:',RUN/'results.json',flush=True)
    raise SystemExit(not report['passed'])
