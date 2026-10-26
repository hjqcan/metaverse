#!/usr/bin/env python3
"""Targeted real-clock tests: GET under writer lock, and delayed queued grant."""
from datetime import datetime, timezone
import hashlib
import json
import os
import signal
import sqlite3
import time
import unittest
import uuid
import activities_api
from foundation_api import ROOT, DLL, EvidenceResult
from material_access_api import MaterialAccessAcceptance, reserve

RUN = ROOT / '.local/iter0022/time' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
activities_api.RUN_ROOT = RUN


class MaterialClockAcceptance(unittest.TestCase):
    setUp = MaterialAccessAcceptance.setUp
    tearDown = MaterialAccessAcceptance.tearDown
    create = MaterialAccessAcceptance.create
    admin = MaterialAccessAcceptance.admin
    enable = MaterialAccessAcceptance.enable
    intent = MaterialAccessAcceptance.intent
    post = MaterialAccessAcceptance.post
    send = MaterialAccessAcceptance.send
    until = MaterialAccessAcceptance.until
    active = MaterialAccessAcceptance.active

    def test_01_get_is_read_only_while_writer_is_locked_across_production_boundary(self):
        self.enable()
        with sqlite3.connect(self.world.data / 'world.db', timeout=10) as lock:
            lock.execute('BEGIN IMMEDIATE')
            before = self.c.observe()
            self.assertEqual(0, before['materialAccess']['generatedWood'])
            started = time.monotonic()
            while time.monotonic() - started < 10.6:
                current = self.c.observe()
                self.assertEqual(before, current)
                time.sleep(.12)
            lock.rollback()
        current = self.until(self.c, lambda o: o['materialAccess']['generatedWood'] == 3, timeout=8)
        self.assertGreaterEqual(current['materialAccess']['serviceMs'] - before['materialAccess']['serviceMs'], 10000)

    def test_02_queued_before_process_pause_gets_full_lease_from_actual_resume_time(self):
        self.enable(); rid = self.send(self.c, reserve())['result']['reservationId']
        before = self.c.observe(); self.assertEqual('queued', before['materialAccess']['currentReservation']['status'])
        os.kill(self.world.process.pid, signal.SIGSTOP)
        try:
            time.sleep(12)
        finally:
            os.kill(self.world.process.pid, signal.SIGCONT)
        resumed = self.active(self.c, rid); source = resumed['materialAccess']; lease = source['currentReservation']
        self.assertGreaterEqual(lease['grantedAtMs'] - source['enabledAtServiceMs'], 12000)
        self.assertLess(source['serviceMs'] - lease['grantedAtMs'], 1000)
        self.assertEqual(60000, lease['expiresAtMs'] - lease['grantedAtMs'])
        self.assertEqual(3, source['generatedWood'])


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    paths = [ROOT/'tests/material_access_api.py', ROOT/'tests/material_access_time_api.py', *sorted((ROOT/'src/World.Server').glob('*.cs'))]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(MaterialClockAcceptance))
    report = {'passed': result.wasSuccessful(), 'testsRun': result.testsRun, 'tests': result.records,
              'actualModelCalls': 0, 'clock': 'real Stopwatch; SQLite lock or SIGSTOP only, no time/material row edits',
              'dllSha256': hashlib.sha256(DLL.read_bytes()).hexdigest(), 'sourceSha256': hashes,
              'sourceUnchanged': hashes == {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              'failureDetails': [(str(t), detail) for t, detail in result.failures + result.errors]}
    (RUN/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('Evidence:', RUN/'results.json')
    raise SystemExit(not result.wasSuccessful())
