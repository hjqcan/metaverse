#!/usr/bin/env python3
"""Build once and run isolated acceptance suites; never invoke live models."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
HTTP = ('foundation', 'passage', 'resident_mission', 'activities', 'postcards', 'mosaic', 'consent', 'inbox', 'entry_guide', 'wilderness', 'wilderness_mission', 'continuous', 'continuous_mission', 'world_instance', 'construction_mission', 'instance_mission', 'actor_state', 'actor_mission', 'material_transfer', 'transfer_mission', 'material_access', 'material_access_time', 'material_access_mission', 'entity_notes', 'entity_notes_mission', 'continuous_material', 'continuous_material_mission', 'entity_canvas', 'entity_canvas_mission')
BROWSER = ('foundation', 'passage', 'resident', 'activities', 'postcards', 'mosaic', 'consent', 'inbox', 'consent-experience', 'entry', 'wilderness', 'wilderness-resident', 'continuous-resident', 'construction-resident', 'actor-resident', 'transfer-resident', 'material-resident', 'entity-note-resident', 'continuous-material-resident', 'entity-canvas-resident')


def cleanup_binaries(evidence):
    """Discard finished run's reproducible binaries, retaining worlds and evidence."""
    if not evidence or not Path('/proc').is_dir():
        return []
    directory = (ROOT / evidence).resolve().parent
    if not directory.is_relative_to(ROOT / '.local'):
        return []
    references = []
    for process in Path('/proc').glob('[0-9]*'):
        try:
            references.append((process / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace'))
            references.append((process / 'maps').read_text())
        except OSError:
            continue
    removed = []
    for marker in list(directory.rglob('World.Server.deps.json')):
        binary = marker.parent
        if any(str(binary) in ref or str(binary.relative_to(ROOT)) in ref for ref in references):
            continue
        paths = [p for p in binary.iterdir() if p.is_file() and
                 (p.suffix in ('.dll', '.pdb', '.xml') or p.name in
                  ('World.Server', 'World.Server.deps.json', 'World.Server.runtimeconfig.json', 'World.Server.staticwebassets.endpoints.json'))]
        if (binary / 'runtimes').is_dir():
            paths.append(binary / 'runtimes')
        for path in paths:
            size = sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.is_dir() else path.stat().st_size
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append({'path': str(path.relative_to(ROOT)), 'logicalBytes': size})
    return removed


def evidence_path(lines):
    for line in reversed(lines):
        if line.lower().startswith(('evidence:', 'browser evidence:')):
            path = Path(line.split(':', 1)[1].strip())
            if path.is_dir():
                path /= 'results.json'
            return str(path.relative_to(ROOT))
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('all', 'http', 'browser'), default='all')
    args = parser.parse_args()
    recorded = datetime.now(timezone.utc)
    output = ROOT / '.local/checks' / (recorded.strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    output.mkdir(parents=True, mode=0o700)

    def run(item):
        name, command = item
        log = output / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        lines = log.read_text().splitlines()
        print(f'{name}: {"PASS" if result.returncode == 0 else "FAIL"}', flush=True)
        if result.returncode:
            print('\n'.join(lines[-25:]), flush=True)
        evidence = evidence_path(lines)
        return {'name': name, 'exitCode': result.returncode, 'log': str(log.relative_to(ROOT)),
                'evidence': evidence, 'removedTemporaryBinaries': cleanup_binaries(evidence)}

    results = []
    for name, command in (
        ('restore', ['dotnet', 'restore', 'src/World.Server/World.Server.csproj', '--locked-mode']),
        ('build', ['dotnet', 'build', 'src/World.Server/World.Server.csproj', '--no-restore']),
    ):
        results.append(run((name, command)))
        if results[-1]['exitCode']:
            break
    else:
        suites = []
        if args.suite in ('all', 'http'):
            suites += [(f'http-{name}', [sys.executable, f'tests/{name}_api.py']) for name in HTTP]
        if args.suite in ('all', 'browser'):
            suites += [(f'browser-{name}', ['node', f'tests/browser/{name}.mjs']) for name in BROWSER]
        with ThreadPoolExecutor(max_workers=3) as pool:
            results += list(pool.map(run, suites))
    passed = all(result['exitCode'] == 0 for result in results)
    summary = {'recordedAtUtc': recorded.isoformat(), 'suite': args.suite, 'passed': passed,
               'actualModelCalls': 0, 'results': results}
    (output / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('Evidence:', output / 'results.json')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
