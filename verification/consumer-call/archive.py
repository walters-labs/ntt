#!/usr/bin/env python3
"""Archive the accepted consumer-call checkpoint and its source bindings."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'target/verification-consumer-call'
SNAPSHOT = 'source/2026-11-17-consumer-call/'


def main():
    subprocess.run([sys.executable, str(Path(__file__).with_name('run.py')), '--check', '--negative-controls'], check=True)
    report = json.loads((TARGET / 'consumer-call-report.json').read_text())
    build = json.loads((TARGET / 'build-report.json').read_text())
    recipe = json.loads((Path(__file__).with_name('recipe.json')).read_text())
    files = {}
    def add(name):
        path = (ROOT / name).resolve()
        relative = str(path.relative_to(ROOT))
        member = relative if relative.startswith('target/') else SNAPSHOT + relative
        files[member] = path.read_bytes()
    for name in report['source_sha256']:
        add(name)
    for path in (ROOT / 'verification').rglob('*.md'):
        add(path)
    for name in build['source_sha256']:
        add(name)
    for name in [build['mir'], build['rebuilt_mir'], build['artifact_log']]:
        add(name)
    for name in ['consumer-call-report.json', 'build-report.json', 'negative-controls.json', 'toolchain.json']:
        add(TARGET / name)
    for path in TARGET.glob('*-check.json'):
        add(path)
    for name in recipe['imports']:
        add(TARGET / (name + '.saw'))
    for node in report['nodes']:
        for name in [node['report'], node['log'], *node['dependencies'], *node['exports']]:
            add(name)
        add(TARGET / 'proof-records' / (node['report_sha256'] + '.json'))
    # These definitions are imported by the mathematical link and may not be
    # reported as SAW script includes.
    for name in ['verification/consumer-composition/ConsumerProduct.cry',
                 'verification/ScalarSpec.cry', 'verification/AdapterSpec.cry']:
        add(name)
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    destination = ROOT / 'verification/results/2026-11-17-consumer-call.tar.gz'
    if destination.exists():
        raise ValueError('Refusing to overwrite an immutable result archive')
    with destination.open('xb') as output, gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as saved:
            for name, data in sorted(files.items()):
                item = tarfile.TarInfo(name)
                item.size = len(data)
                item.mode = 0o644
                saved.addfile(item, io.BytesIO(data))
    with tarfile.open(destination) as saved:
        actual = {m.name: saved.extractfile(m).read() for m in saved if m.isfile()}
    if (set(actual) != set(files) or any(hashlib.sha256(actual[n]).hexdigest() != h for n, h in manifest.items())):
        raise ValueError('Archive failed its complete manifest check')
    print(f'Archived {len(manifest)} files, {destination.stat().st_size} bytes: {destination}')


if __name__ == '__main__':
    main()
