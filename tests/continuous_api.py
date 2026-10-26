#!/usr/bin/env python3
"""Continuous movement, collision, real-time speed, persistence and resource accounting via HTTP."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import sqlite3
import time
import unittest
import uuid
import activities_api
from activities_api import ActivityCandidate
from foundation_api import ROOT, EvidenceResult

RUN = ROOT/'.local/iter0014/api'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
activities_api.RUN_ROOT=RUN

class ContinuousAcceptance(unittest.TestCase):
    def setUp(self):
        self.world=ActivityCandidate(self._testMethodName,scenario='wilderness-continuous-v1')
        self.a,self.b=self.world.client(),self.world.client('a2')
        self.trace=[]
    def tearDown(self):
        (self.world.data/'trace.json').write_text(json.dumps(self.trace,indent=2))
        self.world.stop()
        with sqlite3.connect(self.world.data/'world.db') as db:
            self.assertEqual([],db.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(12,sum(db.execute(q).fetchone()[0] for q in ('SELECT sum(remaining_wood) FROM resource_nodes','SELECT sum(wood) FROM residents','SELECT coalesce(sum(embodied_wood),0) FROM entities')))
            version=db.execute('SELECT state_version FROM worlds').fetchone()[0]
            self.assertEqual(version+1,db.execute('SELECT count(*) FROM events').fetchone()[0])
            self.assertEqual(version,db.execute("SELECT count(*) FROM receipts WHERE json_extract(result_json,'$.status')='committed'").fetchone()[0])
    def intent(self,action,client=None):
        c=client or self.a;o=c.observe()
        return dict(schemaVersion=1,rulesVersion='r8',commandId=uuid.uuid4().hex,expectedStateVersion=o['stateVersion'],action=action)
    def send(self,action,client=None,status=200):
        c=client or self.a;request=self.intent(action,c);code,result=c.command(request)
        self.trace.append({'request':request,'status':code,'result':result})
        self.assertEqual(status,code,result)
        return result
    def walk(self,target,client=None,blocked=False):
        c=client or self.a
        for _ in range(400):
            p=c.observe()['self']['position']
            if math.dist(p,target)<1e-7:return p
            r=self.send({'type':'walk','to':target},c)
            if r['result']['blocked']:
                self.assertTrue(blocked,r);return r['result']['position']
            time.sleep(.08)
        self.fail('walk deadline')
    def gather(self,node='tree-west-north',count=3):
        for _ in range(count):self.send({'type':'gather','nodeId':node})
    def test_01_observation_is_continuous_and_old_grid_is_absent(self):
        o=self.a.observe();self.assertEqual('r8',o['rulesVersion']);self.assertEqual('continuous-xz',o['world']['coordinateSystem'])
        self.assertNotIn('blocked',o['world']);self.assertNotIn('entryGuide',o)
        self.assertEqual([5,7],o['self']['position']);self.assertGreater(len(o['terrain']['river']['polygon']),14)
        self.assertEqual(4,len(o['resourceNodes']));self.assertTrue(o['resourceAudit']['conserved'])
        self.assertEqual([3,6],[r['woodCost'] for r in o['recipes']])
    def test_02_fractional_diagonal_coordinates_persist_across_restart(self):
        r=self.send({'type':'walk','to':[5.12,6.86]});self.assertEqual([5.12,6.86],r['result']['position'])
        before=self.a.observe();self.world.restart();self.assertEqual(before,self.a.observe())
    def test_03_speed_budget_prevents_spam_teleport(self):
        start=time.monotonic()
        for _ in range(35):self.send({'type':'walk','to':[5,1000]})
        elapsed=time.monotonic()-start;p=self.a.observe()['self']['position']
        self.assertLessEqual(math.dist([5,7],p),.6+3*elapsed+.035)
    def test_04_tree_blocks_sweep_and_depletion_removes_collision(self):
        p=self.walk([6.2,7.8],blocked=True);self.assertGreaterEqual(math.dist(p,[6.2,7.8]),.73-1e-6)
        self.gather();self.walk([6.2,7.8]);self.assertEqual(3,self.a.observe()['self']['inventory']['wood'])
    def test_05_rock_and_river_stop_motion(self):
        self.walk([9,7]);p=self.walk([10.5,8.5],blocked=True)
        self.assertGreaterEqual(math.dist(p,[10.5,8.5]),1.33-1e-6)
        self.walk([9,6.5]);p=self.walk([25,6.5],blocked=True)
        self.assertLess(p[0],15.6)
    def test_06_world_boundary_is_continuous(self):
        p=self.walk([-100,7],blocked=True);self.assertAlmostEqual(.28,p[0],delta=.00003)
    def test_07_replay_and_concurrent_same_id_move_once(self):
        req=self.intent({'type':'walk','to':[5.25,7]})
        with ThreadPoolExecutor(max_workers=4) as pool:replies=list(pool.map(lambda _:self.a.command(req),range(4)))
        self.assertTrue(all(r==replies[0] for r in replies));self.assertEqual([5.25,7],self.a.observe()['self']['position'])
        self.assertEqual(replies[0],self.a.request('GET',self.a.prefix+'/commands/'+req['commandId']))
        changed={**req,'action':{'type':'walk','to':[5.251,7]}}
        self.assertEqual('IDEMPOTENCY_CONFLICT',self.a.command(changed)[1]['error']['code'])
    def test_08_legacy_move_stale_and_invalid_coordinates_fail_without_effect(self):
        before=self.a.observe();r=self.send({'type':'move','dx':1,'dy':0},status=422)
        self.assertEqual('CONTINUOUS_MOVEMENT_REQUIRED',r['error']['code'])
        for value in ([1e99,2],['5',2],[1],None):self.assertEqual(400,self.a.command(self.intent({'type':'walk','to':value}))[0])
        req=self.intent({'type':'walk','to':[5.1,7]});self.send({'type':'walk','to':[26.1,17]},self.b)
        self.assertEqual('STALE_STATE',self.a.command(req)[1]['error']['code']);self.assertEqual(before['self'],self.a.observe()['self'])
    def test_09_fractional_platform_uses_collected_wood_and_preserves_history(self):
        self.gather();self.send({'type':'build','recipeId':'platform.v1','at':[3.75,7.1]})
        o=self.a.observe();self.assertEqual([3.75,7.1],o['entities'][0]['position']);self.assertEqual(0,o['self']['inventory']['wood'])
        self.world.restart();self.assertEqual(o,self.a.observe())
    def test_10_build_checks_complete_footprint_and_gather_distance(self):
        self.gather();r=self.send({'type':'build','recipeId':'platform.v1','at':[.5,7]},status=422)
        self.assertEqual('UNREACHABLE',r['error']['code'])
        self.send({'type':'gather','nodeId':'tree-east-north'},status=422)
        self.walk([9,7]);self.send({'type':'build','recipeId':'platform.v1','at':[10.1,8]},status=409)
    def test_11_real_bridge_allows_both_residents_to_cross(self):
        self.gather();self.walk([8,15.5]);self.gather('tree-west-south')
        self.walk([12,15]);self.walk([15.7,12])
        self.send({'type':'build','recipeId':'bridge.v1','at':[18,12]})
        self.walk([20.7,12]);self.assertEqual(0,self.a.observe()['self']['inventory']['wood'])
        for p in ([27,13],[25,10],[21,10],[20.8,12],[15,12]):self.walk(p,self.b)
        o=self.b.observe();self.assertEqual(0,o['self']['inventory']['wood']);self.assertEqual(6,o['resourceAudit']['embodiedWood'])
        (self.world.data/'crossing.json').write_text(json.dumps(o,indent=2))
    def test_12_failed_gather_and_commit_loss_preserve_original_identity(self):
        req=self.intent({'type':'gather','nodeId':'tree-west-north'});before=self.a.observe()
        status,result=self.a.request('POST',self.a.prefix+'/commands',req,{'X-Test-Fault':'throw-after-debit'})
        self.assertEqual(503,status);self.assertIsNone(result['error']['mutated']);self.assertEqual(before,self.a.observe())
        try:self.a.request('POST',self.a.prefix+'/commands',req,{'X-Test-Fault':'after-commit'})
        except (OSError,ValueError):pass
        self.assertEqual(82,self.world.process.wait(timeout=10));self.world.restart()
        receipt=self.a.request('GET',self.a.prefix+'/commands/'+req['commandId'])
        self.assertEqual(receipt,self.a.command(req));self.assertEqual(1,self.a.observe()['self']['inventory']['wood'])

if __name__=='__main__':
    RUN.mkdir(parents=True,exist_ok=True)
    result=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContinuousAcceptance))
    (RUN/'results.json').write_text(json.dumps({'passed':result.wasSuccessful(),'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'failureDetails':[(str(t),e) for t,e in result.failures+result.errors]},indent=2))
    print('Evidence:',RUN)
    raise SystemExit(not result.wasSuccessful())
