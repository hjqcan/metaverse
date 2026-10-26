#!/usr/bin/env python3
"""Build once and run isolated acceptance suites; never invoke live models."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
HTTP = ('foundation', 'passage', 'resident_mission', 'activities', 'postcards', 'mosaic', 'consent', 'inbox', 'entry_guide')
BROWSER = ('foundation', 'passage', 'resident', 'activities', 'postcards', 'mosaic', 'consent', 'inbox', 'entry')


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
        return {'name': name, 'exitCode': result.returncode, 'log': str(log.relative_to(ROOT)),
                'evidence': evidence_path(lines)}

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
