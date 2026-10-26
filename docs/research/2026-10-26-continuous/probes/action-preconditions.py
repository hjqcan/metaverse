#!/usr/bin/env python3
"""Actual current-r8 conflict traces, plus a read-only candidate admission predicate.

The candidate predicate NEVER executes a command or bypasses current validation.
All material, movement and construction in these worlds uses the unmodified API.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
import foundation_api
import activities_api
import continuous_navigation
from activities_api import ActivityCandidate


def main():
    run = ROOT / '.local/research/action-preconditions' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    shutil.copytree(ROOT / 'src/World.Server/bin/Debug/net10.0', run / 'binary')
    foundation_api.DLL = run / 'binary/World.Server.dll'
    activities_api.RUN_ROOT = run
    source_paths = ['src/World.Server/WorldService.cs', 'src/World.Server/ContinuousWorld.cs',
                    'src/World.Server/Protocol.cs', 'scripts/continuous_navigation.py', 'scripts/foundation_agent.py']
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths}
    worlds, trace, cases = [], [], []

    def world(name):
        w = ActivityCandidate(name, scenario='wilderness-continuous-v1')
        worlds.append(w)
        return w, w.client(), w.client('a2')

    def intent(client, action):
        observed = client.observe()
        assert observed['commandBinding']['required'] is True
        return {'schemaVersion': 1, 'rulesVersion': 'r8', 'commandId': uuid.uuid4().hex,
                'expectedStateVersion': observed['stateVersion'], 'action': action}

    def post(client, req, expected=200, code=None):
        status, reply = client.command(req)
        trace.append({'request': req, 'status': status, 'response': reply})
        assert status == expected, (status, reply)
        if code is not None:
            assert reply['error']['code'] == code, reply
        return reply

    def send(client, action):
        return post(client, intent(client, action))

    def predicate(w, client, request):
        actor = client.observe()['self']['actorId']
        with sqlite3.connect(f"file:{w.data / 'world.db'}?mode=ro", uri=True) as db:
            db.execute('BEGIN')
            latest = db.execute('SELECT state_version FROM worlds').fetchone()[0]
            last = db.execute("SELECT coalesce(max(state_version),0) FROM events WHERE json_extract(event_json,'$.actorId')=?", (actor,)).fetchone()[0]
        anchor = request['expectedStateVersion']
        return {'observedStateVersion': anchor, 'currentStateVersion': latest,
                'lastActorCommitVersion': last,
                'eligibleForTransactionalRevalidation': last <= anchor <= latest,
                'candidateAppliedToServer': False}

    def walk(client, target):
        for _ in range(400):
            o = client.observe()
            if math.dist(o['self']['position'], target) <= 0.06:
                return
            plan = continuous_navigation.route_info(o, target, False, False)
            assert plan['reason'] is None and plan['nextAction'], (target, plan)
            time.sleep(o['movement']['maxStepDistance'] / o['movement']['speed'])
            r = send(client, plan['nextAction'])
            assert not r['result']['blocked'], r
        raise AssertionError('walk bound exhausted')

    def approach(client, node):
        o = client.observe()
        point = next(n['position'] for n in o['resourceNodes'] if n['nodeId'] == node)
        start = o['self']['position']
        if math.dist(start, point) <= 1.5:
            return
        nav = continuous_navigation.navigation(o)
        choices = []
        for i in range(24):
            angle = 2 * math.pi * i / 24
            p = [point[0] + 1.2 * math.cos(angle), point[1] + 1.2 * math.sin(angle)]
            route = nav.route(start, p)
            if route is not None:
                choices.append((continuous_navigation.path_length(start, route), p))
        assert choices
        walk(client, min(choices)[1])

    try:
        w, a, b = world('independent-actions')
        for action in [{'type': 'walk', 'to': [5.05, 7]},
                       {'type': 'gather', 'nodeId': 'tree-west-north'}]:
            request = intent(a, action)
            before = a.observe()['self']
            p = b.observe()['self']['position']
            send(b, {'type': 'walk', 'to': [p[0] + 0.05, p[1]]})
            gate = predicate(w, a, request)
            reply = post(a, request, 409, 'STALE_STATE')
            assert a.observe()['self'] == before
            control = send(a, action)
            cases.append({'name': 'unrelated-walk-blocks-' + action['type'], 'request': request,
                          'candidateGate': gate, 'actualRejected': reply, 'freshRequestControl': control})
        for _ in range(2):
            send(a, {'type': 'gather', 'nodeId': 'tree-west-north'})
        action = {'type': 'build', 'recipeId': 'platform.v1', 'at': [4, 7]}
        request = intent(a, action)
        send(b, {'type': 'walk', 'to': [26.15, 17]})
        gate = predicate(w, a, request)
        reply = post(a, request, 409, 'STALE_STATE')
        control = send(a, action)
        cases.append({'name': 'unrelated-walk-blocks-build', 'request': request,
                      'candidateGate': gate, 'actualRejected': reply, 'freshRequestControl': control})

        origin = a.observe()['self']['position']
        older = intent(a, {'type': 'walk', 'to': [origin[0] - 0.1, origin[1]]})
        send(a, {'type': 'walk', 'to': [origin[0] + 0.1, origin[1]]})
        send(a, {'type': 'walk', 'to': origin})
        assert a.observe()['self']['position'] == origin
        gate = predicate(w, a, older)
        assert gate['eligibleForTransactionalRevalidation'] is False
        reply = post(a, older, 409, 'STALE_STATE')
        cases.append({'name': 'same-actor-ABA', 'request': older, 'samePositionAgain': True,
                      'candidateGate': gate, 'actualRejected': reply})
        print('Independent walk/gather/build interference and same-actor ABA verified', flush=True)

        w, a, b = world('last-material')
        for node in ['tree-west-north', 'tree-west-south']:
            approach(a, node)
            for _ in range(3):
                send(a, {'type': 'gather', 'nodeId': node})
        walk(a, [15.7, 12])
        send(a, {'type': 'build', 'recipeId': 'bridge.v1', 'at': [18, 12]})
        walk(a, [20.7, 12])
        node = 'tree-east-north'
        approach(a, node)
        approach(b, node)
        for _ in range(2):
            send(a, {'type': 'gather', 'nodeId': node})
        ra, rb = intent(a, {'type': 'gather', 'nodeId': node}), intent(b, {'type': 'gather', 'nodeId': node})
        assert ra['expectedStateVersion'] == rb['expectedStateVersion']
        winner = post(a, ra)
        gate = predicate(w, b, rb)
        assert gate['eligibleForTransactionalRevalidation'] is True
        loser = post(b, rb, 409, 'STALE_STATE')
        fresh = intent(b, rb['action'])
        depleted = post(b, fresh, 422, 'RESOURCE_DEPLETED')
        observation = b.observe()
        assert observation['self']['inventory']['wood'] == 0
        assert observation['resourceAudit']['conserved'] is True
        cases.append({'name': 'last-unit-competition', 'request': rb, 'winner': winner,
                      'candidateGate': gate, 'actualRejected': loser, 'freshRequestControl': depleted,
                      'candidateMustStillReject': 'RESOURCE_DEPLETED', 'resourceAudit': observation['resourceAudit']})
        print('Two actors competed for the same final unit; depletion revalidation verified', flush=True)
    finally:
        for w in worlds:
            w.stop()
        (run / 'trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2) + '\n')

    audits = []
    for w in worlds:
        with sqlite3.connect(f"file:{w.data / 'world.db'}?mode=ro", uri=True) as db:
            total = sum(db.execute(q).fetchone()[0] for q in [
                'SELECT coalesce(sum(remaining_wood),0) FROM resource_nodes',
                'SELECT sum(wood) FROM residents', 'SELECT coalesce(sum(embodied_wood),0) FROM entities'])
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            fk = len(db.execute('PRAGMA foreign_key_check').fetchall())
            assert total == 12 and integrity == 'ok' and fk == 0
            audits.append({'world': w.data.name, 'materialTotal': total, 'integrity': integrity,
                           'foreignKeyErrors': fk, 'processStopped': w.process.poll() is not None})
    report = {'recordedAtUtc': datetime.now(timezone.utc).isoformat(),
              'kind': 'actual-current-r8-conflicts-and-read-only-candidate-gate',
              'actualModelCalls': 0, 'candidateCommandsExecuted': 0, 'actualHttpCommands': len(trace),
              'repositoryHeadAtFinish': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'assemblySha256': hashlib.sha256(foundation_api.DLL.read_bytes()).hexdigest(),
              'sourceHashes': hashes, 'sourceFilesUnchangedDuringRun': all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == h for p,h in hashes.items()),
              'cases': cases, 'databaseAudits': audits, 'allExperimentProcessesStopped': all(w.process.poll() is not None for w in worlds)}
    (run / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', run / 'results.json')
    print(json.dumps({'cases': len(cases), 'actualHttpCommands': len(trace), 'audits': audits}))


if __name__ == '__main__':
    main()
