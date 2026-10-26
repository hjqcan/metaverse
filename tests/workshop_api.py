#!/usr/bin/env python3
"""Independent workshop-v1 HTTP/SQLite acceptance, with real material acquisition.

Run only against an explicitly frozen candidate:
  WORLD_SERVER_DLL=/absolute/candidate/World.Server.dll python3 tests/workshop_api.py

All services and copies live under .local/test-agent2. No original resident world
is touched. Setup uses real requests and elapsed service time, never SQL grants.
The compact report and HTTP evidence survive automatic disposal of test worlds.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '/v1/worlds/foundation-01'
CAPABILITY = 'workshop-v1'
MODE = 'actor-state-v1'
OWNER, VISITOR = 'a2', 'a3'
RUN = ROOT / '.local/test-agent2' / ('iter27-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
DLL = Path(os.environ['WORLD_SERVER_DLL']).resolve() if os.environ.get('WORLD_SERVER_DLL') else None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def snapshot(data):
    with sqlite3.connect(f'file:{Path(data)/"world.db"}?mode=ro', uri=True) as db:
        result = {name: db.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall()
                  for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()}
        result['user_version'] = db.execute('PRAGMA user_version').fetchone()
        return result


def business_snapshot(data):
    """Separate background material clock commits from request-owned mutations."""
    rows = snapshot(data)
    for table in ('material_source', 'material_production', 'worlds', 'sqlite_sequence'):
        rows.pop(table, None)
    environmental = set()
    with sqlite3.connect(f'file:{Path(data)/"world.db"}?mode=ro', uri=True) as db:
        for seq, raw in db.execute('SELECT seq,event_json FROM events'):
            if json.loads(raw)['type'] in ('materialProduced', 'materialReservationGranted', 'materialReservationExpired'):
                environmental.add(seq)
        rows['events'] = db.execute("SELECT event_json FROM events WHERE json_extract(event_json,'$.type') NOT IN ('materialProduced','materialReservationGranted','materialReservationExpired') ORDER BY seq").fetchall()
        rows['resource_ledger'] = [row for row in db.execute('SELECT event_seq,source_account,destination_account,quantity FROM resource_ledger ORDER BY rowid') if row[0] not in environmental]
    return rows


def build(recipe='workbench.v1', at=(26, 20), tool=None):
    return dict(type='build_workshop', capabilityVersion=1, recipeId=recipe, at=list(at), toolId=tool)


def craft(entity):
    return dict(type='craft_tool', capabilityVersion=1, entityId=entity, recipeId='wooden_mallet.v1')


def storage(action, entity, quantity):
    return dict(type=action, capabilityVersion=1, entityId=entity, quantity=quantity)


class World:
    """Small raw transport: no automatic observation, capability upgrade or retry."""
    def __init__(self, path, source=None):
        self.data = Path(path)
        self.data.mkdir(parents=True, mode=0o700)
        if source is not None:
            with sqlite3.connect(f'file:{Path(source)/"world.db"}?mode=ro', uri=True) as src, sqlite3.connect(self.data/'world.db') as dst:
                src.backup(dst)
            shutil.copy2(Path(source)/'access.json', self.data/'access.json')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('WORLD_')}
        self.env.update(WORLD_DATA_DIR=str(self.data), WORLD_URL=f'http://127.0.0.1:{self.port}', WORLD_ENABLE_FAULTS='1')
        if source is None:
            self.env['WORLD_SCENARIO'] = 'wilderness-material-access-v1'
        self.process = self.log = None
        self.access = json.loads((self.data/'access.json').read_text()) if source else None
        self.instance = None
        self.trace = []

    def start(self):
        self.log = (self.data/'server.log').open('a')
        self.process = subprocess.Popen(['dotnet', str(DLL)], cwd=ROOT, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.stop()
                raise RuntimeError('Candidate startup failed: ' + (self.data/'server.log').read_text()[-5000:])
            try:
                if self.request('GET', '/healthz', authenticated=False, record=False)[0] == 200:
                    self.access = json.loads((self.data/'access.json').read_text())
                    return
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(.05)
        self.stop()
        raise RuntimeError('Dedicated candidate startup timeout')

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()

    def restart(self):
        self.stop()
        self.start()

    def admin(self, verb, instance=None, extra=()):
        return subprocess.run(['dotnet', str(DLL), verb, '--instance', instance or self.instance, *extra],
                              cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=20)

    def request(self, method, path, payload=None, actor=OWNER, capability=CAPABILITY,
                instance=True, token=None, fault=None, authenticated=True, record=True):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + (token or self.access['sessions'][actor]['token'])
        if instance and self.instance:
            headers['World-Instance-Id'] = self.instance if instance is True else instance
        if capability is not None:
            headers['World-Capabilities'] = capability
        if fault:
            headers['X-Test-Fault'] = fault
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            body = json.dumps(payload, separators=(',', ':'), allow_nan=False) if payload is not None else None
            conn.request(method, path, body, headers)
            reply = conn.getresponse()
            content = reply.read()
            parsed = json.loads(content) if content else None
            result = reply.status, parsed, content, reply.getheader('World-Instance-Id')
        finally:
            conn.close()
        if record:
            entry = dict(method=method, path=path, actor=actor, request=payload, capability=capability,
                         status=result[0], response=result[1], responseSha256=hashlib.sha256(result[2]).hexdigest())
            # Avoid repeating full observations for every 0.6m setup walk.
            if path == PREFIX+'/observation' and result[0] == 200:
                entry['response'] = {k: result[1][k] for k in ('stateVersion', 'eventCursor', 'self')}
            self.trace.append(entry)
        return result

    def observe(self, actor=OWNER):
        status, body, _, binding = self.request('GET', PREFIX+'/observation', actor=actor)
        if status != 200:
            raise AssertionError((status, body))
        actual = body['world']['instanceId']
        if self.instance is not None and actual != self.instance:
            raise AssertionError('Unexpected instance replacement')
        if actual != binding:
            raise AssertionError('Observation instance header/body disagree')
        self.instance = actual
        return body

    def intent(self, action, actor=OWNER, observed=None):
        observed = observed or self.observe(actor)
        return dict(schemaVersion=1, rulesVersion=observed['rulesVersion'], commandId='qa2_'+uuid.uuid4().hex,
                    expectedStateVersion=observed['stateVersion'], preconditionMode=MODE, action=deepcopy(action))

    def send(self, action, actor=OWNER):
        intent = self.intent(action, actor)
        response = self.request('POST', PREFIX+'/commands', intent, actor=actor)
        if response[0] != 200:
            raise AssertionError((intent, response[:2]))
        return intent, response

    def walk(self, target, actor=OWNER):
        """Only explicit clear waypoints; this is not the production navigator."""
        for _ in range(350):
            current = self.observe(actor)['self']['position']
            if math.dist(current, target) <= .025:
                return
            time.sleep(.205)
            _, response = self.send({'type': 'walk', 'to': list(target)}, actor)
            if response[1]['result']['blocked']:
                raise AssertionError(('Setup waypoint blocked', current, target, response[1]))
        raise AssertionError(('Setup waypoint did not finish', target))

    def fill(self, actor, target=12):
        """At the actual source: reserve, await real production, harvest one by one."""
        while self.observe(actor)['self']['inventory']['wood'] < target:
            _, reserved = self.send({'type': 'reserve_material', 'sourceId': 'wood-source-east'}, actor)
            rid = reserved[1]['result']['reservationId']
            deadline = time.monotonic()+85
            while time.monotonic() < deadline:
                observed = self.observe(actor)
                if any(r['reservationId'] == rid and r['status'] == 'active' for r in observed['materialAccess']['recentReservations']):
                    break
                time.sleep(.25)
            else:
                raise AssertionError('Real reservation never became active')
            for _ in range(min(3, target-observed['self']['inventory']['wood'])):
                self.send({'type': 'harvest_material', 'reservationId': rid}, actor)
            remaining = next(r for r in self.observe(actor)['materialAccess']['recentReservations'] if r['reservationId'] == rid)
            if remaining['status'] == 'active':
                self.send({'type': 'cancel_reservation', 'reservationId': rid}, actor)


def seed(full=True):
    """Fresh r10/storage11 fixture; distinct from QA1's continuing natural history."""
    world = World(RUN/'seed')
    try:
        world.start()
        world.observe()
        world.stop()
        for verb in ('enable-material-source', 'adopt-continuous-material-source'):
            done = world.admin(verb)
            if done.returncode:
                raise AssertionError((verb, done.stderr))
        world.start()
        for _ in range(3):
            world.send({'type': 'gather', 'nodeId': 'tree-east-south'})
        if not full:
            world.walk([26, 21.4])
            save(RUN/'seed-final.json', {OWNER: world.observe()})
            return world.data
        for point in ([27.2, 17], [27.2, 6], [26.5, 5.8]):
            world.walk(point)
        for _ in range(3):
            world.send({'type': 'gather', 'nodeId': 'tree-east-north'})
        for point in ([27.2, 6], [28, 10]):
            world.walk(point)
        world.fill(OWNER)
        for point in ([30, 10], [30, 21.4], [26, 21.4]):
            world.walk(point)
        world.fill(VISITOR)
        for point in ([30, 10], [30, 21.4]):
            world.walk(point, VISITOR)
        save(RUN/'seed-final.json', {actor: world.observe(actor) for actor in (OWNER, VISITOR)})
        return world.data
    finally:
        world.stop()
        save(RUN/'seed-trace.json', world.trace)


class WorkshopAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DLL is None or not DLL.is_file():
            raise RuntimeError('Set WORLD_SERVER_DLL to the frozen candidate; this suite does not build or use an implicit binary')
        RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
        save(RUN/'candidate.json', {'dll': str(DLL), 'dllSha256': sha(DLL), 'testSha256': sha(__file__),
                                  'contractSha256': sha(ROOT/'docs/contracts/workshop-v1.md'), 'actualModelCalls': 0})
        shutil.copyfile(__file__, RUN/'probe-source.py')
        shutil.copyfile(ROOT/'docs/contracts/workshop-v1.md', RUN/'contract-at-start.md')
        only_canvas = sys.argv[1:] == ['test_18_canvas_adopted_after_workshop_cannot_disappear_on_restart']
        cls.source = seed(full=not only_canvas)

    def setUp(self):
        self.world = World(RUN/self._testMethodName, self.source)
        self.addCleanup(self.cleanup)
        self.world.start()
        self.world.observe()
        self.original = snapshot(self.world.data)
        self.adopted = False

    def cleanup(self):
        self.latest_audit = None
        if self.world.process is not None and self.world.process.poll() is None:
            self.latest_audit = self.world.observe()['resourceAudit']
        self.world.stop()
        save(RUN/(self._testMethodName+'-trace.json'), self.world.trace)
        self.audit_db()

    def audit_db(self):
        with sqlite3.connect(f'file:{self.world.data/"world.db"}?mode=ro', uri=True) as db:
            self.assertEqual('ok', db.execute('PRAGMA integrity_check').fetchone()[0])
            self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())
            tools = chests = 0
            tool_rows = chest_rows = []
            if self.adopted:
                # Storage represents a mallet as one durable row; the v1 recipe is 1 wood.
                tool_rows = db.execute('SELECT tool_id,1 FROM workshop_tools').fetchall()
                chest_rows = db.execute('SELECT entity_id,wood FROM workshop_chests').fetchall()
                tools, chests = sum(r[1] for r in tool_rows), sum(r[1] for r in chest_rows)
                self.assertTrue(all(0 <= q <= 12 for _, q in chest_rows))
            issued, version = db.execute('SELECT issued_wood,state_version FROM worlds').fetchone()
            generated, source = db.execute('SELECT generated_wood,stock_wood FROM material_source').fetchone()
            wild = db.execute('SELECT coalesce(sum(remaining_wood),0) FROM resource_nodes').fetchone()[0]
            inventories = db.execute('SELECT actor_id,wood FROM residents').fetchall()
            entities = db.execute('SELECT entity_id,embodied_wood FROM entities').fetchall()
            self.assertTrue(all(0 <= q <= 12 for _, q in inventories))
            self.assertEqual(12+generated, issued)
            self.assertEqual(wild+source+sum(q for _, q in inventories+entities)+tools+chests, issued)
            self.assertEqual(generated, db.execute('SELECT coalesce(sum(quantity),0) FROM material_production').fetchone()[0])
            self.assertEqual(version+1, db.execute('SELECT count(*) FROM events').fetchone()[0])
            if self.latest_audit is not None:
                expected = dict(wildWood=wild, inventoryWood=sum(q for _, q in inventories), embodiedWood=sum(q for _, q in entities))
                if self.adopted:
                    expected.update(toolWood=tools, storedWood=chests)
                for key, value in expected.items():
                    self.assertEqual(value, self.latest_audit[key], key)
                self.assertIs(True, self.latest_audit['conserved'])
                a = self.latest_audit
                self.assertEqual(a['issuedWood'], sum(a.get(k, 0) for k in ('wildWood', 'sourceWood', 'inventoryWood', 'embodiedWood', 'toolWood', 'storedWood')))
                self.assertEqual(12+a['generatedWood'], a['issuedWood'])
            balances = {}
            for src, dst, q in db.execute('SELECT source_account,destination_account,quantity FROM resource_ledger'):
                balances[src] = balances.get(src, 0)-q
                balances[dst] = balances.get(dst, 0)+q
            self.assertEqual(-12, balances.pop('initial-issuance'))
            self.assertEqual(-generated, balances.pop('ecological-input', 0))
            self.assertEqual(wild, balances.pop('wild-wood', 0))
            self.assertEqual(source, balances.pop('source:wood-source-east', 0))
            for prefix, values in [('inventory:', inventories), ('entity:', entities), ('tool:', tool_rows), ('chest:', chest_rows)]:
                for key, quantity in values:
                    self.assertEqual(quantity, balances.pop(prefix+key, 0), (prefix, key))
            self.assertFalse({k: v for k, v in balances.items() if v}, balances)
            save(RUN/(self._testMethodName+'-audit.json'), dict(issuedWood=issued, generatedWood=generated,
                 wildWood=wild, sourceWood=source, inventoryWood=sum(q for _, q in inventories),
                 embodiedWood=sum(q for _, q in entities), toolWood=tools, storedWood=chests,
                 stateVersion=version, integrity='ok', foreignKeys=[], ledgerBalanced=True))

    def adopt(self):
        self.world.stop()
        result = self.world.admin('adopt-workshop')
        self.assertEqual(0, result.returncode, result.stderr)
        self.adopted = True
        self.world.start()
        return self.world.observe()

    def post(self, request, actor=OWNER, status=200, code=None, **kwargs):
        result = self.world.request('POST', PREFIX+'/commands', request, actor=actor, **kwargs)
        self.assertEqual(status, result[0], result[1])
        if code:
            self.assertEqual(code, result[1]['error']['code'])
        return result

    def reject(self, action, status, code, actor=OWNER):
        intent = self.world.intent(action, actor)
        response = self.post(intent, actor, status, code)
        return intent, response

    def fact(self, intent, response, actor=OWNER):
        body = response[1]
        self.assertEqual('committed', body['status'])
        self.assertEqual(intent['action']['type'], body['result']['action'])
        detail = body['result']['workshopAction']
        self.assertEqual({'capabilityVersion', 'authorActorId', 'operatorId', 'commandId', 'action', 'entity', 'tool',
                          'quantity', 'inventoryWoodBefore', 'inventoryWood', 'storedWoodBefore', 'storedWood',
                          'position', 'stateVersion', 'eventCursor', 'completedAtUtc'}, set(detail))
        self.assertEqual(intent['action'], detail['action'])
        self.assertEqual((1, actor, body['identity']['operatorId'], intent['commandId'], body['stateVersion'], body['eventCursor']),
                         tuple(detail[k] for k in ('capabilityVersion', 'authorActorId', 'operatorId', 'commandId', 'stateVersion', 'eventCursor')))
        status, queried, _, _ = self.world.request('GET', PREFIX+f'/workshop/actions/{actor}/'+intent['commandId'], actor=actor)
        self.assertEqual(200, status, queried)
        self.assertEqual(detail, queried['workshopAction'])
        status, stream, _, _ = self.world.request('GET', PREFIX+'/events?after='+str(detail['eventCursor']-1), actor=actor, capability=None)
        self.assertEqual(200, status, stream)
        event = stream['events'][0]
        self.assertEqual(('workshopActionCompleted', actor, intent['commandId'], detail['stateVersion'], detail['eventCursor']),
                         tuple(event[k] for k in ('type', 'actorId', 'commandId', 'stateVersion', 'seq')))
        self.assertEqual(detail, event['workshopAction'])
        other = VISITOR if actor == OWNER else OWNER
        status, foreign, _, _ = self.world.request('GET', PREFIX+'/events?after='+str(detail['eventCursor']-1), actor=other, capability=None)
        self.assertEqual(200, status, foreign)
        self.assertEqual({key: event[key] for key in ('seq', 'stateVersion', 'actorId', 'commandId', 'type')}, foreign['events'][0])
        self.assertEqual(stream['nextCursor'], foreign['nextCursor'])
        queried = self.world.request('GET', PREFIX+'/commands/'+intent['commandId'], actor=actor, capability=None)
        self.assertEqual(response[2], queried[2])
        return detail

    def chain(self):
        self.adopt()
        self.bench_request, self.bench_reply = self.world.send(build())
        self.bench = self.fact(self.bench_request, self.bench_reply)['entity']['entityId']
        self.tool_request, self.tool_reply = self.world.send(craft(self.bench))
        self.tool = self.fact(self.tool_request, self.tool_reply)['tool']['toolId']
        self.world.walk([28.5, 21.4])
        self.chest_request, self.chest_reply = self.world.send(build('wooden_chest.v1', [28.5, 20], self.tool))
        self.chest = self.fact(self.chest_request, self.chest_reply)['entity']['entityId']

    def test_01_explicit_adoption_old_receipts_pending_and_observation_gate(self):
        legacy, original = self.world.send({'type': 'walk', 'to': [26.05, 21.4]})
        pending = self.world.intent({'type': 'walk', 'to': [26.1, 21.4]})
        no_capability, denied = self.reject(build(), 422, 'WORKSHOP_UNAVAILABLE')
        self.assertEqual(404, self.world.request('GET', PREFIX+'/commands/'+pending['commandId'])[0])
        self.assertNotEqual(0, self.world.admin('adopt-workshop').returncode)
        self.world.stop()
        before = snapshot(self.world.data)
        self.assertNotEqual(0, self.world.admin('adopt-workshop', 'w_'+'0'*32).returncode)
        self.assertEqual(before, snapshot(self.world.data))
        self.assertEqual(0, self.world.admin('adopt-workshop').returncode)
        self.adopted = True
        after = snapshot(self.world.data)
        self.assertEqual((13,), after['user_version'])
        for name, values in before.items():
            if name not in ('worlds', 'events', 'sqlite_sequence', 'user_version', 'recipes'):
                self.assertEqual(values, after[name], name)
        self.assertEqual(before['events'], after['events'][:-1])
        self.assertEqual(len(before['events'])+1, len(after['events']))
        self.assertEqual(0, self.world.admin('adopt-workshop').returncode)
        self.assertEqual(after, snapshot(self.world.data))
        self.world.start()
        for capability in (None, '', 'unrecognized-v1'):
            status, error, _, binding = self.world.request('GET', PREFIX+'/observation', capability=capability)
            self.assertEqual(409, status, error)
            self.assertEqual('CLIENT_CAPABILITY_REQUIRED', error['error']['code'])
            self.assertEqual(['workshop-v1'], error['requiredCapabilities'])
            self.assertEqual(self.world.instance, binding)
        observed = self.world.observe()
        self.assertEqual('r10', observed['rulesVersion'])
        self.assertEqual(original[2], self.post(legacy, capability=None)[2])
        self.assertEqual(denied[2], self.post(no_capability, status=422, code='WORKSHOP_UNAVAILABLE')[2])
        self.assertEqual(200, self.world.request('GET', PREFIX+'/events?after=0', capability=None)[0])
        self.assertEqual(404, self.world.request('GET', PREFIX+'/commands/'+pending['commandId'], capability=None)[0])
        before_gate = business_snapshot(self.world.data)
        for request in (pending, self.world.intent(build())):
            self.post(request, status=409, code='CLIENT_CAPABILITY_REQUIRED', capability=None)
            self.assertEqual(404, self.world.request('GET', PREFIX+'/commands/'+request['commandId'], capability=None)[0])
        self.assertEqual(before_gate, business_snapshot(self.world.data))
        self.post(pending)

    def test_02_complete_chain_original_facts_restart_and_use_withdrawn_wood(self):
        self.chain()
        self.assertEqual(5, self.world.observe()['self']['inventory']['wood'])
        deposited, original = self.world.send(storage('deposit_wood', self.chest, 3))
        detail = self.fact(deposited, original)
        self.assertEqual((5, 2, 0, 3), tuple(detail[k] for k in ('inventoryWoodBefore', 'inventoryWood', 'storedWoodBefore', 'storedWood')))
        self.world.walk([30, 22.5])
        self.world.restart()
        self.assertEqual(original[2], self.post(deposited)[2])
        self.world.walk([28.5, 22.5])
        self.world.walk([28.5, 21.4])
        withdrawn, response = self.world.send(storage('withdraw_wood', self.chest, 3))
        self.assertEqual((2, 5, 3, 0), tuple(self.fact(withdrawn, response)[k] for k in ('inventoryWoodBefore', 'inventoryWood', 'storedWoodBefore', 'storedWood')))
        self.assertEqual(detail, self.fact(deposited, original))
        self.world.send({'type': 'build', 'recipeId': 'platform.v1', 'at': [26, 22.5]})
        self.assertEqual(2, self.world.observe()['self']['inventory']['wood'])
        for intent, reply in ((self.bench_request, self.bench_reply), (self.tool_request, self.tool_reply), (self.chest_request, self.chest_reply), (deposited, original), (withdrawn, response)):
            self.assertEqual(reply[2], self.post(intent)[2])

    def test_03_public_bench_own_mallet_private_chest_and_observation_privacy(self):
        self.chain()
        self.reject(build('wooden_chest.v1', [30, 20]), 422, 'TOOL_REQUIRED', VISITOR)
        self.reject(build('wooden_chest.v1', [30, 20], self.tool), 403, 'TOOL_NOT_OWNED', VISITOR)
        for action in ('deposit_wood', 'withdraw_wood'):
            self.reject(storage(action, self.chest, 1), 403, 'WORKSHOP_ACCESS_DENIED', VISITOR)
        owner_before = self.world.observe()
        pending = self.world.intent(storage('deposit_wood', self.chest, 1))
        self.world.walk([26, 21.4], VISITOR)
        request, reply = self.world.send(craft(self.bench), VISITOR)
        other_tool = self.fact(request, reply, VISITOR)['tool']
        self.assertEqual(VISITOR, other_tool['ownerActorId'])
        self.assertEqual(self.bench, other_tool['workbenchId'])
        self.assertNotEqual(self.tool, other_tool['toolId'])
        owner_after = self.world.observe()
        self.assertEqual(owner_before['self'], owner_after['self'])
        self.assertEqual(12-1, self.world.observe(VISITOR)['self']['inventory']['wood'])
        self.post(pending)  # Another resident's use of my bench does not invalidate me.
        observed = self.world.observe(VISITOR)
        self.assertEqual([], observed['workshop']['chests'])
        self.assertTrue(all(t['ownerActorId'] == VISITOR for t in observed['workshop']['tools']))
        self.assertTrue(any(e['entityId'] == self.chest for e in observed['entities']))
        self.world.walk([30, 21.4], VISITOR)
        request, reply = self.world.send(build('wooden_chest.v1', [30.5, 20], other_tool['toolId']), VISITOR)
        self.fact(request, reply, VISITOR)

    def test_04_strict_fields_integer_quantities_and_target_type(self):
        self.chain()
        before = self.world.observe()['self']
        invalid = []
        for value in (0, -1, 13, 1.5, True, '1', None):
            invalid.append(storage('deposit_wood', self.chest, value))
            invalid.append(storage('withdraw_wood', self.chest, value))
        for action in (build(), craft(self.bench), storage('deposit_wood', self.chest, 1)):
            missing = deepcopy(action)
            del missing['capabilityVersion']
            invalid += [missing, {**action, 'capabilityVersion': 2}, {**action, 'unexpected': 1}]
        missing = build()
        del missing['toolId']
        invalid += [missing, build('invented.v1'), build(at=[26, 20, 1]), build(tool=self.tool)]
        for action in invalid:
            with self.subTest(action=action):
                self.reject(action, 400, 'INVALID_REQUEST')
        for action in (craft(self.chest), craft('e_missing'), storage('deposit_wood', self.bench, 1), storage('withdraw_wood', 'e_missing', 1)):
            self.reject(action, 404, 'WORKSHOP_TARGET_UNAVAILABLE')
        self.assertEqual(before, self.world.observe()['self'])

    def test_05_capacity_no_partial_success_and_parallel_same_and_different_ids(self):
        self.chain()
        request = self.world.intent(storage('deposit_wood', self.chest, 5))
        with ThreadPoolExecutor(max_workers=6) as pool:
            replies = list(pool.map(lambda _: self.world.request('POST', PREFIX+'/commands', request), range(12)))
        self.assertTrue(all(r[0] == 200 and r[2] == replies[0][2] for r in replies))
        self.fact(request, replies[0])
        self.world.walk([29.5, 21.4], VISITOR)
        self.world.send({'type': 'transfer', 'recipientActorId': OWNER, 'resource': 'wood', 'quantity': 12}, VISITOR)
        self.world.send(storage('deposit_wood', self.chest, 7))
        self.reject(storage('deposit_wood', self.chest, 1), 422, 'CHEST_CAPACITY_EXCEEDED')
        self.reject(storage('withdraw_wood', self.chest, 8), 422, 'INVENTORY_CAPACITY_EXCEEDED')
        self.world.send(storage('withdraw_wood', self.chest, 1))
        observed = self.world.observe()
        candidates = [self.world.intent(storage('deposit_wood', self.chest, 1), observed=observed) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda q: self.world.request('POST', PREFIX+'/commands', q), candidates))
        self.assertEqual(1, sum(r[0] == 200 for r in replies))
        self.assertTrue(all(r[0] == 200 or (r[0] == 409 and r[1]['error']['code'] == 'STALE_ACTOR_STATE') for r in replies))
        self.reject(storage('deposit_wood', self.chest, 1), 422, 'CHEST_CAPACITY_EXCEEDED')
        self.world.send(storage('withdraw_wood', self.chest, 7))
        self.reject(storage('withdraw_wood', self.chest, 1), 422, 'INVENTORY_CAPACITY_EXCEEDED')
        self.assertEqual(12, self.world.observe()['self']['inventory']['wood'])

    def test_06_rejection_persists_and_changed_original_id_conflicts(self):
        self.chain()
        original, denied = self.reject(storage('withdraw_wood', self.chest, 1), 422, 'INSUFFICIENT_RESOURCE')
        self.world.send(storage('deposit_wood', self.chest, 3))
        self.assertEqual(denied[2], self.post(original, status=422, code='INSUFFICIENT_RESOURCE')[2])
        changed = deepcopy(original)
        changed['expectedStateVersion'] = self.world.observe()['stateVersion']
        self.post(changed, status=409, code='IDEMPOTENCY_CONFLICT')
        changed['commandId'] = 'qa2_'+uuid.uuid4().hex
        self.post(changed)
        self.world.restart()
        self.assertEqual(denied[2], self.post(original, status=422, code='INSUFFICIENT_RESOURCE')[2])

    def test_07_readonly_authenticated_instance_bound_private_action_detail(self):
        self.chain()
        path = PREFIX+'/workshop/actions/'+OWNER+'/'+self.tool_request['commandId']
        before = business_snapshot(self.world.data)
        for kwargs, status, code in [({}, 200, None), ({'actor': VISITOR}, 403, 'WORKSHOP_ACCESS_DENIED'),
                                     ({'token': 'invalid'}, 401, 'UNAUTHORIZED'),
                                     ({'instance': 'w_'+'0'*32}, 412, 'WORLD_INSTANCE_MISMATCH')]:
            actual, response, _, _ = self.world.request('GET', path, **kwargs)
            self.assertEqual(status, actual, response)
            if code:
                self.assertEqual(code, response['error']['code'])
        status, error, _, _ = self.world.request('GET', path+'?unused=1')
        self.assertEqual((400, 'INVALID_REQUEST'), (status, error['error']['code']))
        status, error, _, _ = self.world.request('GET', PREFIX+'/workshop/actions/'+OWNER+'/qa2_missing')
        self.assertEqual((404, 'WORKSHOP_ACTION_NOT_FOUND'), (status, error['error']['code']))
        self.world.observe()
        self.assertEqual(before, business_snapshot(self.world.data), 'GET endpoints must not mutate resident facts or save receipts')

    def test_08_every_workshop_action_invalidates_own_pending_even_after_aba(self):
        self.adopt()
        commands = [build()]
        for index in range(4):
            observed = self.world.observe()
            pending = self.world.intent({'type': 'walk', 'to': observed['self']['position']}, observed=observed)
            intent, reply = self.world.send(commands[-1])
            detail = self.fact(intent, reply)
            self.post(pending, status=409, code='STALE_ACTOR_STATE')
            if index == 0:
                commands.append(craft(detail['entity']['entityId']))
            elif index == 1:
                self.world.walk([28.5, 21.4])
                commands.append(build('wooden_chest.v1', [28.5, 20], detail['tool']['toolId']))
            elif index == 2:
                commands.append(storage('deposit_wood', detail['entity']['entityId'], 1))
        chest = detail['entity']['entityId']
        observed = self.world.observe()
        stale = self.world.intent(storage('withdraw_wood', chest, 1), observed=observed)
        self.world.send(storage('withdraw_wood', chest, 1))
        self.world.send(storage('deposit_wood', chest, 1))
        self.assertEqual(observed['self'], self.world.observe()['self'])
        self.post(stale, status=409, code='STALE_ACTOR_STATE')

    def test_09_build_and_interact_range_resident_and_reserved_space(self):
        self.chain()
        self.reject(build(at=[28.5, 21.4]), 409, 'AREA_OCCUPIED')
        self.reject(build(at=[28.5, 20]), 409, 'AREA_OCCUPIED')
        self.reject(build(at=[25, 21.4]), 422, 'UNREACHABLE')
        self.world.walk([30, 21.4])
        self.reject(craft(self.bench), 422, 'UNREACHABLE')
        self.reject(storage('deposit_wood', self.chest, 1), 422, 'UNREACHABLE')
        self.world.walk([30, 10])
        self.reject(build(at=[28, 10]), 409, 'AREA_OCCUPIED')
        self.reject(build(at=[32, 10]), 422, 'UNREACHABLE')

    def test_10_furniture_center_thin_corner_and_reachable_operation_side(self):
        self.chain()
        self.world.walk([27.3, 21.4])
        self.world.walk([27.3, 20.5])
        time.sleep(.205)
        _, reply = self.world.send({'type': 'walk', 'to': [27, 20.8]})
        self.assertTrue(reply[1]['result']['blocked'], 'Both endpoints are clear but the swept circle crosses the bench corner')
        self.world.walk([27.3, 21.4])
        self.world.walk([26, 21.4])
        for _ in range(3):
            time.sleep(.205)
            _, reply = self.world.send({'type': 'walk', 'to': [26, 20]})
        self.assertTrue(reply[1]['result']['blocked'])
        self.assertGreaterEqual(self.world.observe()['self']['position'][1], 20.78-1e-5)
        intent, reply = self.world.send(craft(self.bench))
        self.fact(intent, reply)

    def crash(self, fault, code, committed):
        self.chain()
        for action in (build(at=[30, 18]), craft(self.bench), storage('deposit_wood', self.chest, 1), storage('withdraw_wood', self.chest, 1)):
            # Each fault case has genuine preconditions and material, including craft reach.
            if action['type'] == 'build_workshop':
                self.world.walk([30, 21.1])
            elif action['type'] == 'craft_tool':
                self.world.walk([26, 21.4])
            else:
                self.world.walk([28.5, 21.4])
            original = self.world.intent(action)
            before = self.world.observe()['self']['inventory']['wood']
            with self.assertRaises((OSError, http.client.HTTPException)):
                self.world.request('POST', PREFIX+'/commands', original, fault=fault)
            self.assertEqual(code, self.world.process.wait(timeout=10))
            self.world.restart()
            lookup = self.world.request('GET', PREFIX+'/commands/'+original['commandId'])
            self.assertEqual(200 if committed else 404, lookup[0])
            if not committed:
                self.assertEqual(before, self.world.observe()['self']['inventory']['wood'])
            reply = self.post(original)
            if committed:
                self.assertEqual(lookup[2], reply[2])
            self.fact(original, reply)
            self.assertEqual(reply[2], self.post(original)[2])

    def test_11_before_commit_crash_four_actions_roll_back_and_same_id_resumes(self):
        self.crash('before-commit', 81, False)

    def test_12_after_commit_crash_four_actions_recover_original_facts_once(self):
        self.crash('after-commit', 82, True)

    def test_13_r12_canvas_adoption_preserves_original_tables_and_pending(self):
        request, reply = self.world.send({'type': 'build', 'recipeId': 'platform.v1', 'at': [24, 22]})
        entity = reply[1]['result']['entityId']
        self.world.stop()
        result = self.world.admin('adopt-entity-canvas', extra=('--entity', entity))
        self.assertEqual(0, result.returncode, result.stderr)
        before = snapshot(self.world.data)
        self.assertEqual((12,), before['user_version'])
        self.world.start()
        canvas = self.world.observe()['entityCanvas']
        self.world.stop()
        before = snapshot(self.world.data)
        self.adopt()
        self.world.stop()
        after = snapshot(self.world.data)
        for name, values in before.items():
            if name not in ('worlds', 'events', 'sqlite_sequence', 'user_version', 'recipes'):
                self.assertEqual(values, after[name], name)
        self.world.start()
        self.assertEqual(canvas, self.world.observe()['entityCanvas'])
        self.assertEqual(reply[2], self.post(request, capability=None)[2])
        self.world.restart()
        self.assertEqual(canvas, self.world.observe()['entityCanvas'])

    def test_14_storage_releases_real_carry_capacity_for_new_harvest(self):
        self.chain()
        # Spend the remaining five wood on genuine durable outputs before filling again.
        self.world.walk([26, 21.4])
        for _ in range(2):
            self.world.send(craft(self.bench))
        self.world.walk([28.5, 21.4])
        self.world.send({'type': 'build', 'recipeId': 'platform.v1', 'at': [26, 22.5]})
        self.assertEqual(0, self.world.observe()['self']['inventory']['wood'])
        for point in ([30, 21.4], [30, 10], [28, 10]):
            self.world.walk(point)
        self.world.fill(OWNER)
        for point in ([30, 10], [30, 21.4], [28.5, 21.4]):
            self.world.walk(point)
        self.assertEqual(12, self.world.observe()['self']['inventory']['wood'])
        self.world.send(storage('deposit_wood', self.chest, 3))
        observed = self.world.observe()
        self.assertEqual(9, observed['self']['inventory']['wood'])
        self.assertEqual(3, observed['workshop']['chests'][0]['storedWood'])
        for point in ([30, 21.4], [30, 10], [28, 10]):
            self.world.walk(point)
        self.world.fill(OWNER)
        observed = self.world.observe()
        self.assertEqual(12, observed['self']['inventory']['wood'])
        self.assertEqual(3, observed['workshop']['chests'][0]['storedWood'])
        self.world.restart()
        self.assertEqual(observed['workshop']['chests'], self.world.observe()['workshop']['chests'])

    def test_15_unknown_partial_and_inconsistent_storage_refuse_start_without_repair(self):
        self.chain()
        self.world.send(storage('deposit_wood', self.chest, 1))
        self.world.stop()
        for name, sql in [('unknown', 'PRAGMA user_version=14;'),
                          ('partial', 'DROP TABLE workshop_tools;'),
                          ('inconsistent', 'UPDATE workshop_chests SET wood=wood+1;')]:
            probe = World(RUN/self._testMethodName/name, self.world.data)
            try:
                # Deliberate corruption in a disposable negative fixture only.
                with sqlite3.connect(probe.data/'world.db') as db:
                    db.executescript(sql)
                before = snapshot(probe.data)
                with self.assertRaises(RuntimeError):
                    probe.start()
                self.assertEqual(before, snapshot(probe.data))
            finally:
                probe.stop()

    def test_16_throw_after_debit_rolls_back_tools_and_both_storage_directions(self):
        self.chain()
        for action in (build(at=[30, 18]), craft(self.bench), storage('deposit_wood', self.chest, 1), storage('withdraw_wood', self.chest, 1)):
            if action['type'] == 'build_workshop':
                self.world.walk([30, 21.1])
            elif action['type'] == 'craft_tool':
                self.world.walk([26, 21.4])
            else:
                self.world.walk([28.5, 21.4])
            request = self.world.intent(action)
            observed = self.world.observe()
            response = self.post(request, status=503, fault='throw-after-debit')
            self.assertIsNone(response[1]['error']['mutated'])
            self.assertEqual(404, self.world.request('GET', PREFIX+'/commands/'+request['commandId'])[0])
            after = self.world.observe()
            for key in ('self', 'workshop', 'entities'):
                self.assertEqual(observed[key], after[key], key)
            self.fact(request, self.post(request))

    def test_17_interaction_ray_excludes_only_target_and_rejects_other_furniture(self):
        self.adopt()
        request, reply = self.world.send(build())
        bench = self.fact(request, reply)['entity']['entityId']
        request, reply = self.world.send(craft(bench))
        tool = self.fact(request, reply)['tool']['toolId']
        self.world.walk([28, 21.4])
        request, reply = self.world.send(build('wooden_chest.v1', [28, 20], tool))
        chest = self.fact(request, reply)['entity']['entityId']
        self.world.walk([27.4, 21.4])
        self.world.walk([27.05, 20.78])
        position = self.world.observe()['self']['position']
        self.assertLess(math.dist(position, [28, 20]), 1.6)
        self.assertGreater(math.dist(position, [27, 20.5]), .28)
        self.reject(storage('deposit_wood', chest, 1), 422, 'UNREACHABLE')
        self.world.walk([28, 21.4])
        request, reply = self.world.send(storage('deposit_wood', chest, 1))
        self.fact(request, reply)

    def test_18_canvas_adopted_after_workshop_cannot_disappear_on_restart(self):
        self.adopt()
        _, reply = self.world.send({'type': 'build', 'recipeId': 'platform.v1', 'at': [24, 22]})
        entity = reply[1]['result']['entityId']
        self.world.stop()
        adopted = self.world.admin('adopt-entity-canvas', extra=('--entity', entity))
        self.assertEqual(0, adopted.returncode, adopted.stderr)
        self.world.start()
        self.assertEqual(entity, self.world.observe()['entityCanvas']['target']['entityId'])
        self.world.stop()
        probe = World(RUN/self._testMethodName/'missing-canvas', self.world.data)
        try:
            # Drop the whole optional subsystem from a disposable copy while retaining
            # its original adoption event. The server must detect lost historical work.
            with sqlite3.connect(probe.data/'world.db') as db:
                self.assertEqual(11, db.execute('SELECT base_storage_version FROM workshop').fetchone()[0])
                self.assertEqual(1, db.execute("SELECT count(*) FROM events WHERE json_extract(event_json,'$.type')='entityCanvasAdopted'").fetchone()[0])
                db.executescript('DROP TABLE entity_canvas_cells; DROP TABLE entity_canvas_edits; DROP TABLE entity_canvas;')
            before = snapshot(probe.data)
            rejected = False
            try:
                probe.start()
            except RuntimeError:
                rejected = True
            observed = None if rejected else probe.observe()
            probe.stop()
            save(RUN/'canvas-missing-negative.json', {'startupRejected': rejected, 'baseStorageVersion': 11,
                 'adoptionEventRetained': True, 'observedCanvas': None if observed is None else observed.get('entityCanvas'),
                 'observedWorkshop': None if observed is None else observed.get('workshop', {}).get('capability'),
                 'dllSha256': sha(DLL)})
            self.assertTrue(rejected, 'Historical entityCanvasAdopted event survived but startup accepted the loss of all three canvas tables')
            self.assertEqual(before, snapshot(probe.data))
        finally:
            probe.stop()


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def startTest(self, test):
        self.started = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        failures = {str(t) for t, _ in self.failures+self.errors}
        failures.update(str(t.test_case) for t, _ in self.failures+self.errors if hasattr(t, 'test_case'))
        self.records.append(dict(test=test.id(), passed=str(test) not in failures, seconds=time.monotonic()-self.started))
        super().stopTest(test)


def main():
    RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
    suite = unittest.TestSuite(WorkshopAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:] else unittest.defaultTestLoader.loadTestsFromTestCase(WorkshopAcceptance)
    with (RUN/'test.log').open('w') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=EvidenceResult).run(suite)
    report = dict(suite='independent-workshop-http-v1', passed=result.wasSuccessful(), testsRun=result.testsRun,
                  tests=result.records, actualModelCalls=0, skipped=[(str(t), why) for t, why in result.skipped],
                  failures=[(str(t), detail) for t, detail in result.failures+result.errors],
                  dllSha256=sha(DLL) if DLL and DLL.exists() else None,
                  testSha256=sha(__file__), contractSha256=sha(ROOT/'docs/contracts/workshop-v1.md'))
    if (RUN/'candidate.json').exists():
        report['candidateAtStart'] = json.loads((RUN/'candidate.json').read_text())
    # Only this run's disposable copies; preserve small evidence and error log excerpts.
    removed = 0
    for path in RUN.iterdir():
        if path.is_dir():
            removed += sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
            shutil.rmtree(path)
    report['disposedBytes'] = removed
    save(RUN/'results.json', report)
    print(json.dumps({'passed': report['passed'], 'testsRun': result.testsRun, 'evidence': str(RUN/'results.json')}, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
