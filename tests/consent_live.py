#!/usr/bin/env python3
"""Two bounded real model calls: proposal then independent review; no forced acceptance."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3
import uuid

import consent_api
from consent_api import ConsentCandidate, RIVER, ROOT, mission
from activity_comparison import audit_database, write
from codex_goal_selector import CodexGoalSelector
from resident_mission import run_mission


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-one',required=True);parser.add_argument('--account-two',required=True);args=parser.parse_args()
    data=ROOT/'.local/iter0007/live'/(datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]);data.mkdir(parents=True,mode=0o700)
    consent_api.RUN_ROOT=data/'worlds'
    result={'schemaVersion':1,'kind':'mosaic-consent-session','recordedAtUtc':datetime.now(timezone.utc).isoformat(),'modelAttemptLimit':2,'actualModelCalls':0,'fixtureSource':'explicit-program-using-normal-HTTP-not-a-model-creation','seedCommands':[],'runs':[],'passed':False}
    world=None
    try:
        world=ConsentCandidate('shared-world');a=world.client()
        def send(action):
            o=a.observe();body={'schemaVersion':1,'rulesVersion':o['rulesVersion'],'commandId':uuid.uuid4().hex,'expectedStateVersion':o['stateVersion'],'action':action}
            status,r=a.command(body);assert status==200,r
            result['seedCommands'].append({'request':body,'result':r['result'],'stateVersion':r['stateVersion']});return r
        for _ in range(5):send({'type':'move','dx':0,'dy':1})
        visit=send({'type':'visit','activityId':'garden'})
        send({'type':'mosaic','activityId':'garden','visitCommandId':visit['commandId'],'expectedMosaicRevision':0,'patch':RIVER})
        for _ in range(5):send({'type':'move','dx':0,'dy':-1})
        result['initialMosaic']=a.observe()['mosaic'];proposal=None
        for index,(actor,role,account) in enumerate([('a2','proposer',args.account_two),('a1','reviewer',args.account_one)]):
            if role=='reviewer' and proposal is None:
                result['runs'].append({'actorId':actor,'role':role,'error':{'type':'DependencyUnavailable','message':'No confirmed proposal; second call not started.'},'actualModelCalls':0});break
            record={'actorId':actor,'role':role,'report':None,'decisionInput':None,'error':None,'actualModelCalls':0};result['runs'].append(record)
            decisions=data/'decisions'/role;selector=CodexGoalSelector(account,evidence_dir=decisions);calls=0
            def choose(context):
                nonlocal calls
                assert calls==0,'No second choice is permitted';calls+=1
                record['decisionInput']=deepcopy(context);write(data/'attempts.json',{'started':index+1,'limit':2,'current':actor});write(data/'session.json',result)
                return selector(context)
            try:
                spec=mission(role,proposal,commands=12 if role=='proposer' else 14,name='consent-'+role)
                write(data/(role+'.spec.json'),spec)
                report=run_mission(world.client(actor),spec,data/(role+'.state.json'),choose);record['report']=report;write(data/(role+'.json'),report)
                o=world.client(actor).observe();f=report['facts']
                record['journeyVerified']=report['mission']['status']=='completed' and f['activityCompleted'] and f['returned'] and o['self']['position']==report['mission']['origin']
                if role=='proposer':
                    proposal=f.get('mosaicProposal')
                    record['proposalVerified']=bool(proposal and f['mosaicProposed'] and not f['mosaicPainted'] and proposal['visitCommandId']==f['activityVisit']['commandId'] and any(p['commandId']==proposal['commandId'] and p['authorActorId']==actor for p in o['mosaicProposals']))
                    record['proposalDidNotPaint']=o['mosaic']==result['initialMosaic']
                    record['purposeVerified']=bool(proposal and len(proposal['patch'])==1 and proposal['patch'][0] in [{'x':x,'y':2,'color':'sun'} for x in [1,3]])
                else:
                    review=f.get('mosaicReview');record['originalProposalInInput']=record['decisionInput']['observation'].get('mosaicProposal',{}).get('commandId')==proposal['commandId']
                    record['reviewVerified']=bool(review and f['mosaicReviewed'] and review['proposalActorId']==proposal['authorActorId'] and review['proposalCommandId']==proposal['commandId'] and review['visitCommandId']==f['activityVisit']['commandId'] and review['authorActorId']==actor and review in o['self']['mosaicReviews'])
                    record['decision']=review['decision'] if review else None
                    if review and review['decision']=='accept':
                        edit=review['mosaicEdit'];record['effectVerified']=bool(f['mosaicPainted'] and edit==f['mosaicEdit'] and edit['patch']==proposal['patch'] and edit['authorActorId']=='a1' and edit['commandId']==review['commandId'])
                        changed={(c['x'],c['y']):c['color'] for c in proposal['patch']}
                        record['effectVerified']=record['effectVerified'] and all((c['color']==changed[(c['x'],c['y'])] and c['authorActorId']=='a1' and c['commandId']==review['commandId']) if (c['x'],c['y']) in changed else c==result['initialMosaic']['cells'][i] for i,c in enumerate(o['mosaic']['cells']))
                    else:record['effectVerified']=bool(review and not f['mosaicPainted'] and review['mosaicEdit'] is None and o['mosaic']==result['initialMosaic'])
            except Exception as error:record['error']={'type':type(error).__name__,'message':str(error)[:500]}
            finally:
                events=[json.loads(p.read_text()) for p in sorted(decisions.glob('decision-*.json'))] if decisions.exists() else []
                record['decisionEvents']=[{k:v for k,v in e.items() if k!='accountAlias'} for e in events];record['actualModelCalls']=len(events);result['actualModelCalls']+=len(events)
                write(data/'session.json',result);print(json.dumps({k:record.get(k) for k in ['actorId','role','actualModelCalls','journeyVerified','decision','error']},ensure_ascii=False),flush=True)
        o=a.observe();result['finalMosaic']=o['mosaic'];result['publicProposals']=o['mosaicProposals'];result['resourceAudit']=o['resourceAudit']
        result['passed']=bool(len(result['runs'])==2 and result['actualModelCalls']==2 and all(r.get('journeyVerified') and r.get('error') is None for r in result['runs']) and all(result['runs'][0].get(k) for k in ['proposalVerified','proposalDidNotPaint','purposeVerified']) and all(result['runs'][1].get(k) for k in ['originalProposalInInput','reviewVerified','effectVerified']))
    finally:
        if world:
            world.stop();result['databaseAudit']=audit_database(world.data/'world.db')
            with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro',uri=True) as db:
                result['databaseAudit'].update({k:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for k,table in [('proposalRows','mosaic_proposals'),('reviewRows','mosaic_reviews'),('mosaicEditRows','mosaic_edits')]})
                events=[json.loads(r[0]) for r in db.execute('SELECT event_json FROM events ORDER BY state_version')]
                for e in events:
                    if e['type'] not in ['mosaic_proposed','mosaic_reviewed']:continue
                    receipt=json.loads(db.execute('SELECT result_json FROM receipts WHERE actor_id=? AND command_id=?',(e['authorActorId'],e['commandId'])).fetchone()[0]);assert receipt['status']=='committed'
                    assert all(e[k]==v for k,v in receipt['result'].items() if k!='action')
                result['passed']=bool(result['passed'] and result['databaseAudit']['conserved'] and result['databaseAudit']['proposalRows']==1 and result['databaseAudit']['reviewRows']==1)
        result['finishedAtUtc']=datetime.now(timezone.utc).isoformat();write(data/'session.json',result);print('Evidence:',data/'session.json',flush=True)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
