#!/usr/bin/env python3
"""Native Godot navigation against isolated HTTP worlds; no model calls."""
from datetime import datetime, timezone
import json
import math
import sqlite3
import time
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import ROOT
from godot_client import launch, Proxy

RUN = ROOT / '.local/iter0016' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN
RUN.mkdir(parents=True)


def send(client, action):
    observation = client.observe()
    status, receipt = client.command(dict(schemaVersion=1, rulesVersion='r8', commandId=uuid.uuid4().hex,
        expectedStateVersion=observation['stateVersion'], action=action))
    assert status == 200, receipt
    return receipt


def walk(client, target):
    for _ in range(250):
        if math.dist(client.observe()['self']['position'], target) < 1e-6:
            return
        receipt = send(client, {'type': 'walk', 'to': target})
        assert not receipt['result']['blocked'], receipt
        time.sleep(.08)
    raise AssertionError('setup walking deadline')


results = []
for name in ('obstacles', 'tree-change', 'bridge', 'cancel', 'route-loss'):
    world = ActivityCandidate(name, scenario='wilderness-continuous-v1')
    proxy = None
    try:
        if name == 'bridge':
            a = world.client()
            for _ in range(3):
                send(a, {'type': 'gather', 'nodeId': 'tree-west-north'})
            walk(a, [8, 15.5])
            for _ in range(3):
                send(a, {'type': 'gather', 'nodeId': 'tree-west-south'})
            for target in ([12, 15], [15.7, 12]):
                walk(a, target)
        if name in ('cancel', 'route-loss'):
            proxy = Proxy(world, 'after' if name == 'route-loss' else 'delay', delay=.12 if name == 'cancel' else 0)
        report = launch(world, name, url=proxy.url if proxy else None, script=ROOT/'tests/godot/navigation.gd')
        if name == 'bridge':
            with sqlite3.connect(world.data/'world.db') as db:
                resident = db.execute("SELECT x,y,wood FROM residents WHERE actor_id='a2'").fetchone()
                assert math.dist(resident[:2], [13, 7]) < .06 and resident[2] == 0, resident
                builder = db.execute("SELECT x,y FROM residents WHERE actor_id='a1'").fetchone()
                assert math.dist(builder, [26, 9]) < .06, builder
                assert db.execute("SELECT count(*) FROM receipts WHERE actor_id='a2'").fetchone()[0] > 0
        if proxy:
            (world.data/'requests.json').write_text(json.dumps([json.loads(body) for body in proxy.posts], indent=2))
        results.append({'name': name, **report})
        print(name + ': PASS', flush=True)
    except Exception as error:
        results.append({'name': name, 'passed': False, 'error': str(error)})
        print(name + ': FAIL ' + str(error), flush=True)
    finally:
        if proxy:
            proxy.stop()
        world.stop()
        with sqlite3.connect(world.data/'world.db') as db:
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            assert 12 == sum(db.execute(query).fetchone()[0] for query in (
                'SELECT sum(remaining_wood) FROM resource_nodes', 'SELECT sum(wood) FROM residents',
                'SELECT coalesce(sum(embodied_wood),0) FROM entities'))

passed = all(result['passed'] for result in results)
(RUN/'results.json').write_text(json.dumps({'passed': passed, 'groups': len(results),
    'assertions': sum(len(result.get('checks', [])) for result in results), 'results': results}, indent=2))
print('Evidence:', RUN)
raise SystemExit(not passed)
