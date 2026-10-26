#!/usr/bin/env python3
"""Independent forestry-v1 HTTP/SQLite acceptance on explicitly frozen binaries.

WORLD_SERVER_DLL=<frozen dll> FORESTRY_SOURCE=<stopped r10/storage13 copy> \
  python3 tests/forestry_api.py [test_method ...]

All setup uses actual commands and real service time. Intermediate stopped copies
are reused, never SQL grants or clock edits. This is isolated API evidence, not
native activity on the continuing resident world. The shared transport and route
finder are setup helpers; protocol, accounting and collision assertions are here.
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
import sqlite3
import sys
import time
import unittest
import uuid

sys.dont_write_bytecode = True
import workshop_api as transport

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import continuous_navigation as navigation

PREFIX = transport.PREFIX
CAPS = 'workshop-v1,forestry-v1'
ACTORS = ('a1', 'a1_alias', 'a2', 'a3')
OWNER, OTHER = 'a2', 'a3'
PLOTS = {'forest-west-north': [7, 12], 'forest-west-south': [7, 16],
         'forest-east-north': [21, 7], 'forest-east-far': [29, 5]}
RUN = ROOT / '.local/test-agent2' / ('iter28-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
DLL = transport.DLL
SOURCE = Path(os.environ['FORESTRY_SOURCE']).resolve() if os.environ.get('FORESTRY_SOURCE') else None
sha, save, snapshot = transport.sha, transport.save, transport.snapshot


def action(kind, **fields):
    return dict(type=kind, capabilityVersion=1, **fields)


def connect(data):
    return sqlite3.connect(f'file:{Path(data) / "world.db"}?mode=ro', uri=True)


class World(transport.World):
    def request(self, method, path, payload=None, actor=OWNER, capability=CAPS, **kwargs):
        return super().request(method, path, payload, actor=actor, capability=capability, **kwargs)

    def go(self, target, actor=OWNER):
        observed = self.observe(actor)
        route = navigation.navigation(observed).route(observed['self']['position'], target)
        if route is None:
            raise AssertionError(('No setup route', actor, observed['self']['position'], target))
        for waypoint in route:
            self.walk(waypoint, actor)

    def until(self, predicate, timeout=190, actor=OWNER):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            observed = self.observe(actor)
            if predicate(observed):
                return observed
            time.sleep(.5)
        raise AssertionError(('Real service deadline', timeout, observed.get('forestry')))

    def until_ms(self, deadline, actor=OWNER):
        return self.until(lambda o: o['forestry']['nursery']['serviceMs'] >= deadline,
                          max(10, (deadline-self.observe(actor)['forestry']['nursery']['serviceMs'])/1000+10), actor)

    def reservation(self, rid, actor=OWNER):
        return next((r for r in self.observe(actor)['forestry']['reservations'] if r['reservationId'] == rid), None)

    def apply(self, kind, actor=OWNER, **fields):
        return self.send(action(kind, **fields), actor)


class ForestryAcceptance(unittest.TestCase):
    fixtures = {}
    meta = {}

    @classmethod
    def setUpClass(cls):
        if DLL is None or not DLL.is_file() or SOURCE is None or not (SOURCE/'world.db').is_file():
            raise RuntimeError('Require WORLD_SERVER_DLL frozen candidate and FORESTRY_SOURCE stopped storage13 source')
        RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
        save(RUN/'candidate.json', dict(dll=str(DLL), dllSha256=sha(DLL), testSha256=sha(__file__),
             helperSha256=sha(transport.__file__), navigationSha256=sha(navigation.__file__),
             contractSha256=sha(ROOT/'docs/contracts/forestry-v1.md'), source=str(SOURCE), actualModelCalls=0))
        shutil.copyfile(__file__, RUN/'probe-source.py')
        shutil.copyfile(ROOT/'docs/contracts/forestry-v1.md', RUN/'contract-at-start.md')
        legacy = World(RUN/'fixture-legacy', SOURCE)
        with connect(legacy.data) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 13:
                raise AssertionError('Source must be the original stopped storage13 history')
            legacy.instance = db.execute('SELECT instance_id FROM world_instance').fetchone()[0]
        cls.instance = legacy.instance
        cls.fixtures['legacy'] = legacy.data
        save(RUN/'source-fingerprint.json', cls.fingerprint(legacy.data))

    @staticmethod
    def fingerprint(data):
        return {key: dict(rows=len(rows), sha256=hashlib.sha256(json.dumps(rows, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest())
                for key, rows in snapshot(data).items()}

    @classmethod
    def fixture(cls, kind):
        if kind in cls.fixtures:
            return cls.fixtures[kind]
        parent = {'adopted': 'legacy', 'prepared': 'adopted', 'growing': 'prepared', 'mature': 'growing', 'stock-full': 'adopted'}[kind]
        world = World(RUN/('fixture-'+kind), cls.fixture(parent))
        world.instance = cls.instance
        metadata = deepcopy(cls.meta.get(parent, {}))
        try:
            if kind == 'adopted':
                result = world.admin('adopt-forestry')
                if result.returncode:
                    raise AssertionError(('adopt-forestry', result.returncode, result.stderr))
            else:
                world.start()
                if kind == 'prepared':
                    for actor in (OWNER, OTHER):
                        world.go([26, 21.3], actor)
                        bench = next(e for e in world.observe(actor)['entities'] if e['definitionId'] == 'workbench' and e['ownerActorId'] == OWNER)
                        intent, reply = world.apply('craft_forestry_tool', actor, entityId=bench['entityId'], recipeId='wooden_axe.v1')
                        metadata[actor+'Tool'] = reply[1]['result']['forestryAction']['tool']['toolId']
                        metadata[actor+'Craft'] = [intent, reply[1]]
                        # Keep the operation side clear for the other resident.
                        world.go([27.5, 22] if actor == OWNER else [25, 22], actor)
                    world.go([8.2, 6])
                    intent, reply = world.apply('reserve_forest')
                    metadata['reserveIntent'], metadata['reserveReply'] = intent, reply[1]
                    rid = reply[1]['result']['forestryAction']['reservation']['reservationId']
                    metadata['reservationId'] = rid
                    observed = world.until(lambda o: any(r['reservationId'] == rid and r['status'] == 'preparing' for r in o['forestry']['reservations']), 80)
                    metadata['plotId'] = next(r for r in observed['forestry']['reservations'] if r['reservationId'] == rid)['plotId']
                elif kind == 'growing':
                    intent, reply = world.apply('collect_seed', sourceId='nursery-west', reservationId=metadata['reservationId'])
                    metadata['collectIntent'], metadata['collectReply'] = intent, reply[1]
                    x, z = PLOTS[metadata['plotId']]
                    world.go([x+1.2, z])
                    intent, reply = world.apply('plant_tree', plotId=metadata['plotId'], reservationId=metadata['reservationId'])
                    metadata['plantIntent'], metadata['plantReply'] = intent, reply[1]
                    metadata['plant'] = reply[1]['result']['forestryAction']['plant']
                elif kind == 'mature':
                    pid = metadata['plant']['plantId']
                    world.until(lambda o: any(p['plantId'] == pid and p['state'] == 'mature' for p in o['forestry']['plants']), 135)
                elif kind == 'stock-full':
                    observed = world.until(lambda o: o['forestry']['nursery']['stockSeeds'] == 4, 255)
                    metadata['firstFull'] = observed['forestry']['nursery']
        finally:
            world.stop()
            save(RUN/('fixture-'+kind+'-trace.json'), world.trace)
        cls.fixtures[kind], cls.meta[kind] = world.data, metadata
        save(RUN/('fixture-'+kind+'-facts.json'), metadata)
        return world.data

    def setUp(self):
        self.world = None
        self.worlds = []
        self.addCleanup(self.cleanup)

    def use(self, kind='adopted', start=True, suffix=''):
        if self.world is not None:
            self.world.stop()
        self.world = World(RUN/(self._testMethodName+suffix), self.fixture(kind))
        self.worlds.append(self.world)
        self.world.instance = self.instance
        self.facts = deepcopy(self.meta.get(kind, {}))
        if start:
            self.world.start()
        return self.world

    def cleanup(self):
        for world in self.worlds:
            world.stop()
        for world in self.worlds:
            save(RUN/(world.data.name+'-trace.json'), world.trace)
            with connect(world.data) as db:
                self.assertEqual('ok', db.execute('PRAGMA integrity_check').fetchone()[0])
                self.assertEqual([], db.execute('PRAGMA foreign_key_check').fetchall())
            save(RUN/(world.data.name+'-fingerprint.json'), self.fingerprint(world.data))

    def post(self, intent, actor=OWNER, expected=200, code=None, **kwargs):
        reply = self.world.request('POST', PREFIX+'/commands', intent, actor=actor, **kwargs)
        self.assertEqual(expected, reply[0], reply[1])
        if code:
            self.assertEqual(code, reply[1]['error']['code'])
        return reply

    def reject(self, intent_action, actor=OWNER, expected=None, **kwargs):
        intent = self.world.intent(intent_action, actor)
        before = self.world.observe(actor)
        reply = self.world.request('POST', PREFIX+'/commands', intent, actor=actor, **kwargs)
        self.assertIn(reply[0], (400, 403, 404, 409, 412, 422), reply[1])
        if expected is not None:
            self.assertEqual(expected, reply[0], reply[1])
        after = self.world.observe(actor)
        self.assertEqual(before['self'], after['self'])
        self.assertEqual(before['forestry']['seeds'], after['forestry']['seeds'])
        self.assertEqual(before['forestry']['tools'], after['forestry']['tools'])
        return intent, reply

    def fact(self, intent, reply, actor=OWNER):
        body = reply[1]
        self.assertEqual('committed', body['status'])
        detail = body['result']['forestryAction']
        self.assertEqual({'capabilityVersion', 'authorActorId', 'operatorId', 'commandId', 'action', 'position', 'serviceMs',
                          'stateVersion', 'eventCursor', 'completedAtUtc', 'inventoryWoodBefore', 'inventoryWood',
                          'seedsBefore', 'seeds', 'nurseryStockBefore', 'nurseryStock', 'reservationBefore', 'reservation',
                          'plantBefore', 'plant', 'tool'}, set(detail))
        self.assertEqual(intent['action']['type'], body['result']['action'])
        self.assertEqual(intent['action'], detail['action'])
        self.assertEqual(actor, detail['authorActorId'])
        self.assertEqual(intent['commandId'], detail['commandId'])
        self.assertEqual(body['stateVersion'], detail['stateVersion'])
        self.assertEqual(body['eventCursor'], detail['eventCursor'])
        status, queried, _, _ = self.world.request('GET', PREFIX+f'/forestry/actions/{actor}/'+intent['commandId'], actor=actor)
        self.assertEqual(200, status, queried)
        self.assertEqual(detail, queried['forestryAction'])
        status, stream, _, _ = self.world.request('GET', PREFIX+'/events?after='+str(detail['eventCursor']-1), actor=actor, capability=None)
        self.assertEqual(200, status, stream)
        event = stream['events'][0]
        self.assertEqual(detail, event['forestryAction'])
        other = OTHER if actor == OWNER else OWNER
        status, public, _, _ = self.world.request('GET', PREFIX+'/events?after='+str(detail['eventCursor']-1), actor=other, capability=None)
        self.assertEqual(200, status, public)
        self.assertEqual({k: event[k] for k in ('seq', 'stateVersion', 'actorId', 'commandId', 'type')}, public['events'][0])
        self.assertEqual(reply[2], self.world.request('GET', PREFIX+'/commands/'+intent['commandId'], actor=actor, capability=None)[2])
        return detail

    def audit(self):
        observed = self.world.observe()
        a, s = observed['resourceAudit'], observed['seedAudit']
        self.assertIs(True, a['conserved'])
        self.assertIs(True, s['conserved'])
        self.assertEqual(a['issuedWood'], a['initialWood']+a['generatedWood']+a['forestGeneratedWood'])
        self.assertEqual(a['initialWood']+a['generatedWood']+a['forestGeneratedWood'],
                         sum(a[k] for k in ('wildWood', 'sourceWood', 'inventoryWood', 'embodiedWood', 'toolWood', 'storedWood', 'standingForestWood')))
        self.assertEqual(s['nurseryGeneratedSeeds']+s['harvestGeneratedSeeds'],
                         s['nurseryStockSeeds']+s['residentSeeds']+s['consumedPlantSeeds'])
        self.assertLessEqual(s['reservedSeeds'], s['nurseryStockSeeds'])
        self.assertLessEqual(a['standingForestWood'], 12)
        with connect(self.world.data) as db:
            self.assertEqual(a['issuedWood'], db.execute('SELECT issued_wood FROM worlds').fetchone()[0])
            self.assertEqual(a['inventoryWood'], db.execute('SELECT sum(wood) FROM residents').fetchone()[0])
            self.assertEqual(a['embodiedWood'], db.execute('SELECT sum(embodied_wood) FROM entities').fetchone()[0])
            self.assertEqual(a['storedWood'], db.execute('SELECT sum(wood) FROM workshop_chests').fetchone()[0])
            old_tools = db.execute('SELECT count(*) FROM workshop_tools').fetchone()[0]
            self.assertEqual(a['toolWood'], old_tools+a['forestryToolWood'])
            self.assertEqual(a['generatedWood'], db.execute('SELECT sum(quantity) FROM material_production').fetchone()[0])
            events = [json.loads(row[0]) for row in db.execute('SELECT event_json FROM events')]
            matured = [e for e in events if e['type'] == 'forestTreeMatured']
            self.assertEqual(a['forestGeneratedWood'], 3*len(matured))
            plants = [json.loads(row[0]) for row in db.execute('SELECT data_json FROM forestry_plants')]
            tools = [json.loads(row[0]) for row in db.execute('SELECT data_json FROM forestry_tools')]
            seeds = db.execute('SELECT actor_id,seeds FROM forestry_seeds').fetchall()
            seed_events = [e for e in events if e['type'] == 'forestSeedProduced']
            self.assertEqual(s['residentSeeds'], sum(row[1] for row in seeds))
            self.assertEqual(s['consumedPlantSeeds'], len(plants))
            self.assertEqual(s['harvestGeneratedSeeds'], sum(p['state'] == 'harvested' for p in plants))
            self.assertEqual(s['nurseryGeneratedSeeds'], sum(e['quantity'] for e in seed_events))
            self.assertEqual(a['standingForestWood'], sum(p['standingWood'] for p in plants))
            self.assertEqual(a['forestryToolWood'], 2*len(tools))
            self.assertEqual(len(matured), len({e['plant']['plantId'] for e in matured}))
            for p in plants:
                matching = [e for e in matured if e['plant']['plantId'] == p['plantId']]
                self.assertEqual(0 if p['state'] == 'growing' else 1, len(matching))
                if matching:
                    e = matching[0]
                    self.assertEqual(p['matureEventCursor'], e['seq'])
                    self.assertEqual(p['maturesAtMs'], e['serviceMs'])
                    self.assertEqual(p['eventCursor'], e['plant']['eventCursor'])
                    self.assertEqual(3, e['quantity'])
            balances = {}
            for src, dst, quantity in db.execute('SELECT source_account,destination_account,quantity FROM resource_ledger'):
                balances[src] = balances.get(src, 0)-quantity
                balances[dst] = balances.get(dst, 0)+quantity
            self.assertEqual(-a['initialWood'], balances.pop('initial-issuance'))
            self.assertEqual(-a['generatedWood'], balances.pop('ecological-input', 0))
            self.assertEqual(-a['forestGeneratedWood'], balances.pop('forest-ecological-input', 0))
            self.assertEqual(a['wildWood'], balances.pop('wild-wood', 0))
            self.assertEqual(a['sourceWood'], balances.pop('source:wood-source-east', 0))
            accounts = [('inventory:', db.execute('SELECT actor_id,wood FROM residents').fetchall()),
                        ('entity:', db.execute('SELECT entity_id,embodied_wood FROM entities').fetchall()),
                        ('chest:', db.execute('SELECT entity_id,wood FROM workshop_chests').fetchall()),
                        ('tool:', db.execute('SELECT tool_id,1 FROM workshop_tools').fetchall()+[(t['toolId'], 2) for t in tools]),
                        ('plant:', [(p['plantId'], p['standingWood']) for p in plants])]
            for prefix, rows in accounts:
                for key, quantity in rows:
                    self.assertEqual(quantity, balances.pop(prefix+key, 0), prefix+key)
            self.assertFalse({k: v for k, v in balances.items() if v}, balances)
        save(RUN/(self.world.data.name+'-audit.json'), dict(resourceAudit=a, seedAudit=s, maturityEvents=matured,
                                                          resourceLedgerBalanced=True, seedEventLedgerBalanced=True))
        return observed

    def test_01_explicit_adoption_preserves_original_history_and_is_idempotent(self):
        w = self.use('legacy', start=False)
        before = snapshot(w.data)
        self.assertNotEqual(0, w.admin('adopt-forestry', 'w_'+'0'*32).returncode)
        self.assertEqual(before, snapshot(w.data))
        result = w.admin('adopt-forestry')
        self.assertEqual(0, result.returncode, result.stderr)
        after = snapshot(w.data)
        self.assertEqual((14,), after['user_version'])
        for table, rows in before.items():
            if table not in ('worlds', 'events', 'sqlite_sequence', 'user_version'):
                self.assertEqual(rows, after[table], table)
        self.assertEqual(before['events'], after['events'][:-1])
        self.assertEqual(0, w.admin('adopt-forestry').returncode)
        self.assertEqual(after, snapshot(w.data))
        w.start()
        observed = self.audit()
        f = observed['forestry']
        self.assertEqual(0, f['nursery']['stockSeeds'])
        self.assertEqual(0, observed['resourceAudit']['forestGeneratedWood'])
        self.assertEqual([], f['plants'])
        self.assertEqual([], f['tools'])
        self.assertEqual(4, len(f['plots']))
        self.assertEqual(f['adoption']['adoptedServiceMs']+60000, f['nursery']['nextProductionAtMs'])
        self.assertEqual(self.instance, observed['world']['instanceId'])
        self.assertNotEqual(0, w.admin('adopt-forestry').returncode, 'Running world must keep adoption lock')
        w.restart()
        self.assertEqual(0, self.audit()['resourceAudit']['forestGeneratedWood'])

    def test_02_legacy_receipt_precedes_capability_new_effects_require_both(self):
        w = self.use('legacy')
        old, reply = w.send({'type': 'walk', 'to': w.observe()['self']['position']})
        pending = w.intent({'type': 'walk', 'to': w.observe()['self']['position']})
        w.stop()
        self.assertEqual(0, w.admin('adopt-forestry').returncode)
        w.start()
        for capability in (None, '', 'workshop-v1', 'forestry-v1', 'workshop-v1,forestry-v2'):
            with self.subTest(capability=capability):
                self.assertEqual(reply[2], self.post(old, capability=capability)[2])
                self.assertEqual(reply[2], w.request('GET', PREFIX+'/commands/'+old['commandId'], capability=capability)[2])
                status, body, _, _ = w.request('GET', PREFIX+'/observation', capability=capability)
                self.assertEqual((409, 'CLIENT_CAPABILITY_REQUIRED'), (status, body['error']['code']))
                self.post(pending, expected=409, code='CLIENT_CAPABILITY_REQUIRED', capability=capability)
                self.assertEqual(404, w.request('GET', PREFIX+'/commands/'+pending['commandId'], capability=capability)[0])
        self.post(pending)
        self.audit()

    def test_03_strict_action_fields_integer_versions_and_same_id(self):
        w = self.use()
        samples = [action('reserve_forest'), action('cancel_forest_reservation', reservationId='original'),
                   action('collect_seed', sourceId='nursery-west', reservationId='original'),
                   action('plant_tree', plotId='forest-west-north', reservationId='original'),
                   action('harvest_tree', plantId='original', reservationId='original', toolId='original'),
                   action('craft_forestry_tool', entityId='original', recipeId='wooden_axe.v1')]
        for sample in samples:
            invalid = [dict(sample, capabilityVersion=v) for v in (True, 1.0, '1', 0, 2, None)]
            invalid += [dict(sample, extra=1), {k: v for k, v in sample.items() if k != 'capabilityVersion'}]
            for item in invalid:
                with self.subTest(action=item):
                    self.reject(item, expected=400)
        intent = w.intent(action('reserve_forest'))
        with ThreadPoolExecutor(max_workers=6) as pool:
            replies = list(pool.map(lambda _: w.request('POST', PREFIX+'/commands', intent), range(12)))
        self.assertTrue(all(r[0] == 200 and r[2] == replies[0][2] for r in replies))
        self.fact(intent, replies[0])
        changed = deepcopy(intent)
        changed['action'] = action('cancel_forest_reservation', reservationId=replies[0][1]['result']['forestryAction']['reservation']['reservationId'])
        self.post(changed, expected=409, code='IDEMPOTENCY_CONFLICT')
        self.audit()

    def test_04_action_detail_auth_instance_privacy_and_readonly(self):
        w = self.use()
        intent, reply = w.apply('reserve_forest')
        self.fact(intent, reply)
        path = PREFIX+'/forestry/actions/a2/'+intent['commandId']
        before = snapshot(w.data)
        for kwargs, expected in [({}, 200), ({'actor': OTHER}, 403), ({'token': 'invalid'}, 401),
                                 ({'instance': 'w_'+'0'*32}, 412)]:
            actual = w.request('GET', path, **kwargs)
            self.assertEqual(expected, actual[0], actual[1])
        self.assertEqual(400, w.request('GET', path+'?unused=1')[0])
        self.assertEqual(404, w.request('GET', PREFIX+'/forestry/actions/a2/missing')[0])
        after = snapshot(w.data)
        for table in before:
            if table != 'material_source':
                self.assertEqual(before[table], after[table], table)
        self.audit()

    def test_05_seed_zero_fifo_alias_reserved_is_not_collected_and_no_jump(self):
        w = self.use()
        initial = w.observe()['forestry']
        self.assertEqual(0, initial['nursery']['stockSeeds'])
        requests = {}
        for actor in (OWNER, OTHER, 'a1_alias'):
            intent, reply = w.apply('reserve_forest', actor)
            d = self.fact(intent, reply, actor)
            self.assertEqual('queued', d['reservation']['status'])
            requests[actor] = d['reservation']['reservationId']
        self.reject(action('reserve_forest'), 'a1')
        self.assertEqual(3, len(w.observe()['forestry']['reservations']))
        granted = w.until(lambda o: any(r['reservationId'] == requests[OWNER] and r['status'] == 'preparing' for r in o['forestry']['reservations']), 75)
        nursery = granted['forestry']['nursery']
        self.assertEqual((1, 1, 0), tuple(nursery[k] for k in ('stockSeeds', 'reservedSeeds', 'freeSeeds')))
        self.assertEqual(0, granted['forestry']['seeds'])
        self.assertEqual('queued', w.reservation(requests[OTHER])['status'])
        self.reject(action('collect_seed', sourceId='nursery-west', reservationId=requests[OWNER]))
        w.go([8.2, 6])
        intent, reply = w.apply('collect_seed', sourceId='nursery-west', reservationId=requests[OWNER])
        d = self.fact(intent, reply)
        self.assertEqual((0, 1, 1, 0), tuple(d[k] for k in ('seedsBefore', 'seeds', 'nurseryStockBefore', 'nurseryStock')))
        self.reject(action('collect_seed', sourceId='nursery-west', reservationId=requests[OWNER]))
        w.apply('cancel_forest_reservation', reservationId=requests[OWNER])
        self.assertEqual(1, w.observe()['forestry']['seeds'], 'Cancellation retains personally collected seed')
        _, reply = w.apply('reserve_forest')
        later = reply[1]['result']['forestryAction']['reservation']['reservationId']
        self.assertEqual('queued', w.reservation(later)['status'], 'Having seed cannot bypass the older seedless head')
        w.until(lambda o: any(r['reservationId'] == requests[OTHER] and r['status'] == 'preparing' for r in o['forestry']['reservations']), 80)
        self.assertEqual('queued', w.reservation(later)['status'])
        w.apply('cancel_forest_reservation', OTHER, reservationId=requests[OTHER])
        w.until(lambda o: any(r['reservationId'] == requests['a1_alias'] and r['status'] == 'preparing' for r in o['forestry']['reservations']), 10)
        w.apply('cancel_forest_reservation', 'a1_alias', reservationId=requests['a1_alias'])
        w.until(lambda o: any(r['reservationId'] == later and r['status'] == 'preparing' for r in o['forestry']['reservations']), 10)
        self.assertEqual(0, w.reservation(later)['reservedSeed'])
        self.reject(action('collect_seed', sourceId='nursery-west', reservationId=later))
        self.audit()

    def test_06_preparation_expiry_releases_reserved_seed_and_new_lease_starts_now(self):
        w = self.use('prepared')
        original = w.reservation(self.facts['reservationId'])
        self.assertEqual(90000, original['expiresAtMs']-original['grantedAtMs'])
        _, reply = w.apply('reserve_forest', OTHER)
        next_id = reply[1]['result']['forestryAction']['reservation']['reservationId']
        # The second seed can grant OTHER another empty plot before OWNER expires.
        # Keep it queued only if scarcity does, then verify each independently.
        w.until_ms(original['expiresAtMs']+500)
        self.assertIsNone(w.reservation(original['reservationId']))
        next_reservation = w.reservation(next_id)
        self.assertEqual('preparing', next_reservation['status'])
        self.assertEqual(90000, next_reservation['expiresAtMs']-next_reservation['grantedAtMs'])
        self.assertEqual(0, w.observe()['forestry']['seeds'])
        nursery = w.observe()['forestry']['nursery']
        self.assertEqual((2, 1, 1), tuple(nursery[k] for k in ('stockSeeds', 'reservedSeeds', 'freeSeeds')))
        with connect(w.data) as db:
            expired = [json.loads(row[0]) for row in db.execute("SELECT event_json FROM events WHERE json_extract(event_json,'$.type')='forestReservationExpired'")]
        released = [e for e in expired if e['reservation']['reservationId'] == original['reservationId']]
        self.assertEqual(1, len(released))
        self.assertEqual((original['expiresAtMs'], 1), (released[0]['serviceMs'], released[0]['releasedSeed']))
        self.reject(action('collect_seed', sourceId='nursery-west', reservationId=original['reservationId']))
        self.audit()

    def test_07_nursery_capacity_skips_full_periods_without_backlog(self):
        w = self.use('stock-full')
        full = w.observe()['forestry']['nursery']
        self.assertEqual((4, 4), (full['generatedSeeds'], full['stockSeeds']))
        w.until_ms(full['nextProductionAtMs']+1000)
        skipped = w.observe()['forestry']['nursery']
        self.assertEqual((4, 4), (skipped['generatedSeeds'], skipped['stockSeeds']))
        self.assertGreater(skipped['productionPeriod'], full['productionPeriod'])
        w.go([8.2, 6])
        _, reply = w.apply('reserve_forest')
        rid = reply[1]['result']['forestryAction']['reservation']['reservationId']
        w.until(lambda o: any(r['reservationId'] == rid and r['status'] == 'preparing' for r in o['forestry']['reservations']), 10)
        w.apply('collect_seed', sourceId='nursery-west', reservationId=rid)
        time.sleep(1)
        consumed = w.observe()['forestry']['nursery']
        self.assertEqual((4, 3), (consumed['generatedSeeds'], consumed['stockSeeds']))
        w.until_ms(consumed['nextProductionAtMs']+500)
        produced = w.observe()['forestry']['nursery']
        self.assertEqual((5, 4), (produced['generatedSeeds'], produced['stockSeeds']))
        self.audit()

    def harvest_action(self, plant=None, reservation=None, tool=None):
        return action('harvest_tree', plantId=(plant or self.facts['plant'])['plantId'],
                      reservationId=reservation or self.facts['reservationId'], toolId=tool or self.facts['a2Tool'])

    def test_08_growing_collision_offline_pause_original_planting_replay(self):
        w = self.use('growing')
        p = self.facts['plant']
        self.assertEqual(120000, p['maturesAtMs']-p['plantedAtMs'])
        observed = self.audit()
        self.assertEqual(0, observed['resourceAudit']['forestGeneratedWood'])
        obstacle = next(o for o in observed['terrain']['obstacles'] if o['position'] == PLOTS[p['plotId']])
        self.assertEqual(.45, obstacle['radius'])
        self.reject(self.harvest_action())
        self.reject(action('cancel_forest_reservation', reservationId=self.facts['reservationId']))
        self.reject(action('reserve_forest'))
        for _ in range(4):
            time.sleep(.205)
            _, reply = w.send({'type': 'walk', 'to': PLOTS[p['plotId']]})
        self.assertTrue(reply[1]['result']['blocked'])
        self.assertGreaterEqual(math.dist(w.observe()['self']['position'], PLOTS[p['plotId']]), .73-1e-5)
        x, z = PLOTS[p['plotId']]
        w.go([x+1.2, z])
        w.stop()
        with connect(w.data) as db:
            stopped = db.execute('SELECT service_ms FROM material_source').fetchone()[0]
        time.sleep(2)
        w.start()
        resumed = w.observe()['forestry']['nursery']['serviceMs']
        self.assertLess(resumed-stopped, 1000, 'Offline wall time must not become service time')
        recovered = self.post(self.facts['plantIntent'])
        self.assertEqual(self.facts['plantReply'], recovered[1])
        self.fact(self.facts['plantIntent'], recovered)
        self.assertEqual([p['plantId']], [t['plantId'] for t in w.observe()['forestry']['plants']])
        self.audit()

    def test_09_maturity_once_capacity_atomic_two_generations_original_pending(self):
        w = self.use('mature')
        original_plant = self.facts['plant']
        observed = self.audit()
        self.assertEqual((3, 3), tuple(observed['resourceAudit'][k] for k in ('forestGeneratedWood', 'standingForestWood')))
        obstacle = next(o for o in observed['terrain']['obstacles'] if o['position'] == PLOTS[original_plant['plotId']])
        self.assertEqual(.45, obstacle['radius'])
        self.assertEqual(10, observed['self']['inventory']['wood'])
        rejected_intent, denied = self.reject(self.harvest_action())
        after = self.audit()
        self.assertEqual(3, after['resourceAudit']['standingForestWood'])
        self.assertEqual(0, after['forestry']['seeds'])
        self.reject(self.harvest_action(tool=self.facts['a3Tool']))
        self.reject(self.harvest_action(tool='missing-original-tool'))
        x, z = PLOTS[original_plant['plotId']]
        # A real nearby platform spends 3 carried wood; no inventory edits.
        w.send({'type': 'build', 'recipeId': 'platform.v1', 'at': [x+3, z]})
        self.assertEqual(denied[2], self.post(rejected_intent, expected=denied[0])[2])
        unknown_pending = w.intent(self.harvest_action())
        self.assertEqual(404, w.request('GET', PREFIX+'/commands/'+unknown_pending['commandId'])[0])
        original_intent, original_reply = w.send(self.harvest_action())
        d = self.fact(original_intent, original_reply)
        self.assertEqual((7, 10, 0, 1), tuple(d[k] for k in ('inventoryWoodBefore', 'inventoryWood', 'seedsBefore', 'seeds')))
        self.assertEqual('harvested', d['plant']['state'])
        self.assertEqual(0, d['plant']['standingWood'])
        self.assertFalse(any(o['position'] == PLOTS[original_plant['plotId']] for o in w.observe()['terrain']['obstacles']))
        w.restart()
        self.assertEqual(original_reply[2], self.post(original_intent)[2])
        self.assertEqual(3, self.audit()['resourceAudit']['forestGeneratedWood'])
        _, reservation_reply = w.apply('reserve_forest')
        rid = reservation_reply[1]['result']['forestryAction']['reservation']['reservationId']
        w.until(lambda o: any(r['reservationId'] == rid and r['status'] == 'preparing' for r in o['forestry']['reservations']), 10)
        reservation = w.reservation(rid)
        self.assertEqual(original_plant['plotId'], reservation['plotId'])
        plant_intent, plant_reply = w.apply('plant_tree', plotId=reservation['plotId'], reservationId=rid)
        second = self.fact(plant_intent, plant_reply)['plant']
        self.assertNotEqual(original_plant['plantId'], second['plantId'])
        self.assertEqual(original_reply[2], self.post(original_intent)[2])
        self.post(unknown_pending, expected=409, code='STALE_ACTOR_STATE')
        _, old_tree_denied = self.reject(self.harvest_action(), expected=409)
        self.assertEqual('FOREST_TREE_NOT_MATURE', old_tree_denied[1]['error']['code'])
        unchanged = self.audit()
        self.assertEqual([second], unchanged['forestry']['plants'])
        self.assertEqual((3, 0), tuple(unchanged['resourceAudit'][k] for k in ('forestGeneratedWood', 'standingForestWood')))
        self.assertEqual(0, unchanged['forestry']['seeds'])
        # Make capacity using another real platform before the second harvest.
        w.send({'type': 'build', 'recipeId': 'platform.v1', 'at': [x+3, z+2.1]})
        w.until_ms(second['maturesAtMs']+500)
        intent, reply = w.send(self.harvest_action(plant=second, reservation=rid))
        self.fact(intent, reply)
        self.assertEqual(6, self.audit()['resourceAudit']['forestGeneratedWood'])
        self.assertEqual(0, w.observe()['resourceAudit']['standingForestWood'])
        self.assertEqual(original_reply[2], self.post(original_intent)[2])
        self.assertEqual(plant_reply[2], self.post(plant_intent)[2])
        w.restart()
        self.assertEqual(6, self.audit()['resourceAudit']['forestGeneratedWood'])
        self.assertEqual(1, w.observe()['forestry']['seeds'])

    def test_10_mature_public_handoff_lease_is_not_backdated(self):
        w = self.use('mature')
        plant = self.facts['plant']
        original = w.reservation(self.facts['reservationId'])
        self.assertEqual(plant['maturesAtMs']+60000, original['expiresAtMs'])
        # Leave the mature tree unclaimed well beyond its original expiry.
        w.until_ms(original['expiresAtMs']+10000)
        self.assertIsNone(w.reservation(original['reservationId']))
        self.assertEqual(3, self.audit()['resourceAudit']['standingForestWood'])
        w.go([8.2, 13], OTHER)
        intent, reply = w.apply('reserve_forest', OTHER)
        rid = self.fact(intent, reply, OTHER)['reservation']['reservationId']
        w.until(lambda o: any(r['reservationId'] == rid and r['status'] == 'harvesting' for r in o['forestry']['reservations']), 10, OTHER)
        granted = w.reservation(rid, OTHER)
        self.assertEqual(plant['plantId'], granted['plantId'])
        self.assertGreater(granted['grantedAtMs'], original['expiresAtMs']+9000)
        self.assertEqual(60000, granted['expiresAtMs']-granted['grantedAtMs'])
        self.assertEqual(0, granted['reservedSeed'])
        self.reject(action('cancel_forest_reservation', reservationId=rid), OTHER)
        self.reject(self.harvest_action())
        w.until_ms(granted['expiresAtMs']+500)
        self.assertIsNone(w.reservation(rid, OTHER))
        self.assertEqual(3, self.audit()['resourceAudit']['standingForestWood'])
        self.reject(self.harvest_action(reservation=rid, tool=self.facts['a3Tool']), OTHER, expected=409)
        # Expiry preserves the tree; a new explicit queue entry creates a new lease.
        _, reply = w.apply('reserve_forest', OTHER)
        next_id = reply[1]['result']['forestryAction']['reservation']['reservationId']
        self.assertNotEqual(rid, next_id)
        w.until(lambda o: any(r['reservationId'] == next_id and r['status'] == 'harvesting' for r in o['forestry']['reservations']), 10, OTHER)
        renewed = w.reservation(next_id, OTHER)
        self.assertEqual(plant['plantId'], renewed['plantId'])
        self.assertEqual(60000, renewed['expiresAtMs']-renewed['grantedAtMs'])
        self.assertGreater(renewed['grantedAtMs'], granted['expiresAtMs'])
        rid = next_id
        # a2 remains 1.2m east of the trunk; a3 uses a distinct free operation side.
        w.go([7, 13.2], OTHER)
        intent, reply = w.send(self.harvest_action(reservation=rid, tool=self.facts['a3Tool']), OTHER)
        d = self.fact(intent, reply, OTHER)
        self.assertEqual((0, 3, 0, 1), tuple(d[k] for k in ('inventoryWoodBefore', 'inventoryWood', 'seedsBefore', 'seeds')))
        self.assertEqual(OWNER, d['plant']['planterActorId'])
        self.assertEqual(OTHER, d['plant']['harvestActorId'])
        self.assertEqual(3, self.audit()['resourceAudit']['forestGeneratedWood'])

    def fault_action(self, kind):
        fixture = {'craft_forestry_tool': 'prepared', 'reserve_forest': 'adopted', 'cancel_forest_reservation': 'prepared',
                   'collect_seed': 'prepared', 'plant_tree': 'prepared', 'harvest_tree': 'mature'}[kind]
        w = self.use(fixture, suffix='-'+kind)
        if kind == 'craft_forestry_tool':
            w.go([26, 21.3])
            bench = next(e for e in w.observe()['entities'] if e['definitionId'] == 'workbench' and e['ownerActorId'] == OWNER)
            return action(kind, entityId=bench['entityId'], recipeId='wooden_axe.v1')
        if kind == 'reserve_forest':
            return action(kind)
        if kind == 'cancel_forest_reservation':
            return action(kind, reservationId=self.facts['reservationId'])
        if kind == 'collect_seed':
            return action(kind, reservationId=self.facts['reservationId'], sourceId='nursery-west')
        if kind == 'plant_tree':
            w.apply('collect_seed', reservationId=self.facts['reservationId'], sourceId='nursery-west')
            x, z = PLOTS[self.facts['plotId']]
            w.go([x+1.2, z])
            return action(kind, reservationId=self.facts['reservationId'], plotId=self.facts['plotId'])
        x, z = PLOTS[self.facts['plotId']]
        w.send({'type': 'build', 'recipeId': 'platform.v1', 'at': [x+3, z]})
        return self.harvest_action()

    def transaction_crashes(self, fault, exit_code, committed):
        for kind in ('craft_forestry_tool', 'reserve_forest', 'cancel_forest_reservation', 'collect_seed', 'plant_tree', 'harvest_tree'):
            with self.subTest(action=kind):
                a = self.fault_action(kind)
                w = self.world
                intent = w.intent(a)
                before = w.observe()
                with self.assertRaises((OSError, http.client.HTTPException)):
                    w.request('POST', PREFIX+'/commands', intent, fault=fault)
                self.assertEqual(exit_code, w.process.wait(timeout=10))
                w.restart()
                lookup = w.request('GET', PREFIX+'/commands/'+intent['commandId'])
                self.assertEqual(200 if committed else 404, lookup[0], lookup[1])
                if not committed:
                    after = w.observe()
                    for field in ('self',):
                        self.assertEqual(before[field], after[field])
                    for field in ('seeds', 'plants', 'tools', 'reservations'):
                        self.assertEqual(before['forestry'][field], after['forestry'][field])
                reply = self.post(intent)
                if committed:
                    self.assertEqual(lookup[2], reply[2])
                self.fact(intent, reply)
                self.assertEqual(reply[2], self.post(intent)[2])
                self.audit()

    def test_11_six_actions_before_commit_crash_rolls_back_original_id_resumes(self):
        self.transaction_crashes('before-commit', 81, False)

    def test_12_six_actions_after_commit_crash_recovers_same_fact_once(self):
        self.transaction_crashes('after-commit', 82, True)

    def test_13_four_resource_debit_exceptions_leave_no_partial_effect(self):
        for kind in ('craft_forestry_tool', 'collect_seed', 'plant_tree', 'harvest_tree'):
            with self.subTest(action=kind):
                a = self.fault_action(kind)
                w = self.world
                intent = w.intent(a)
                before = w.observe()
                self.post(intent, expected=503, fault='throw-after-debit')
                self.assertEqual(404, w.request('GET', PREFIX+'/commands/'+intent['commandId'])[0])
                after = w.observe()
                self.assertEqual(before['self'], after['self'])
                for field in ('seeds', 'plants', 'tools', 'reservations'):
                    self.assertEqual(before['forestry'][field], after['forestry'][field])
                self.fact(intent, self.post(intent))
                self.audit()

    def test_14_adoption_crash_transaction_and_retry_are_idempotent(self):
        for fault, exit_code, committed in [('before-commit', 91, False), ('after-commit', 92, True)]:
            with self.subTest(fault=fault):
                w = self.use('legacy', start=False, suffix='-'+fault)
                before = snapshot(w.data)
                w.env['WORLD_FORESTRY_ADOPTION_TEST_FAULT'] = fault
                result = w.admin('adopt-forestry')
                self.assertEqual(exit_code, result.returncode, result.stderr)
                after = snapshot(w.data)
                self.assertEqual((14 if committed else 13,), after['user_version'])
                if not committed:
                    self.assertEqual(before, after)
                w.env.pop('WORLD_FORESTRY_ADOPTION_TEST_FAULT')
                self.assertEqual(0, w.admin('adopt-forestry').returncode)
                final = snapshot(w.data)
                if committed:
                    self.assertEqual(after, final)
                self.assertEqual(0, w.admin('adopt-forestry').returncode)
                self.assertEqual(final, snapshot(w.data))
                w.start()
                self.audit()

    def test_15_adoption_rechecks_current_residents_and_existing_buildings(self):
        for collision in ('resident', 'building'):
            with self.subTest(collision=collision):
                w = self.use('legacy', suffix='-'+collision)
                w.go([8.2, 12])
                if collision == 'building':
                    w.send({'type': 'build', 'recipeId': 'platform.v1', 'at': [7, 12]})
                    w.go([10, 12])
                w.stop()
                before = snapshot(w.data)
                result = w.admin('adopt-forestry')
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, snapshot(w.data))
                w.start()
                self.assertNotIn('forestry', w.observe())

    def test_16_reserved_building_footprints_and_body_occupied_planting(self):
        w = self.use('prepared')
        w.apply('collect_seed', sourceId='nursery-west', reservationId=self.facts['reservationId'])
        x, z = PLOTS[self.facts['plotId']]
        w.go([x+1.2, z])
        for a in ({'type': 'build', 'recipeId': 'platform.v1', 'at': [x, z]},
                  action('build_workshop', recipeId='workbench.v1', at=[x, z], toolId=None)):
            self.reject(a, expected=409)
        # An empty plot is walkable; planting must not materialize through a body.
        w.go([x, z], OTHER)
        intent, denied = self.reject(action('plant_tree', plotId=self.facts['plotId'], reservationId=self.facts['reservationId']), expected=409)
        self.assertEqual('AREA_OCCUPIED', denied[1]['error']['code'])
        self.assertEqual(1, w.observe()['forestry']['seeds'])
        w.go([x, z+1.2], OTHER)
        self.assertEqual(denied[2], self.post(intent, expected=409)[2])
        fresh, reply = w.apply('plant_tree', plotId=self.facts['plotId'], reservationId=self.facts['reservationId'])
        self.fact(fresh, reply)
        self.audit()

    def test_17_adoption_respects_actual_resident_radius_at_clear_boundary(self):
        w = self.use('legacy')
        # The forest reserve ends at x=8.5; a radius .28 resident at x=8.85 is clear.
        w.go([8.85, 12])
        observed = w.observe()
        self.assertEqual(.28, observed['movement']['radius'])
        self.assertGreater(observed['self']['position'][0]-.28, 8.5)
        w.stop()
        result = w.admin('adopt-forestry')
        self.assertEqual(0, result.returncode, result.stderr)
        w.start()
        self.audit()

    def test_18_original_workshop_recipes_and_mallet_remain_distinct_from_axe(self):
        w = self.use('prepared')
        w.go([26, 21.3])
        observed = w.observe()
        self.assertEqual(['workbench.v1', 'wooden_mallet.v1', 'wooden_chest.v1'],
                         [r['id'] for r in observed['workshop']['recipes']])
        self.assertTrue(all(t['definitionId'] == 'wooden_mallet' and t['embodiedWood'] == 1 for t in observed['workshop']['tools']))
        self.assertNotIn(self.facts['a2Tool'], [t['toolId'] for t in observed['workshop']['tools']])
        bench = next(e for e in observed['entities'] if e['definitionId'] == 'workbench' and e['ownerActorId'] == OWNER)
        intent, reply = w.send(transport.craft(bench['entityId']))
        detail = reply[1]['result']['workshopAction']
        self.assertNotIn('forestryAction', reply[1]['result'])
        self.assertEqual(('wooden_mallet', 1), (detail['tool']['definitionId'], detail['tool']['embodiedWood']))
        self.assertEqual(1, detail['inventoryWoodBefore']-detail['inventoryWood'])
        self.assertEqual(detail, w.request('GET', PREFIX+'/workshop/actions/a2/'+intent['commandId'])[1]['workshopAction'])
        self.assertEqual(reply[2], self.post(intent, capability=None)[2])
        w.go([30, 22.2])
        self.reject(transport.build('wooden_chest.v1', [30, 20.8], self.facts['a2Tool']))
        _, built = w.send(transport.build('wooden_chest.v1', [30, 20.8], detail['tool']['toolId']))
        chest = built[1]['result']['workshopAction']['entity']['entityId']
        w.send(transport.storage('deposit_wood', chest, 1))
        w.send(transport.storage('withdraw_wood', chest, 1))
        self.assertEqual(6, w.observe()['self']['inventory']['wood'])
        self.audit()


def main():
    RUN.mkdir(parents=True, mode=0o700, exist_ok=True)
    suite = unittest.TestSuite(ForestryAcceptance(name) for name in sys.argv[1:]) if sys.argv[1:] else unittest.defaultTestLoader.loadTestsFromTestCase(ForestryAcceptance)
    try:
        with (RUN/'test.log').open('w') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=transport.EvidenceResult).run(suite)
        report = dict(suite='independent-forestry-http-v1', passed=result.wasSuccessful(), testsRun=result.testsRun,
                      tests=result.records, actualModelCalls=0, skipped=[(str(t), why) for t, why in result.skipped],
                      failures=[(str(t), detail) for t, detail in result.failures+result.errors],
                      testSha256=sha(__file__), dllSha256=sha(DLL) if DLL and DLL.exists() else None)
        report['candidateAtStart'] = json.loads((RUN/'candidate.json').read_text()) if (RUN/'candidate.json').exists() else None
    finally:
        # Only run-owned disposable databases, tokens and logs; evidence is kept.
        removed = 0
        for path in RUN.iterdir():
            if path.is_dir():
                removed += sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
                shutil.rmtree(path)
    report['disposedBytes'] = removed
    save(RUN/'results.json', report)
    print(json.dumps(dict(passed=report['passed'], testsRun=result.testsRun, evidence=str(RUN/'results.json')), ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
