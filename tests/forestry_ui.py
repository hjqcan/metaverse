#!/usr/bin/env python3
"""Render recorded forestry facts through a private Godot project, without a world."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    fixture = Path(os.environ.get('FORESTRY_UI_FIXTURE', ROOT / 'tests/fixtures/forestry-ui.json')).resolve()
    binary = Path(os.environ.get('GODOT_BIN', ROOT / '.local/tools/godot/Godot_v4.7.2-stable_linux.x86_64')).resolve()
    if not fixture.is_file() or not binary.is_file():
        raise SystemExit('Provide an existing FORESTRY_UI_FIXTURE and GODOT_BIN')
    run = ROOT / '.local/iter0028/native-ui' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    stage = run / 'project'
    paths = [*sorted((ROOT / 'clients/godot').glob('*.gd')), ROOT / 'tests/godot/forestry_ui.gd', Path(__file__).resolve()]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    manifest = {'sourceSha256': hashes, 'fixtureSha256': digest(fixture), 'fixtureSource': str(fixture.relative_to(ROOT)) if fixture.is_relative_to(ROOT) else str(fixture)}
    (run / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(fixture, run / 'fixture.json')
    env = {k: v for k, v in os.environ.items() if not k.startswith('WORLD_')}
    private_dirs = []
    for key, name in [('XDG_DATA_HOME', 'data'), ('XDG_CONFIG_HOME', 'config'), ('XDG_CACHE_HOME', 'cache'), ('TMPDIR', 'tmp')]:
        path = run / name
        path.mkdir(mode=0o700)
        private_dirs.append(path)
        env[key] = str(path)
    env.update(GODOT_TEST_OUTPUT=str(run / 'ui.json'), GODOT_TEST_FIXTURE=str(run / 'fixture.json'),
               GODOT_TEST_SCREENSHOTS=str(run), WORLD_CLIENT_STATE=str(run / 'pending.json'), WORLD_URL='http://127.0.0.1:9')
    exit_code = 1
    try:
        shutil.copytree(ROOT / 'clients/godot', stage, ignore=shutil.ignore_patterns('.godot'))
        shutil.copyfile(ROOT / 'tests/godot/forestry_ui.gd', stage / 'test_runner.gd')
        with (run / 'import.log').open('w') as log:
            subprocess.run([str(binary), '--headless', '--path', str(stage), '--editor', '--import'],
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=40, check=True)
        with (run / 'ui.log').open('w') as log:
            process = subprocess.run(['xvfb-run', '-a', '-e', str(run / 'xvfb.log'), '-s', '-screen 0 1280x900x24',
                                      str(binary), '--path', str(stage), '--script', 'res://test_runner.gd',
                                      '--resolution', '1280x900', '--audio-driver', 'Dummy'],
                                     env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        result = json.loads((run / 'ui.json').read_text())
        unchanged = hashes == {str(p.relative_to(ROOT)): digest(p) for p in paths}
        exit_code = 0 if process.returncode == 0 and result['passed'] and unchanged else 1
        (run / 'results.json').write_text(json.dumps({'passed': exit_code == 0, 'sourceUnchanged': unchanged,
            'sourceSha256': hashes, 'fixtureSha256': digest(fixture), 'checks': result,
            'worldServiceStarted': False, 'actualModelCalls': 0,
            'scope': 'Recorded HTTP facts and explicit UI-only variants; not a new natural-world activity'}, indent=2) + '\n')
    finally:
        removed = []
        for path in [stage, *private_dirs]:
            if path.exists():
                size = sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
                shutil.rmtree(path)
                removed.append({'path': str(path.relative_to(ROOT)), 'logicalBytes': size})
        (run / 'cleanup.json').write_text(json.dumps({'removed': removed, 'originalClientProjectUntouched': True}, indent=2) + '\n')
        print('Evidence:', run / 'results.json')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
