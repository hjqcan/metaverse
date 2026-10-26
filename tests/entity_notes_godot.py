#!/usr/bin/env python3
"""Actual native Godot input, immutable evidence and original-note recovery."""
from datetime import datetime, timezone
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import threading
import uuid
from foundation_api import ROOT
from godot_client import launch
from entity_notes_api import EntityNotesAcceptance, DLL, facts
import entity_notes_api as api

RUN = ROOT/'.local/iter0023/godot'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
api.RUN = RUN

class Proxy:
    def __init__(self, world, mode):
        self.mode, self.posts, self.gets = mode, [], []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_GET(self): self.forward()
            def do_POST(self): self.forward()
            def forward(self):
                body=self.rfile.read(int(self.headers.get('Content-Length',0))); post=self.command=='POST'
                if post:
                    owner.posts.append(body.decode())
                    if owner.mode=='before': self.close_connection=True; return
                else: owner.gets.append(self.path)
                conn=http.client.HTTPConnection('127.0.0.1',world.port,timeout=10)
                headers={'Authorization':self.headers.get('Authorization',''),'Content-Type':'application/json'}
                if 'World-Instance-Id' in self.headers:headers['World-Instance-Id']=self.headers['World-Instance-Id']
                conn.request(self.command,self.path,body or None,headers); reply=conn.getresponse();data=reply.read();status=reply.status;instance=reply.getheader('World-Instance-Id');conn.close()
                if post and owner.mode=='after':self.close_connection=True;return
                if status==200:
                    value=json.loads(data)
                    if post and owner.mode=='corrupt':value['result']['text']='unrelated text'
                    if owner.mode=='event' and '/events?' in self.path and value.get('events'):value['events'][0]['text']='unrelated event'
                    if owner.mode=='observation' and self.path.endswith('/observation') and value.get('entityNotes',{}).get('notes'):value['entityNotes']['notes'][0]['text']='unrelated observation'
                    data=json.dumps(value).encode()
                self.send_response(status);self.send_header('Content-Type','application/json')
                if instance:self.send_header('World-Instance-Id',instance)
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{self.server.server_port}'
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()


def main():
    EntityNotesAcceptance.setUpClass();results=[]
    paths=[*sorted((ROOT/'clients/godot').glob('*.gd')),ROOT/'tests/entity_notes_godot.py',ROOT/'tests/godot/entity_notes.gd']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for mode in (sys.argv[1:] or ('ui','before','after','corrupt','event','observation')):
        prep=EntityNotesAcceptance('test_01_same_instance_two_authors_reference_return_and_old_facts');prep._testMethodName=mode
        proxy=None
        try:
            prep.setUp();prep.adopt();prep.walk(prep.b,prep.target['position']);prep.walk(prep.c,prep.target['position'])
            proxy=Proxy(prep.world,mode)
            report=launch(prep.world,mode,url=proxy.url,script=ROOT/'tests/godot/entity_notes.gd')
            if mode!='ui':
                proxy.mode='return'
                restored=launch(prep.world,'return',url=proxy.url,script=ROOT/'tests/godot/entity_notes.gd')
                report['checks']+=restored['checks']
                assert len(proxy.posts)==(2 if mode=='before' else 1),proxy.posts
                assert len(set(proxy.posts))==1
            assert prep.b.observe()['entityNotes']['totalCount']==(2 if mode=='ui' else 1)
            results.append({'name':mode,**report});print(mode+': PASS',flush=True)
        except Exception as error:
            results.append({'name':mode,'passed':False,'error':str(error)});print(mode+': FAIL '+str(error),flush=True)
        finally:
            if proxy:proxy.stop()
            if hasattr(prep,'world'):prep.tearDown()
    passed=all(r['passed'] for r in results)
    report={'passed':passed,'actualModelCalls':0,'groups':len(results),'assertions':sum(len(r.get('checks',[])) for r in results),
            'results':results,'sourceSha256':hashes,'sourceUnchanged':hashes=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'dllSha256':hashlib.sha256(DLL.read_bytes()).hexdigest()}
    (RUN/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Evidence:',RUN/'results.json')
    return not passed
if __name__=='__main__':raise SystemExit(main())
