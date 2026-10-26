#!/usr/bin/env python3
"""Real native input and original-request recovery in the adopted old world."""
from datetime import datetime, timezone
import hashlib
import json
import shutil
import sys
import uuid
from foundation_api import ROOT
from godot_client import launch
from entity_notes_godot import Proxy
from continuous_material_api import Continued, baseline, SOURCE_DLL, rows

RUN=ROOT/'.local/iter0024/godot'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])


def main():
    RUN.mkdir(parents=True);dll=SOURCE_DLL.resolve()
    (RUN/'binary-location.json').write_text(json.dumps({'path':str(dll),'sha256':hashlib.sha256(dll.read_bytes()).hexdigest()},indent=2)+'\n')
    source=baseline(RUN/'seed',dll);results=[]
    paths=[*sorted((ROOT/'clients/godot').glob('*.gd')),ROOT/'tests/continuous_material_godot.py',ROOT/'tests/godot/continuous_material.gd']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for mode in (sys.argv[1:] or ('ui','policy','before','after')):
        world=proxy=None
        try:
            world=Continued(source,RUN/mode,dll=dll);client=world.client('a2');instance=client.observe()['world']['instanceId']
            before=rows(world.data);world.stop();adopted=world.adopt(instance)
            assert adopted.returncode==0,adopted.stderr
            world.start();proxy=Proxy(world,mode)
            report=launch(world,mode,url=proxy.url,script=ROOT/'tests/godot/continuous_material.gd')
            if mode in ('before','after'):
                proxy.mode='return'
                restored=launch(world,'return',url=proxy.url,script=ROOT/'tests/godot/continuous_material.gd')
                report['checks']+=restored['checks']
                assert len(proxy.posts)==(2 if mode=='before' else 1)
                assert len(set(proxy.posts))==1
            after=rows(world.data)
            for name in ('entities','receipts','events','entity_notes','entity_note_adoption','world_instance'):
                assert set(before[name]).issubset(set(after[name])),name
            assert len(after['entity_notes'])==2
            assert len(after['entities'])==(6 if mode=='ui' else 5)
            results.append({'name':mode,**report});print(mode+': PASS',flush=True)
        except Exception as error:
            results.append({'name':mode,'passed':False,'error':str(error)});print(mode+': FAIL '+str(error),flush=True)
        finally:
            if proxy:proxy.stop()
            if world:world.stop()
    passed=all(r['passed'] for r in results)
    report={'passed':passed,'groups':len(results),'assertions':sum(len(r.get('checks',[])) for r in results),
            'results':results,'actualModelCalls':0,'sourceSha256':hashes,
            'sourceUnchanged':hashes=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'dllSha256':hashlib.sha256(dll.read_bytes()).hexdigest(),'baseline':str(source)}
    (RUN/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Evidence:',RUN/'results.json')
    return not passed

if __name__=='__main__':raise SystemExit(main())
