#!/usr/bin/env python3
"""Native mouse editing and original-request recovery against isolated real worlds."""
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
from entity_canvas_api import EntityCanvasAcceptance, DLL, paint
import entity_canvas_api as api

RUN = ROOT/'.local/iter0025/godot'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
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
                if post and owner.mode in ('after','capability'):self.close_connection=True;return
                if status==200:
                    value=json.loads(data)
                    if owner.mode=='corrupt' and (post or '/commands/' in self.path):value['result']['patch'][0]['color']='rose'
                    if owner.mode=='event' and '/events?' in self.path and value.get('events'):value['events'][0]['patch'][0]['color']='rose'
                    if owner.mode=='detail' and '/canvas/edits/' in self.path:value['edit']['patch'][0]['color']='rose'
                    if owner.mode=='unknown-capability' and self.path.endswith('/observation'):value['entityCanvas']['version']=99
                    data=json.dumps(value).encode()
                self.send_response(status);self.send_header('Content-Type','application/json')
                if instance:self.send_header('World-Instance-Id',instance)
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{self.server.server_port}'
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()

def main():
    EntityCanvasAcceptance.setUpClass();results=[]
    paths=[*sorted((ROOT/'clients/godot').glob('*.gd')),ROOT/'tests/entity_canvas_godot.py',ROOT/'tests/godot/entity_canvas.gd']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for mode in (sys.argv[1:] or ('ui','before','after','corrupt','event','detail','capability')):
        prep=EntityCanvasAcceptance('test_01_same_original_platform_two_residents_paint_and_return');prep._testMethodName=mode
        proxy=None
        try:
            prep.setUp();prep.adopt();prep.walk(prep.z,prep.position);prep.walk(prep.b,prep.position)
            before_wood=prep.b.observe()['self']['inventory']['wood']
            proxy=Proxy(prep.world,mode)
            report=launch(prep.world,mode,url=proxy.url,script=ROOT/'tests/godot/entity_canvas.gd')
            if mode!='ui':
                if mode=='after':
                    # A later real command from the same author changes the current
                    # cell; recovery must still confirm the original immutable edit.
                    prep.send(prep.z,paint(prep.target,1,[{'x':1,'y':1,'color':'leaf'}]))
                proxy.mode='unknown-capability' if mode=='capability' else 'return'
                restored=launch(prep.world,'return',url=proxy.url,script=ROOT/'tests/godot/entity_canvas.gd')
                report['checks']+=restored['checks']
                assert len(proxy.posts)==(2 if mode=='before' else 1),proxy.posts
                assert len(set(proxy.posts))==1
            final=prep.b.observe()
            assert final['entityCanvas']['editCount']==(2 if mode in ('ui','after') else 1)
            assert final['self']['inventory']['wood']==before_wood
            assert prep.z.observe()['self']['inventory']['wood']==0
            results.append({'name':mode,**report});print(mode+': PASS',flush=True)
        except Exception as error:
            results.append({'name':mode,'passed':False,'error':str(error)});print(mode+': FAIL '+str(error),flush=True)
        finally:
            if proxy:proxy.stop()
            if hasattr(prep,'world'):prep.tearDown()
    passed=all(r['passed'] for r in results)
    report={'passed':passed,'actualModelCalls':0,'groups':len(results),'assertions':sum(len(r.get('checks',[])) for r in results),
            'results':results,'sourceSha256':hashes,'sourceUnchanged':hashes=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'dllSha256':hashlib.sha256(DLL.read_bytes()).hexdigest(),'baseline':str(EntityCanvasAcceptance.source)}
    (RUN/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Evidence:',RUN/'results.json')
    return not passed
if __name__=='__main__':raise SystemExit(main())
