#!/usr/bin/env python3
"""Audit and retain the three exact published packages and their proof links."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import check as publication

ROOT, OUT = publication.ROOT, publication.OUT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='audit the existing immutable publication archive')
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT / 'verification/consumer-call/run.py'), '--check', '--negative-controls'],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    recipe = json.loads((ROOT / 'verification/consumer-call/recipe.json').read_text())
    files, summary = {}, {}
    def add(path):
        path = (ROOT / path).resolve()
        if path.is_relative_to(ROOT):
            relative = str(path.relative_to(ROOT))
            member = relative if relative.startswith('target/') else 'source/2026-11-17-publication/' + relative
        else:
            member = 'release-source/' + str(path.relative_to(ROOT.parent))
        files[member] = path.read_bytes()
    for name, version in publication.VERSIONS.items():
        receipt_path = OUT / 'receipts' / (name + '.json')
        record = json.loads(receipt_path.read_text())
        if (record['status'] != 'published' or record['version'] != version or
                publication.sha(record['package']) != record['checksum'] or
                publication.sha(record['mir']) != record['mir_sha256'] or
                publication.sha(record['index']) != record['index_sha256'] or
                publication.sha(Path(__file__).with_name('check.py')) != record['checker_sha256']):
            raise ValueError('Changed publication evidence: ' + name)
        rows = [json.loads(s) for s in Path(record['index']).read_text().splitlines()]
        row = next(r for r in rows if r['vers'] == version)
        if row['yanked'] or row['cksum'] != record['checksum']:
            raise ValueError('Published registry checksum differs from the proved artifact')
        for path, sha in record['release_files'].items():
            if publication.sha(path) != sha:
                raise ValueError('Changed released source: ' + path)
            # The tagged Git source and earlier result archives retain the
            # historical proof tarballs; avoid duplicating them in this bundle.
            if not path.endswith('.tar.gz'):
                add(path)
        for job in record['jobs']:
            if job['exit_code'] != 0:
                raise ValueError('Unsuccessful publication check')
            for stream in ('stdout', 'stderr'):
                if publication.sha(job[stream]) != job[stream + '_sha256']:
                    raise ValueError('Changed publication transcript')
                add(job[stream])
        roots = ['ntt', 'intt', 'polymul_ntt'] if name == 'ntt' else [
            'multiply_1024_12289', 'multiply_2048_12289', 'multiply_2048_151019521']
        for key, expected in record['mir_identity'].items():
            old = ROOT / recipe[key if name == 'ntt' else 'current_mir']
            if publication.compare(old, record['mir'], roots) != expected:
                raise ValueError('Published MIR does not match the successful proofs')
        publish_log = OUT / (name + '-publish.log')
        if f'Published {name} v{version} at registry' not in publish_log.read_text():
            raise ValueError('Missing successful Cargo publication transcript')
        tag = OUT / (name + '-tag.txt')
        if tag.read_text().split() != [record['commit'], f'refs/tags/v{version}^{{}}']:
            raise ValueError('Public Git tag does not identify the checked release commit')
        for path in [receipt_path, record['package'], record['mir'], record['index'], publish_log, tag]:
            add(path)
        summary[name] = {'version': version, 'checksum': record['checksum'], 'commit': record['commit'],
                         'url': f'https://crates.io/crates/{name}/{version}'}
    for path in Path(__file__).parent.iterdir():
        if path.is_file():
            add(path)
    for path in [ROOT / 'verification/README.md', ROOT / 'verification/roadmap.md', ROOT / 'verification/results/README.md']:
        add(path)
    files['publication-summary.json'] = (json.dumps(summary, indent=2) + '\n').encode()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    destination = ROOT / 'verification/results/2026-11-17-published.tar.gz'
    if not args.check:
        with destination.open('xb') as output, gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as archive:
                for name, data in sorted(files.items()):
                    item = tarfile.TarInfo(name)
                    item.size, item.mode = len(data), 0o644
                    archive.addfile(item, io.BytesIO(data))
    with tarfile.open(destination) as archive:
        actual = {m.name: archive.extractfile(m).read() for m in archive if m.isfile()}
    if set(actual) != set(files) or any(hashlib.sha256(actual[n]).hexdigest() != h for n, h in manifest.items()):
        raise ValueError('Publication archive failed its manifest check')
    print(f'Validated all published checksums, clean release sources, public tags, and MIR proof links; archived {len(manifest)} files')


if __name__ == '__main__':
    main()
