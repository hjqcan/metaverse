#!/usr/bin/env python3
"""Run the native receipt-validator probe in an isolated minimal Godot project."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[4]


def main():
    run = ROOT / '.local/research/godot-execution-evidence' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    source = ROOT / 'clients/godot/command_evidence.gd'
    snapshot = source.read_bytes()
    (run / 'command_evidence.gd').write_bytes(snapshot)
    shutil.copyfile(Path(__file__).with_suffix('.gd'), run / 'probe.gd')
    (run / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="Research validator"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    executable = os.environ.get('GODOT_BIN', str(ROOT / '.local/tools/godot/Godot_v4.7.2-stable_linux.x86_64'))
    version = subprocess.check_output([executable, '--headless', '--version'], text=True, timeout=20).strip()
    env = {**os.environ, 'RESEARCH_OUTPUT': str(run / 'native-result.json')}
    with (run / 'import.log').open('w') as log:
        imported = subprocess.run([executable, '--headless', '--path', str(run), '--import'],
                                  stdout=log, stderr=subprocess.STDOUT, env=env, timeout=40)
    if imported.returncode:
        raise RuntimeError('Isolated Godot import failed; see ' + str(run / 'import.log'))
    with (run / 'native.log').open('w') as log:
        process = subprocess.run([executable, '--headless', '--path', str(run), '--script', 'res://probe.gd'],
                                 stdout=log, stderr=subprocess.STDOUT, env=env, timeout=20)
    report = json.loads((run / 'native-result.json').read_text())
    report.update(recordedAtUtc=datetime.now(timezone.utc).isoformat(), godotVersion=version,
                  sourceFile='clients/godot/command_evidence.gd', sourceSha256=hashlib.sha256(snapshot).hexdigest(),
                  sourceUnchangedDuringRun=source.read_bytes() == snapshot,
                  nativeExitCode=process.returncode, allExperimentProcessesStopped=True)
    assert len(report['checks']) == 6, report
    assert report['passed'] == (process.returncode == 0), report
    (run / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', run / 'results.json')
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks']),
                      'exitCode': process.returncode, 'sourceSha256': report['sourceSha256'],
                      'sourceUnchangedDuringRun': report['sourceUnchangedDuringRun']}, ensure_ascii=False))
    raise SystemExit(process.returncode)


if __name__ == '__main__':
    main()
