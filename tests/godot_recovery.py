#!/usr/bin/env python3
"""Recovery format regression using independent Godot processes. No model calls."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / '.local/godot-recovery' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
GODOT = os.environ.get('GODOT_BIN') or str(ROOT / '.local/tools/godot/Godot_v4.7.2-stable_linux.x86_64')
if not Path(GODOT).is_file():
    GODOT = shutil.which('godot') or shutil.which('godot4')


def launch(name, mode, state, **extra):
    output = RUN / (name + '.json')
    env = {**os.environ, 'RECOVERY_STATE': str(state), 'RECOVERY_MODE': mode,
           'RECOVERY_OUTPUT': str(output), **extra}
    log_path = RUN / (name + '.log')
    log = log_path.open('w')
    process = subprocess.Popen([GODOT, '--headless', '--path', str(ROOT / 'clients/godot'),
                                '--script', str(ROOT / 'tests/godot/pending_store.gd')],
                               cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    return name, process, log, log_path, output


def finish(job):
    name, process, log, log_path, output = job
    try:
        code = process.wait(timeout=30)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        log.close()
    text = log_path.read_text()
    assert code == 0 and 'ERROR:' not in text, name + ': ' + text[-3000:]
    report = json.loads(output.read_text())
    assert report['passed'], report
    print(name + ': PASS', flush=True)
    return {'name': name, **report}


def main():
    if not GODOT:
        raise SystemExit('Set GODOT_BIN to Godot 4.7.2.')
    RUN.mkdir(parents=True)
    jobs = []
    results = []
    try:
        for writer in ('first', 'second'):
            jobs.append(launch(writer, 'writer', RUN / 'shared.json', RECOVERY_WRITER=writer,
                               RECOVERY_READY=str(RUN / (writer + '.ready')), RECOVERY_GO=str(RUN / 'go')))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not all((RUN / (w + '.ready')).exists() for w in ('first', 'second')):
            time.sleep(0.02)
        assert all((RUN / (w + '.ready')).exists() for w in ('first', 'second')), 'writers did not reach barrier'
        (RUN / 'go').touch()
        results += [finish(job) for job in jobs]
        results.append(finish(launch('verify-concurrent', 'verify-concurrent', RUN / 'shared.json')))
        for mode in ('legacy', 'conflict', 'corrupt'):
            results.append(finish(launch(mode, mode, RUN / (mode + '-pending.json'))))
    finally:
        for _, process, log, _, _ in jobs:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            if not log.closed:
                log.close()
    summary = {'recordedAtUtc': datetime.now(timezone.utc).isoformat(), 'passed': True,
               'actualModelCalls': 0, 'results': results}
    (RUN / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('Evidence:', RUN / 'results.json')


if __name__ == '__main__':
    main()
