#!/usr/bin/env python3
"""Actual bounded gifting and recipient construction, including original-command recovery."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import sys
import unittest
import uuid

import activities_api
from foundation_api import ROOT, DLL, EvidenceResult
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice
from construction_mission_api import mission as build_mission
from material_transfer_api import TransferAcceptance, gift

RUN = ROOT / '.local/iter0020/python' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN


def mission(target=None):
    return {'missionId': 'gift-task', 'objective': '在会面点赠送 a2 三块木材，然后返回。',
            'goals': [{'id': 'gift', 'label': '会面交付', 'target': target or [26, 16],
                       'transfer': {'recipientActorId': 'a2', 'resource': 'wood', 'quantity': 3}}],
            'allowTransfer': True, 'allowBuild': False, 'allowGather': False,
            'budgets': {'commands': 50, 'wood': 3, 'seconds': 600, 'modelCalls': 1}}


class TransferMissionAcceptance(unittest.TestCase):
    create = TransferAcceptance.create
    intent = TransferAcceptance.intent
    post = TransferAcceptance.post
    send = TransferAcceptance.send
    walk = TransferAcceptance.walk
    approach = TransferAcceptance.approach
    collect = TransferAcceptance.collect
    bridge = TransferAcceptance.bridge
    meeting = TransferAcceptance.meeting

    def setUp(self):
        TransferAcceptance.setUp(self)
        self.meeting()
        self.state = self.world.data / 'mission.json'
        self.choose, self.reports = Choice('gift'), []

    def tearDown(self):
        (self.world.data / 'reports.json').write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + '\n')
        TransferAcceptance.tearDown(self)

    def task(self, job=None, client=None, **kwargs):
        report = run_mission(client or self.a, job or mission(), self.state, self.choose, **kwargs)
        self.reports.append(report)
        return report

    def client(self, *, before=None, after=None, actor='a1'):
        owner = self
        class Controlled(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                if method == 'POST' and before:
                    headers = before(payload, headers)
                result = super().request(method, path, payload, headers)
                if method == 'POST' or '/commands/' in path:
                    owner.trace.append({'method': method, 'path': path, 'request': deepcopy(payload), 'response': deepcopy(result)})
                return after(method, path, payload, result) if after else result
        return Controlled(self.world.url, self.world.access['sessions'][actor]['token'])

    def completed(self, report):
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['transferCompleted'] and report['facts']['returned'] and report['facts']['goalReached'])
        fact = report['facts']['transfer']
        self.assertEqual(('a1', 'a2', 'wood', 3, 6, 3), tuple(fact[k] for k in ('senderActorId', 'recipientActorId', 'resource', 'quantity', 'inventoryWoodBefore', 'inventoryWoodAfter')))
        self.assertEqual(report['mission']['worldInstanceId'], fact['worldInstanceId'])
        self.assertEqual((3, 3, 0), (report['budget']['used']['wood'], report['facts']['woodTransferred'], report['facts']['woodGathered']))
        self.assertEqual([], report['facts']['createdEntityIds'])
        self.assertEqual(1, sum(s['action']['type'] == 'transfer' and s['status'] == 'committed' for s in report['steps']))

    def test_01_real_meeting_gift_return_and_recipient_build(self):
        # Even a choice provider adding its own amount cannot change the authorized goal.
        def choose(context):
            return {**self.choose(context), 'transfer': {'recipientActorId': 'a1', 'quantity': 12}}
        report = run_mission(self.a, mission([25.5, 16]), self.state, choose)
        self.reports.append(report); self.completed(report)
        self.assertEqual(1, self.choose.calls)
        received = self.b.observe()['recentTransfers']['items'][-1]
        self.assertEqual(report['facts']['transfer']['commandId'], received['commandId'])
        job = build_mission(target=[28, 16]); job['allowGather'] = False
        built = run_mission(self.b, job, self.world.data / 'recipient.json', Choice('construction'))
        self.reports.append(built)
        self.assertEqual('completed', built['mission']['status'], built['mission'])
        self.assertEqual(('a2', 3), (built['facts']['construction']['ownerActorId'], built['facts']['construction']['woodSpent']))
        self.assertEqual(0, self.b.observe()['self']['inventory']['wood'])
        self.assertEqual(received, built['world']['recentTransfers']['items'][-1])
        for name, value in [('sender-report.json', report), ('recipient-report.json', built)]:
            (self.world.data / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    def test_02_authorization_budget_material_and_meeting_bounds(self):
        for field, value in [('allowTransfer', False), ('allowTransfer', 'yes')]:
            invalid = mission(); invalid[field] = value
            with self.assertRaises(ValueError): self.task(invalid)
        invalid = mission(); invalid.pop('allowTransfer')
        with self.assertRaises(ValueError): self.task(invalid)
        self.assertFalse(self.state.exists()); self.assertEqual(0, self.choose.calls)
        cases = []
        cheap = mission(); cheap['budgets']['wood'] = 2
        cases.append((cheap, self.a, 'budget_exhausted', 'wood'))
        missing = mission(); missing['goals'][0]['transfer']['recipientActorId'] = 'missing'
        cases.append((missing, self.a, 'blocked', 'transfer_recipient_unavailable'))
        cases.append((mission([5, 7]), self.a, 'blocked', 'transfer_recipient_not_at_meeting'))
        empty = mission([26.7, 16]); empty['goals'][0]['transfer']['recipientActorId'] = 'a1'
        cases.append((empty, self.b, 'blocked', 'transfer_material_unavailable'))
        before = self.a.observe()['stateVersion']
        for index, (job, client, status, reason) in enumerate(cases):
            self.state = self.world.data / f'blocked-{index}.json'
            report = self.task(job, client)
            self.assertEqual((status, reason), (report['mission']['status'], report['mission']['reason']))
            self.assertEqual(0, report['budget']['used']['commands'])
        self.assertEqual(before, self.a.observe()['stateVersion'])

    def test_03_lost_reply_new_session_after_recipient_spends_recovers_original(self):
        def lost(method, path, payload, response):
            if method == 'POST': raise OSError('lost after commit')
            return response
        first = self.task(client=self.client(after=lost))
        self.assertEqual('unknown', first['mission']['status'])
        original = json.loads(self.state.read_text())['_state']['pending']['request']
        self.send(self.b, {'type': 'build', 'recipeId': 'platform.v1', 'at': [28, 16]})
        fresh = self.world.issue('a1', 600)
        final = self.task(client=fresh); self.completed(final)
        self.assertEqual(original['commandId'], final['facts']['transfer']['commandId'])
        self.assertEqual(1, final['budget']['used']['commands'])
        self.assertEqual(0, self.b.observe()['self']['inventory']['wood'])

    def test_04_before_commit_exit_resends_original_with_original_budget(self):
        first = self.task(client=self.client(before=lambda _, h: {**(h or {}), 'X-Test-Fault': 'before-commit'}))
        self.assertEqual('unknown', first['mission']['status'])
        self.assertEqual(81, self.world.process.wait(timeout=10)); self.world.restart()
        original = json.loads(self.state.read_text())['_state']['pending']['request']
        final = self.task(); self.completed(final)
        self.assertEqual(original['commandId'], final['facts']['transfer']['commandId'])
        self.assertEqual(1, final['budget']['used']['commands'])

    def test_05_corrupt_receipts_keep_original_until_authoritative_query(self):
        mutations = [lambda r: r.update(rulesVersion='r8'), lambda r: r.update(identity=None),
                     lambda r: r['result'].update(senderActorId='a2'), lambda r: r['result'].update(recipientActorId='a1'),
                     lambda r: r['result'].update(quantity=True), lambda r: r['result'].update(resource='stone'),
                     lambda r: r['result'].update(inventoryWood=6), lambda r: r.pop('execution'),
                     lambda r: r.update(commandId='different'), lambda r: r['result'].pop('recipientActorId')]
        original = None
        for mutate in mutations:
            def corrupt(method, path, payload, response):
                status, receipt = response
                if isinstance(receipt, dict) and receipt.get('result', {}).get('action') == 'transfer': mutate(receipt)
                return status, receipt
            report = self.task(client=self.client(after=corrupt))
            self.assertEqual('unknown', report['mission']['status'])
            pending = json.loads(self.state.read_text())['_state']['pending']['request']
            original = original or pending
            self.assertEqual(original, pending)
            self.assertEqual((False, 0, 1), (report['facts']['transferCompleted'], report['budget']['used']['wood'], report['budget']['used']['commands']))
        self.completed(self.task()); self.assertEqual(3, self.b.observe()['self']['inventory']['wood'])

    def test_06_incoming_gift_stops_original_receiver_task_without_budget_reset(self):
        job = build_mission(target=[27.5, 16]); job['goals'][0].pop('buildRecipeId')
        job.update(allowBuild=False, allowGather=False); job['budgets']['wood'] = 0
        self.choose = Choice('construction')
        def offline(*_): raise OSError('original walk not sent')
        first = self.task(job, self.client(before=offline, actor='a2'))
        self.assertEqual('unknown', first['mission']['status'])
        self.send(self.a, gift())
        final = self.task(job, self.b)
        self.assertEqual(('blocked', 'command_rejected:STALE_ACTOR_STATE'), (final['mission']['status'], final['mission']['reason']))
        self.assertEqual((1, 0), (final['budget']['used']['commands'], final['budget']['used']['wood']))
        saved = self.state.read_bytes()
        offline_client = self.world.client('a2')
        offline_client.request = lambda *_a, **_k: self.fail('stopped original task made a network request')
        self.assertEqual(final, self.task(job, offline_client)); self.assertEqual(saved, self.state.read_bytes())
        explicit = build_mission(target=[28, 16]); explicit['allowGather'] = False
        continued = run_mission(self.b, explicit, self.world.data / 'explicit-new-task.json', Choice('construction'))
        self.assertEqual('completed', continued['mission']['status'], continued['mission'])

    def test_07_damaged_pending_authorization_and_before_facts_make_no_request(self):
        def offline(*_): raise OSError('before submit')
        self.task(client=self.client(before=offline))
        baseline = json.loads(self.state.read_text())
        mutations = [lambda s: s['_state']['pending'].pop('transferBefore'),
                     lambda s: s['_state']['pending']['transferBefore'].update(inventoryWood=True),
                     lambda s: s['_state']['pending']['transferBefore'].update(inventoryWood=-1),
                     lambda s: s['_state']['pending']['transferBefore'].update(inventoryWood=2),
                     lambda s: s['_state']['pending']['transferBefore'].update(inventoryWood=9),
                     lambda s: s['_state']['pending']['transferBefore'].update(position=[None, 1]),
                     lambda s: s['_state']['pending']['transferBefore'].update(position=[0, 0]),
                     lambda s: s['_state']['pending']['transferBefore'].update(position=[26.05, 16]),
                     lambda s: s['_state']['pending'].update(woodCost=1),
                     lambda s: s['mission'].update(allowTransfer=False),
                     lambda s: s['_state']['pending']['request']['action'].update(quantity=6),
                     lambda s: s['_state']['pending']['request']['action'].update(recipientActorId='a1')]
        for mutate in mutations:
            state = deepcopy(baseline); mutate(state); self.state.write_text(json.dumps(state))
            raw = self.state.read_bytes()
            client = self.world.client(); client.request = lambda *_a, **_k: self.fail('damaged pending made a request')
            with self.assertRaises(ValueError): self.task(client=client)
            self.assertEqual(raw, self.state.read_bytes())
        self.state.write_text(json.dumps(baseline)); self.completed(self.task())

    def test_08_same_url_new_instance_never_receives_old_pending(self):
        def offline(*_): raise OSError('before submit')
        self.task(client=self.client(before=offline))
        original = json.loads(self.state.read_text())['_state']['pending']['request']
        other = self.create('replacement'); other.stop(); self.world.stop()
        other.port, other.url = self.world.port, self.world.url
        other.env['WORLD_URL'] = other.url; other.start()
        report = self.task(client=other.client())
        self.assertEqual('unknown', report['mission']['status'])
        self.assertEqual(original, json.loads(self.state.read_text())['_state']['pending']['request'])
        self.assertEqual(0, other.client().observe()['stateVersion'])
        other.stop(); self.world.start(); self.completed(self.task())

    def test_09_initial_cross_river_no_permission_stops_without_exception_or_actions(self):
        fresh = self.create('initial-no-route')
        job = mission([26, 17])
        report = run_mission(fresh.client(), job, fresh.data / 'mission.json', Choice('gift'))
        self.reports.append(report)
        self.assertEqual(('blocked', 'no_route'), (report['mission']['status'], report['mission']['reason']))
        self.assertEqual(0, report['budget']['used']['commands'])
        self.assertEqual(0, fresh.client().observe()['stateVersion'])

    def test_10_initial_collect_bridge_then_collect_gift_with_total_budget_nine(self):
        fresh = self.create('initial-staged-gift')
        job = mission([26, 17]); job.update(allowBuild=True, allowGather=True)
        job['budgets'].update(commands=300, wood=9)
        chooser = Choice('gift')
        report = run_mission(fresh.client(), job, fresh.data / 'mission.json', chooser)
        self.reports.append(report)
        self.assertEqual('completed', report['mission']['status'], report['mission'])
        self.assertTrue(report['facts']['transferCompleted'] and report['facts']['returned'])
        self.assertEqual((9, 9, 3, 1), (report['facts']['woodGathered'], report['budget']['used']['wood'], report['facts']['woodTransferred'], chooser.calls))
        steps = report['steps']; bridge_index = next(i for i, s in enumerate(steps) if s['action']['type'] == 'build')
        self.assertEqual(6, sum(s['action']['type'] == 'gather' for s in steps[:bridge_index]))
        self.assertEqual(3, sum(s['action']['type'] == 'gather' for s in steps[bridge_index + 1:]))
        observed = fresh.client('a2').observe()
        self.assertEqual((3, 3, 6), (observed['self']['inventory']['wood'], observed['resourceAudit']['wildWood'], observed['resourceAudit']['embodiedWood']))
        (fresh.data / 'actual-staged-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TransferMissionAcceptance)
    if len(sys.argv) > 1:
        suite = unittest.TestSuite(t for t in suite if t._testMethodName in set(sys.argv[1:]))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    evidence = {'suite': 'transfer-mission-v1', 'passed': result.wasSuccessful(), 'testsRun': result.testsRun,
                'tests': result.records, 'actualModelCalls': 0, 'dllSha256': hashlib.sha256(DLL.read_bytes()).hexdigest(),
                'sourceSha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((ROOT / 'scripts').glob('*.py'))},
                'failureDetails': [(str(t), detail) for t, detail in result.failures + result.errors]}
    (RUN / 'results.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json')
    raise SystemExit(not result.wasSuccessful())
