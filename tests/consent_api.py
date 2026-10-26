#!/usr/bin/env python3
"""Independent consent acceptance: actual HTTP/SQLite; explicit model test doubles."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import socket
import sqlite3
import sys
import unittest
import uuid

from foundation_api import Candidate, EvidenceResult, FoundationAcceptance, ROOT
from activities_api import ActivityAcceptance
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice

RUN_ROOT = ROOT / '.local/iter0007/api' / (datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6])
RIVER = [{'x': x, 'y': 2, 'color': 'river'} for x in [1, 2, 3]]
PATCH = [{'x': 1, 'y': 2, 'color': 'sun'}]


class ConsentCandidate(Candidate):
    def __init__(self, name, scenario='consent-v1', fixture=None):
        self.data = RUN_ROOT / name; self.data.mkdir(parents=True, mode=0o700)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.env = {**os.environ, 'WORLD_URL': self.url, 'WORLD_DATA_DIR': str(self.data), 'WORLD_ENABLE_FAULTS': '1'}
        self.env.pop('WORLD_SCENARIO', None)
        if scenario: self.env['WORLD_SCENARIO'] = scenario
        if fixture:
            with sqlite3.connect(self.data / 'world.db') as db: db.executescript((ROOT / 'tests/fixtures' / fixture).read_text())
            (self.data / 'access.json').write_text(json.dumps({'sessions': {a: {'token': 'fixture-r5-' + a} for a in ['a1', 'a2']}}))
            self.fixture_before = self.dump()
        self.process = self.log = None; self.start()
        self.access = json.loads((self.data / 'access.json').read_text())

    def dump(self):
        with sqlite3.connect(f'file:{self.data / "world.db"}?mode=ro', uri=True) as db:
            return db.execute('PRAGMA user_version').fetchone()[0], '\n'.join(db.iterdump())


def mission(role='proposer', proposal=None, commands=30, name=None):
    d = json.loads((ROOT / f'examples/consent/{role}.json').read_text())
    d['missionId'] = name or 'test-' + role; d['budgets']['commands'] = commands
    if proposal: d['reviewMosaicProposal'] = {'proposalActorId': proposal['authorActorId'], 'proposalCommandId': proposal['commandId']}
    return d


class ConsentChoice(Choice):
    def __init__(self, decision=None, patch=None):
        super().__init__('garden'); self.decision = decision; self.patch = deepcopy(patch or PATCH)
    def __call__(self, context):
        value = super().__call__(context)
        if self.decision: value.update(reviewDecision=self.decision, reviewText='保留河流，按约定决定。')
        else: value.update(mosaicPatch=deepcopy(self.patch), proposalText='建议只把这一端点改为日黄，留下阳光标记。')
        return value


class ConsentAcceptance(unittest.TestCase):
    audit = FoundationAcceptance.audit
    send = FoundationAcceptance.send
    intent = ActivityAcceptance.intent
    walk = ActivityAcceptance.walk

    def setUp(self):
        self.world = ConsentCandidate(self._testMethodName)
        self.a, self.b = self.world.client(), self.world.client('a2')
        self.trace, self.reports = [], []
        self.state = self.world.data / 'mission.json'

    def tearDown(self):
        (self.world.data / 'reports.json').write_text(json.dumps(self.reports, ensure_ascii=True, indent=2)+'\n')
        before = self.a.observe() if self.world.process.poll() is None else None
        FoundationAcceptance.tearDown(self)
        with sqlite3.connect(f'file:{self.world.data / "world.db"}?mode=ro', uri=True) as db:
            self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())
            events = [json.loads(r[0]) for r in db.execute('SELECT event_json FROM events ORDER BY state_version')]
            proposals = [e for e in events if e['type'] == 'mosaic_proposed']; reviews = [e for e in events if e['type'] == 'mosaic_reviewed']
            self.assertEqual(len(proposals), db.execute('SELECT count(*) FROM mosaic_proposals').fetchone()[0])
            self.assertEqual(len(reviews), db.execute('SELECT count(*) FROM mosaic_reviews').fetchone()[0])
            edits = [e if e['type'] == 'mosaic_painted' else e['mosaicEdit'] for e in events if e['type'] == 'mosaic_painted' or e['type'] == 'mosaic_reviewed' and e['decision'] == 'accept']
            self.assertEqual(len(edits), db.execute('SELECT count(*) FROM mosaic_edits').fetchone()[0])
            board = [{'x':i%5,'y':i//5,'color':'blank','authorActorId':None,'commandId':None,'stateVersion':None} for i in range(25)]
            for revision, edit in enumerate(edits, 1):
                self.assertEqual((revision-1, revision), (edit['baseRevision'],edit['revision']))
                for c in edit['patch']:
                    old = board[c['y']*5+c['x']];self.assertNotEqual(old['color'],c['color'])
                    self.assertIn(old['authorActorId'],[None,edit['authorActorId']])
                    board[c['y']*5+c['x']]={**c,**{k:edit[k] for k in ['authorActorId','commandId','stateVersion']}}
            for e in proposals + reviews:
                receipt=json.loads(db.execute('SELECT result_json FROM receipts WHERE actor_id=? AND command_id=?',(e['authorActorId'],e['commandId'])).fetchone()[0])
                self.assertEqual('committed',receipt['status'])
                for k,v in receipt['result'].items():
                    if k!='action':self.assertEqual(v,e[k])
            if before:self.assertEqual(board,before['mosaic']['cells']);self.assertEqual(len(edits),before['mosaic']['revision'])

    def visit(self, client):
        self.walk(client,(1,6)); return self.send(client,{'type':'visit','activityId':'garden'})[0]['commandId']
    def seed(self):
        v=self.visit(self.a)
        self.send(self.a,{'type':'mosaic','activityId':'garden','visitCommandId':v,'expectedMosaicRevision':0,'patch':deepcopy(RIVER)})
        self.walk(self.a,(1,1))
    def propose_action(self, visit, patch=None, base=None):
        return {'type':'mosaic_propose','activityId':'garden','visitCommandId':visit,'expectedMosaicRevision':self.a.observe()['mosaic']['revision'] if base is None else base,'patch':deepcopy(PATCH if patch is None else patch),'text':'建议在端点留一格阳光。'}
    def propose(self):
        v=self.visit(self.b);return self.send(self.b,self.propose_action(v))[1]['result']
    def review_action(self,p,visit,decision='accept'):
        return {'type':'mosaic_review','activityId':'garden','visitCommandId':visit,'proposalActorId':p['authorActorId'],'proposalCommandId':p['commandId'],'decision':decision,'text':'同意这次端点改动。' if decision=='accept' else '这次保留原来的河流。'}
    def task(self,spec,choose,client=None,**kwargs):
        r=run_mission(client or self.b,spec,self.state,choose,**kwargs);self.reports.append(r);return r

    def test_01_proposal_is_public_immutable_and_does_not_paint(self):
        self.seed();before=self.audit();p=self.propose();after=self.audit()
        self.assertEqual(before['mosaic'],after['mosaic']);self.assertEqual('a1',p['targetActorId'])
        self.assertEqual(p['patch'],PATCH);self.assertIsNone(after['mosaicProposals'][0]['review'])
        self.assertEqual(after['mosaicProposals'],self.b.observe()['self']['mosaicProposals']);self.assertEqual([],after['self']['mosaicProposals'])
        self.world.restart();self.assertEqual(after,self.audit())
        with sqlite3.connect(self.world.data/'world.db') as db:
            with self.assertRaises(sqlite3.DatabaseError):db.execute('DELETE FROM mosaic_proposals')

    def test_02_direct_edit_requires_consent_including_erased_foreign_cells(self):
        self.seed();v=self.visit(self.b);before=self.audit()
        _,r=self.send(self.b,{'type':'mosaic','activityId':'garden','visitCommandId':v,'expectedMosaicRevision':1,'patch':PATCH},expected=409)
        self.assertEqual('MOSAIC_CONSENT_REQUIRED',r['error']['code']);self.assertEqual(before,self.audit())
        av=self.visit(self.a);self.send(self.a,{'type':'mosaic','activityId':'garden','visitCommandId':av,'expectedMosaicRevision':1,'patch':[{'x':1,'y':2,'color':'blank'}]})
        _,r=self.send(self.b,{'type':'mosaic','activityId':'garden','visitCommandId':v,'expectedMosaicRevision':2,'patch':PATCH},expected=409)
        self.assertEqual('MOSAIC_CONSENT_REQUIRED',r['error']['code'])

    def test_03_proposal_shape_target_visit_and_one_per_visit(self):
        self.seed();v=self.visit(self.b)
        for patch in [[],PATCH*2,[{'x':True,'y':2,'color':'sun'}],[{'x':1,'y':2,'color':'sun','extra':1}]]:self.send(self.b,self.propose_action(v,patch),expected=400)
        for patch in [[{'x':0,'y':0,'color':'sun'}],PATCH+[{'x':0,'y':0,'color':'sun'}]]:
            _,r=self.send(self.b,self.propose_action(v,patch),expected=422);self.assertEqual('MOSAIC_PROPOSAL_TARGET_INVALID',r['error']['code'])
        _,r=self.send(self.a,self.propose_action(v),expected=422);self.assertEqual('NOT_AT_ACTIVITY',r['error']['code'])
        original,r=self.send(self.b,self.propose_action(v, PATCH+[{'x':3,'y':2,'color':'sun'}]))
        reordered=deepcopy(original);reordered['action']['patch'].reverse();self.assertEqual((200,r),self.b.command(reordered))
        changed=deepcopy(original);changed['action']['text']='另一份内容';self.assertEqual('IDEMPOTENCY_CONFLICT',self.b.command(changed)[1]['error']['code'])
        _,r=self.send(self.b,self.propose_action(v),expected=409);self.assertEqual('VISIT_ALREADY_PROPOSED',r['error']['code'])

    def test_04_accept_preserves_proposer_and_records_actual_reviewer_edit(self):
        self.seed();p=self.propose();v=self.visit(self.a);before=self.audit();_,r=self.send(self.a,self.review_action(p,v));edit=r['result']['mosaicEdit'];o=self.audit()
        self.assertEqual('a1',edit['authorActorId']);self.assertEqual('a2',r['result']['proposalActorId']);self.assertEqual(v,edit['visitCommandId'])
        self.assertEqual(PATCH,edit['patch']);self.assertEqual(2,o['mosaic']['revision']);self.assertEqual(edit['commandId'],o['mosaic']['cells'][11]['commandId'])
        self.assertEqual(before['resourceAudit'],o['resourceAudit']);self.assertEqual(r['result']['decision'],o['mosaicProposals'][0]['review']['decision'])
        self.world.restart();self.assertEqual(o,self.audit())
        with sqlite3.connect(self.world.data/'world.db') as db:
            with self.assertRaises(sqlite3.DatabaseError):db.execute('DELETE FROM mosaic_reviews')

    def test_05_reject_does_not_paint_and_cannot_be_reopened(self):
        self.seed();p=self.propose();v=self.visit(self.a);before=self.audit();original,r=self.send(self.a,self.review_action(p,v,'reject'));after=self.audit()
        self.assertIsNone(r['result']['mosaicEdit']);self.assertEqual(before['mosaic'],after['mosaic']);self.assertEqual((200,r),self.a.command(original))
        _,r=self.send(self.a,self.review_action(p,v),expected=409);self.assertEqual('MOSAIC_PROPOSAL_REVIEWED',r['error']['code'])
        self.send(self.a,{'type':'mosaic','activityId':'garden','visitCommandId':v,'expectedMosaicRevision':1,'patch':PATCH})

    def test_06_only_target_can_review_and_requires_own_visit(self):
        self.seed();p=self.propose();bv=self.b.observe()['self']['visits'][-1]['commandId']
        _,r=self.send(self.b,self.review_action(p,bv),expected=403);self.assertEqual('MOSAIC_REVIEW_FORBIDDEN',r['error']['code'])
        self.walk(self.a,(1,6));_,r=self.send(self.a,self.review_action(p,bv),expected=422);self.assertEqual('VISIT_REQUIRED',r['error']['code'])
        v=self.visit(self.a);missing={**p,'commandId':'missing'};_,r=self.send(self.a,self.review_action(missing,v),expected=404);self.assertEqual('MOSAIC_PROPOSAL_NOT_FOUND',r['error']['code'])

    def test_07_stale_accept_fails_but_stale_reject_is_allowed(self):
        self.seed();p=self.propose();v=self.visit(self.a)
        self.send(self.a,{'type':'mosaic','activityId':'garden','visitCommandId':v,'expectedMosaicRevision':1,'patch':[{'x':0,'y':0,'color':'leaf'}]})
        v=self.visit(self.a);before=self.audit();_,r=self.send(self.a,self.review_action(p,v),expected=409)
        self.assertEqual('MOSAIC_CHANGED',r['error']['code']);self.assertEqual(before,self.audit())
        self.send(self.a,self.review_action(p,v,'reject'));self.assertEqual(before['mosaic'],self.audit()['mosaic'])

    def test_08_concurrent_reviews_have_only_one_terminal_decision(self):
        self.seed();p=self.propose();v=self.visit(self.a);original=self.intent(self.a,self.review_action(p,v))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.a.command(original),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(200,results[0][0]);self.assertEqual(1,len(self.audit()['self']['mosaicReviews']))
        _,r=self.send(self.a,self.review_action(p,v,'reject'),expected=409);self.assertEqual('MOSAIC_PROPOSAL_REVIEWED',r['error']['code'])

    def crash_review(self,stage,code,committed):
        self.seed();p=self.propose();v=self.visit(self.a);original=self.intent(self.a,self.review_action(p,v));before=self.audit()
        with self.assertRaises((OSError,ValueError)):self.a.request('POST',self.a.prefix+'/commands',original,{'X-Test-Fault':stage})
        self.assertEqual(code,self.world.process.wait(timeout=10));self.world.restart();o=self.audit()
        self.assertEqual(1+int(committed),o['mosaic']['revision']);self.assertEqual(before['stateVersion']+int(committed),o['stateVersion'])
        self.assertEqual(int(committed),len(o['self']['mosaicReviews']));self.assertEqual(200,self.a.command(original)[0]);self.assertEqual(2,self.audit()['mosaic']['revision'])
    def test_09_before_commit_exit_rolls_back_review_and_all_tiles(self):self.crash_review('before-commit',81,False)
    def test_10_after_commit_exit_retains_review_and_all_tiles(self):self.crash_review('after-commit',82,True)

    def test_11_proposer_pause_resume_and_budget_visit_only(self):
        self.seed();choose=ConsentChoice();spec=mission(commands=12)
        first=self.task(spec,choose,max_steps=5);self.assertTrue(first['facts']['activityCompleted']);self.assertFalse(first['facts']['mosaicProposed'])
        final=self.task(spec,choose);self.assertEqual('completed',final['mission']['status']);self.assertTrue(final['facts']['mosaicProposed']);self.assertFalse(final['facts']['mosaicPainted']);self.assertEqual(1,choose.calls)
        before=self.audit();state=self.state.read_bytes();self.task(spec,choose);self.assertEqual(state,self.state.read_bytes());self.assertEqual(before,self.audit())
        self.state=self.world.data/'budget.json';limited=self.task(mission(commands=5,name='limited'),ConsentChoice())
        self.assertEqual('budget_exhausted',limited['mission']['status']);self.assertTrue(limited['facts']['activityCompleted']);self.assertFalse(limited['facts']['mosaicProposed'])

    def test_12_reviewer_accept_and_reject_reports_distinguish_actual_paint(self):
        self.seed();p=self.propose();choose=ConsentChoice('reject');r=self.task(mission('reviewer',p),choose,client=self.a)
        self.assertEqual('completed',r['mission']['status']);self.assertTrue(r['facts']['mosaicReviewed']);self.assertFalse(r['facts']['mosaicPainted']);self.assertTrue(r['facts']['returned'])
        self.state=self.world.data/'accept.json';p=self.propose();choose=ConsentChoice('accept');r=self.task(mission('reviewer',p),choose,client=self.a)
        self.assertEqual('completed',r['mission']['status']);self.assertTrue(r['facts']['mosaicReviewed'] and r['facts']['mosaicPainted']);self.assertEqual(1,choose.calls)

    def test_13_lost_review_commit_recovers_original_once(self):
        self.seed();p=self.propose();choose=ConsentChoice('accept');spec=mission('reviewer',p)
        class Crash(WorldClient):
            def request(self,method,path,payload=None,headers=None):
                if method=='POST' and payload.get('action',{}).get('type')=='mosaic_review':headers={'X-Test-Fault':'after-commit'}
                return super().request(method,path,payload,headers)
        r=self.task(spec,choose,client=Crash(self.world.url,self.world.access['sessions']['a1']['token']))
        self.assertEqual('unknown',r['mission']['status']);original=r['steps'][-1]['commandId'];self.assertEqual(82,self.world.process.wait(timeout=10));self.world.restart()
        r=self.task(spec,choose,client=self.a);self.assertEqual('completed',r['mission']['status']);self.assertEqual(original,r['facts']['mosaicReview']['commandId']);self.assertEqual(1,choose.calls)

    def test_14_stale_frozen_review_stops_without_new_decision(self):
        self.seed();p=self.propose();choose=ConsentChoice('accept');spec=mission('reviewer',p);self.task(spec,choose,client=self.a,max_steps=6)
        v=self.visit(self.a);self.send(self.a,{'type':'mosaic','activityId':'garden','visitCommandId':v,'expectedMosaicRevision':1,'patch':[{'x':0,'y':0,'color':'leaf'}]})
        r=self.task(spec,choose,client=self.a);self.assertEqual('blocked',r['mission']['status']);self.assertIn('MOSAIC_CHANGED',r['mission']['reason']);self.assertFalse(r['facts']['mosaicReviewed']);before=self.audit()
        self.task(spec,choose,client=self.a);self.assertEqual(before,self.audit());self.assertEqual(1,choose.calls)

    def test_15_wrong_receipt_and_query_failure_keep_original_pending(self):
        self.seed();p=self.propose();choose=ConsentChoice('accept');spec=mission('reviewer',p)
        class Wrong(WorldClient):
            def observe(self):
                o=super().observe();o['self']['mosaicReviews']=[];return o
            def request(self,method,path,payload=None,headers=None):
                if method=='GET' and '/commands/' in path:return 503,{'error':{'code':'TEMPORARY'}}
                status,result=super().request(method,path,payload,headers)
                if method=='POST' and payload.get('action',{}).get('type')=='mosaic_review' and status==200:
                    result=deepcopy(result);result['result']['proposalCommandId']='wrong'
                return status,result
        bad=Wrong(self.world.url,self.world.access['sessions']['a1']['token']);r=self.task(spec,choose,client=bad)
        self.assertEqual('unknown',r['mission']['status']);self.assertFalse(r['facts']['mosaicReviewed']);original=r['steps'][-1]['commandId']
        self.task(spec,choose,client=bad);self.assertEqual(original,json.loads(self.state.read_text())['_state']['pending']['request']['commandId'])
        r=self.task(spec,choose,client=self.a);self.assertEqual('completed',r['mission']['status']);self.assertEqual(original,r['facts']['mosaicReview']['commandId']);self.assertEqual(1,choose.calls)

    def test_16_capabilities_and_bad_draft_fail_before_world_actions(self):
        self.seed();before=self.audit();bad=ConsentChoice(patch=[{'x':0,'y':0,'color':'sun'}]);r=self.task(mission(),bad)
        self.assertEqual('decision_failed',r['mission']['status']);self.assertEqual(before,self.audit())
        with self.assertRaises(ValueError):run_mission(self.a,mission('reviewer',{'authorActorId':'a2','commandId':'missing'}),self.world.data/'missing.json',ConsentChoice('accept'))
        self.assertEqual(before,self.audit())

    def test_17_populated_r5_stays_unchanged_with_original_overwrite_rules(self):
        old=ConsentCandidate('old-r5',scenario=None,fixture='mosaic-v5-populated.sql')
        try:
            o=old.client().observe();self.assertEqual('r5',o['rulesVersion']);self.assertEqual(2,o['mosaic']['revision']);self.assertEqual([],o['mosaicProposals']);self.assertEqual(old.fixture_before,old.dump())
            old.restart();self.assertEqual(o,old.client().observe());self.assertEqual(old.fixture_before,old.dump())
            c=old.client();self.walk(c,(1,6));v=self.send(c,{'type':'visit','activityId':'garden'})[0]['commandId']
            self.send(c,{'type':'mosaic','activityId':'garden','visitCommandId':v,'expectedMosaicRevision':2,'patch':[{'x':0,'y':0,'color':'sun'}]})
            self.assertEqual('a1',c.observe()['mosaic']['cells'][0]['authorActorId'])
        finally:old.stop()

    def test_18_history_limits_preserve_complete_database(self):
        self.seed()
        for i in range(102):
            p=self.propose();v=self.visit(self.a);self.send(self.a,self.review_action(p,v,'reject'))
        a,b=self.audit(),self.b.observe();self.assertEqual(50,len(a['mosaicProposals']));self.assertEqual(100,len(b['self']['mosaicProposals']));self.assertEqual(100,len(a['self']['mosaicReviews']))
        self.assertEqual(1,a['mosaic']['revision']);self.assertTrue(all(p['review']['decision']=='reject' for p in a['mosaicProposals']))

    def test_19_world_stale_retries_only_settled_attempt_with_same_frozen_decision(self):
        self.seed();p=self.propose();choose=ConsentChoice('accept');spec=mission('reviewer',p);outer=self
        class Stale(WorldClient):
            changed=False
            def request(self,method,path,payload=None,headers=None):
                if method=='POST' and payload.get('action',{}).get('type')=='mosaic_review' and not self.changed:
                    self.changed=True;outer.send(outer.b,{'type':'move','dx':0,'dy':-1})
                return super().request(method,path,payload,headers)
        r=self.task(spec,choose,client=Stale(self.world.url,self.world.access['sessions']['a1']['token']))
        self.assertEqual('completed',r['mission']['status']);self.assertEqual(1,choose.calls)
        attempts=[s for s in r['steps'] if s['action']['type']=='mosaic_review']
        self.assertEqual(['rejected','committed'],[s['status'] for s in attempts])
        self.assertNotEqual(attempts[0]['commandId'],attempts[1]['commandId']);self.assertEqual(attempts[0]['action'],attempts[1]['action'])
        self.assertEqual(1,r['facts']['mosaicEdit']['baseRevision']);self.assertEqual(13,r['budget']['used']['commands'])


if __name__=='__main__':
    RUN_ROOT.mkdir(parents=True,mode=0o700)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ConsentAcceptance)
    if len(sys.argv)>1:suite=unittest.TestSuite(t for t in suite if t._testMethodName in set(sys.argv[1:]))
    r=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(suite)
    result={'suite':'mosaic-consent-http-v1','decisionSource':'explicit-test-double','actualModelCalls':0,'recordedAtUtc':datetime.now(timezone.utc).isoformat(),'passed':r.wasSuccessful(),'testsRun':r.testsRun,'tests':r.records,'dataRoot':str(RUN_ROOT.relative_to(ROOT)),'failures':[{'test':str(t),'detail':d} for t,d in r.failures+r.errors]}
    (RUN_ROOT/'results.json').write_text(json.dumps(result,ensure_ascii=True,indent=2)+'\n');print('Evidence:',RUN_ROOT/'results.json')
    raise SystemExit(0 if r.wasSuccessful() else 1)
