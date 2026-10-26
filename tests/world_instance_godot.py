#!/usr/bin/env python3
"""Real Godot restarts, endpoint replacement and relocation. Isolated worlds, no models."""
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import ROOT
from godot_client import GODOT, Proxy

RUN = ROOT / '.local/world-instance/godot' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN


def launch(name, mode, world, state, original, url=None, access=None):
    output = RUN / (name + '.json')
    env = {**os.environ, 'WORLD_URL': url or world.url, 'WORLD_CLIENT_STATE': str(state),
           'INSTANCE_TEST_MODE': mode, 'INSTANCE_TEST_ACCESS': str(access or world.data / 'access.json'),
           'INSTANCE_TEST_OUTPUT': str(output), 'INSTANCE_TEST_ORIGINAL': str(original)}
    log = RUN / (name + '.log')
    with log.open('w') as stream:
        process = subprocess.run([GODOT, '--headless', '--path', str(ROOT / 'clients/godot'),
                                  '--script', str(ROOT / 'tests/godot/world_instance.gd')],
                                 env=env, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=35)
    text = log.read_text()
    assert process.returncode == 0 and 'ERROR:' not in text, name + ': ' + text[-4000:]
    result = json.loads(output.read_text())
    assert result['passed'], result
    print(name + ': PASS', flush=True)
    return {'name': name, **result}


def contents(state):
    directory = state.with_name(state.name + '.d')
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*.json')}


def main():
    RUN.mkdir(parents=True)
    results = []
    worlds, proxies = [], []
    try:
        for loss in ('after', 'before'):
            original_world = ActivityCandidate(loss + '-original', scenario='wilderness-continuous-v1')
            worlds.append(original_world)
            state, original = RUN / (loss + '-pending.json'), RUN / (loss + '-original.json')
            proxy = Proxy(original_world, loss)
            proxies.append(proxy)
            results.append(launch(loss + '-save', 'save', original_world, state, original, proxy.url))
            pending_before = contents(state)
            assert len(pending_before) == 1
            endpoint = proxy.url
            proxy.stop(); proxies.remove(proxy)
            original_world.stop()
            replacement = ActivityCandidate(loss + '-replacement', scenario='wilderness-continuous-v1')
            worlds.append(replacement)
            replacement.stop()
            replacement.url = endpoint
            replacement.port = int(endpoint.rsplit(':', 1)[1])
            replacement.env['WORLD_URL'] = endpoint
            replacement.start()
            results.append(launch(loss + '-replacement', 'replacement', replacement, state, original))
            assert contents(state) == pending_before, 'replacement altered the original durable record'
            replacement.stop()
            with sqlite3.connect(replacement.data / 'world.db') as db:
                assert db.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0
                assert db.execute('SELECT sum(wood) FROM residents').fetchone()[0] == 0
            # Test corruption on a copied journal; keep the original available to recover.
            corrupt_state = RUN / (loss + '-corrupt.json')
            shutil.copytree(str(state) + '.d', str(corrupt_state) + '.d')
            record_path = next(corrupt_state.with_name(corrupt_state.name + '.d').rglob('*.json'))
            damaged = json.loads(record_path.read_text()); del damaged['record']['instanceId']
            record_path.write_text(json.dumps(damaged))
            corrupt_before = contents(corrupt_state)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); original_world.port = sock.getsockname()[1]
            original_world.url = f'http://127.0.0.1:{original_world.port}'
            original_world.env['WORLD_URL'] = original_world.url
            original_world.issue('a1', 86400)
            new_access = original_world.data / 'issued-a1.json'
            results.append(launch(loss + '-corrupt', 'corrupt', original_world, corrupt_state, original, access=new_access))
            assert contents(corrupt_state) == corrupt_before
            results.append(launch(loss + '-return', 'return', original_world, state, original, access=new_access))
            assert contents(state) == {}, 'settled original record survived'
            original_world.stop()
            with sqlite3.connect(original_world.data / 'world.db') as db:
                assert db.execute('SELECT count(*) FROM receipts').fetchone()[0] == 1
                assert db.execute('SELECT wood FROM residents WHERE actor_id="a1"').fetchone()[0] == 1

        legacy_world = ActivityCandidate('legacy-record', scenario='wilderness-continuous-v1')
        worlds.append(legacy_world)
        state = RUN / 'legacy.json'
        intent = dict(schemaVersion=1, rulesVersion='r8', commandId='legacy_unbound', expectedStateVersion=0,
                      action={'type': 'gather', 'nodeId': 'tree-west-north'})
        key = hashlib.sha256((legacy_world.url + '/foundation-01/a1').encode()).hexdigest()
        state.write_text(json.dumps({key: {'actorId': 'a1', 'commandId': intent['commandId'], 'body': json.dumps(intent)}}))
        before = state.read_bytes()
        results.append(launch('legacy-check', 'legacy', legacy_world, state, RUN / 'unused.json'))
        assert state.read_bytes() == before
        legacy_world.stop()
        with sqlite3.connect(legacy_world.data / 'world.db') as db:
            assert db.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0
    finally:
        for proxy in proxies:
            proxy.stop()
        for world in worlds:
            world.stop()
    report = {'passed': True, 'actualModelCalls': 0, 'groups': len(results),
              'assertions': sum(len(r['checks']) for r in results), 'results': results,
              'allExperimentProcessesStopped': all(w.process.poll() is not None for w in worlds)}
    (RUN / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json')


if __name__ == '__main__':
    main()
