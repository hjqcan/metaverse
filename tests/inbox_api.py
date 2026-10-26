#!/usr/bin/env python3
"""Inbox acceptance against real HTTP/SQLite, with explicitly labelled choice doubles."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import socket
import sqlite3
import sys
import unittest
import uuid

import consent_api
from consent_api import ConsentAcceptance, ConsentCandidate, ConsentChoice, PATCH, ROOT, mission
from foundation_api import EvidenceResult
from foundation_agent import WorldClient
from resident_mission import run_mission


RUN_ROOT = ROOT / '.local/iter0008/api' / (datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6])
consent_api.RUN_ROOT = RUN_ROOT


class InboxCandidate(ConsentCandidate):
    def __init__(self, name, scenario='consent-v1', fixture=None, fixture_prefix='fixture-r6-'):
        if not fixture:
            super().__init__(name, scenario)
            return
        self.data = RUN_ROOT / name; self.data.mkdir(parents=True, mode=0o700)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.env = {**os.environ, 'WORLD_URL': self.url, 'WORLD_DATA_DIR': str(self.data), 'WORLD_ENABLE_FAULTS': '1'}
        self.env.pop('WORLD_SCENARIO', None)
        with sqlite3.connect(self.data / 'world.db') as db:
            db.executescript((ROOT / 'tests/fixtures' / fixture).read_text())
        self.access = {'sessions': {actor: {'token': fixture_prefix + actor} for actor in ['a1', 'a2']}}
        (self.data / 'access.json').write_text(json.dumps(self.access))
        self.fixture_before = self.dump(); self.process = self.log = None; self.start()


class InboxAcceptance(unittest.TestCase):
    audit = ConsentAcceptance.audit
    send = ConsentAcceptance.send
    intent = ConsentAcceptance.intent
    walk = ConsentAcceptance.walk
    seed = ConsentAcceptance.seed
    visit = ConsentAcceptance.visit
    propose = ConsentAcceptance.propose
    propose_action = ConsentAcceptance.propose_action
    review_action = ConsentAcceptance.review_action
    task = ConsentAcceptance.task
    tearDown = ConsentAcceptance.tearDown

    def setUp(self):
        self.world = InboxCandidate(self._testMethodName)
        self.a, self.b = self.world.client(), self.world.client('a2')
        self.trace, self.reports = [], []
        self.state = self.world.data / 'mission.json'

    def get(self, suffix='', client=None, status=200):
        code, body = (client or self.a).request('GET', self.a.prefix + '/mosaic-proposals' + suffix)
        self.assertEqual(status, code, body)
        if status == 200:
            self.assertEqual(1, body['schemaVersion']); self.assertEqual('r6', body['rulesVersion'])
            self.assertIsNone(body['error'])
        return body

    def detail(self, p, client=None, status=200):
        return self.get('/' + p['authorActorId'] + '/' + p['commandId'], client, status)

    def decide(self, p, decision='reject'):
        reviewer = self.a if p['targetActorId'] == 'a1' else self.b
        v = self.visit(reviewer)
        return self.send(reviewer, self.review_action(p, v, decision))[1]['result']

    def history(self, count=51):
        self.seed(); first = self.propose()
        for _ in range(count):
            p = self.propose(); self.decide(p)
        return first

    def list_all(self, query, client=None):
        items, before = [], None
        while True:
            data = self.get('?' + query + (f'&before={before}' if before is not None else ''), client)
            rows = data['items']; self.assertLessEqual(len(rows), data['query']['limit'])
            versions = [p['stateVersion'] for p in rows]
            self.assertEqual(sorted(versions, reverse=True), versions)
            if before is not None: self.assertTrue(all(n < before for n in versions))
            items.extend(rows); before = data['nextBefore']
            if before is None: return items
            self.assertEqual(rows[-1]['stateVersion'], before)

    def test_01_oldest_pending_survives_recent_50_and_own_100_limits(self):
        p = self.history(102)
        self.assertFalse(any(x['commandId'] == p['commandId'] for x in self.a.observe()['mosaicProposals']))
        self.assertFalse(any(x['commandId'] == p['commandId'] for x in self.b.observe()['self']['mosaicProposals']))
        d = self.get(); self.assertEqual({'pending': 1, 'reviewed': 102, 'all': 103}, d['counts'])
        self.assertEqual([p['commandId']], [x['commandId'] for x in d['items']]); self.assertIsNone(d['nextBefore'])
        self.assertEqual({**{k: v for k, v in p.items() if k != 'action'}, 'review': None}, self.detail(p)['proposal'])

    def test_02_scope_is_derived_from_authenticated_resident(self):
        self.seed(); received = self.propose(); done = self.propose(); self.decide(done)
        v = self.visit(self.b)
        self.send(self.b, {'type': 'mosaic', 'activityId': 'garden', 'visitCommandId': v, 'expectedMosaicRevision': 1, 'patch': [{'x': 4, 'y': 4, 'color': 'leaf'}]})
        v = self.visit(self.a)
        sent = self.send(self.a, self.propose_action(v, patch=[{'x': 4, 'y': 4, 'color': 'rose'}]))[1]['result']
        for client, scope, expected in [(self.a, 'received', [received, done]), (self.b, 'sent', [received, done]), (self.a, 'sent', [sent]), (self.b, 'received', [sent])]:
            with self.subTest(scope=scope, actor='a1' if client is self.a else 'a2'):
                d = self.get(f'?scope={scope}&status=all', client)
                self.assertEqual({p['commandId'] for p in expected}, {p['commandId'] for p in d['items']})
                self.assertEqual(len(expected), d['counts']['all'])
        self.assertEqual(3, self.get('?scope=all&status=all')['counts']['all'])
        self.assertEqual('a2', self.get(client=self.b)['identity']['actorId'])
        # The pending old revision is still a pending decision, never auto-rejected.
        self.assertEqual(1, self.get()['counts']['pending'])

    def test_03_status_counts_and_cursor_are_independent(self):
        self.seed(); pending = []
        for i in range(27):
            p = self.propose()
            if i % 3: self.decide(p)
            else: pending.append(p)
        d = self.get('?scope=received&status=reviewed&limit=4')
        self.assertEqual({'pending': 9, 'reviewed': 18, 'all': 27}, d['counts'])
        self.assertEqual(4, len(d['items'])); self.assertTrue(all(p['review'] for p in d['items']))
        self.assertEqual(18, len(self.list_all('scope=received&status=reviewed&limit=4')))
        self.assertEqual({p['commandId'] for p in pending}, {p['commandId'] for p in self.list_all('scope=received&status=pending&limit=4')})
        self.assertEqual(27, len(self.list_all('scope=all&status=all&limit=20')))
        tail = self.get('?scope=all&status=all&before=1')
        self.assertEqual([], tail['items']); self.assertIsNone(tail['nextBefore']); self.assertEqual(27, tail['counts']['all'])

    def test_04_get_and_errors_leave_complete_logical_database_unchanged(self):
        self.seed(); p = self.propose(); self.decide(p)
        before = self.world.dump()
        for client in [self.a, self.b]:
            self.get(client=client); self.get('?scope=all&status=all', client); self.detail(p, client)
            self.get('?unknown=1', client, 400); self.get('/a2/missing', client, 404)
        self.assertEqual(before, self.world.dump())

    def test_05_strict_query_and_detail_path_validation(self):
        invalid = ['scope=', 'scope=other', 'status=', 'status=accepted', 'limit=', 'limit=0', 'limit=21', 'limit=-1', 'limit=+2', 'limit=1.0', 'limit=999999999999999999999999', 'before=', 'before=0', 'before=-1', 'before=+1', 'before=1.1', 'before=9223372036854775808', 'scope=all&scope=all', 'status=pending&status=pending', 'before=1&before=2', 'limit=2&limit=2', 'actorId=a2', 'anything=1']
        for query in invalid:
            with self.subTest(query=query): self.assertEqual('INVALID_REQUEST', self.get('?' + query, status=400)['error']['code'])
        self.seed(); p = self.propose()
        self.get('/a2/' + p['commandId'] + '?limit=1', status=400)
        self.get('/a2/bad.id', status=400)
        d = self.get('?limit=01&before=0002'); self.assertEqual(1, d['query']['limit']); self.assertEqual(2, d['query']['before'])

    def test_06_new_insert_does_not_repeat_or_skip_older_page(self):
        self.seed(); proposals = [self.propose() for _ in range(23)]
        d = self.get('?scope=all&status=all&limit=7'); first = d['items']; cursor = d['nextBefore']
        new = self.propose(); rest = []
        while cursor is not None:
            d = self.get(f'?scope=all&status=all&limit=7&before={cursor}'); rest.extend(d['items']); cursor = d['nextBefore']
        ids = [x['commandId'] for x in first + rest]
        self.assertEqual(23, len(ids)); self.assertEqual(23, len(set(ids))); self.assertEqual({p['commandId'] for p in proposals}, set(ids))
        self.assertNotIn(new['commandId'], ids); self.assertEqual(new['commandId'], self.get('?scope=all&status=all')['items'][0]['commandId'])

    def test_07_review_changes_filter_and_detail_but_not_proposal_order(self):
        self.seed(); old, new = self.propose(), self.propose()
        before = self.get(); self.assertEqual(2, before['counts']['pending'])
        review = self.decide(old, 'accept')
        d = self.detail(old)['proposal']; self.assertEqual({k: v for k, v in review.items() if k != 'action'}, d['review']); self.assertEqual(old['stateVersion'], d['stateVersion'])
        self.assertEqual(new['commandId'], self.get()['items'][0]['commandId'])
        self.assertEqual([new['commandId'], old['commandId']], [p['commandId'] for p in self.get('?status=all')['items']])
        self.assertEqual({'pending': 1, 'reviewed': 1, 'all': 2}, self.get()['counts'])
        self.assertEqual(2, review['mosaicEdit']['revision'])

    def test_08_read_is_public_but_review_authority_and_authentication_remain(self):
        self.seed(); p = self.propose()
        self.assertEqual(self.detail(p)['proposal'], self.detail(p, self.b)['proposal'])
        v = self.visit(self.b)
        _, receipt = self.send(self.b, self.review_action(p, v), expected=403)
        self.assertEqual('MOSAIC_REVIEW_FORBIDDEN', receipt['error']['code'])
        for suffix in ['', '/a2/' + p['commandId']]:
            status, _ = self.a.request('GET', self.a.prefix + '/mosaic-proposals' + suffix, headers={'Authorization': 'Bearer invalid'})
            self.assertEqual(401, status)
        self.assertEqual('MOSAIC_PROPOSAL_NOT_FOUND', self.get('/a1/' + p['commandId'], status=404)['error']['code'])

    def test_09_populated_r6_is_read_without_migration_or_logical_changes(self):
        old = InboxCandidate('old-r6', fixture='consent-v6-populated.sql')
        try:
            self.assertEqual(old.fixture_before, old.dump()); o = old.client().observe()
            self.assertEqual({'version': 1, 'maxPageSize': 20}, o['mosaicProposalInbox']); self.assertEqual('r6', o['rulesVersion'])
            status, d = old.client().request('GET', old.client().prefix + '/mosaic-proposals?scope=all&status=all')
            self.assertEqual(200, status); self.assertEqual(1, d['counts']['reviewed']); self.assertEqual('accept', d['items'][0]['review']['decision'])
            old.restart(); self.assertEqual(o, old.client().observe()); self.assertEqual(old.fixture_before, old.dump())
        finally: old.stop()

    def test_10_old_scenarios_reject_new_reads_without_querying_absent_tables(self):
        for scenario in ['foundation-v1', 'passage-v1', 'activities-v1', 'postcards-v1', 'mosaic-v1']:
            with self.subTest(scenario=scenario):
                old = InboxCandidate(scenario, scenario=scenario)
                try:
                    c = old.client(); before = old.dump(); self.assertNotIn('mosaicProposalInbox', c.observe())
                    for suffix in ['', '/a2/anything']:
                        status, d = c.request('GET', c.prefix + '/mosaic-proposals' + suffix)
                        self.assertEqual(422, status); self.assertEqual('MOSAIC_CONSENT_UNAVAILABLE', d['error']['code'])
                    self.assertEqual(before, old.dump())
                finally: old.stop()

    def test_11_new_task_reads_original_older_proposal_before_single_choice(self):
        p = self.history(); self.walk(self.a, (1, 1)); self.walk(self.b, (1, 2)); choice = ConsentChoice('accept')
        self.assertFalse(any(x['commandId'] == p['commandId'] for x in self.a.observe()['mosaicProposals']))
        r = self.task(mission('reviewer', p), choice, client=self.a)
        self.assertEqual('completed', r['mission']['status']); self.assertEqual(1, choice.calls)
        self.assertEqual(p['commandId'], choice.contexts[0]['observation']['mosaicProposal']['commandId'])
        self.assertEqual(p['patch'], r['facts']['mosaicEdit']['patch']); self.assertEqual(p['commandId'], r['facts']['mosaicReview']['proposalCommandId'])
        self.assertTrue(r['facts']['returned']); self.assertEqual(12, r['budget']['used']['commands'])

    def test_12_lookup_failure_cannot_fallback_to_recent_list_or_call_model(self):
        self.seed(); p = self.propose(); job = mission('reviewer', p); before = self.world.dump()
        for code, body in [(503, {'error': {'code': 'TEMPORARY'}}), (401, {'error': {'code': 'UNAUTHORIZED'}}), (404, {'error': {'code': 'MOSAIC_PROPOSAL_NOT_FOUND'}}), (404, {'error': {'code': 'OTHER'}})]:
            class Failed(WorldClient):
                def request(self, method, path, payload=None, headers=None):
                    if '/mosaic-proposals/' in path: return code, body
                    return super().request(method, path, payload, headers)
            self.state = self.world.data / f'failed-{code}-{body["error"]["code"]}.json'; choice = ConsentChoice('accept')
            with self.assertRaises((ValueError, RuntimeError)): self.task(job, choice, client=Failed(self.world.url, self.world.access['sessions']['a1']['token']))
            self.assertEqual(0, choice.calls); self.assertFalse(self.state.exists()); self.assertEqual(before, self.world.dump())

    def test_13_wrong_lookup_identity_reference_and_evidence_fail_before_choice(self):
        self.seed(); p = self.propose(); job = mission('reviewer', p); before = self.world.dump()
        changes = [(['identity', 'actorId'], 'a2'), (['schemaVersion'], True), (['rulesVersion'], 'r5'), (['stateVersion'], -1), (['eventCursor'], False), (['proposal', 'commandId'], 'other'), (['proposal', 'authorActorId'], 'a1'), (['proposal', 'targetActorId'], 'a2'), (['proposal', 'stateVersion'], 999999), (['proposal', 'position'], [1, 5]), (['proposal', 'review'], {'decision': 'reject'})]
        for i, (keys, value) in enumerate(changes):
            class Wrong(WorldClient):
                def request(self, method, path, payload=None, headers=None):
                    code, d = super().request(method, path, payload, headers)
                    if '/mosaic-proposals/' in path:
                        d = deepcopy(d); target = d
                        for key in keys[:-1]: target = target[key]
                        target[keys[-1]] = value
                    return code, d
            self.state = self.world.data / f'wrong-{i}.json'; choice = ConsentChoice('accept')
            with self.subTest(keys=keys), self.assertRaises(ValueError): self.task(job, choice, client=Wrong(self.world.url, self.world.access['sessions']['a1']['token']))
            self.assertEqual(0, choice.calls); self.assertFalse(self.state.exists()); self.assertEqual(before, self.world.dump())

    def test_14_newer_detail_refreshes_observation_without_replacing_original(self):
        self.seed(); p = self.propose(); self.walk(self.b, (1, 2)); outer = self
        class Advanced(WorldClient):
            advanced = False
            def request(self, method, path, payload=None, headers=None):
                if '/mosaic-proposals/' in path and not self.advanced:
                    self.advanced = True; outer.send(outer.b, {'type': 'move', 'dx': 1, 'dy': 0})
                return super().request(method, path, payload, headers)
        choice = ConsentChoice('reject'); r = self.task(mission('reviewer', p), choice, client=Advanced(self.world.url, self.world.access['sessions']['a1']['token']), max_steps=0)
        self.assertEqual(1, choice.calls); context = choice.contexts[0]['observation']
        self.assertEqual(r['facts']['startStateVersion'], context['stateVersion']); self.assertEqual(p['commandId'], context['mosaicProposal']['commandId'])
        self.assertEqual(self.a.observe()['stateVersion'], context['stateVersion'])

    def test_15_old_service_capability_absence_preserves_existing_review_path(self):
        self.seed(); p = self.propose()
        class Legacy(WorldClient):
            def observe(self):
                o = super().observe(); o.pop('mosaicProposalInbox', None); return o
            def request(self, method, path, payload=None, headers=None):
                if '/mosaic-proposals' in path: raise AssertionError('Legacy server cannot receive new lookup')
                return super().request(method, path, payload, headers)
        choice = ConsentChoice('reject'); r = self.task(mission('reviewer', p), choice, client=Legacy(self.world.url, self.world.access['sessions']['a1']['token']))
        self.assertEqual('completed', r['mission']['status']); self.assertEqual(1, choice.calls); self.assertFalse(r['facts']['mosaicPainted'])

    def test_16_resume_and_completed_task_do_not_lookup_again(self):
        self.seed(); p = self.propose()
        class Counting(WorldClient):
            lookups = 0
            def request(self, method, path, payload=None, headers=None):
                if '/mosaic-proposals/' in path:
                    self.lookups += 1
                    if self.lookups > 1: raise AssertionError('Original task must not repeat lookup')
                return super().request(method, path, payload, headers)
        c = Counting(self.world.url, self.world.access['sessions']['a1']['token']); choice = ConsentChoice('accept'); job = mission('reviewer', p)
        r = self.task(job, choice, client=c, max_steps=6); self.assertEqual('paused', r['mission']['status']); self.assertTrue(r['facts']['activityCompleted'])
        self.world.restart(); r = self.task(job, choice, client=c); self.assertEqual('completed', r['mission']['status']); original = self.state.read_bytes()
        self.task(job, choice, client=c); self.assertEqual(original, self.state.read_bytes()); self.assertEqual(1, c.lookups); self.assertEqual(1, choice.calls)

    def test_17_malformed_capability_and_reference_do_not_start_task(self):
        self.seed(); p = self.propose(); before = self.world.dump()
        for i, capability in enumerate([None, {'version': True, 'maxPageSize': 20}, {'version': 2, 'maxPageSize': 20}, {'version': 1, 'maxPageSize': 100}]):
            class Bad(WorldClient):
                def observe(self):
                    o = super().observe(); o['mosaicProposalInbox'] = capability; return o
            self.state = self.world.data / f'capability-{i}.json'; choice = ConsentChoice('accept')
            with self.assertRaises(ValueError): self.task(mission('reviewer', p), choice, client=Bad(self.world.url, self.world.access['sessions']['a1']['token']))
            self.assertEqual(0, choice.calls); self.assertFalse(self.state.exists())
        choice = ConsentChoice('accept')
        with self.assertRaises(ValueError): self.task(mission('reviewer', {**p, 'commandId': '../anything'}), choice, client=self.a)
        self.assertEqual(0, choice.calls); self.assertEqual(before, self.world.dump())


if __name__ == '__main__':
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InboxAcceptance)
    if len(sys.argv) > 1: suite = unittest.TestSuite(t for t in suite if t._testMethodName in set(sys.argv[1:]))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    evidence = {'suite': 'mosaic-inbox-http-v1', 'decisionSource': 'explicit-test-double', 'actualModelCalls': 0, 'recordedAtUtc': datetime.now(timezone.utc).isoformat(), 'passed': result.wasSuccessful(), 'testsRun': result.testsRun, 'tests': result.records, 'dataRoot': str(RUN_ROOT.relative_to(ROOT)), 'failures': [{'test': str(t), 'detail': detail} for t, detail in result.failures + result.errors]}
    (RUN_ROOT / 'results.json').write_text(json.dumps(evidence, ensure_ascii=True, indent=2) + '\n'); print('Evidence:', RUN_ROOT / 'results.json')
    raise SystemExit(0 if result.wasSuccessful() else 1)
