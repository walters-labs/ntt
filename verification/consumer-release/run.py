#!/usr/bin/env python3
"""Package, test, and bind prepared crate releases to the accepted MIR proof."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = ROOT / 'target/verification-consumer-release'
TARGET = BASE
INPUTS = BASE / 'staged'
VERSIONS = {'ntt': '0.1.10', 'ring-lwe': '0.1.9', 'module-lwe': '0.1.6'}
FOLDERS = {'ntt': 'ntt-release', 'ring-lwe': 'ring-lwe', 'module-lwe': 'module-lwe'}
JOBS = ['package-ntt', 'package-ring-lwe', 'package-module-lwe', 'test-ntt', 'test-ntt-release',
        'clippy-ntt', 'test-ring-lwe', 'benches-ring-lwe', 'test-module-lwe', 'benches-module-lwe',
        'harness-lock', 'release-mir']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    resolved = Path(path).resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(resolved)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def unpacked(name):
    return TARGET / 'unpacked' / f'{name}-{VERSIONS[name]}'


def patches(names, prepared=False):
    return [part for name in names for part in
            ['--config', f'patch.crates-io.{name}.path={json.dumps(str(INPUTS / FOLDERS[name] if prepared else unpacked(name)))}']]


def source_files(folder):
    return [p for p in folder.rglob('*') if p.is_file() and
            not {'target', '.git', '__pycache__'}.intersection(p.relative_to(folder).parts)]


def execute(name, command, env=None):
    started = time.monotonic()
    output = TARGET / 'logs' / (name + '.stdout')
    error = output.with_suffix('.stderr')
    output.parent.mkdir(parents=True, exist_ok=True)
    print('Running ' + name, flush=True)
    environment = dict(os.environ, CARGO_NET_OFFLINE='true')
    environment.update(env or {})
    with output.open('w') as stdout, error.open('w') as stderr:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr, timeout=600)
    if result.returncode:
        print(output.read_text()[-5000:])
        print(error.read_text()[-5000:])
        raise ValueError('Release check failed: ' + name)
    return {'name': name, 'command': command, 'environment': env or {}, 'status': 'passed',
            'seconds': round(time.monotonic() - started, 3),
            'stdout': relative(output), 'stdout_sha256': sha(output),
            'stderr': relative(error), 'stderr_sha256': sha(error)}


def crate_path(name):
    return TARGET / 'package-build/package' / f'{name}-{VERSIONS[name]}.crate'


def extract(name):
    destination = unpacked(name)
    if destination.exists():
        with tarfile.open(crate_path(name)) as saved:
            expected = {str(Path(m.name).relative_to(destination.name)): saved.extractfile(m).read()
                        for m in saved if m.isfile()}
        actual = {str(p.relative_to(destination)): p.read_bytes() for p in source_files(destination)}
        if actual != expected:
            changed = {n for n in actual.keys() | expected.keys() if actual.get(n) != expected.get(n)}
            if set(actual) != set(expected) or not changed <= {'Cargo.toml', 'Cargo.toml.orig', 'Cargo.lock', '.cargo_vcs_info.json'}:
                raise ValueError('Refusing to overwrite changed extracted Rust source: ' + str(destination))
            # Repackaging can change manifest/lock/VCS metadata. Fresh tests
            # and MIR checks below are required before accepting the new tar.
            for name in changed:
                (destination / name).write_bytes(expected[name])
        return
    with tarfile.open(crate_path(name)) as saved:
        saved.extractall(TARGET / 'unpacked', filter='data')


def package_contract(name):
    manifest = tomllib.loads((unpacked(name) / 'Cargo.toml').read_text())
    if manifest['package']['name'] != name or manifest['package']['version'] != VERSIONS[name]:
        raise ValueError('Wrong packaged crate version')
    expected = {} if name == 'ntt' else {'ntt': '=0.1.10', 'polynomial-ring': '=0.5.1'}
    if name == 'module-lwe':
        expected['ring-lwe'] = '=0.1.9'
    for dependency, version in expected.items():
        entry = manifest['dependencies'][dependency]
        if entry['version'] != version or {'path', 'git', 'branch', 'rev'} & set(entry):
            raise ValueError('Packaged dependency is not the intended registry version')
    # Cargo normalizes the manifest; every packaged Rust file must retain the
    # exact prepared bytes, including the independently written regressions.
    staged = INPUTS / FOLDERS[name]
    for path in unpacked(name).rglob('*.rs'):
        if sha(path) != sha(staged / path.relative_to(unpacked(name))):
            raise ValueError('Package changed a Rust source file')
    if sha(unpacked(name) / 'Cargo.toml.orig') != sha(staged / 'Cargo.toml'):
        raise ValueError('Package was built from a different original manifest')


def identity(mir):
    sys.path.insert(0, str(ROOT / 'verification/consumer-call'))
    from mir_identity import Identity
    recipe = json.loads((ROOT / 'verification/consumer-call/recipe.json').read_text())
    comparison = Identity(ROOT / recipe['current_mir'], mir)
    def find(module, suffix):
        candidates = [f['name'] for f in module['fns'] if f['name'].endswith('::' + suffix)]
        if len(candidates) != 1:
            raise ValueError('Wrong or missing release entry: ' + suffix)
        return candidates[0]
    names = ['multiply_1024_12289', 'multiply_2048_12289', 'multiply_2048_151019521']
    roots = [(find(comparison.modules[0], n), find(comparison.modules[1], n)) for n in names]
    return comparison.rooted(roots)


def prior_check():
    subprocess.run([sys.executable, str(ROOT / 'verification/consumer-call/run.py'), '--check', '--negative-controls'],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    return sha(ROOT / 'target/verification-consumer-call/consumer-call-report.json')


def inputs():
    files = source_files(HERE) + [ROOT / 'verification/consumer-call/mir_identity.py']
    for name in VERSIONS:
        files += source_files(INPUTS / FOLDERS[name]) + source_files(unpacked(name))
    files += [TARGET / 'harness/Cargo.toml', TARGET / 'harness/Cargo.lock', ROOT / 'verification/consumer-call/harness.rs']
    return {relative(p): sha(p) for p in sorted(set(files))}


def check(record):
    if record.get('status') != 'passed' or record['versions'] != VERSIONS:
        raise ValueError('Incomplete or incorrect release checkpoint')
    if [job['name'] for job in record['jobs']] != JOBS:
        raise ValueError('Missing, duplicate, or reordered release jobs')
    if inputs() != record['source_sha256']:
        raise ValueError('Release input coverage or source changed')
    for key in ('source_sha256', 'artifact_sha256'):
        for name, expected in record[key].items():
            if sha(ROOT / name) != expected:
                raise ValueError('Changed release evidence: ' + name)
    for job in record['jobs']:
        if job['status'] != 'passed':
            raise ValueError('Unsuccessful release check')
        for stream in ('stdout', 'stderr'):
            if sha(ROOT / job[stream]) != job[stream + '_sha256']:
                raise ValueError('Changed release transcript')
    for name in VERSIONS:
        package_contract(name)
    if prior_check() != record['prior_consumer_proof_sha256']:
        raise ValueError('Underlying composed proof changed')
    if identity(ROOT / record['mir']) != record['mir_graph_identity']:
        raise ValueError('Release MIR identity changed')


def main():
    global TARGET, INPUTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--from-checkouts', action='store_true', help='build final packages from the actual release repositories')
    args = parser.parse_args()
    if args.from_checkouts:
        TARGET = BASE / 'final'
        INPUTS = ROOT.parent
    report = TARGET / 'release-report.json'
    if args.check:
        check(json.loads(report.read_text()))
        print('Validated exact release packages and all three consumer entry graphs')
        return
    previous = prior_check()
    jobs = []
    # Cargo's package verifier resolves local path prerequisites from the
    # prepared checkouts. The tests and MIR below use only the extracted crate
    # archives. Registry verification follows publication of each prerequisite.
    for name in VERSIONS:
        command = ['cargo', 'package', '--manifest-path', str(INPUTS / FOLDERS[name] / 'Cargo.toml'),
                   '--locked', '--allow-dirty', '--target-dir', str(TARGET / 'package-build')]
        command += patches([] if name == 'ntt' else ['ntt'] if name == 'ring-lwe' else ['ntt', 'ring-lwe'], prepared=True)
        jobs.append(execute('package-' + name, command))
        extract(name)
        package_contract(name)
    shared_patches = patches(['ntt', 'ring-lwe'])
    for name in VERSIONS:
        command = ['cargo', 'test', '--locked', '--manifest-path', str(unpacked(name) / 'Cargo.toml'),
                   '--target-dir', str(TARGET / 'package-native')]
        # NTT has no dependency on Ring-LWE; avoid unused patch warnings there.
        command += [] if name == 'ntt' else shared_patches
        jobs.append(execute('test-' + name, command))
        if name == 'ntt':
            jobs.append(execute('test-ntt-release', command + ['--release']))
            lint = ['cargo', 'clippy', '--locked', '--all-targets', '--manifest-path',
                    str(unpacked(name) / 'Cargo.toml'), '--target-dir', str(TARGET / 'package-native'), '--', '-D', 'warnings']
            jobs.append(execute('clippy-ntt', lint))
        else:
            jobs.append(execute('benches-' + name, ['cargo', 'check', '--locked', '--benches', '--manifest-path',
                                str(unpacked(name) / 'Cargo.toml'), '--target-dir', str(TARGET / 'package-native'), *shared_patches]))
    harness = TARGET / 'harness'
    write(harness / 'Cargo.toml', f'''[package]
name = "ntt-consumer-call-proof"
version = "0.0.0"
edition = "2021"
publish = false
[lib]
path = {json.dumps(str(ROOT / 'verification/consumer-call/harness.rs'))}
[dependencies]
polynomial-ring = "=0.5.1"
ring-lwe = {{ path = {json.dumps(str(unpacked('ring-lwe')))} }}
[patch.crates-io]
ntt = {{ path = {json.dumps(str(unpacked('ntt')))} }}
''')
    jobs.append(execute('harness-lock', ['cargo', '+nightly-2026-03-21', 'generate-lockfile', '--manifest-path', str(harness / 'Cargo.toml')]))
    old_ring = ROOT / 'target/verification-polynomial-boundary/checkouts/ring-lwe-555b26a579779f265bce237d9c2d3d5c91090372'
    flags = (f'--remap-path-prefix={unpacked("ntt")}/src/=src/ '
             f'--remap-path-prefix={unpacked("ring-lwe")}/src/={old_ring}/src/')
    job = execute('release-mir', ['cargo', '+nightly-2026-03-21', 'saw-build', '--manifest-path',
                  str(harness / 'Cargo.toml'), '--lib', '--target-dir', str(TARGET / 'mir-build'), '--message-format=json'],
                  {'RUSTFLAGS': flags})
    jobs.append(job)
    events = [json.loads(s) for s in (ROOT / job['stdout']).read_text().splitlines()]
    paths = [Path(e['executable'] + '.linked-mir.json') for e in events if e.get('reason') == 'compiler-artifact'
             and e.get('target', {}).get('name') == 'ntt_consumer_call_proof' and e.get('executable')]
    if len(paths) != 1:
        raise ValueError('Expected exactly one release MIR artifact')
    comparison = identity(paths[0])
    mir = TARGET / 'artifacts' / (sha(paths[0]) + '.linked-mir.json')
    mir.parent.mkdir(exist_ok=True)
    shutil.copyfile(paths[0], mir)
    record = {'status': 'passed', 'versions': VERSIONS,
              'scope': 'Unpublished crate artifacts tested with exact local packaged prerequisites; existing fixed-array MIR proofs carried by graph identity',
              'prior_consumer_proof_sha256': previous, 'jobs': jobs,
              'source_sha256': inputs(),
              'artifact_sha256': {relative(p): sha(p) for p in [mir, *(crate_path(n) for n in VERSIONS)]},
              'mir': relative(mir), 'mir_graph_identity': comparison}
    check(record)
    write(report, json.dumps(record, indent=2) + '\n')
    print('Passed exact release packages and MIR identity for all three consumer entry paths')


if __name__ == '__main__':
    main()
