#!/usr/bin/env python3
"""Real renderer, mouse gift input, recipient building and interrupted original commands."""
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import sys
import threading
import uuid

import activities_api
from foundation_api import ROOT
from godot_client import launch
from material_transfer_api import TransferAcceptance, gift

RUN = ROOT / '.local/iter0020/godot' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN
RUN.mkdir(parents=True)


class Proxy:
    def __init__(self, world, mode):
        self.mode, self.posts, self.injected = mode, [], False
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
                    if owner.mode == 'before-save':
                        self.close_connection = True; return
                    if owner.mode == 'incoming' and not owner.injected:
                        sender = world.client(); observed = sender.observe()
                        status, receipt = sender.command({'schemaVersion': 1, 'rulesVersion': 'r9', 'commandId': 'incoming-gift',
                            'expectedStateVersion': observed['stateVersion'], 'preconditionMode': 'actor-state-v1', 'action': gift()})
                        assert status == 200, receipt
                        owner.injected = True
                connection = http.client.HTTPConnection('127.0.0.1', world.port, timeout=10)
                headers = {'Authorization': self.headers.get('Authorization', ''), 'Content-Type': 'application/json'}
                if 'World-Instance-Id' in self.headers: headers['World-Instance-Id'] = self.headers['World-Instance-Id']
                connection.request(self.command, self.path, body or None, headers)
                reply = connection.getresponse(); data = reply.read(); status = reply.status
                instance = reply.getheader('World-Instance-Id'); connection.close()
                if post and owner.mode == 'after-save': self.close_connection = True; return
                if post and owner.mode == 'corrupt' and status == 200:
                    changed = json.loads(data); changed['result']['recipientActorId'] = 'a1'; data = json.dumps(changed).encode()
                self.send_response(status); self.send_header('Content-Type', 'application/json')
                if instance: self.send_header('World-Instance-Id', instance)
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()


results = []
for mode in (sys.argv[1:] or ('ui', 'incoming', 'corrupt', 'before-save', 'after-save')):
    preparation = TransferAcceptance('test_01_cooperation_real_materials_received_then_built_and_original_receipt')
    preparation.worlds, preparation.trace = [], []
    preparation.world = preparation.create(mode)
    preparation.a, preparation.b = preparation.world.client(), preparation.world.client('a2')
    proxy = None
    try:
        preparation.meeting()
        proxy = Proxy(preparation.world, mode)
        report = launch(preparation.world, mode, url=proxy.url, script=ROOT / 'tests/godot/material_transfer.gd')
        if mode.endswith('-save'):
            proxy.mode = mode.replace('-save', '-return')
            restored = launch(preparation.world, proxy.mode, url=proxy.url, script=ROOT / 'tests/godot/material_transfer.gd')
            report['checks'] += restored['checks']
            assert len(proxy.posts) == (2 if mode == 'before-save' else 1)
            assert len(set(proxy.posts)) == 1
        if mode == 'corrupt': assert len(proxy.posts) == 1
        with sqlite3.connect(preparation.world.data / 'world.db') as db:
            assert db.execute("SELECT count(*) FROM resource_ledger WHERE source_account='inventory:a1' AND destination_account='inventory:a2'").fetchone()[0] == 1
            assert db.execute("SELECT wood FROM residents WHERE actor_id='a1'").fetchone()[0] == 3
            assert db.execute("SELECT wood FROM residents WHERE actor_id='a2'").fetchone()[0] == (0 if mode == 'ui' else 3)
        results.append({'name': mode, **report}); print(mode + ': PASS', flush=True)
    except Exception as error:
        results.append({'name': mode, 'passed': False, 'error': str(error)}); print(mode + ': FAIL ' + str(error), flush=True)
    finally:
        if proxy: proxy.stop()
        preparation.tearDown()
passed = all(item['passed'] for item in results)
(RUN / 'results.json').write_text(json.dumps({'passed': passed, 'actualModelCalls': 0, 'groups': len(results),
    'assertions': sum(len(item.get('checks', [])) for item in results), 'results': results}, ensure_ascii=False, indent=2) + '\n')
print('Evidence:', RUN / 'results.json')
raise SystemExit(not passed)
