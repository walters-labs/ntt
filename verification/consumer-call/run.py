#!/usr/bin/env python3
"""Replay or audit the three fixed consumer entry paths and their proof imports.

MIR MethodSpecs cannot be serialized by SAW 1.6. Imports below use its unsafe
primitive, then this checker discharges them by an earlier successful proof,
identical contracts, and isomorphic reachable MIR graphs. This checker is part
of the trusted proof boundary; a standalone SAW exit is not the final result.
"""
import argparse
import copy
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

from mir_identity import Identity

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TARGET = ROOT / 'target/verification-consumer-call'
RECIPE = json.loads((HERE / 'recipe.json').read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sources():
    paths = [p for p in HERE.rglob('*') if p.is_file() and p.suffix in {'.py', '.rs', '.saw', '.in', '.json'}]
    paths += [ROOT / 'verification/check-consumer-bridge.py', ROOT / 'verification/check-polynomial-boundary.py',
              ROOT / 'verification/check-archived-1024.py']
    return {relative(p): sha(p) for p in sorted(paths)}


def render(name):
    return (HERE / 'templates' / (name + '.saw.in')).read_text().replace('@ROOT@', str(ROOT))


def generate(check):
    for name in RECIPE['imports'] + [task['name'] for task in RECIPE['tasks']]:
        path = TARGET / (name + '.saw')
        if check and (not path.exists() or path.read_text() != render(name)):
            raise ValueError('Changed generated proof script: ' + name)
        if not check:
            write(path, render(name))


def fragment(text, start, end):
    return text[text.index(start):text.index(end)].strip()


def contracts():
    """Every imported contract must be precisely an established contract."""
    with tarfile.open(ROOT / 'verification/results/2026-11-16.tar.gz') as saved:
        original = saved.extractfile('source/2026-11-16/verification/kernels.saw').read().decode()
    for size, text in [(1024, original), (2048, (ROOT / 'verification/kernels-staged.saw').read_text())]:
        imported = render(f'import-kernel-{size}')
        if fragment(imported, 'let kernel_spec', 'forward_kernel <-') != fragment(text, 'let kernel_spec', 'let kernel_proof'):
            raise ValueError('Kernel contract changed')
    ctor = fragment((ROOT / 'verification/polynomial-boundary/constructor.saw').read_text(), 'let constructor_spec', 'checked <-')
    if fragment(render('import-constructor'), 'let constructor_spec', 'constructor_verified <-') != ctor:
        raise ValueError('Constructor contract changed')
    padding = fragment(render('padding-symbolic-512'), 'let padding_spec', 'checked <-')
    for name in ('padding-symbolic-1024-long', 'import-padding'):
        end = 'checked <-' if name.startswith('padding-') else 'padding_verified <-'
        if fragment(render(name), 'let padding_spec', end) != padding:
            raise ValueError('Padding contract changed')
    # The only allowed consequence strengthens the precondition with zero-tail
    # and substitutes the equal result vector. All allocation/frame fields stay.
    premise = '  mir_precond {{ all (\\i -> (i < length) || (a @ i == 0)) ([0..d-1] : [d][64]) }};\n'
    derived = padding.replace('  let input =', premise + '  let input =', 1).replace(
        '[if j < length then a @ j else 0 | j <- ([0..d-1] : [d][64])] # (zero:[d][64])',
        'a # (zero:[d][64])')
    if fragment(render('import-padding-normalized'), 'let padding_spec', 'padding_verified <-') != derived:
        raise ValueError('Unjustified padding refinement')
    witness = (HERE / 'padding-equality.saw').read_text().split('enable_experimental;', 1)[1]
    for name, degree in [('padding-equality-rewrite-abc', 512), ('padding-equality-1024', 1024)]:
        expected = render(name).replace(f'let d = {degree};\n', '').split('enable_experimental;', 1)[1]
        if expected != witness:
            raise ValueError('Padding consequence witness changed')
    for case, proof, imported in [
        ('1024-12289', 'cyclic-1024-canonical', 'import-cyclic-1024'),
        ('2048-12289', 'cyclic-2048-12289-probe', 'import-cyclic-2048-12289'),
        ('2048-151019521', 'cyclic-2048-151019521-probe', 'import-cyclic-2048-151019521')]:
        end = 'let canonical_proof' if 'let canonical_proof' in render(proof) else 'let proof ='
        if fragment(render(proof), 'let cyclic_spec', end) != fragment(render(imported), 'let cyclic_spec', 'cyclic_verified <-'):
            raise ValueError('Cyclic product contract changed: ' + case)
    model_source = (HERE / 'model-link.saw').read_text()
    model_fragment = fragment(model_source, 'let rust_final_model', 'padding_model <-')
    compact = lambda text: re.sub(r'\s+', '', text)
    for case, instance, caller, cyclic in [
        ('1024-12289', 'Ntt1024.cry', 'caller-1024-normalized', 'cyclic-1024-canonical'),
        ('2048-12289', 'Ntt2048.cry', 'caller-2048-12289', 'cyclic-2048-12289-probe'),
        ('2048-151019521', 'Ntt2048_151019521.cry', 'caller-2048-151019521', 'cyclic-2048-151019521-probe')]:
        for name in (caller, cyclic, 'model-link-' + case):
            found = re.findall(r'import "[^"]*/(Ntt[^/" ]*\.cry)"', render(name))
            if found != [instance] * (2 if name == caller else 1):
                raise ValueError('Wrong parameter-instance binding: ' + name)
        expected = fragment(render(caller), 'let final_model', 'let caller_spec')
        expected = expected.replace('Ntt::', '')
        actual = model_fragment.replace('rust_final_model', 'final_model').replace(
            'actual_product', 'staged_product' if case.startswith('2048') else 'spectral_product')
        if compact(actual) != compact(expected):
            raise ValueError('MIR postcondition differs from the mathematical result term')
        if '"ntt_consumer_call_proof::multiply_' + case.replace('-', '_') + '"' not in render(caller):
            raise ValueError('Wrong complete entry function')
    # Exact generated templates restrict the import primitive to these known
    # bindings. No other included proof source may introduce an admission.
    counts = {name: render(name).count('mir_unsafe_assume_spec') for name in RECIPE['imports']}
    if sum(counts.values()) != 10 or any('mir_unsafe_assume_spec' in render(t['name']) for t in RECIPE['tasks']):
        raise ValueError('Unexpected MIR import')


def prior_checks():
    sys.path.insert(0, str(ROOT / 'verification'))
    archived = module('archived_ntt', 'verification/check-archived-1024.py')
    archived_result = archived.audit(ROOT / 'verification/results/2026-11-16.tar.gz')
    if sha(ROOT / RECIPE['old_1024_mir']) != archived_result['mir_sha256']:
        raise ValueError('1024 kernel import uses a different MIR artifact')
    boundary = module('boundary_ntt', 'verification/check-polynomial-boundary.py')
    boundary_report = json.loads((ROOT / 'target/verification-polynomial-boundary/boundary-report.json').read_text())
    boundary.check(boundary_report)
    if sha(ROOT / RECIPE['boundary_mir']) != boundary_report['mir_sha256']:
        raise ValueError('Constructor import uses a different MIR artifact')
    bridge = module('bridge_ntt', 'verification/check-consumer-bridge.py')
    bridge.check(json.loads((ROOT / 'target/verification-consumer-composition/bridge-report.json').read_text()))
    results = {'1024-12289': archived_result}
    for case, name in RECIPE['pairs'].items():
        pair = json.loads((ROOT / name).read_text())
        if sha(ROOT / RECIPE['old_2048_mir']) != pair['mir_sha256']:
            raise ValueError('2048 kernel import uses a different MIR artifact')
        for kind in ('rust', 'math', 'model', 'build'):
            if sha(pair[kind + '_report']) != pair[kind + '_report_sha256']:
                raise ValueError('Changed prior proof report')
        output = TARGET / ('prior-' + case + '-check.json')
        subprocess.run([sys.executable, str(ROOT / 'verification/check-split.py'), case,
                        pair['math_report'], pair['rust_report'], '--build-report', pair['build_report'],
                        '--model-report', pair['model_report'], '--output', str(output)], check=True, stdout=subprocess.DEVNULL)
        results[case] = json.loads(output.read_text())
    return results


def find_function(module_, needle):
    matches = [f['name'] for f in module_['fns'] if needle in re.sub(r'/[0-9a-f]+(?=::)', '', f['name'])]
    if len(matches) != 1:
        raise ValueError('Expected one MIR function: ' + needle)
    return matches[0]


def identities():
    comparisons = {}
    for label, old_key, needles in [
        ('kernels-1024', 'old_1024_mir', ['::prepared::forward_transform', '::prepared::inverse_transform']),
        ('kernels-2048', 'old_2048_mir', ['::prepared::forward_transform', '::prepared::inverse_transform']),
        ('constructor-and-padding', 'boundary_mir', ['polynomial_ring::{impl#1}::new::_inst', '::ntt_padding::padded'])]:
        identity = Identity(ROOT / RECIPE[old_key], ROOT / RECIPE['current_mir'])
        roots = [(find_function(identity.modules[0], n), find_function(identity.modules[1], n)) for n in needles]
        comparisons[label] = identity.rooted(roots)
    return comparisons


def build(check):
    path = TARGET / 'build-report.json'
    ring = ROOT / RECIPE['ring']
    paths = list((ROOT / 'src').rglob('*.rs')) + list((ring / 'src').rglob('*.rs'))
    paths += [ROOT / 'Cargo.toml', ROOT / 'Cargo.lock', HERE / 'harness.rs', ring / 'Cargo.toml',
              TARGET / 'harness/Cargo.toml', TARGET / 'harness/Cargo.lock']
    inputs = {relative(p): sha(p) for p in sorted(paths)}
    flags = '--remap-path-prefix=' + str(ROOT / 'src') + '/=src/'
    command = ['cargo', '+nightly-2026-03-21', 'saw-build', '--manifest-path',
               str(TARGET / 'harness/Cargo.toml'), '--lib', '--target-dir', str(TARGET / 'build'), '--message-format=json']
    if not check:
        env = dict(os.environ, CARGO_NET_OFFLINE='true', RUSTFLAGS=flags)
        log = TARGET / 'accepted-build-artifacts.jsonl'
        with log.open('w') as output:
            subprocess.run(command, cwd=ROOT, env=env, stdout=output, check=True, timeout=180)
        events = [json.loads(line) for line in log.read_text().splitlines()]
        artifacts = [Path(e['executable'] + '.linked-mir.json') for e in events
                     if e.get('reason') == 'compiler-artifact' and e.get('target', {}).get('name') == 'ntt_consumer_call_proof'
                     and e.get('profile', {}).get('test') and e.get('executable')]
        if len(artifacts) != 1:
            raise ValueError('Expected one rebuilt consumer MIR artifact')
        rebuilt = TARGET / 'artifacts' / (sha(artifacts[0]) + '.linked-mir.json')
        if not rebuilt.exists():
            shutil.copyfile(artifacts[0], rebuilt)
        write(path, json.dumps({'source_sha256': inputs, 'command': command, 'rustflags': flags,
                               'mir': RECIPE['current_mir'], 'mir_sha256': sha(ROOT / RECIPE['current_mir']),
                               'rebuilt_mir': relative(rebuilt), 'rebuilt_mir_sha256': sha(rebuilt),
                               'artifact_log': relative(log), 'artifact_log_sha256': sha(log)}, indent=2) + '\n')
    record = json.loads(path.read_text())
    if (record['source_sha256'] != inputs or record['command'] != command or record['rustflags'] != flags or
            record['mir'] != RECIPE['current_mir'] or sha(ROOT / record['mir']) != record['mir_sha256'] or
            sha(ROOT / record['artifact_log']) != record['artifact_log_sha256']):
        raise ValueError('Changed consumer build provenance')
    if (record['mir_sha256'] != Path(RECIPE['current_mir']).name.split('.')[0] or
            sha(ROOT / record['rebuilt_mir']) != record['rebuilt_mir_sha256']):
        raise ValueError('Changed content-addressed MIR')
    # The linker may reorder declarations between identical builds. Compare
    # complete reachable graphs for all three entry functions, not list order.
    identity = Identity(ROOT / record['mir'], ROOT / record['rebuilt_mir'])
    needles = ['::multiply_1024_12289', '::multiply_2048_12289', '::multiply_2048_151019521']
    identity.rooted([(find_function(identity.modules[0], n), find_function(identity.modules[1], n)) for n in needles])
    return record


def inspect(task, report_path):
    report = json.loads(report_path.read_text())
    script = TARGET / (task['name'] + '.saw')
    if (report.get('status') != 'passed' or report.get('exit_code') != 0 or
            report['entry_script_sha256'] != sha(script) or str(script) not in report['command'] or
            report['runner_sha256'] != sha(ROOT / 'verification/run-isolated.py')):
        raise ValueError('Unsuccessful or changed proof entry')
    if task['mir']:
        if ('--detect-vacuity' not in report['command'] or
                report['mir_sha256'] != sha(ROOT / RECIPE[task['mir']])):
            raise ValueError('Wrong MIR or missing vacuity check')
    log = ROOT / report['log']
    transcript = log.read_text()
    if transcript.count(task['marker'] + '\n') != 1 or transcript.count('Proof succeeded!') != task['mir_contracts']:
        raise ValueError('Missing successful contract checks: ' + task['name'])
    matches = re.findall(r'(?m)^(?:\[[^\]\n]*\]\s*)?(Not convertible|Convertible)\s*$', transcript)
    if matches != ['Convertible'] * task['conversions']:
        raise ValueError('Proposition boundaries do not match')
    dependencies = {str(script)} | set(re.findall(r'^Loading file "([^"]+)"', transcript, re.MULTILINE))
    bindings = {}
    for name in dependencies:
        source = (ROOT / name).resolve()
        key = relative(source)
        value = sha(source)
        expected = report['source_sha256'].get(key)
        if expected is not None and value != expected:
            raise ValueError('Changed loaded proof dependency: ' + key)
        if source != script and 'mir_unsafe_assume_spec' in source.read_text() and source.stem not in RECIPE['imports']:
            raise ValueError('Undeclared MIR import')
        bindings[key] = value
    for key, value in report['source_sha256'].items():
        if key.endswith('.cry') or key.startswith('src/') or key in {'Cargo.toml', 'Cargo.lock', 'verification/harness.rs'}:
            if sha(ROOT / key) != value:
                raise ValueError('Changed mathematical or implementation input: ' + key)
            bindings[key] = value
    exports = {}
    if task['kind'] == 'model-link':
        for name in ('model-composition.core', 'consumer-result.core'):
            p = TARGET / 'model-links' / task['case'] / name
            exports[relative(p)] = sha(p)
        # Every serialized premise must be a hash-checked export of an already
        # accepted dependency graph, not merely a file with the expected name.
        imported = re.findall(r'let (?:signed|spectral|model)_path = "([^"]+)";', script.read_text())
        graph_paths = [ROOT / 'target/verification-consumer-composition/bridge-report.json']
        if task['case'].startswith('2048'):
            pair = json.loads((ROOT / RECIPE['pairs'][task['case']]).read_text())
            graph_paths += [Path(pair['math_report']), Path(pair['model_report'])]
        graphs = [json.loads(p.read_text()) for p in graph_paths]
        def values(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == 'sha256' and isinstance(v, str):
                        yield v
                    yield from values(v)
            elif isinstance(obj, list):
                for item in obj:
                    yield from values(item)
        known = set().union(*(set(values(g)) for g in graphs))
        # The consumer bridge uses {path: hash} exports.
        for g in graphs:
            nodes = g.get('nodes', [])
            for node in nodes.values() if isinstance(nodes, dict) else nodes:
                known.update(v for v in node.get('exports', {}).values() if isinstance(v, str))
        for name in imported[:3 if task['case'].startswith('2048') else 1]:
            if sha(name) not in known:
                raise ValueError('Unproved serialized premise: ' + name)
            bindings[relative(name)] = sha(name)
    return {'task': task, 'report': relative(report_path), 'report_sha256': sha(report_path),
            'log': relative(log), 'log_sha256': sha(log), 'dependencies': bindings, 'exports': exports,
            'wall_seconds': report['wall_elapsed_seconds'], 'rss_bytes': report['child_max_rss_bytes']}


def run_task(task, check, adopt=False):
    for path in sorted((ROOT / 'target/verification-isolated').glob(task['name'] + '-*.json'), reverse=True):
        try:
            cache = TARGET / 'proof-records' / (sha(path) + '.json')
            if not cache.exists() and not adopt:
                continue
            node = inspect(task, path)
            if cache.exists():
                if json.loads(cache.read_text()) != node:
                    continue
            elif not check:
                # Initial evidence adoption is explicit. Subsequent runs only
                # accept these frozen dependency bindings or run a fresh proof.
                write(cache, json.dumps(node, indent=2) + '\n')
            else:
                continue
            return node
        except (ValueError, KeyError, OSError):
            continue
    if check:
        raise ValueError('Missing accepted proof: ' + task['name'])
    command = [sys.executable, str(ROOT / 'verification/run-isolated.py'), str(TARGET / (task['name'] + '.saw')),
               '--heap', task['heap'], '--seconds', str(task['seconds']), '--detect-vacuity']
    if task['mir']:
        command += ['--mir', str(ROOT / RECIPE[task['mir']])]
    if sys.platform == 'darwin':
        command.append('--keep-awake')
    env = dict(os.environ, CRYPTOLPATH=str(ROOT / 'verification'))
    before = sources()
    process = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, check=True)
    if sources() != before:
        raise ValueError('Proof sources changed while SAW was running')
    print(process.stdout, end='', flush=True)
    log = Path(re.search(r'^Log: (.+)$', process.stdout, re.MULTILINE).group(1))
    report = log.with_suffix('.json')
    node = inspect(task, report)
    write(TARGET / 'proof-records' / (sha(report) + '.json'), json.dumps(node, indent=2) + '\n')
    return node


def negative_controls(result):
    controls = {}
    def reject(name, action):
        try:
            action()
        except ValueError as error:
            controls[name] = str(error)
        else:
            raise ValueError('Accepted negative control: ' + name)
    def compare(changed):
        if changed != result:
            raise ValueError('Checkpoint differs from independently audited proof graph')
    for label, mutate in [
        ('missing_job', lambda r: r['nodes'].pop()),
        ('wrong_tuple', lambda r: r['nodes'][-1]['task'].update(case='2048-17')),
        ('changed_transcript', lambda r: r['nodes'][0].update(log_sha256='0'*64)),
        ('missing_consequence', lambda r: r['nodes'].pop(2))]:
        changed = copy.deepcopy(result)
        mutate(changed)
        reject(label, lambda: compare(changed))
    old, new = ROOT / RECIPE['old_2048_mir'], ROOT / RECIPE['current_mir']
    def graph_mutation(kind):
        identity = Identity(old, new)
        left = find_function(identity.modules[0], '::prepared::forward_transform')
        right = find_function(identity.modules[1], '::prepared::forward_transform')
        def dictionaries(obj):
            if isinstance(obj, dict):
                yield obj
                for value in obj.values():
                    yield from dictionaries(value)
            elif isinstance(obj, list):
                for value in obj:
                    yield from dictionaries(value)
        if kind == 'layout':
            identity.indices[1]['ty::i64']['tys']['layout']['size'] = 4
        else:
            function = identity.indices[1][right]['fns']
            if kind == 'opcode':
                node = next(v for v in dictionaries(function) if v.get('kind') == 'BinaryOp')
                node['op']['kind'] = 'Ne' if node['op']['kind'] == 'Eq' else 'Eq'
            else:
                node = next(v for v in dictionaries(function) if 'val' in v and v.get('kind') == 'usize')
                node['val'] = str(int(node['val']) + 1)
        identity.rooted([(left, right)])
    for kind in ('layout', 'opcode', 'literal'):
        reject('changed_mir_' + kind, lambda: graph_mutation(kind))
    def collision():
        identity = Identity(old, new)
        identity.bind('one', 'target', 'control')
        identity.bind('two', 'target', 'control')
    reject('identifier_collision', collision)
    global render
    original = render
    try:
        render = lambda name: original(name).replace('length <=', 'length <') if name == 'import-padding-normalized' else original(name)
        reject('changed_import_contract', contracts)
    finally:
        render = original
    return controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='audit retained proofs without running SAW or rebuilding')
    parser.add_argument('--adopt-evidence', action='store_true', help='initially freeze reviewed existing runs and all loaded dependencies')
    parser.add_argument('--negative-controls', action='store_true')
    args = parser.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    generate(args.check)
    contracts()
    prior = prior_checks()
    build_record = build(args.check)
    matches = identities()
    nodes = []
    for task in RECIPE['tasks']:
        node = run_task(task, args.check, args.adopt_evidence)
        nodes.append(node)
        print('Accepted ' + task['name'], flush=True)
    result = {'status': 'passed', 'scope': 'Three fixed-array Rust entry paths through the actual patched Ring-LWE adapter',
              'method': 'Checked MIR proof imports plus explicit mathematical implications',
              'source_sha256': sources(), 'build_report_sha256': sha(TARGET / 'build-report.json'),
              'prior_checks': prior, 'mir_graph_identity': matches, 'nodes': nodes,
              'new_mir_contracts': sum(n['task']['mir_contracts'] for n in nodes),
              'proposition_matches': sum(n['task']['conversions'] for n in nodes),
              'proof_wall_seconds_sum': sum(n['wall_seconds'] for n in nodes),
              'maximum_child_rss_bytes': max(n['rss_bytes'] for n in nodes)}
    output = TARGET / 'consumer-call-report.json'
    if args.check:
        if json.loads(output.read_text()) != result:
            raise ValueError('Changed checkpoint evidence or proof graph')
    else:
        write(output, json.dumps(result, indent=2) + '\n')
    if args.negative_controls:
        controls = negative_controls(result)
        write(TARGET / 'negative-controls.json', json.dumps(controls, indent=2) + '\n')
        print(f'Rejected {len(controls)} negative controls')
    print(f"Passed: {len(nodes)} proof jobs, {result['new_mir_contracts']} new MIR contracts, "
          f"{result['proposition_matches']} exact proposition matches")


if __name__ == '__main__':
    main()
