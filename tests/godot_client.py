#!/usr/bin/env python3
"""Real Godot renderer + input + HTTP adapter, isolated .NET/SQLite and loss proxy. No models."""
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import ROOT

RUN = ROOT / '.local/iter0011/godot' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN
GODOT = os.environ.get('GODOT_BIN') or str(ROOT / '.local/tools/godot/Godot_v4.7.2-stable_linux.x86_64')
if not Path(GODOT).is_file():
    GODOT = shutil.which('godot') or shutil.which('godot4')
if not GODOT:
    sys.exit('Set GODOT_BIN to Godot 4.7.2.')


class Proxy:
    def __init__(self, world, mode):
        self.mode, self.world, self.posts = mode, world, []
        self.drop = True
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self): self.forward()
            def do_POST(self): self.forward()
            def forward(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                is_post = self.command == 'POST'
                if owner.mode == 'offline' and owner.posts and self.path.endswith('/observation'):
                    self.send_response(503); self.end_headers(); return
                if is_post:
                    owner.posts.append(body.decode())
                    if owner.mode == 'stale' and owner.drop:
                        b = world.client('a2'); o = b.observe()
                        status, _ = b.request('POST', '/v1/worlds/foundation-01/commands', {'schemaVersion': 1, 'rulesVersion': 'r7', 'commandId': 'other-resident', 'expectedStateVersion': o['stateVersion'], 'action': {'type': 'move', 'dx': 0, 'dy': -1}})
                        assert status == 200
                    if owner.mode == 'before' and owner.drop:
                        owner.drop = False
                        self.close_connection = True
                        return
                connection = http.client.HTTPConnection('127.0.0.1', world.port, timeout=10)
                connection.request(self.command, self.path, body=body or None, headers={'Authorization': self.headers.get('Authorization', ''), 'Content-Type': 'application/json'})
                reply = connection.getresponse(); data = reply.read(); status = reply.status
                connection.close()
                if is_post and owner.mode == 'after' and owner.drop:
                    owner.drop = False
                    self.close_connection = True
                    return
                if is_post and owner.mode == 'wrong-receipt' and owner.drop:
                    changed = json.loads(data)
                    changed['result']['nodeId'] = 'another-tree'
                    data = json.dumps(changed).encode()
                if is_post:
                    owner.drop = False
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()


def launch(world, mode, url=None):
    output = world.data / mode
    env = {**os.environ, 'WORLD_URL': url or world.url, 'WORLD_ACCESS_FILE': str(world.data / 'access.json'),
           'WORLD_ACTOR': 'a1', 'WORLD_CLIENT_STATE': str(world.data / 'pending.json'),
           'GODOT_TEST_OUTPUT': str(output), 'GODOT_TEST_MODE': mode}
    command = [GODOT, '--path', str(ROOT / 'clients/godot'), '--script', str(ROOT / 'tests/godot/acceptance.gd'), '--resolution', '1280x800', '--audio-driver', 'Dummy']
    command = ['xvfb-run', '-a', '-s', '-screen 0 1280x800x24', *command]
    with output.with_suffix('.log').open('w') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=80)
    text = output.with_suffix('.log').read_text()
    if result.returncode or 'SCRIPT ERROR:' in text or 'ERROR:' in text:
        raise AssertionError(f'{mode}: exit {result.returncode}\n{text[-5000:]}')
    report = json.loads(output.with_suffix('.json').read_text())
    assert report['passed'], report
    return report


def main():
    RUN.mkdir(parents=True)
    results = []
    for name in ('basic', 'bridge', 'after', 'before', 'stale', 'wrong-receipt', 'offline', 'corrupt-journal'):
        world = ActivityCandidate(name, scenario='wilderness-v1')
        proxy = None
        try:
            if name in ('basic', 'bridge', 'corrupt-journal'):
                if name == 'corrupt-journal':
                    (world.data / 'pending.json').write_text('{"bad":{"actorId":"a1","body":"{}"}}')
                report = launch(world, name)
                observed = world.client().observe()
                assert observed['resourceAudit']['conserved']
                results.append({'name': name, **report})
            else:
                proxy = Proxy(world, name)
                if name in ('stale', 'offline'):
                    report = launch(world, name, proxy.url)
                else:
                    first = launch(world, 'lost', proxy.url)
                    original = json.loads(proxy.posts[0])
                    world.restart()
                    report = launch(world, 'retry' if name == 'before' else 'reconnect', proxy.url)
                    assert len(proxy.posts) == (2 if name == 'before' else 1)
                    assert all(json.loads(post) == original for post in proxy.posts)
                    report['checks'] = first['checks'] + report['checks']
                    assert world.client().observe()['self']['inventory']['wood'] == 1
                (world.data / 'requests.json').write_text(json.dumps([json.loads(p) for p in proxy.posts], indent=2))
                results.append({'name': name, **report})
            print(name + ': PASS', flush=True)
        except Exception as error:
            results.append({'name': name, 'passed': False, 'error': str(error)})
            print(name + ': FAIL ' + str(error), flush=True)
        finally:
            if proxy: proxy.stop()
            world.stop()
            with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
                assert not db.execute('PRAGMA foreign_key_check').fetchall()
                total = db.execute('SELECT sum(remaining_wood) FROM resource_nodes').fetchone()[0]
                total += db.execute('SELECT sum(wood) FROM residents').fetchone()[0]
                total += db.execute('SELECT coalesce(sum(embodied_wood),0) FROM entities').fetchone()[0]
                assert total == 12
    summary = {'recordedAtUtc': datetime.now(timezone.utc).isoformat(), 'passed': all(r['passed'] for r in results),
               'actualModelCalls': 0, 'engine': subprocess.check_output([GODOT, '--version'], text=True).strip(), 'results': results}
    (RUN / 'results.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print('Evidence:', RUN / 'results.json')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
