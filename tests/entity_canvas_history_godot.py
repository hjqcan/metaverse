#!/usr/bin/env python3
"""Native UI checks using a recorded observation and labelled synthetic UI inputs.

No world client, server, database, network fixture, or model is started. The
unchanged product panel and platform view run in a small disposable Godot project.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/entity-canvas-observation.json'
FIXTURE_SHA = '575c2f6b9482621d3d74c82e80f2a1705c669fe754e69565228232d943fd4778'
SCRIPTS = ('entity_canvas_panel.gd', 'entity_canvas_evidence.gd',
           'entity_note_evidence.gd', 'world_view.gd', 'river.gdshader')
GROUPS = (
    'original_two_creations', 'draft_and_stale_revision',
    'pending_and_non_author_viewer', 'blank_and_current_picture',
    'recent_window', 'identity_changes', 'unknown_capability',
    'current_editing_signals',
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def live_group(pgid):
    """Only inspect members of the child process group owned by this run."""
    members = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == pgid and fields[0] != 'Z':
                members.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
            continue
    return members


def stop_group(pgid):
    for sig, seconds in ((signal.SIGTERM, 3), (signal.SIGKILL, 2)):
        if not live_group(pgid):
            return True
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return True
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if not live_group(pgid):
                return True
            time.sleep(0.05)
    return not live_group(pgid)


def run_process(argv, path, env, timeout, runs):
    with path.open('w') as log:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        record = {'log': path.name, 'pid': process.pid, 'exitCode': None,
                  'timedOut': False, 'processGroupStopped': False}
        runs.append(record)
        try:
            record['exitCode'] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            record['timedOut'] = True
        finally:
            record['processGroupStopped'] = stop_group(process.pid)
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            record['exitCode'] = process.returncode
    output = path.read_text()
    if record['timedOut'] or record['exitCode'] != 0 or not record['processGroupStopped']:
        raise RuntimeError(f'{path.name}: {record}\n{output[-6000:]}')
    if 'SCRIPT ERROR:' in output or 'ERROR:' in output:
        raise RuntimeError(f'{path.name}: Godot reported an error\n{output[-6000:]}')


def main():
    run = ROOT / '.local/iter0026' / (
        'worker-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    temporary = run / 'temporary'
    stage = temporary / 'project'
    stage.mkdir(parents=True)
    paths = [*(ROOT / 'clients/godot' / name for name in SCRIPTS),
             ROOT / 'clients/godot/project.godot', Path(__file__).resolve(),
             ROOT / 'tests/godot/entity_canvas_history.gd', FIXTURE]
    before = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    runs = []
    result = {
        'passed': False, 'validationLevel': 'builder-fixture-driven-native-ui',
        'actualModelCalls': 0, 'worldIoMode': 'no-world-client-or-http',
        'worldServicesStarted': 0, 'databasesCreated': 0, 'runtimeBinariesCopied': 0,
        'fixture': str(FIXTURE.relative_to(ROOT)), 'fixtureSha256': before[str(FIXTURE.relative_to(ROOT))],
        'sourceHashesBefore': before, 'processes': runs,
        'scope': 'Actual Godot mouse input on unchanged product controls and platform view; recorded original observation and labelled synthetic boundary fixtures. No live world acceptance.',
    }
    try:
        if digest(FIXTURE) != FIXTURE_SHA:
            raise ValueError('Recorded original observation differs from its reviewed SHA-256')
        binary = os.environ.get('GODOT_BIN') or str(ROOT / '.local/tools/godot/Godot_v4.7.2-stable_linux.x86_64')
        if not Path(binary).is_file():
            binary = shutil.which('godot') or shutil.which('godot4')
        if not binary or not shutil.which('xvfb-run'):
            raise RuntimeError('Set GODOT_BIN to Godot 4.7.2 and provide xvfb-run')
        version = subprocess.run([binary, '--headless', '--version'], capture_output=True,
                                 text=True, timeout=10, check=True).stdout.strip()
        result['godotVersion'] = version
        if not version.startswith('4.7.'):
            raise RuntimeError('This project pins Godot 4.7: ' + version)
        expected_panel = os.environ.get('ENTITY_CANVAS_PANEL_SHA')
        if expected_panel and before['clients/godot/entity_canvas_panel.gd'] != expected_panel:
            raise ValueError('Panel differs from the coordinator-frozen source')
        for name in SCRIPTS:
            shutil.copyfile(ROOT / 'clients/godot' / name, stage / name)
        shutil.copyfile(ROOT / 'tests/godot/entity_canvas_history.gd', stage / 'test_runner.gd')
        shutil.copyfile(FIXTURE, stage / 'observation.json')
        (stage / 'project.godot').write_text('''config_version=5
[application]
config/name="ITER-0026 native fixture checks"
config/features=PackedStringArray("4.7", "GL Compatibility")
[display]
window/size/viewport_width=1280
window/size/viewport_height=900
window/size/window_width_override=1280
window/size/window_height_override=900
window/subwindows/embed_subwindows=true
[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
environment/defaults/default_clear_color=Color(0.055, 0.09, 0.105, 1)
''')
        env = dict(os.environ)
        for key, directory in (('XDG_DATA_HOME', 'data'), ('XDG_CONFIG_HOME', 'config'),
                               ('XDG_CACHE_HOME', 'cache'), ('TMPDIR', 'tmp')):
            target = temporary / directory
            target.mkdir(mode=0o700)
            env[key] = str(target)
        env.update({'GODOT_TEST_OUTPUT': str(run / 'ui.json'),
                    'GODOT_TEST_SCREENSHOTS': str(run),
                    'GODOT_TEST_FIXTURE': str(stage / 'observation.json')})
        run_process([binary, '--headless', '--path', str(stage), '--editor', '--import'],
                    run / 'import.log', env, 40, runs)
        run_process(['xvfb-run', '-a', '-e', str(run / 'xvfb.log'), '-s', '-screen 0 1280x900x24', binary,
                     '--path', str(stage), '--script', 'res://test_runner.gd',
                     '--resolution', '1280x900', '--audio-driver', 'Dummy'],
                    run / 'ui.log', env, 150, runs)
        ui = json.loads((run / 'ui.json').read_text())
        result['ui'] = ui
        names = [group['name'] for group in ui.get('groups', [])]
        if names != list(GROUPS) or not ui.get('passed') or not ui.get('checks'):
            raise AssertionError('The expected eight UI groups did not all complete')
        if not all(check['passed'] for check in ui['checks']):
            raise AssertionError('A native UI assertion failed')
        result['passed'] = True
    except Exception:
        result['failure'] = traceback.format_exc()
        print(result['failure'], file=sys.stderr)
        if (run / 'ui.json').exists():
            result['ui'] = json.loads((run / 'ui.json').read_text())
    finally:
        after = {str(p.relative_to(ROOT)): digest(p) for p in paths}
        result['sourceHashesAfter'] = after
        result['sourceUnchanged'] = before == after
        result['allStartedProcessesStopped'] = all(p['processGroupStopped'] for p in runs)
        result['temporaryBytesRemoved'] = sum(p.stat().st_size for p in temporary.rglob('*') if p.is_file())
        shutil.rmtree(temporary)
        result['temporaryRemoved'] = not temporary.exists()
        result['passed'] = bool(result['passed'] and result['sourceUnchanged']
                                and result['allStartedProcessesStopped'] and result['temporaryRemoved'])
        result['groups'] = len(result.get('ui', {}).get('groups', []))
        result['assertions'] = len(result.get('ui', {}).get('checks', []))
        (run / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Evidence:', run / 'results.json', flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
