#!/usr/bin/env python3
"""Persisted missions cannot adopt a replacement database at the same address."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import socket
import sys
import unittest
import uuid

import activities_api
from activities_api import ActivityCandidate
from continuous_mission_api import mission
from foundation_api import EvidenceResult, ROOT
from foundation_agent import WorldClient
from resident_mission import run_mission
from resident_mission_api import Choice
from wilderness_api import WildernessAcceptance

RUN_ROOT = ROOT / '.local/instance-mission/api' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN_ROOT


class InstanceMissionAcceptance(unittest.TestCase):
    def setUp(self):
        self.world = ActivityCandidate(self._testMethodName, scenario='wilderness-continuous-v1')
        self.a = self.world.client()
        self.state = self.world.data / 'mission.json'
        self.choose = Choice('destination')
        self.trace, self.reports, self.extra = [], [], []

    def tearDown(self):
        for world in self.extra: world.stop()
        (self.world.data / 'reports.json').write_text(json.dumps(self.reports, ensure_ascii=False, indent=2) + '\n')
        WildernessAcceptance.tearDown(self)

    def task(self, client=None, **kwargs):
        report = run_mission(client or self.a, mission(), self.state, self.choose, **kwargs)
        self.reports.append(report)
        return report

    def dropped(self):
        class Drop(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                result = super().request(method, path, payload, headers)
                if method == 'POST': raise OSError('lost committed reply')
                return result
        report = self.task(Drop(self.world.url, self.world.access['sessions']['a1']['token']))
        self.assertEqual('unknown', report['mission']['status'])
        return json.loads(self.state.read_text())

    def counted(self, world):
        class Count(WorldClient):
            def request(inner, method, path, payload=None, headers=None):
                self.trace.append({'method':method, 'path':path, 'commandId':(payload or {}).get('commandId')})
                return super().request(method, path, payload, headers)
        return Count(world.url, world.access['sessions']['a1']['token'])

    def unchanged_intent(self, before):
        after = json.loads(self.state.read_text())
        for key in ('binding','pending','spec','startedEpoch','initial'):
            self.assertEqual(before['_state'][key], after['_state'][key], key)
        for key in ('origin','goal','actorId','rulesVersion'):
            self.assertEqual(before['mission'][key], after['mission'][key], key)
        for key in ('commands','wood','modelCalls'):
            self.assertEqual(before['budget']['used'][key], after['budget']['used'][key], key)
        self.assertEqual(before['decision'], after['decision']); self.assertEqual(before['steps'], after['steps'])

    def test_01_same_url_new_database_never_replays_old_pending(self):
        before = self.dropped(); instance = before['_state']['binding']['instanceId']
        self.assertRegex(instance, r'^w_[0-9a-f]{32}$')
        replacement = ActivityCandidate(self._testMethodName + '-replacement', scenario='wilderness-continuous-v1')
        self.extra.append(replacement); replacement.stop(); self.world.stop()
        replacement.url = self.world.url; replacement.env['WORLD_URL'] = replacement.url; replacement.start()
        replacement_before = replacement.dump()
        report = self.task(self.counted(replacement))
        self.assertEqual(('unknown','observation_unavailable:WorldBindingError'),
                         (report['mission']['status'],report['mission']['reason']))
        self.unchanged_intent(before)
        self.assertTrue(self.trace); self.assertTrue(all(x['method']=='GET' and x['path'].endswith('/observation') for x in self.trace))
        self.assertEqual(replacement_before, replacement.dump())
        replacement.stop(); self.world.start()
        final = self.task(self.world.client()); self.assertEqual('completed', final['mission']['status'])
        self.assertEqual(before['_state']['pending']['request']['commandId'], final['steps'][0]['commandId'])
        self.assertEqual(1, self.choose.calls)

    def test_02_same_instance_new_endpoint_recovers_original_request(self):
        before = self.dropped(); self.world.stop()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        self.world.url=f'http://127.0.0.1:{port}'; self.world.env['WORLD_URL']=self.world.url; self.world.start()
        self.trace=[]; final = self.task(self.counted(self.world))
        self.assertEqual('completed', final['mission']['status'])
        after=json.loads(self.state.read_text())
        self.assertEqual(before['_state']['binding']['instanceId'],after['_state']['binding']['instanceId'])
        self.assertEqual(self.world.url,after['_state']['binding']['url'])
        original=before['_state']['pending']['request']['commandId']
        self.assertEqual(original,final['steps'][0]['commandId'])
        self.assertTrue(any(x['path'].endswith('/commands/'+original) for x in self.trace))
        self.assertFalse(any(x['method']=='POST' and x['commandId']==original for x in self.trace))
        self.assertEqual(1,self.choose.calls)

    def test_03_legacy_unbound_task_cannot_adopt_current_instance(self):
        before=self.dropped()
        for key in ('instanceId','bindingVersion'): before['_state']['binding'].pop(key)
        before['mission'].pop('worldInstanceId',None)
        before['world'].pop('instanceId',None); before['_state']['initial']['world'].pop('instanceId',None)
        self.state.write_text(json.dumps(before)); self.trace=[]
        report=self.task(self.counted(self.world))
        self.assertEqual('unknown',report['mission']['status']); self.unchanged_intent(before)
        self.assertTrue(all(x['method']=='GET' and x['path'].endswith('/observation') for x in self.trace))
        self.assertEqual(1,self.choose.calls)

    def test_04_missing_or_invalid_protected_identity_never_downgrades(self):
        before=self.dropped()
        for change in (lambda b:b.pop('instanceId'), lambda b:b.update(instanceId=None),
                       lambda b:b.update(instanceId='w_invalid'), lambda b:b.update(bindingVersion=0),
                       lambda b:b.pop('bindingVersion')):
            bad=deepcopy(before); change(bad['_state']['binding']); self.state.write_text(json.dumps(bad)); original=self.state.read_bytes()
            self.trace=[]
            with self.assertRaises(ValueError): self.task(self.counted(self.world))
            self.assertEqual(original,self.state.read_bytes()); self.assertEqual([],self.trace)

    def test_05_completed_report_is_historical_without_contacting_new_world(self):
        report=self.task(); self.assertEqual('completed',report['mission']['status']); original=self.state.read_bytes()
        class Offline(WorldClient):
            def request(inner,*args,**kwargs): raise AssertionError('historical report contacted a world')
        self.assertEqual(report,self.task(Offline('http://127.0.0.1:1','new-credentials')))
        self.assertEqual(original,self.state.read_bytes()); self.assertEqual(1,self.choose.calls)


if __name__ == '__main__':
    RUN_ROOT.mkdir(parents=True,mode=0o700)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(InstanceMissionAcceptance)
    if len(sys.argv)>1: suite=unittest.TestSuite(t for t in suite if t._testMethodName in set(sys.argv[1:]))
    result=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(suite)
    (RUN_ROOT/'results.json').write_text(json.dumps({'suite':'instance-mission-http','actualModelCalls':0,
        'decisionSource':'test-double','passed':result.wasSuccessful(),'testsRun':result.testsRun,'tests':result.records,
        'failures':[{'test':str(t),'detail':d} for t,d in result.failures+result.errors]},ensure_ascii=False,indent=2)+'\n')
    print('Evidence:',RUN_ROOT/'results.json')
    raise SystemExit(0 if result.wasSuccessful() else 1)
