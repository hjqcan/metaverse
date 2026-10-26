#!/usr/bin/env python3
"""Real native input, actor contention and original-command recovery; no model calls."""
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import threading
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import ROOT
from godot_client import launch

RUN = ROOT / '.local/iter0019/godot' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN
RUN.mkdir(parents=True)


class Interference:
    def __init__(self, world, mode):
        self.mode, self.posts, self.injected, self.drop = mode, [], False, True
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
                    if owner.mode == 'strict-save' and owner.drop:
                        owner.drop = False
                        self.close_connection = True
                        return
                    if not owner.injected and owner.mode in ('unrelated', 'held', 'route'):
                        other = world.client('a2' if owner.mode == 'unrelated' else 'a1')
                        o = other.observe()
                        status, receipt = other.command(dict(schemaVersion=1, rulesVersion='r8', commandId='interference', expectedStateVersion=o['stateVersion'], action={'type': 'walk', 'to': [26.1, 17] if owner.mode == 'unrelated' else [5.1, 7]}))
                        assert status == 200, receipt
                        owner.injected = True
                conn = http.client.HTTPConnection('127.0.0.1', world.port, timeout=10)
                headers = {'Authorization': self.headers.get('Authorization', ''), 'Content-Type': 'application/json'}
                if 'World-Instance-Id' in self.headers:
                    headers['World-Instance-Id'] = self.headers['World-Instance-Id']
                conn.request(self.command, self.path, body or None, headers)
                reply = conn.getresponse(); data = reply.read(); status = reply.status
                instance = reply.getheader('World-Instance-Id'); conn.close()
                if owner.mode == 'strict-save' and self.path.endswith('/observation') and status == 200:
                    changed = json.loads(data); changed.pop('commandConcurrency', None); data = json.dumps(changed).encode()
                if post and status == 200 and owner.mode in ('missing-execution', 'bad-quantity'):
                    changed = json.loads(data)
                    if owner.mode == 'missing-execution': changed.pop('execution')
                    else: changed['result']['remainingWoodBefore'] = 99
                    data = json.dumps(changed).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                if instance: self.send_header('World-Instance-Id', instance)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()


results = []
for name in ('unrelated', 'held', 'route', 'missing-execution', 'bad-quantity', 'strict-save'):
    world = ActivityCandidate(name, scenario='wilderness-continuous-v1')
    proxy = Interference(world, name)
    try:
        report = launch(world, name, url=proxy.url, script=ROOT / 'tests/godot/actor_state.gd')
        if name == 'strict-save':
            proxy.mode = 'strict-return'
            second = launch(world, 'strict-return', url=proxy.url, script=ROOT / 'tests/godot/actor_state.gd')
            report['checks'] += second['checks']
            assert len(proxy.posts) == 2 and proxy.posts[0] == proxy.posts[1]
        elif name not in ('held', 'route'):
            assert len(proxy.posts) == 1
        with sqlite3.connect(world.data / 'world.db') as db:
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []
            total = sum(db.execute(q).fetchone()[0] for q in ('SELECT sum(remaining_wood) FROM resource_nodes', 'SELECT sum(wood) FROM residents', 'SELECT coalesce(sum(embodied_wood),0) FROM entities'))
            assert total == 12
            if name in ('held', 'route'):
                rows = [json.loads(row) for row in proxy.posts]
                assert len(rows) >= 2
                receipt = json.loads(db.execute('SELECT result_json FROM receipts WHERE command_id=?', (rows[0]['commandId'],)).fetchone()[0])
                assert receipt['error']['code'] == 'STALE_ACTOR_STATE'
            else:
                assert db.execute('SELECT wood FROM residents WHERE actor_id="a1"').fetchone()[0] == 1
        results.append({'name': name, **report})
        print(name + ': PASS', flush=True)
    except Exception as error:
        results.append({'name': name, 'passed': False, 'error': str(error)})
        print(name + ': FAIL ' + str(error), flush=True)
    finally:
        proxy.stop(); world.stop()
passed = all(item['passed'] for item in results)
(RUN / 'results.json').write_text(json.dumps({'passed': passed, 'actualModelCalls': 0, 'groups': len(results), 'assertions': sum(len(item.get('checks', [])) for item in results), 'results': results}, indent=2) + '\n')
print('Evidence:', RUN / 'results.json')
raise SystemExit(not passed)
