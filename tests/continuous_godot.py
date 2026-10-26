#!/usr/bin/env python3
"""Actual Godot/OpenGL input, continuous HTTP world and durable command recovery. No models."""
from datetime import datetime, timezone
import json
import sqlite3
import math
import time
import uuid
import activities_api
from activities_api import ActivityCandidate
from foundation_api import ROOT
from godot_client import launch, Proxy
RUN=ROOT/'.local/iter0014/godot'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
activities_api.RUN_ROOT=RUN
RUN.mkdir(parents=True)
results=[]
for name in ('basic','bridge','input-loss','after','before','wrong-receipt','stale','offline','corrupt-journal'):
    world=ActivityCandidate(name,scenario='wilderness-continuous-v1')
    proxy=None
    try:
        if name=='input-loss':
            proxy=Proxy(world,'after')
            report=launch(world,name,url=proxy.url,script=ROOT/'tests/godot/continuous.gd')
        elif name in ('basic','bridge'):
            if name=='bridge':
                def send(client,action):
                    o=client.observe()
                    status,r=client.command(dict(schemaVersion=1,rulesVersion='r8',commandId=uuid.uuid4().hex,expectedStateVersion=o['stateVersion'],action=action))
                    assert status==200,r
                    return r
                def walk(client,target):
                    for _ in range(250):
                        if math.dist(client.observe()['self']['position'],target)<1e-6:return
                        r=send(client,{'type':'walk','to':target});assert not r['result']['blocked'],r
                        time.sleep(.08)
                    raise AssertionError('bridge setup walk deadline')
                a,b=world.client(),world.client('a2')
                for _ in range(3):send(a,{'type':'gather','nodeId':'tree-west-north'})
                walk(a,[8,15.5])
                for _ in range(3):send(a,{'type':'gather','nodeId':'tree-west-south'})
                for p in ([12,15],[15.7,12]):walk(a,p)
                for p in ([27,13],[25,10],[21,10],[20.8,12]):walk(b,p)
            report=launch(world,name,script=ROOT/'tests/godot/continuous.gd')
        else:
            script=ROOT/'tests/godot/continuous_recovery.gd'
            if name=='corrupt-journal':
                (world.data/'pending.json').write_text('{"bad":{"actorId":"a1","body":"{}"}}')
                report=launch(world,name,script=script)
            else:
                proxy=Proxy(world,name)
                report=launch(world,'lost' if name in ('before','after') else name,url=proxy.url,script=script)
                if name in ('before','after'):
                    world.restart()
                    second=launch(world,'retry' if name=='before' else 'reconnect',url=proxy.url,script=script)
                    report['checks']+=second['checks']
                    assert len(proxy.posts)==(2 if name=='before' else 1)
                    if name=='before':assert proxy.posts[0]==proxy.posts[1]
                if name=='offline':assert len(proxy.posts)==1
                if name=='wrong-receipt':assert len(proxy.posts)==1
                (world.data/'requests.json').write_text(json.dumps([json.loads(x) for x in proxy.posts],indent=2))
        results.append({'name':name,**report})
        print(name+': PASS',flush=True)
    except Exception as error:
        results.append({'name':name,'passed':False,'error':str(error)})
        print(name+': FAIL '+str(error),flush=True)
    finally:
        if proxy:proxy.stop()
        world.stop()
        with sqlite3.connect(world.data/'world.db') as db:
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert 12==sum(db.execute(q).fetchone()[0] for q in ('SELECT sum(remaining_wood) FROM resource_nodes','SELECT sum(wood) FROM residents','SELECT coalesce(sum(embodied_wood),0) FROM entities'))
passed=all(r['passed'] for r in results)
(RUN/'results.json').write_text(json.dumps({'passed':passed,'groups':len(results),'assertions':sum(len(r.get('checks',[])) for r in results),'results':results},indent=2))
print('Evidence:',RUN)
raise SystemExit(not passed)
