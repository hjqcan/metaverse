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
import time
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
    def __init__(self, world, mode, delay=0):
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
                    if delay:
                        time.sleep(delay)
                    if owner.mode == 'stale' and owner.drop:
                        b = world.client('a2'); o = b.observe()
                        status, _ = b.request('POST', '/v1/worlds/foundation-01/commands', {'schemaVersion': 1, 'rulesVersion': o['rulesVersion'], 'commandId': 'other-resident', 'expectedStateVersion': o['stateVersion'], 'action': ({'type': 'walk', 'to': [26.1, 17]} if o['rulesVersion'] == 'r8' else {'type': 'move', 'dx': 0, 'dy': -1})})
                        assert status == 200
                    if owner.mode == 'before' and owner.drop:
                        owner.drop = False
                        self.close_connection = True
                        return
                connection = http.client.HTTPConnection('127.0.0.1', world.port, timeout=10)
                headers = {'Authorization': self.headers.get('Authorization', ''), 'Content-Type': 'application/json'}
                if 'World-Instance-Id' in self.headers:
                    headers['World-Instance-Id'] = self.headers['World-Instance-Id']
                connection.request(self.command, self.path, body=body or None, headers=headers)
                reply = connection.getresponse(); data = reply.read(); status = reply.status
                instance = reply.getheader('World-Instance-Id')
                connection.close()
                if owner.mode == 'stale' and self.path.endswith('/observation') and status == 200:
                    legacy = json.loads(data)
                    legacy.pop('commandConcurrency', None)
                    data = json.dumps(legacy).encode()
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
                if instance:
                    self.send_header('World-Instance-Id', instance)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()


def launch(world, mode, url=None, script=None):
    output = world.data / mode
    env = {**os.environ, 'WORLD_URL': url or world.url, 'WORLD_ACCESS_FILE': str(world.data / 'access.json'),
           'WORLD_ACTOR': 'a1', 'WORLD_CLIENT_STATE': str(world.data / 'pending.json'),
           'GODOT_TEST_OUTPUT': str(output), 'GODOT_TEST_MODE': mode}
    command = [GODOT, '--path', str(ROOT / 'clients/godot'), '--script', str(script or ROOT / 'tests/godot/acceptance.gd'), '--resolution', '1280x800', '--audio-driver', 'Dummy']
    command = ['xvfb-run', '-a', '-s', '-screen 0 1280x800x24', *command]
    with output.with_suffix('.log').open('w') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=80)
    text = output.with_suffix('.log').read_text()
    if result.returncode or 'SCRIPT ERROR:' in text or 'ERROR:' in text:
        raise AssertionError(f'{mode}: exit {result.returncode}\n{text[-5000:]}')
    report = json.loads(output.with_suffix('.json').read_text())
    assert report['passed'] and all(item['passed'] for item in report.get('checks', [])), report
    return report


def main():
    return subprocess.call([sys.executable, str(ROOT / 'tests/continuous_godot.py')])

if __name__ == '__main__':
    raise SystemExit(main())
