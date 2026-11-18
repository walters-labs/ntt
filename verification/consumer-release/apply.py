#!/usr/bin/env python3
"""Prepare or apply a reviewed release plan without touching the proof checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'target/verification-consumer-release'
VERSIONS = {'ntt': '0.1.10', 'ring-lwe': '0.1.9', 'module-lwe': '0.1.6'}
FOLDERS = {'ntt': 'ntt-release', 'ring-lwe': 'ring-lwe', 'module-lwe': 'module-lwe'}
BASES = {'ntt': 'c814327d44e503f1a3000b696b34fb93b705be38',
         'ring-lwe': '555b26a579779f265bce237d9c2d3d5c91090372',
         'module-lwe': '6fd32d3f70e8a0d9154f3edd1726267cbec9b3ff'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return digest(path.read_bytes()) if path.is_file() else None


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def original(name, relative):
    checkout = ROOT if name == 'ntt' else ROOT.parent / name
    result = subprocess.run(['git', '-C', str(checkout), 'show', BASES[name] + ':' + relative], capture_output=True)
    return digest(result.stdout) if result.returncode == 0 else None


def prepare():
    entries = []
    for name in VERSIONS:
        destination = ROOT.parent / FOLDERS[name]
        stage = TARGET / 'staged' / FOLDERS[name]
        changes = []
        for path in sorted(stage.rglob('*')):
            if not path.is_file() or {'target', '.git'}.intersection(path.relative_to(stage).parts):
                continue
            relative = str(path.relative_to(stage))
            before, after = original(name, relative), file_hash(path)
            if before != after:
                changes.append({'file': relative, 'before_sha256': before, 'after_sha256': after,
                                'prepared': str(path.relative_to(ROOT))})
        entries.append({'name': name, 'version': VERSIONS[name], 'base': BASES[name],
                        'destination': str(destination), 'branch': 'codex/verified-release-' + VERSIONS[name],
                        'changes': changes})
    path = TARGET / 'application-plan.json'
    path.write_text(json.dumps({'versions': VERSIONS, 'entries': entries}, indent=2) + '\n')
    print('Prepared plan: ' + str(path))
    for entry in entries:
        print(f"{entry['name']} {entry['version']}: {len(entry['changes'])} files -> {entry['destination']}")


def validate(plan, applied):
    if plan['versions'] != VERSIONS or [e['name'] for e in plan['entries']] != list(VERSIONS):
        raise ValueError('Wrong release plan or dependency order')
    for entry in plan['entries']:
        name, checkout = entry['name'], Path(entry['destination'])
        if checkout != ROOT.parent / FOLDERS[name] or entry['base'] != BASES[name]:
            raise ValueError('Changed release destination/base')
        if entry['branch'] != 'codex/verified-release-' + VERSIONS[name]:
            raise ValueError('Changed release branch')
        for change in entry['changes']:
            relative = Path(change['file'])
            prepared = TARGET / 'staged' / FOLDERS[name] / relative
            if (relative.is_absolute() or '..' in relative.parts or
                    ROOT / change['prepared'] != prepared or
                    original(name, change['file']) != change['before_sha256'] or
                    file_hash(prepared) != change['after_sha256']):
                raise ValueError('Invalid or changed prepared release file')
        if not checkout.exists():
            if name == 'ntt' and not applied:
                continue
            raise ValueError('Missing release checkout')
        if git(checkout, 'rev-parse', 'HEAD') != entry['base']:
            raise ValueError('Release base changed')
        if applied and git(checkout, 'branch', '--show-current') != entry['branch']:
            raise ValueError('Wrong release branch')
        if not applied and git(checkout, 'status', '--porcelain', '--untracked-files=all'):
            raise ValueError('Refusing to overwrite a changed checkout: ' + str(checkout))
        for change in entry['changes']:
            if file_hash(ROOT / change['prepared']) != change['after_sha256']:
                raise ValueError('Prepared release source changed')
            expected = change['after_sha256' if applied else 'before_sha256']
            if file_hash(checkout / change['file']) != expected:
                raise ValueError('Unexpected release file: ' + str(checkout / change['file']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--refresh-manifests', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return
    # Source, exact crate archives, successful tests, dependency versions, and
    # the complete entry graph comparison must pass before writing any checkout.
    subprocess.run([sys.executable, str(Path(__file__).with_name('run.py')), '--check'], check=True)
    plan_path = TARGET / 'application-plan.json'
    plan = json.loads(plan_path.read_text())
    if args.check:
        validate(plan, True)
        print('All release checkouts match the checked package source plan')
        return
    if args.refresh_manifests:
        pending = []
        for entry in plan['entries']:
            destination = Path(entry['destination'])
            name = entry['name']
            if (destination != ROOT.parent / FOLDERS[name] or entry['base'] != BASES[name] or
                    entry['branch'] != 'codex/verified-release-' + VERSIONS[name]):
                raise ValueError('Changed manifest-refresh destination or base')
            if git(destination, 'rev-parse', 'HEAD') != entry['base'] or git(destination, 'branch', '--show-current') != entry['branch']:
                raise ValueError('Release checkout changed')
            for change in entry['changes']:
                output = destination / change['file']
                if file_hash(output) == change['after_sha256']:
                    continue
                if change['file'] != 'Cargo.toml':
                    raise ValueError('Non-manifest source changed')
                text = output.read_text().replace('ntt = { version = "=0.1.10", path = "../ntt-release" }', 'ntt = "=0.1.10"').replace(
                    'ring-lwe = { version = "=0.1.9", path = "../ring-lwe" }', 'ring-lwe = "=0.1.9"')
                if digest(text.encode()) != change['after_sha256']:
                    raise ValueError('Unexpected dependency-manifest change')
                pending.append((output, text))
        for output, text in pending:
            output.write_text(text)
    else:
        validate(plan, False)
        for entry in plan['entries']:
            destination = Path(entry['destination'])
            if entry['name'] == 'ntt':
                subprocess.run(['git', '-C', str(ROOT), 'worktree', 'add', '-b', entry['branch'],
                                str(destination), entry['base']], check=True)
            else:
                subprocess.run(['git', '-C', str(destination), 'switch', '-c', entry['branch']], check=True)
            for change in entry['changes']:
                output = destination / change['file']
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / change['prepared'], output)
    validate(plan, True)
    report = {'status': 'applied', 'application_plan_sha256': file_hash(plan_path),
              'release_report_sha256': file_hash(TARGET / 'release-report.json'), 'entries': plan['entries']}
    (TARGET / 'application-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Applied all three prepared releases on separate branches')


if __name__ == '__main__':
    main()
