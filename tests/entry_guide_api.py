#!/usr/bin/env python3
"""Real HTTP and SQLite entry-guide acceptance; no external model calls."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3
import sys
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate, ActivityAcceptance, mission
from foundation_api import FoundationAcceptance, EvidenceResult, ROOT
from foundation_agent import WorldClient
from resident_mission import _public, run_mission
from resident_mission_api import Choice

RUN_ROOT=ROOT/'.local/iter0009/api'/(datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6])
activities_api.RUN_ROOT=RUN_ROOT

class EntryAcceptance(unittest.TestCase):
    send=FoundationAcceptance.send
    intent=ActivityAcceptance.intent
    walk=ActivityAcceptance.walk
    audit=FoundationAcceptance.audit
    tearDown=FoundationAcceptance.tearDown
    def setUp(self):
        self.world=ActivityCandidate(self._testMethodName,scenario='consent-v1')
        self.a,self.b=self.world.client(),self.world.client('a2');self.trace=[]

    def guide(self,client=None):
        o=(client or self.a).observe();g=o['entryGuide']
        self.assertEqual((1,o['stateVersion'],o['self']['actorId'],o['self']['position']),(g['version'],g['stateVersion'],g['actorId'],g['position']))
        for p in g['places']:
            cursor=g['position']
            for step in p['route']:
                self.assertEqual(1,sum(abs(a-b) for a,b in zip(cursor,step)));self.assertNotIn(step,o['world']['blocked']);cursor=step
            if p['reachable']:
                self.assertEqual(p['position'],cursor);self.assertEqual(len(p['route']),p['walkingSteps'])
                self.assertEqual([b['entityId'] for step in p['route'] for b in g['sharedBridges'] if step==b['position']],p['bridgeEntityIds'])
            else:self.assertEqual((None,[],[]),(p['walkingSteps'],p['route'],p['bridgeEntityIds']))
        return o,g

    def build(self,count=2):
        self.send(self.a,{'type':'claim','quantity':6})
        self.walk(self.a,[3,3]);self.send(self.a,{'type':'build','recipeId':'bridge.v1','at':[4,3]})
        if count==2:
            self.send(self.a,{'type':'move','dx':1,'dy':0});self.send(self.a,{'type':'build','recipeId':'bridge.v1','at':[5,3]})

    def test_01_unbuilt_recipe_does_not_claim_existing_access(self):
        o,g=self.guide();self.assertEqual([],g['sharedBridges'])
        self.assertEqual([True,True,False],[p['reachable'] for p in g['places']]);self.assertEqual([5,5,None],[p['walkingSteps'] for p in g['places']])
        self.assertEqual({'publicWood':12,'ownWood':0,'depotPosition':[1,1]},g['materials'])
        self.assertEqual(0,o['stateVersion']);self.assertTrue(g['participation']['foreignMosaicNeedsConsent'])

    def test_02_one_bridge_is_not_a_complete_route(self):
        self.build(1);_,g=self.guide(self.b);self.assertEqual(1,len(g['sharedBridges']));self.assertFalse(g['places'][2]['reachable'])
        self.walk(self.a,[4,3]);_,g=self.guide();self.assertFalse(g['places'][2]['reachable']);self.assertTrue(g['places'][0]['reachable'])

    def test_03_later_resident_reuses_actual_bridges_without_material_or_rebuilding(self):
        self.build();before=self.a.observe();o,g=self.guide(self.b);self.assertEqual([],o['self']['visits'])
        destination=g['places'][2];self.assertTrue(destination['reachable']);self.assertEqual(2,len(destination['bridgeEntityIds']));self.assertTrue(all(b['ownerActorId']=='a1' for b in g['sharedBridges']))
        origin=o['self']['position'];steps=0
        for next_cell in destination['route']:
            current=self.b.observe()['self']['position'];self.send(self.b,{'type':'move','dx':next_cell[0]-current[0],'dy':next_cell[1]-current[1]});steps+=1
        self.send(self.b,{'type':'visit','activityId':'lookout'})
        self.walk(self.b,origin);after=self.b.observe()
        self.assertEqual(before['entities'],after['entities']);self.assertEqual(before['resourceAudit'],after['resourceAudit']);self.assertEqual(0,after['self']['inventory']['wood'])
        evidence={'kind':'program-late-entry','decisionSource':'fixed-program-following-actual-guide','actualModelCalls':0,'constructionStateVersion':before['stateVersion'],'entryGuide':g,'outboundSteps':steps,'visited':after['self']['visits'][-1],'returned':after['self']['position']==origin,'finalResourceAudit':after['resourceAudit'],'originalBridgesPreserved':before['entities']==after['entities']}
        (self.world.data/'late-entry.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')

    def test_04_here_zero_steps_and_identity_specific_routes(self):
        self.walk(self.a,[1,6]);_,g=self.guide();self.assertEqual((True,0,[]),(g['places'][0]['reachable'],g['places'][0]['walkingSteps'],g['places'][0]['route']))
        _,peer=self.guide(self.b);self.assertEqual(4,peer['places'][0]['walkingSteps']);self.assertEqual('a2',peer['actorId'])

    def test_05_empty_shared_stock_is_reported_but_free_participation_remains(self):
        self.send(self.a,{'type':'claim','quantity':12});_,g=self.guide(self.b)
        self.assertEqual({'publicWood':0,'ownWood':0,'depotPosition':[1,1]},g['materials']);self.assertEqual(0,g['participation']['walkWoodCost']);self.assertTrue(g['participation']['postcardSupported'])
        self.send(self.b,{'type':'claim','quantity':1},expected=422);self.walk(self.b,[1,6]);_,v=self.send(self.b,{'type':'visit','activityId':'garden'})
        self.send(self.b,{'type':'postcard','activityId':'garden','visitCommandId':v['commandId'],'text':'没领到木材，仍可以来到花园写下自己的故事。'})
        self.assertEqual(0,self.b.observe()['self']['inventory']['wood']);self.assertEqual(12,self.a.observe()['self']['inventory']['wood'])

    def test_06_reading_and_restart_leave_complete_logical_database_unchanged(self):
        self.build();before=self.world.dump();a=self.a.observe();b=self.b.observe()
        for _ in range(5):self.guide();self.guide(self.b)
        self.assertEqual(before,self.world.dump());self.world.restart();self.assertEqual(a,self.a.observe());self.assertEqual(b,self.b.observe());self.assertEqual(before,self.world.dump())

    def test_07_old_scenarios_and_populated_database_keep_rules_and_materials(self):
        for scenario,expected in [('foundation-v1',(False,False,False,False)),('passage-v1',(False,False,False,False)),('activities-v1',(True,False,False,False)),('postcards-v1',(True,True,False,False)),('mosaic-v1',(True,True,True,False))]:
            world=ActivityCandidate('old-'+scenario,scenario=scenario)
            try:
                before=world.dump();o=world.client().observe();p=o['entryGuide']['participation'];self.assertEqual(expected,tuple(p[k] for k in ['visitSupported','postcardSupported','mosaicSupported','foreignMosaicNeedsConsent']));self.assertEqual(before,world.dump())
            finally:world.stop()
        world=ActivityCandidate('old-populated',scenario=None,fixture='passage-v2-populated.sql')
        try:
            self.assertEqual(world.fixture_before,world.dump());o=world.client().observe();self.assertEqual('r2',o['rulesVersion']);self.assertTrue(o['entryGuide']['places'][0]['reachable']);self.assertEqual(2,len(o['entryGuide']['sharedBridges']));self.assertEqual(world.fixture_before,world.dump())
        finally:world.stop()

    def test_08_public_model_input_uses_whitelist_and_legacy_service_remains_usable(self):
        self.build();o=self.b.observe();g=o['entryGuide'];g['token']='never-export';g['materials']['secret']='never-export';g['sharedBridges'][0]['sessionId']='never-export';g['places'][0]['authorization']='never-export';g['participation']['privateInventory']='never-export'
        public=_public(o);self.assertNotIn('never-export',json.dumps(public));self.assertEqual(2,len(public['entryGuide']['sharedBridges']))
        public['entryGuide']['places'][0]['route'].clear();self.assertNotEqual(public['entryGuide'],o['entryGuide'])
        del o['entryGuide'];self.assertNotIn('entryGuide',_public(o))
        class Old(WorldClient):
            def observe(self):
                result=super().observe();result.pop('entryGuide');return result
        choice=Choice('garden');r=run_mission(Old(self.world.url,self.world.access['sessions']['a2']['token']),mission('legacy-entry',commands=12,wood=0),self.world.data/'legacy-state.json',choice)
        self.assertEqual('completed',r['mission']['status']);self.assertEqual(1,choice.calls)

    def test_09_new_task_receives_same_guide_before_actions(self):
        self.build();before=self.b.observe();calls=[]
        def choose(context):
            calls.append(deepcopy(context));self.assertEqual(before['entryGuide'],context['observation']['entryGuide']);return Choice('garden')(context)
        r=run_mission(self.b,mission('entry-context',commands=12,wood=0),self.world.data/'new-state.json',choose)
        self.assertEqual(1,len(calls));self.assertEqual('completed',r['mission']['status']);self.assertEqual(0,r['budget']['used']['wood'])

if __name__=='__main__':
    RUN_ROOT.mkdir(parents=True,mode=0o700)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(EntryAcceptance)
    result=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(suite)
    evidence={'suite':'entry-guide-http-v1','recordedAtUtc':datetime.now(timezone.utc).isoformat(),'passed':result.wasSuccessful(),'testsRun':result.testsRun,'tests':result.records,'actualModelCalls':0,'decisionSource':'explicit-program-and-test-double','dataRoot':str(RUN_ROOT.relative_to(ROOT)),'failures':[{'test':str(t),'detail':d} for t,d in result.failures+result.errors]}
    (RUN_ROOT/'results.json').write_text(json.dumps(evidence,ensure_ascii=True,indent=2)+'\n');print('Evidence:',RUN_ROOT/'results.json');raise SystemExit(0 if result.wasSuccessful() else 1)
