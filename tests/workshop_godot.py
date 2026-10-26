#!/usr/bin/env python3
"""Native original-command recovery with real HTTP, journal, process restarts and loss.

WORLD_SERVER_DLL selects the frozen candidate. Uses the independent HTTP fixture
builder for actual material acquisition; this suite is an author regression, not
independent gameplay acceptance. No renderer or model call is required here.
"""
from datetime import datetime, timezone
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import uuid
import workshop_api as api

ROOT = api.ROOT
RUN = ROOT/'.local/iter0027/godot'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
GODOT = Path(os.environ.get('GODOT_BIN', ROOT/'.local/tools/godot/Godot_v4.7.2-stable_linux.x86_64')).resolve()


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
                    if owner.mode in ('before', 'capability'):
                        self.close_connection = True
                        return
                else:
                    owner.gets.append(self.path)
                headers = {k: self.headers[k] for k in ('Authorization', 'Content-Type', 'World-Instance-Id', 'World-Capabilities') if k in self.headers}
                conn = http.client.HTTPConnection('127.0.0.1', world.port, timeout=15)
                try:
                    conn.request(self.command, self.path, body or None, headers)
                    reply = conn.getresponse()
                    raw, status, instance = reply.read(), reply.status, reply.getheader('World-Instance-Id')
                finally:
                    conn.close()
                if post and owner.mode in ('after', 'after-later', 'legacy'):
                    self.close_connection = True
                    return
                if status == 200:
                    value = json.loads(raw)
                    if owner.mode == 'receipt' and (post or '/commands/' in self.path):
                        value['result']['workshopAction']['quantity'] += 1
                    if owner.mode == 'event' and '/events?' in self.path and value.get('events'):
                        value['events'][0]['workshopAction']['storedWood'] += 1
                    if owner.mode == 'detail' and '/workshop/actions/' in self.path:
                        value['workshopAction']['storedWood'] += 1
                    if owner.mode == 'unknown' and self.path.endswith('/observation'):
                        value['workshop']['version'] = 99
                    raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                if instance:
                    self.send_header('World-Instance-Id', instance)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def launch(world, proxy, mode, action, output, command='', project=None):
    env = {**os.environ, 'WORLD_URL': proxy.url, 'WORLD_ACCESS_FILE': str(world.data/'access.json'),
           'WORLD_CLIENT_STATE': str(world.data/'pending.json'), 'GODOT_TEST_OUTPUT': str(output),
           'GODOT_TEST_MODE': mode, 'WORKSHOP_TEST_ACTION': json.dumps(action), 'WORKSHOP_TEST_COMMAND': command}
    argv = [str(GODOT), '--headless', '--path', str(project or ROOT/'clients/godot'),
            '--script', str(ROOT/'tests/godot/workshop_recovery.gd')]
    with output.with_suffix('.log').open('w') as log:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            raise
    text = output.with_suffix('.log').read_text()
    assert process.returncode == 0 and 'ERROR:' not in text, text[-5000:]
    result = json.loads(output.read_text())
    assert result['passed'] and all(c['passed'] for c in result['checks']), result
    return result


def journal_hashes(data):
    return {str(p.relative_to(data)): api.sha(p) for p in data.rglob('*') if p.is_file() and ('pending.json' in str(p.relative_to(data)))}


def main():
    if api.DLL is None or not api.DLL.is_file() or not GODOT.is_file():
        raise SystemExit('Set WORLD_SERVER_DLL and provide Godot 4.7.2.')
    RUN.mkdir(parents=True)
    api.RUN = RUN
    paths = [*sorted((ROOT/'clients/godot').glob('*.gd')), Path(__file__).resolve(), ROOT/'tests/godot/workshop_recovery.gd']
    hashes = {str(p.relative_to(ROOT)): api.sha(p) for p in paths}
    # The source below has real tree/source acquisitions and no workshop grants.
    source = api.seed()
    world = api.World(RUN/'prepared', source)
    try:
        world.start()
        world.observe()
        world.stop()
        assert world.admin('adopt-workshop').returncode == 0
        world.start()
        bench = world.send(api.build())[1][1]['result']['workshopAction']['entity']['entityId']
        tool = world.send(api.craft(bench))[1][1]['result']['workshopAction']['tool']['toolId']
        chest = world.send(api.build('wooden_chest.v1', (28.5, 20), tool))[1][1]['result']['workshopAction']['entity']['entityId']
        world.walk([28.5, 21.4])
    finally:
        world.stop()
        api.save(RUN/'prepare-trace.json', world.trace)
    results = []
    cases = [('build_workshop', 'before'), ('craft_tool', 'after'), ('deposit_wood', 'after-later'),
             ('withdraw_wood', 'before'), ('deposit_wood', 'receipt'), ('deposit_wood', 'event'),
             ('deposit_wood', 'detail'), ('deposit_wood', 'capability'), ('walk', 'legacy')]
    if sys.argv[1:]:
        names = {kind+'-'+mode for kind, mode in cases}
        if not set(sys.argv[1:]) <= names:
            raise SystemExit('Unknown recovery case')
        cases = [(kind, mode) for kind, mode in cases if kind+'-'+mode in sys.argv[1:]]
    for kind, mode in cases:
        name = kind+'-'+mode
        current = api.World(RUN/(name+'-world'), source if mode == 'legacy' else world.data)
        proxy = None
        try:
            current.start()
            current.observe()
            if kind == 'build_workshop':
                # The independent visitor is at (30, 21.4); leave that resident
                # outside the new solid furniture footprint.
                action = api.build(at=(30.5, 23))
            elif kind == 'craft_tool':
                current.walk([26, 21.4])
                action = api.craft(bench)
            elif kind == 'walk':
                action = {'type': 'walk', 'to': [26.1, 21.4]}
            else:
                if kind == 'withdraw_wood':
                    current.send(api.storage('deposit_wood', chest, 3))
                action = api.storage(kind, chest, 3)
            old_project = None
            if mode == 'legacy':
                old_project = RUN/'legacy-client'
                old_project.mkdir()
                # Captured immutable old revision, not a simulated missing header.
                for file in ('world_client.gd', 'command_evidence.gd', 'entity_note_evidence.gd', 'entity_canvas_evidence.gd', 'pending_store.gd', 'project.godot'):
                    data = subprocess.run(['git', 'show', '782c2637fe74d3bb71ae974b3112c09e5df6cb13:clients/godot/'+file], cwd=ROOT, check=True, capture_output=True).stdout
                    (old_project/file).write_bytes(data)
                api.save(RUN/'legacy-client-sha256.json', {p.name: api.sha(p) for p in old_project.iterdir()})
            proxy = Proxy(current, mode)
            first = launch(current, proxy, 'lost', action, RUN/(name+'-lost.json'), project=old_project)
            original = first['pending']['commandId']
            saved = journal_hashes(current.data)
            if mode == 'after-later':
                current.send(api.storage('withdraw_wood', chest, 3))
            current.stop()
            if mode == 'legacy':
                assert current.admin('adopt-workshop').returncode == 0
            current.start()
            if mode == 'capability':
                proxy.mode = 'unknown'
                held = launch(current, proxy, 'hold', action, RUN/(name+'-held.json'), original)
                first['checks'] += held['checks']
                assert journal_hashes(current.data) == saved
                assert len(proxy.posts) == 1
            proxy.mode = 'return'
            second = launch(current, proxy, 'return', action, RUN/(name+'-return.json'), original)
            assert len(proxy.posts) == (2 if mode in ('before', 'capability') else 1)
            assert len(set(proxy.posts)) == 1
            if mode == 'after-later':
                assert second['receipt']['result']['workshopAction']['storedWood'] == 3
                assert current.observe()['workshop']['chests'][0]['storedWood'] == 0
            assert not journal_hashes(current.data)
            assert current.observe()['resourceAudit']['conserved']
            with sqlite3.connect(current.data/'world.db') as db:
                assert db.execute('PRAGMA foreign_key_check').fetchall() == []
                assert db.execute('SELECT count(*) FROM receipts WHERE actor_id=? AND command_id=?', ('a2', original)).fetchone()[0] == 1
            results.append({'name': name, 'passed': True, 'checks': first['checks']+second['checks'],
                            'postCount': len(proxy.posts), 'originalBodySha256': hashlib.sha256(proxy.posts[0].encode()).hexdigest(),
                            'receipt': second['receipt']})
            print(name+': PASS', flush=True)
        except Exception as error:
            results.append({'name': name, 'passed': False, 'error': str(error)})
            print(name+': FAIL '+str(error), flush=True)
        finally:
            if proxy:
                api.save(RUN/(name+'-transport.json'), {'posts': [json.loads(p) for p in proxy.posts], 'gets': proxy.gets})
                proxy.stop()
            current.stop()
            api.save(RUN/(name+'-setup.json'), current.trace)
            shutil.rmtree(current.data)
            if mode == 'legacy' and (RUN/'legacy-client').exists():
                shutil.rmtree(RUN/'legacy-client')
    for data in (world.data, source):
        shutil.rmtree(data)
    unchanged = hashes == {str(p.relative_to(ROOT)): api.sha(p) for p in paths}
    passed = unchanged and all(r['passed'] for r in results)
    api.save(RUN/'results.json', {'passed': passed, 'groups': len(results), 'assertions': sum(len(r.get('checks', [])) for r in results),
             'results': results, 'actualModelCalls': 0, 'sourceSha256': hashes, 'sourceUnchanged': unchanged,
             'dllSha256': api.sha(api.DLL), 'temporaryWorldsRemoved': True})
    print('Evidence:', RUN/'results.json')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
