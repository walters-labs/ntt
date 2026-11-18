#!/usr/bin/env python3
"""Check clean release packages against real registry dependencies and saved proofs.

This command never uploads. Publication is a separate, explicit Cargo action.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'target/verification-publication'
VERSIONS = {'ntt': '0.1.10', 'ring-lwe': '0.1.9', 'module-lwe': '0.1.6'}
CHECKOUTS = {n: ROOT.parent / ('ntt-release' if n == 'ntt' else n) for n in VERSIONS}
REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def run(folder, label, command, extra_env=None):
    output, error = folder / (label + '.stdout'), folder / (label + '.stderr')
    output.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CARGO_NET_OFFLINE='true')
    env.update(extra_env or {})
    print('Running ' + label, flush=True)
    start = time.monotonic()
    with output.open('w') as stdout, error.open('w') as stderr:
        process = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, timeout=900)
    if process.returncode:
        print(output.read_text()[-4000:] + error.read_text()[-6000:])
        raise ValueError('Failed publication check: ' + label)
    return {'label': label, 'command': command, 'environment': extra_env or {},
            'stdout': str(output), 'stdout_sha256': sha(output),
            'stderr': str(error), 'stderr_sha256': sha(error),
            'seconds': round(time.monotonic() - start, 3), 'exit_code': process.returncode}


def metadata(folder, manifest, jobs):
    job = run(folder, 'metadata-' + manifest.parent.name,
              ['cargo', 'metadata', '--locked', '--offline', '--format-version', '1', '--manifest-path', str(manifest)])
    jobs.append(job)
    return json.loads(Path(job['stdout']).read_text())


def receipt(name):
    path = OUT / 'receipts' / (name + '.json')
    result = json.loads(path.read_text())
    if result['version'] != VERSIONS[name] or result['status'] != 'published':
        raise ValueError('Missing published prerequisite: ' + name)
    return result


def dependencies(name, manifest, meta):
    wanted = [] if name == 'ntt' else ['ntt'] if name == 'ring-lwe' else ['ntt', 'ring-lwe']
    lock = tomllib.loads((manifest.parent / 'Cargo.lock').read_text())
    resolved = {}
    for dep in wanted:
        packages = [p for p in meta['packages'] if p['name'] == dep]
        entries = [p for p in lock['package'] if p['name'] == dep]
        expected = receipt(dep)
        if (len(packages) != 1 or len(entries) != 1 or packages[0]['version'] != VERSIONS[dep] or
                packages[0]['source'] != REGISTRY or entries[0].get('source') != REGISTRY or
                entries[0].get('checksum') != expected['checksum']):
            raise ValueError('Dependency is not the exact verified registry package: ' + dep)
        resolved[dep] = {'version': VERSIONS[dep], 'checksum': expected['checksum'],
                         'source': packages[0]['source'], 'manifest': packages[0]['manifest_path']}
    return resolved


def load_identity():
    sys.path.insert(0, str(ROOT / 'verification/consumer-call'))
    from mir_identity import Identity
    return Identity


def compare(old, new, names):
    identity = load_identity()(old, new)
    def find(module, suffix):
        matches = [f['name'] for f in module['fns'] if f['name'].endswith('::' + suffix)]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous MIR root: ' + suffix)
        return matches[0]
    return identity.rooted([(find(identity.modules[0], n), find(identity.modules[1], n)) for n in names])


def check_package(name):
    checkout, version = CHECKOUTS[name], VERSIONS[name]
    if git(checkout, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Commit the release source before packaging: ' + name)
    if tomllib.loads((checkout / 'Cargo.toml').read_text())['package']['version'] != version:
        raise ValueError('Unexpected release version')
    subprocess.run([sys.executable, str(ROOT / 'verification/consumer-call/run.py'), '--check', '--negative-controls'],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    commit = git(checkout, 'rev-parse', 'HEAD')
    folder = OUT / 'checks' / (name + '-' + version) / commit
    folder.mkdir(parents=True, exist_ok=True)
    jobs = []
    meta = metadata(folder, checkout / 'Cargo.toml', jobs)
    resolved = dependencies(name, checkout / 'Cargo.toml', meta)
    build = OUT / 'build' / name
    jobs.append(run(folder, 'package', ['cargo', 'package', '--locked', '--offline', '--manifest-path',
                                     str(checkout / 'Cargo.toml'), '--target-dir', str(build)]))
    crate = build / 'package' / f'{name}-{version}.crate'
    checksum = sha(crate)
    retained = OUT / 'artifacts' / (checksum + '.crate')
    retained.parent.mkdir(exist_ok=True)
    if not retained.exists():
        shutil.copyfile(crate, retained)
    extracted = OUT / 'extracted' / checksum
    if not extracted.exists():
        extracted.mkdir(parents=True)
        with tarfile.open(retained) as saved:
            saved.extractall(extracted, filter='data')
    package = extracted / f'{name}-{version}'
    vcs = json.loads((package / '.cargo_vcs_info.json').read_text())
    if vcs['git']['sha1'] != commit or vcs['git'].get('dirty', False):
        raise ValueError('Package is not bound to the clean release commit')
    manifest = tomllib.loads((package / 'Cargo.toml').read_text())
    for dep in ([] if name == 'ntt' else ['ntt', 'polynomial-ring'] if name == 'ring-lwe' else ['ntt', 'ring-lwe', 'polynomial-ring']):
        expected = '=0.5.1' if dep == 'polynomial-ring' else '=' + VERSIONS[dep]
        entry = manifest['dependencies'][dep]
        if entry['version'] != expected or set(entry) & {'path', 'git', 'rev', 'branch'}:
            raise ValueError('Unexpected packaged dependency requirement')
    for path in package.rglob('*.rs'):
        if sha(path) != sha(checkout / path.relative_to(package)):
            raise ValueError('Packaged Rust differs from the release checkout')
    package_meta = metadata(folder, package / 'Cargo.toml', jobs)
    if dependencies(name, package / 'Cargo.toml', package_meta) != resolved:
        raise ValueError('Package and checkout resolve different prerequisite sources')
    command = ['cargo', 'test', '--locked', '--offline', '--manifest-path', str(package / 'Cargo.toml'),
               '--target-dir', str(OUT / 'native')]
    jobs.append(run(folder, 'tests', command))
    if name == 'ntt':
        jobs.append(run(folder, 'tests-release', command + ['--release']))
        jobs.append(run(folder, 'clippy', ['cargo', 'clippy', '--locked', '--offline', '--all-targets', '--manifest-path',
                    str(package / 'Cargo.toml'), '--target-dir', str(OUT / 'native'), '--', '-D', 'warnings']))
        mir_manifest, target_name = package / 'Cargo.toml', 'ntt'
        flags = f'--remap-path-prefix={package}/src/=src/'
    else:
        jobs.append(run(folder, 'benches', ['cargo', 'check', '--locked', '--offline', '--benches', '--manifest-path',
                    str(package / 'Cargo.toml'), '--target-dir', str(OUT / 'native')]))
        harness = folder / 'harness'
        local_name = 'ring-lwe' if name == 'ring-lwe' else 'module-lwe'
        text = f'''[package]
name = "ntt-consumer-call-proof"
version = "0.0.0"
edition = "2021"
publish = false
[lib]
path = {json.dumps(str(ROOT / 'verification/consumer-call/harness.rs'))}
[dependencies]
polynomial-ring = "=0.5.1"
{local_name} = {{ path = {json.dumps(str(package))} }}
'''
        if name == 'module-lwe':
            text += 'ring-lwe = "=0.1.9"\n'
        write(harness / 'Cargo.toml', text)
        jobs.append(run(folder, 'harness-lock', ['cargo', '+nightly-2026-03-21', 'generate-lockfile', '--offline',
                                             '--manifest-path', str(harness / 'Cargo.toml')]))
        mir_manifest, target_name = harness / 'Cargo.toml', 'ntt_consumer_call_proof'
        ntt_root = Path(resolved['ntt']['manifest']).parent
        ring_root = package if name == 'ring-lwe' else Path(resolved['ring-lwe']['manifest']).parent
        old_ring = ROOT / 'target/verification-polynomial-boundary/checkouts/ring-lwe-555b26a579779f265bce237d9c2d3d5c91090372'
        flags = f'--remap-path-prefix={ntt_root}/src/=src/ --remap-path-prefix={ring_root}/src/={old_ring}/src/'
    job = run(folder, 'mir', ['cargo', '+nightly-2026-03-21', 'saw-build', '--manifest-path', str(mir_manifest),
                            '--lib', '--target-dir', str(OUT / 'mir-build' / name), '--message-format=json'], {'RUSTFLAGS': flags})
    jobs.append(job)
    events = [json.loads(s) for s in Path(job['stdout']).read_text().splitlines()]
    paths = [Path(e['executable'] + '.linked-mir.json') for e in events if e.get('reason') == 'compiler-artifact'
             and e.get('target', {}).get('name') == target_name and e.get('executable')]
    if len(paths) != 1:
        raise ValueError('Expected one linked MIR artifact')
    mir = OUT / 'artifacts' / (sha(paths[0]) + '.linked-mir.json')
    if not mir.exists():
        shutil.copyfile(paths[0], mir)
    recipe = json.loads((ROOT / 'verification/consumer-call/recipe.json').read_text())
    if name == 'ntt':
        roots = ['ntt', 'intt', 'polymul_ntt']
        identities = {key: compare(ROOT / recipe[key], mir, roots) for key in ('old_1024_mir', 'old_2048_mir')}
    else:
        identities = {'consumer_entries': compare(ROOT / recipe['current_mir'], mir,
                      ['multiply_1024_12289', 'multiply_2048_12289', 'multiply_2048_151019521'])}
    evidence = {'status': 'passed', 'crate': name, 'version': version, 'commit': commit,
                'package': str(retained), 'checksum': checksum, 'dependencies': resolved,
                'mir': str(mir), 'mir_sha256': sha(mir), 'mir_identity': identities, 'jobs': jobs,
                'prior_proof_sha256': sha(ROOT / 'target/verification-consumer-call/consumer-call-report.json'),
                'checker_sha256': sha(Path(__file__)),
                'release_files': {str(p): sha(p) for p in checkout.rglob('*') if p.is_file()
                                  and not {'.git', 'target', '__pycache__'}.intersection(p.relative_to(checkout).parts)}}
    write(folder / 'check.json', json.dumps(evidence, indent=2) + '\n')
    write(OUT / (name + '-checked.json'), json.dumps(evidence, indent=2) + '\n')
    print(f'Checked {name} {version}: {checksum}')


def record_index(name, index):
    checked = json.loads((OUT / (name + '-checked.json')).read_text())
    entries = [json.loads(s) for s in index.read_text().splitlines()]
    entries = [p for p in entries if p['vers'] == VERSIONS[name]]
    if len(entries) != 1 or entries[0]['yanked'] or entries[0]['cksum'] != checked['checksum']:
        raise ValueError('Registry does not contain the exact checked package')
    checked.update(status='published', index=str(index), index_sha256=sha(index))
    write(OUT / 'receipts' / (name + '.json'), json.dumps(checked, indent=2) + '\n')
    print(f'Confirmed published {name} {VERSIONS[name]} with the checked package checksum')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('crate', choices=VERSIONS)
    parser.add_argument('--record-index', type=Path)
    args = parser.parse_args()
    if args.record_index:
        record_index(args.crate, args.record_index)
    else:
        check_package(args.crate)


if __name__ == '__main__':
    main()
