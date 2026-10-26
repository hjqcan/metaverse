#!/usr/bin/env python3
"""Actual HTTP and stopped-database acceptance for scattered, resource-gathering residents."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate, ActivityAcceptance
from foundation_api import FoundationAcceptance, EvidenceResult, ROOT
from foundation_agent import WorldClient
from resident_mission import _public, _route_info

RUN_ROOT=ROOT/'.local/iter0010/api'/(datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6])
activities_api.RUN_ROOT=RUN_ROOT
WEST='tree-west-north'; SOUTH='tree-west-south'; EAST='tree-east-south'

class WildernessAcceptance(unittest.TestCase):
    send=FoundationAcceptance.send
    intent=ActivityAcceptance.intent
    walk=ActivityAcceptance.walk
    def setUp(self):
        self.world=ActivityCandidate(self._testMethodName,scenario='wilderness-v1')
        self.a,self.b=self.world.client(),self.world.client('a2');self.trace=[]

    def tearDown(self):
        (self.world.data/'trace.json').write_text(json.dumps(self.trace,ensure_ascii=True,indent=2)+'\n')
        self.world.stop()
        with sqlite3.connect(f'file:{self.world.data / "world.db"}?mode=ro',uri=True) as db:
            self.assertEqual([],db.execute('PRAGMA foreign_key_check').fetchall())
            balances=defaultdict(int)
            for src,dst,quantity in db.execute('SELECT source_account,destination_account,quantity FROM resource_ledger ORDER BY id'):
                if src!='initial-issuance':balances[src]-=quantity
                balances[dst]+=quantity
            wild=db.execute('SELECT sum(remaining_wood) FROM resource_nodes').fetchone()[0]
            self.assertEqual(wild,balances.pop('wild-wood',0));self.assertEqual(0,balances.pop('depot',0))
            total=wild
            for actor,wood in db.execute('SELECT actor_id,wood FROM residents'):
                self.assertEqual(wood,balances.pop('inventory:'+actor,0));total+=wood
            for entity,wood in db.execute('SELECT entity_id,embodied_wood FROM entities'):
                self.assertEqual(wood,balances.pop('entity:'+entity,0));total+=wood
            self.assertEqual({},dict(balances));self.assertEqual(12,total)
            gathered=defaultdict(int)
            for encoded,seq in db.execute('SELECT event_json,seq FROM events'):
                event=json.loads(encoded)
                if event['type']!='gathered':continue
                gathered[event['nodeId']]+=event['quantity']
                receipt=json.loads(db.execute('SELECT result_json FROM receipts WHERE actor_id=? AND command_id=?',(event['actorId'],event['commandId'])).fetchone()[0])
                self.assertEqual(('committed','gather',event['nodeId'],1),(receipt['status'],receipt['result']['action'],receipt['result']['nodeId'],receipt['result']['quantity']))
                self.assertEqual(('wild-wood','inventory:'+event['actorId'],1),db.execute('SELECT source_account,destination_account,quantity FROM resource_ledger WHERE event_seq=?',(seq,)).fetchone())
            for node,initial,remaining in db.execute('SELECT node_id,initial_wood,remaining_wood FROM resource_nodes'):
                self.assertEqual(initial-gathered[node],remaining)
            version=db.execute('SELECT state_version FROM worlds').fetchone()[0]
            self.assertEqual(version+1,db.execute('SELECT count(*) FROM events').fetchone()[0])

    def audit(self,client=None):
        o=(client or self.a).observe();a=o['resourceAudit']
        self.assertTrue(a['conserved']);self.assertEqual(12,sum(a[k] for k in ('wildWood','depotWood','inventoryWood','embodiedWood')))
        self.assertEqual(sum(n['remainingWood'] for n in o['resourceNodes']),a['wildWood'])
        return o

    def gather(self,client=None,node=WEST,count=1):
        for _ in range(count):self.send(client or self.a,{'type':'gather','nodeId':node})

    def bridge(self):
        self.gather(count=3);self.walk(self.a,[1,5]);self.gather(node=SOUTH,count=3)
        self.walk(self.a,[3,3]);self.send(self.a,{'type':'build','recipeId':'bridge.v1','at':[4,3]})
        self.walk(self.a,[4,3]);self.send(self.a,{'type':'build','recipeId':'bridge.v1','at':[5,3]})

    def test_01_scattered_empty_hands_natural_sources_and_no_prefabricated_services(self):
        o=self.audit();b=self.audit(self.b)
        self.assertEqual(('r7','wilderness-v1'),(o['rulesVersion'],o['world']['scenarioId']))
        self.assertEqual(([1,1],[6,6]),(o['self']['position'],b['self']['position']))
        self.assertEqual((0,0,0,False),(o['self']['inventory']['wood'],b['self']['inventory']['wood'],o['depot']['wood'],o['depot']['available']))
        self.assertEqual([],o['entities']);self.assertEqual(4,len(o['resourceNodes']));self.assertIsNone(o['mosaic']);self.assertEqual([],o['postcards'])
        self.assertEqual(['林间空地','河岸','对岸林地'],[p['label'] for p in o['activities']])
        self.assertEqual(7,sqlite3.connect(self.world.data/'world.db').execute('PRAGMA user_version').fetchone()[0])
        self.assertEqual({'publicWood':0,'ownWood':0,'depotPosition':[1,1],'depotAvailable':False,'wildWood':12},o['entryGuide']['materials'])

    def test_02_public_claim_and_build_without_collected_wood_are_rejected(self):
        before=self.audit()
        _,r=self.send(self.a,{'type':'claim','quantity':3},expected=422);self.assertEqual('NO_PUBLIC_DEPOT',r['error']['code'])
        self.send(self.a,{'type':'build','recipeId':'platform.v1','at':[2,1]},expected=422)
        self.assertEqual(before,self.audit())

    def test_03_gather_depletes_source_unblocks_land_and_build_spends_actual_inventory(self):
        self.send(self.a,{'type':'move','dx':-1,'dy':0},expected=422)
        self.send(self.a,{'type':'build','recipeId':'platform.v1','at':[0,1]},expected=409)
        self.gather(count=3);o=self.audit();self.assertEqual(3,o['self']['inventory']['wood']);self.assertNotIn([0,1],o['world']['blocked'])
        _,r=self.send(self.a,{'type':'gather','nodeId':WEST},expected=422);self.assertEqual('RESOURCE_DEPLETED',r['error']['code'])
        self.send(self.a,{'type':'build','recipeId':'platform.v1','at':[0,1]});self.walk(self.a,[0,1]);o=self.audit()
        self.assertEqual((9,0,3),(o['resourceAudit']['wildWood'],o['self']['inventory']['wood'],o['resourceAudit']['embodiedWood']))

    def test_04_distance_unknown_node_strict_fields_and_identity(self):
        before=self.audit()
        for action,status,code in [({'type':'gather','nodeId':EAST},422,'UNREACHABLE'),({'type':'gather','nodeId':'missing'},404,'RESOURCE_NOT_FOUND')]:
            _,r=self.send(self.a,action,expected=status);self.assertEqual(code,r['error']['code'])
        for extra,status in [({'quantity':12},400),({'actorId':'a2'},403),({'nodeId':''},400)]:
            req=self.intent(self.a,{'type':'gather','nodeId':WEST,**extra});self.assertEqual(status,self.a.command(req)[0])
        self.assertEqual(401,WorldClient(self.world.url,'invalid').request('GET',self.a.prefix+'/observation')[0])
        self.assertEqual(before,self.audit())

    def test_05_original_command_replay_has_one_receipt_and_changed_node_conflicts(self):
        req=self.intent(self.a,{'type':'gather','nodeId':WEST},command_id='one-cut')
        with ThreadPoolExecutor(max_workers=4) as pool:replies=list(pool.map(lambda _:self.a.command(req),range(4)))
        self.assertTrue(all(r==replies[0] for r in replies));self.assertEqual(200,replies[0][0]);self.assertEqual(1,self.audit()['self']['inventory']['wood'])
        self.assertEqual(replies[0],self.a.command({**req,'action':{'nodeId':WEST,'type':'gather'}}))
        r=self.a.command({**req,'action':{'type':'gather','nodeId':SOUTH}});self.assertEqual((409,'IDEMPOTENCY_CONFLICT'),(r[0],r[1]['error']['code']))
        self.assertEqual(replies[0],self.a.request('GET',self.a.prefix+'/commands/one-cut'));self.assertEqual(404,self.b.request('GET',self.b.prefix+'/commands/one-cut')[0])

    def test_06_failure_after_tree_debit_rolls_back_every_material_fact(self):
        before=self.audit();req=self.intent(self.a,{'type':'gather','nodeId':WEST})
        status,r=self.a.request('POST',self.a.prefix+'/commands',req,{'X-Test-Fault':'throw-after-debit'})
        self.assertEqual(503,status);self.assertIsNone(r['error']['mutated']);self.assertEqual(before,self.audit())
        self.assertEqual(404,self.a.request('GET',self.a.prefix+'/commands/'+req['commandId'])[0]);self.assertEqual(200,self.a.command(req)[0]);self.assertEqual(1,self.audit()['self']['inventory']['wood'])

    def crash(self,point,code,committed):
        before=self.audit();req=self.intent(self.a,{'type':'gather','nodeId':WEST})
        try:self.a.request('POST',self.a.prefix+'/commands',req,{'X-Test-Fault':point})
        except (OSError,ValueError):pass
        self.assertEqual(code,self.world.process.wait(timeout=10));self.world.restart()
        self.assertEqual(before['stateVersion']+int(committed),self.audit()['stateVersion'])
        self.assertEqual(200,self.a.command(req)[0]);self.assertEqual((1,1),(self.audit()['stateVersion'],self.audit()['self']['inventory']['wood']))

    def test_07_exit_before_commit_keeps_tree_and_inventory_atomic(self):self.crash('before-commit',81,False)
    def test_08_exit_after_commit_recovers_original_cut_once(self):self.crash('after-commit',82,True)

    def test_09_two_actors_compete_for_final_unit(self):
        self.bridge();self.walk(self.a,[6,6]);self.gather(self.b,EAST,2)
        requests=[(c,self.intent(c,{'type':'gather','nodeId':EAST})) for c in (self.a,self.b)]
        with ThreadPoolExecutor(max_workers=2) as pool:replies=list(pool.map(lambda pair:pair[0].command(pair[1]),requests))
        self.assertEqual([200,409],sorted(r[0] for r in replies));loser=self.a if replies[0][0]!=200 else self.b
        _,r=self.send(loser,{'type':'gather','nodeId':EAST},expected=422);self.assertEqual('RESOURCE_DEPLETED',r['error']['code'])
        self.assertEqual((3,3,6),(self.audit()['resourceAudit']['wildWood'],self.audit()['resourceAudit']['inventoryWood'],self.audit()['resourceAudit']['embodiedWood']))

    def test_10_collection_builds_shared_bridge_and_other_resident_reuses_it(self):
        initial=self.audit();self.bridge();built=self.audit();before=self.b.observe();origin=before['self']['position'];self.walk(self.b,[1,1]);self.walk(self.b,origin);after=self.audit(self.b)
        self.assertEqual(built['entities'],after['entities']);self.assertEqual(0,after['self']['inventory']['wood']);self.assertEqual(6,after['resourceAudit']['wildWood'])
        self.assertTrue(all(e['ownerActorId']=='a1' for e in after['entities']))
        evidence={'kind':'program-gather-build-and-reuse','actualModelCalls':0,'initialResidents':initial['residents'],'initialInventoryWood':0,'initialWildWood':12,'builderGatheredWood':6,'builderBridges':built['entities'],'travelerOrigin':origin,'travelerReached':[1,1],'travelerReturned':after['self']['position']==origin,'travelerInventoryWood':0,'finalResourceAudit':after['resourceAudit']}
        (self.world.data/'gather-build-reuse.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')

    def test_11_restart_never_refills_depleted_trees_or_resets_scattered_residents(self):
        self.gather(count=3);self.walk(self.b,[6,5]);before=self.audit();dump=self.world.dump();events=self.a.request('GET',self.a.prefix+'/events?after=0')
        self.world.restart();self.assertEqual(before,self.audit());self.assertEqual(dump,self.world.dump());self.assertEqual(events,self.a.request('GET',self.a.prefix+'/events?after=0'))

    def test_12_guide_routes_respect_live_trees_and_update_after_felling(self):
        o=self.audit();self.assertFalse(next(p for p in o['entryGuide']['places'] if p['id']=='riverwalk')['reachable'])
        self.walk(self.a,[1,5]);self.gather(node=SOUTH,count=3);o=self.audit()
        self.assertTrue(next(p for p in o['entryGuide']['places'] if p['id']=='riverwalk')['reachable'])
        for p in o['entryGuide']['places']:
            for cell in p['route']:self.assertNotIn(cell,o['world']['blocked'])

    def test_13_old_scenarios_and_populated_r6_are_not_migrated_or_given_trees(self):
        for scenario in ('foundation-v1','passage-v1','activities-v1','postcards-v1','mosaic-v1','consent-v1'):
            other=ActivityCandidate(self._testMethodName+'-'+scenario,scenario=scenario)
            try:
                c=other.client();o=c.observe();self.assertNotIn('resourceNodes',o);self.assertEqual(12,o['depot']['wood']);req=self.intent(c,{'type':'gather','nodeId':WEST});status,r=c.command(req)
                self.assertEqual((422,'GATHERING_UNAVAILABLE'),(status,r['error']['code']));self.assertEqual(o,c.observe())
            finally:other.stop()
        other=ActivityCandidate(self._testMethodName+'-fixture',scenario=None,fixture='consent-v6-populated.sql')
        try:
            c=WorldClient(other.url,'fixture-r6-a1');self.assertEqual('r6',c.observe()['rulesVersion']);self.assertEqual(other.fixture_before,other.dump())
        finally:other.stop()

    def test_14_public_context_has_natural_sources_without_claiming_automatic_collection(self):
        o=self.audit();o['resourceNodes'][0]['token']='never-export';o['gathering']['secret']='never-export';p=_public(o)
        self.assertNotIn('never-export',json.dumps(p));self.assertEqual(4,len(p['resourceNodes']));self.assertFalse(p['depot']['available']);self.assertEqual(12,p['entryGuide']['materials']['wildWood'])
        self.assertEqual('natural_material_collection_required',_route_info(o,[6,1],True)['reason'])

    def test_15_completed_wood_sources_do_not_regenerate_and_unsupported_creative_services_stay_absent(self):
        self.bridge();self.walk(self.a,[6,1]);self.gather(node='tree-east-north',count=3);self.gather(self.b,EAST,3)
        o=self.audit();self.assertEqual(0,o['resourceAudit']['wildWood']);self.world.restart();self.assertEqual(o,self.audit())
        self.assertEqual(422,self.a.request('GET',self.a.prefix+'/mosaic-proposals')[0]);self.assertEqual(0,o['depot']['wood'])

    def test_16_fresh_unspecified_world_defaults_to_wilderness(self):
        other=ActivityCandidate(self._testMethodName+'-default',scenario=None)
        try:
            o=other.client().observe();self.assertEqual('wilderness-v1',o['world']['scenarioId']);self.assertEqual(0,o['depot']['wood']);self.assertEqual([6,6],other.client('a2').observe()['self']['position'])
            other.restart();self.assertEqual(o,other.client().observe())
        finally:other.stop()

if __name__=='__main__':
    RUN_ROOT.mkdir(parents=True,mode=0o700)
    result=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(WildernessAcceptance))
    evidence={'suite':'wilderness-http-v1','recordedAtUtc':datetime.now(timezone.utc).isoformat(),'passed':result.wasSuccessful(),'testsRun':result.testsRun,'tests':result.records,'actualModelCalls':0,'decisionSource':'explicit-fixed-program','dataRoot':str(RUN_ROOT.relative_to(ROOT)),'failures':[{'test':str(t),'detail':d} for t,d in result.failures+result.errors]}
    (RUN_ROOT/'results.json').write_text(json.dumps(evidence,ensure_ascii=True,indent=2)+'\n');print('Evidence:',RUN_ROOT/'results.json');raise SystemExit(0 if result.wasSuccessful() else 1)
