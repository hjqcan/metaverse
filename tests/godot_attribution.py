#!/usr/bin/env python3
"""Actual rendered attribution and connection refresh; isolated HTTP worlds, no models."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import sqlite3
import time
import uuid

import activities_api
from activities_api import ActivityCandidate
from foundation_api import ROOT, DLL
from godot_client import launch

RUN = ROOT / '.local/iter0021' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN
RUN.mkdir(parents=True)
SOURCE = ['clients/godot/main.gd', 'clients/godot/world_view.gd', 'clients/godot/world_client.gd',
          'clients/godot/pending_store.gd', 'tests/godot/attribution.gd', 'tests/godot_attribution.py']


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCE}


def send(client, action):
    o = client.observe()
    status, receipt = client.command(dict(schemaVersion=1, rulesVersion='r8', commandId=uuid.uuid4().hex,
        expectedStateVersion=o['stateVersion'], action=action))
    assert status == 200 and receipt['status'] == 'committed', receipt
    return receipt


def audit(world):
    with sqlite3.connect(f'file:{world.data / "world.db"}?mode=ro', uri=True) as db:
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        total = sum(db.execute(q).fetchone()[0] for q in ('SELECT sum(remaining_wood) FROM resource_nodes',
            'SELECT sum(wood) FROM residents', 'SELECT coalesce(sum(embodied_wood),0) FROM entities'))
        assert total == 12, total
        rows = db.execute('SELECT entity_id,owner_actor_id,embodied_wood FROM entities ORDER BY owner_actor_id').fetchall()
        receipts = [json.loads(row[0]) for row in db.execute('SELECT result_json FROM receipts')]
        builds = [r for r in receipts if r['status'] == 'committed' and r.get('result', {}).get('action') == 'build']
        assert len(builds) == len(rows)
        for entity, owner, wood in rows:
            assert wood == 3
            assert any(r['identity']['actorId'] == owner and r['result']['entityId'] == entity for r in builds)
        return {'materialTotal': total, 'entities': rows, 'receiptCount': len(receipts), 'buildCount': len(builds)}


worlds = []
source_before = hashes()
report = {'passed': False, 'actualModelCalls': 0}
try:
    original = ActivityCandidate('original', scenario='wilderness-continuous-v1'); worlds.append(original)
    replacement = ActivityCandidate('replacement', scenario='wilderness-continuous-v1'); worlds.append(replacement)
    a = original.client()
    for _ in range(3):
        send(a, {'type': 'gather', 'nodeId': 'tree-west-north'})
    for _ in range(100):
        if math.dist(a.observe()['self']['position'], [8, 9]) < 1e-6:
            break
        step = send(a, {'type': 'walk', 'to': [8, 9]})
        assert not step['result']['blocked']
        time.sleep(.1)
    else:
        raise AssertionError('setup movement timed out')
    send(a, {'type': 'build', 'recipeId': 'platform.v1', 'at': [8.2, 10.4]})
    os.environ['WORLD_REPLACEMENT_URL'] = replacement.url
    os.environ['WORLD_REPLACEMENT_ACCESS'] = str(replacement.data / 'access.json')
    report.update(launch(original, 'attribution', script=ROOT / 'tests/godot/attribution.gd'))
except Exception as error:
    report.update(passed=False, error=str(error))
finally:
    for world in worlds:
        world.stop()
    report['databaseAudit'] = {w.data.name: audit(w) for w in worlds}
    report['allSelfStartedServicesStopped'] = all(w.process is None or w.process.poll() is not None for w in worlds)
    report['sourceBefore'] = source_before
    report['sourceAfter'] = hashes()
    report['serverDllSha256'] = hashlib.sha256(DLL.read_bytes()).hexdigest()
    assert source_before == report['sourceAfter']
    (RUN / 'results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
print('Evidence:', RUN)
print('PASS' if report['passed'] else 'FAIL', report.get('error', ''))
raise SystemExit(not report['passed'])
