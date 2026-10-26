#!/usr/bin/env python3
"""Author native adapter recovery on a stopped, actually played forestry history.

WORLD_SERVER_DLL and FORESTRY_SOURCE are required frozen inputs. Transport faults
never grant resources or change service time. Every case uses its own DB/journal.
"""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib, http.client, json, os
from pathlib import Path
import shutil, sqlite3, subprocess, sys, threading, uuid
import workshop_api as api

ROOT = api.ROOT
RUN = ROOT/'.local/iter0028/godot'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
GODOT = Path(os.environ.get('GODOT_BIN', ROOT/'.local/tools/godot/Godot_v4.7.2-stable_linux.x86_64')).resolve()
SOURCE = Path(os.environ['FORESTRY_SOURCE']).resolve()

class World(api.World):
    def request(self, *args, **kwargs):
        kwargs.setdefault('capability', 'workshop-v1,forestry-v1')
        return super().request(*args, **kwargs)

class Proxy:
    def __init__(self, world, mode):
        self.mode, self.posts, self.gets = mode, [], []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self): self.forward()
            def do_POST(self): self.forward()
            def forward(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                post = self.command == 'POST'
                if post:
                    owner.posts.append(body.decode())
                    if owner.mode in ('before','capability'):
                        self.close_connection = True
                        return
                else: owner.gets.append(self.path)
                headers = {k: self.headers[k] for k in ('Authorization','Content-Type','World-Instance-Id','World-Capabilities') if k in self.headers}
                conn = http.client.HTTPConnection('127.0.0.1', world.port, timeout=15)
                try:
                    conn.request(self.command, self.path, body or None, headers)
                    reply = conn.getresponse()
                    raw,status,instance = reply.read(),reply.status,reply.getheader('World-Instance-Id')
                finally: conn.close()
                if post and owner.mode == 'after':
                    self.close_connection = True
                    return
                if status == 200:
                    value = json.loads(raw)
                    if owner.mode == 'receipt' and (post or '/commands/' in self.path):
                        value['result']['forestryAction']['seeds'] += 1
                    if owner.mode == 'event' and '/events?' in self.path and value.get('events'):
                        value['events'][0]['forestryAction']['seeds'] += 1
                    if owner.mode == 'detail' and '/forestry/actions/' in self.path:
                        value['forestryAction']['seeds'] += 1
                    if owner.mode == 'unknown' and self.path.endswith('/observation'):
                        value['forestry']['version'] = 99
                    raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                if instance: self.send_header('World-Instance-Id',instance)
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join()


def launch(world,proxy,mode,action,output,command=''):
    env={**os.environ,'WORLD_URL':proxy.url,'WORLD_ACCESS_FILE':str(world.data/'access.json'),
         'WORLD_CLIENT_STATE':str(world.data/'pending.json'),'GODOT_TEST_OUTPUT':str(output),'GODOT_TEST_MODE':mode,
         'FORESTRY_TEST_ACTION':json.dumps(action),'FORESTRY_TEST_COMMAND':command}
    with output.with_suffix('.log').open('w') as log:
        p=subprocess.run([str(GODOT),'--headless','--path',str(ROOT/'clients/godot'),'--script',str(ROOT/'tests/godot/forestry_recovery.gd')],
                         env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=45)
    raw=output.with_suffix('.log').read_text()
    assert p.returncode==0 and 'ERROR:' not in raw,raw[-5000:]
    result=json.loads(output.read_text());assert result['passed'],result
    return result


def main():
    assert api.DLL and api.DLL.is_file() and (SOURCE/'world.db').is_file()
    RUN.mkdir(parents=True)
    paths=[*sorted((ROOT/'clients/godot').glob('*.gd')),Path(__file__).resolve(),ROOT/'tests/godot/forestry_recovery.gd']
    hashes={str(p.relative_to(ROOT)):api.sha(p) for p in paths}
    cases=[('reserve_forest',m) for m in ('before','after','receipt','event','detail','capability')]+[('cancel_forest_reservation',m) for m in ('before','after')]
    if sys.argv[1:]:cases=[c for c in cases if '-'.join(c) in sys.argv[1:]]
    results=[]
    for kind,mode in cases:
        name=kind+'-'+mode;w=World(RUN/(name+'-world'),SOURCE);proxy=None
        try:
            w.start();w.observe()
            action=dict(type=kind,capabilityVersion=1)
            if kind=='cancel_forest_reservation':
                rid=w.send(dict(type='reserve_forest',capabilityVersion=1))[1][1]['result']['forestryAction']['reservation']['reservationId']
                action['reservationId']=rid
            proxy=Proxy(w,mode)
            first=launch(w,proxy,'lost',action,RUN/(name+'-lost.json'))
            original=first['pending']['commandId']
            journal=lambda:{str(p.relative_to(w.data)):api.sha(p) for p in w.data.rglob('*') if p.is_file() and 'pending.json' in str(p.relative_to(w.data))}
            saved=journal();w.restart()
            if mode=='capability':
                proxy.mode='unknown';held=launch(w,proxy,'hold',action,RUN/(name+'-held.json'),original)
                first['checks']+=held['checks'];assert saved==journal() and len(proxy.posts)==1
            proxy.mode='return';second=launch(w,proxy,'return',action,RUN/(name+'-return.json'),original)
            assert len(proxy.posts)==(2 if mode in ('before','capability') else 1) and len(set(proxy.posts))==1 and not journal()
            o=w.observe();assert o['resourceAudit']['conserved'] and o['seedAudit']['conserved']
            with sqlite3.connect(w.data/'world.db') as db:
                assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
                assert db.execute('SELECT count(*) FROM receipts WHERE actor_id=? AND command_id=?',('a2',original)).fetchone()[0]==1
            results.append(dict(name=name,passed=True,checks=first['checks']+second['checks'],postCount=len(proxy.posts),originalBodySha256=hashlib.sha256(proxy.posts[0].encode()).hexdigest(),receipt=second['receipt']))
            print(name+': PASS',flush=True)
        except Exception as e:
            results.append(dict(name=name,passed=False,error=str(e)));print(name+': FAIL '+str(e),flush=True)
        finally:
            if proxy:
                api.save(RUN/(name+'-transport.json'),dict(posts=[json.loads(p) for p in proxy.posts],gets=proxy.gets));proxy.stop()
            w.stop();api.save(RUN/(name+'-setup.json'),w.trace);shutil.rmtree(w.data)
    unchanged=hashes=={str(p.relative_to(ROOT)):api.sha(p) for p in paths}
    passed=unchanged and all(x['passed'] for x in results)
    api.save(RUN/'results.json',dict(passed=passed,groups=len(results),assertions=sum(len(x.get('checks',[])) for x in results),results=results,
        sourceSha256=hashes,sourceUnchanged=unchanged,dllSha256=api.sha(api.DLL),temporaryWorldsRemoved=True,actualModelCalls=0))
    print('Evidence:',RUN/'results.json');return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
