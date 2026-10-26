#!/usr/bin/env python3
"""Isolated SQL microbenchmark, not a World.Server world or HTTP load test.

Python creates synthetic event fixtures; measured SELECTs use the copied native
SQLite library shipped in this repository's Linux x64 service build, read-only.
"""
import ctypes as C
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import statistics
import time
import uuid

ROOT = Path(__file__).resolve().parents[4]
ROWS = 200_000


class NativeSqlite:
    def __init__(self, library, path):
        self.lib = C.CDLL(str(library))
        signatures = {
            'sqlite3_open_v2': ([C.c_char_p, C.POINTER(C.c_void_p), C.c_int, C.c_char_p], C.c_int),
            'sqlite3_close': ([C.c_void_p], C.c_int),
            'sqlite3_prepare_v2': ([C.c_void_p, C.c_char_p, C.c_int, C.POINTER(C.c_void_p), C.c_void_p], C.c_int),
            'sqlite3_step': ([C.c_void_p], C.c_int),
            'sqlite3_reset': ([C.c_void_p], C.c_int),
            'sqlite3_finalize': ([C.c_void_p], C.c_int),
            'sqlite3_column_int64': ([C.c_void_p, C.c_int], C.c_int64),
            'sqlite3_column_text': ([C.c_void_p, C.c_int], C.c_char_p),
            'sqlite3_stmt_status': ([C.c_void_p, C.c_int, C.c_int], C.c_int),
            'sqlite3_errmsg': ([C.c_void_p], C.c_char_p),
            'sqlite3_libversion': ([], C.c_char_p),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        self.db = C.c_void_p()
        assert self.lib.sqlite3_open_v2(str(path).encode(), C.byref(self.db), 1, None) == 0

    def prepare(self, sql):
        statement = C.c_void_p()
        status = self.lib.sqlite3_prepare_v2(self.db, sql.encode(), -1, C.byref(statement), None)
        assert status == 0, self.lib.sqlite3_errmsg(self.db)
        return statement

    def plan(self, sql):
        statement, result = self.prepare('EXPLAIN QUERY PLAN ' + sql), []
        try:
            while True:
                status = self.lib.sqlite3_step(statement)
                if status == 101:
                    return result
                assert status == 100
                result.append(self.lib.sqlite3_column_text(statement, 3).decode())
        finally:
            self.lib.sqlite3_finalize(statement)

    def measure(self, sql, expected):
        statement = self.prepare(sql)
        milliseconds, steps = [], []
        try:
            for iteration in range(8):
                assert self.lib.sqlite3_reset(statement) == 0
                self.lib.sqlite3_stmt_status(statement, 4, 1)  # SQLITE_STMTSTATUS_VM_STEP
                start = time.perf_counter_ns()
                assert self.lib.sqlite3_step(statement) == 100
                result = self.lib.sqlite3_column_int64(statement, 0)
                assert self.lib.sqlite3_step(statement) == 101
                elapsed = (time.perf_counter_ns() - start) / 1_000_000
                assert result == expected, (result, expected)
                if iteration:  # one unreported warm-up; seven measured repetitions
                    milliseconds.append(elapsed)
                    steps.append(self.lib.sqlite3_stmt_status(statement, 4, 0))
        finally:
            self.lib.sqlite3_finalize(statement)
        return {'result': expected, 'samplesMs': milliseconds, 'medianMs': statistics.median(milliseconds),
                'minMs': min(milliseconds), 'maxMs': max(milliseconds), 'vmSteps': steps,
                'queryPlan': self.plan(sql)}

    def close(self):
        assert self.lib.sqlite3_close(self.db) == 0


def main():
    run = ROOT / '.local/research/event-query-cost' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    source = ROOT / 'src/World.Server/bin/Debug/net10.0/runtimes/linux-x64/native/libe_sqlite3.so'
    library = run / 'libe_sqlite3.so'
    shutil.copyfile(source, library)
    base, indexed = run / 'range-index.db', run / 'actor-index.db'
    with sqlite3.connect(base) as db:
        db.executescript('''
            CREATE TABLE worlds(id TEXT PRIMARY KEY);
            INSERT INTO worlds VALUES('foundation-01');
            CREATE TABLE events(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, world_id TEXT NOT NULL REFERENCES worlds(id),
              state_version INTEGER NOT NULL, event_json TEXT NOT NULL, UNIQUE(world_id,state_version));
        ''')
        def records():
            for i in range(1, ROWS + 1):
                event = {'seq': i, 'stateVersion': i, 'commandId': 'synthetic_' + str(i),
                         'actorId': 'a1', 'type': 'walked', 'position': [5, 7], 'blocked': False}
                yield ('foundation-01', i, json.dumps(event, separators=(',', ':')))
        db.executemany('INSERT INTO events(world_id,state_version,event_json) VALUES(?,?,?)', records())
        db.commit()
    shutil.copyfile(base, indexed)
    with sqlite3.connect(indexed) as db:
        db.execute("CREATE INDEX research_events_actor_version ON events(world_id,json_extract(event_json,'$.actorId'),state_version)")
    print('200000 synthetic events created in isolated SQL fixtures', flush=True)
    modes = []
    version = None
    for label, path in [('existing-world-version-index', base), ('candidate-actor-expression-index', indexed)]:
        native = NativeSqlite(library, path)
        try:
            version = native.lib.sqlite3_libversion().decode()
            cases = []
            for suffix in [0, 20, 2_000, ROWS]:
                anchor = ROWS - suffix
                sql = f"SELECT EXISTS(SELECT 1 FROM events WHERE world_id='foundation-01' AND state_version>{anchor} AND json_extract(event_json,'$.actorId')='a2')"
                cases.append({'eventsAfterAnchor': suffix, 'queriedActor': 'a2', 'sql': sql, **native.measure(sql, 0)})
            sql = "SELECT EXISTS(SELECT 1 FROM events WHERE world_id='foundation-01' AND state_version>0 AND json_extract(event_json,'$.actorId')='a1')"
            cases.append({'eventsAfterAnchor': ROWS, 'queriedActor': 'a1', 'sql': sql, **native.measure(sql, 1)})
            modes.append({'mode': label, 'databaseBytes': path.stat().st_size, 'cases': cases})
        finally:
            native.close()
    audits = []
    for path in [base, indexed]:
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
            digest = hashlib.sha256()
            for (event,) in db.execute('SELECT event_json FROM events ORDER BY seq'):
                digest.update(event.encode())
                digest.update(b'\n')
            audits.append({'file': path.name, 'eventRows': db.execute('SELECT count(*) FROM events').fetchone()[0],
                           'eventContentSha256': digest.hexdigest(), 'integrity': db.execute('PRAGMA integrity_check').fetchone()[0]})
    assert audits[0]['eventContentSha256'] == audits[1]['eventContentSha256']
    assert all(a['eventRows'] == ROWS and a['integrity'] == 'ok' for a in audits)
    report = {'recordedAtUtc': datetime.now(timezone.utc).isoformat(), 'kind': 'synthetic-sql-read-query-microbenchmark',
              'actualWorldCommands': 0, 'actualModelCalls': 0, 'serverExecuted': False,
              'candidateRuleExecuted': False, 'fixtureRows': ROWS,
              'dataset': 'Every synthetic event belongs to a1; a2 has no commits after the observation anchor.',
              'measuredNativeSqliteVersion': version, 'nativeLibrarySha256': hashlib.sha256(library.read_bytes()).hexdigest(),
              'sourceLibrary': str(source.relative_to(ROOT)), 'fixtureWriterPythonSqliteVersion': sqlite3.sqlite_version,
              'timingScope': 'prepared SELECT only, one warm-up and seven repetitions, read-only native connections; not HTTP/transaction/lock-wait or cold-cache performance',
              'indexExtraBytes': indexed.stat().st_size - base.stat().st_size, 'modes': modes, 'audits': audits}
    output = run / 'results.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', output)
    for mode in modes:
        print(mode['mode'], [(c['eventsAfterAnchor'], c['queriedActor'], round(c['medianMs'], 6), c['vmSteps'][0]) for c in mode['cases']])
    print('Extra index bytes:', report['indexExtraBytes'])


if __name__ == '__main__':
    main()
