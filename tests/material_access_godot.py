#!/usr/bin/env python3
"""Actual Godot source UI, original-record recovery, and receipt/reference validation."""
from datetime import datetime, timezone
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import sys
import threading
import uuid
import activities_api
from foundation_api import ROOT, DLL
from godot_client import launch
from material_access_api import MaterialAccessAcceptance, reserve

RUN = ROOT / '.local/iter0022/godot' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN
RUN.mkdir(parents=True)


class Proxy:
    def __init__(self, world, mode):
        self.mode, self.posts = mode, []
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
                    if owner.mode.endswith('-before'):
                        self.close_connection = True; return
                conn = http.client.HTTPConnection('127.0.0.1', world.port, timeout=10)
                headers = {'Authorization': self.headers.get('Authorization', ''), 'Content-Type': 'application/json'}
                if 'World-Instance-Id' in self.headers: headers['World-Instance-Id'] = self.headers['World-Instance-Id']
                conn.request(self.command, self.path, body or None, headers)
                reply = conn.getresponse(); data = reply.read(); status = reply.status; instance = reply.getheader('World-Instance-Id'); conn.close()
                if post and owner.mode.endswith('-after'):
                    self.close_connection = True; return
                if post and owner.mode.endswith('-corrupt') and status == 200:
                    changed = json.loads(data); changed['result']['reservationId'] = 'm_wrong'; data = json.dumps(changed).encode()
                self.send_response(status); self.send_header('Content-Type', 'application/json')
                if instance: self.send_header('World-Instance-Id', instance)
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()


paths = [*sorted((ROOT/'clients/godot').glob('*.gd')), ROOT/'tests/material_access_godot.py', ROOT/'tests/godot/material_access.gd']
hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
results = []
for mode in (sys.argv[1:] or ('ui', 'reserve-corrupt', 'harvest-corrupt', 'reserve-before', 'reserve-after', 'harvest-before', 'harvest-after', 'cancel-before', 'cancel-after')):
    prep = MaterialAccessAcceptance('test_01_initial_identity_inactive_protocol_and_offline_activation_lock')
    prep._testMethodName += '-' + mode
    prep.setUp(); proxy = None
    try:
        prep.enable()
        if mode.startswith(('harvest-', 'cancel-')):
            rid = prep.send(prep.c, reserve())['result']['reservationId']
            if mode.startswith('harvest-'): prep.active(prep.c, rid)
        proxy = Proxy(prep.world, mode)
        report = launch(prep.world, mode, url=proxy.url, script=ROOT/'tests/godot/material_access.gd')
        if mode.endswith(('-before', '-after')):
            proxy.mode = mode.rsplit('-', 1)[0] + '-return'
            restored = launch(prep.world, proxy.mode, url=proxy.url, script=ROOT/'tests/godot/material_access.gd')
            report['checks'] += restored['checks']
            assert len(proxy.posts) == (2 if mode.endswith('-before') else 1)
            assert len(set(proxy.posts)) == 1
        if mode.endswith('-corrupt'): assert len(proxy.posts) == 1
        with sqlite3.connect(prep.world.data/'world.db') as db:
            assert db.execute("SELECT wood FROM residents WHERE actor_id='a3'").fetchone()[0] == (1 if mode.startswith('harvest-') else 0)
            if mode == 'ui':
                assert db.execute("SELECT owner_actor_id,embodied_wood FROM entities").fetchall() == [('a3', 3)]
            assert db.execute("SELECT count(*) FROM material_reservations").fetchone()[0] == 1
        results.append({'name': mode, **report}); print(mode+': PASS', flush=True)
    except Exception as error:
        results.append({'name': mode, 'passed': False, 'error': str(error)}); print(mode+': FAIL '+str(error), flush=True)
    finally:
        if proxy: proxy.stop()
        prep.tearDown()
passed = all(r['passed'] for r in results)
report = {'passed': passed, 'actualModelCalls': 0, 'groups': len(results), 'assertions': sum(len(r.get('checks', [])) for r in results),
          'results': results, 'sourceSha256': hashes, 'sourceUnchanged': hashes == {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
          'dllSha256': hashlib.sha256(DLL.read_bytes()).hexdigest()}
(RUN/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print('Evidence:', RUN/'results.json')
raise SystemExit(not passed)
