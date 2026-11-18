#!/usr/bin/env python3
"""Retain exact prepared releases and verification evidence, without binaries."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'target/verification-consumer-release'


def main():
    subprocess.run([sys.executable, str(Path(__file__).with_name('run.py')), '--from-checkouts', '--check'], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('apply.py')), '--check'], check=True)
    files = {}
    def add(name):
        path = (ROOT / name).resolve()
        if path.is_relative_to(ROOT):
            relative = str(path.relative_to(ROOT))
            member = relative if relative.startswith('target/') else 'source/2026-11-17-consumer-release/' + relative
        else:
            relative = path.relative_to(ROOT.parent)
            member = 'release-checkouts/' + str(relative)
        files[member] = path.read_bytes()
    for phase in (BASE, BASE / 'final'):
        report = json.loads((phase / 'release-report.json').read_text())
        add(phase / 'release-report.json')
        for key in ('source_sha256', 'artifact_sha256'):
            for name in report[key]:
                add(name)
        for job in report['jobs']:
            add(job['stdout'])
            add(job['stderr'])
    for name in ('application-plan.json', 'application-report.json', 'release-controls.json', 'registry-versions.json'):
        add(BASE / name)
    for path in BASE.glob('index-*.jsonl'):
        add(path)
    for path in (ROOT / 'verification').glob('*.md'):
        add(path)
    add(ROOT / 'verification/results/README.md')
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    destination = ROOT / 'verification/results/2026-11-17-consumer-release.tar.gz'
    with destination.open('xb') as output, gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as saved:
            for name, data in sorted(files.items()):
                item = tarfile.TarInfo(name)
                item.size, item.mode = len(data), 0o644
                saved.addfile(item, io.BytesIO(data))
    with tarfile.open(destination) as saved:
        actual = {m.name: saved.extractfile(m).read() for m in saved if m.isfile()}
    if set(actual) != set(files) or any(hashlib.sha256(actual[n]).hexdigest() != h for n, h in manifest.items()):
        raise ValueError('Archive manifest verification failed')
    print(f'Archived {len(manifest)} files, {destination.stat().st_size} bytes: {destination}')


if __name__ == '__main__':
    main()
