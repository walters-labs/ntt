#!/usr/bin/env python3
"""Prove the complete padded-cyclic to centered-negacyclic bridge."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TARGET = ROOT / "target/verification-consumer-composition"
CASES = [("1024-12289", 1024, 12289, "Ntt1024.cry"),
         ("2048-12289", 2048, 12289, "Ntt2048.cry"),
         ("2048-151019521", 2048, 151019521, "Ntt2048_151019521.cry")]
ACTIVE, LOCK, STOP = set(), threading.Lock(), threading.Event()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != value:
        path.write_text(value)


def sources():
    paths = [p for p in HERE.iterdir() if p.suffix in {".py", ".saw", ".cry"}]
    paths += [ROOT / "verification" / name for name in
              ["NttSpec.cry", "ScalarSpec.cry", "AdapterSpec.cry", "run-isolated.py"] +
              [case[3] for case in CASES]]
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(paths))}


def tasks():
    blocks = [{"case": name, "n": n, "q": q, "instance": instance, "kind": "block", "first": first}
              for name, n, q, instance in CASES for first in range(0, n // 2, 32)]
    return blocks + [{"case": name, "n": n, "q": q, "instance": instance, "kind": kind}
                     for name, n, q, instance in CASES for kind in ("coverage", "normalized")]


def identity(task):
    return f"{task['case']}-{task['kind']}" + (f"-{task['first']}" if task['kind'] == "block" else "")


def entry(task):
    value = f'import "{ROOT / "verification" / task["instance"]}" as Ntt;\n'
    if task["kind"] == "block":
        value += f'let first = {task["first"]};\n'
    return value + f'include "{HERE / (task["kind"] + ".saw")}";\n'


def outputs(task, fingerprint):
    folder = TARGET / "outputs" / fingerprint / task["case"]
    names = ([f"block-{task['first']}-32.core"] if task["kind"] == "block" else
             ["coverage.core", "full.core"] if task["kind"] == "coverage" else
             ["normalized.core", "signed-product.core"])
    return [folder / name for name in names]


def marker(task):
    prefix = {"block": "Verified closed consumer bridge block", "coverage": "Verified complete consumer bridge coverage",
              "normalized": "Verified signed-input consumer bridge"}[task["kind"]]
    return f"{prefix} {task['n']} {task['q']}" + (f" {task['first']} 32" if task['kind'] == "block" else "")


def validate(task, node, fingerprint, premises):
    if (node.get("status") != "passed" or node.get("task") != task or
            node.get("input_digest") != fingerprint or node.get("premises") != premises):
        raise ValueError("Changed task, fingerprint, or proved dependencies")
    script, report, log = [ROOT / node[key] for key in ("script", "report", "log")]
    if script.read_text() != entry(task):
        raise ValueError("Changed entry script")
    for path, key in [(script, "script_sha256"), (report, "report_sha256"), (log, "log_sha256")]:
        if digest(path) != node[key]:
            raise ValueError("Changed proof artifact")
    record = json.loads(report.read_text())
    if (record["status"] != "passed" or record["exit_code"] != 0 or
            record["entry_script_sha256"] != digest(script) or
            record["runner_sha256"] != digest(ROOT / "verification/run-isolated.py") or
            "--detect-vacuity" not in record["command"] or record["log"] != node["log"] or
            record["wall_elapsed_seconds"] != node["wall_seconds"] or
            record["child_max_rss_bytes"] != node["rss_bytes"]):
        raise ValueError("Unsuccessful or mismatched proof report")
    if log.read_text().count(marker(task) + "\n") != 1:
        raise ValueError("Missing exact proof-completion marker")
    expected = {str(path.relative_to(ROOT)): digest(path) for path in outputs(task, fingerprint)}
    if node["exports"] != expected:
        raise ValueError("Changed proposition exports")


def run(task, fingerprint, premises, check_only):
    node_path = TARGET / "nodes" / fingerprint / (identity(task) + ".json")
    if node_path.exists():
        node = json.loads(node_path.read_text())
        validate(task, node, fingerprint, premises)
        return node
    if check_only or STOP.is_set():
        raise ValueError(f"Missing proof: {identity(task)}")
    script = TARGET / "entries" / fingerprint / (identity(task) + ".saw")
    write(script, entry(task))
    folder = outputs(task, fingerprint)[0].parent
    folder.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CRYPTOLPATH"] = str(ROOT / "verification") + os.pathsep + env.get("CRYPTOLPATH", "")
    env["NTT_MATH_OUTPUT"] = str(folder)
    env["NTT_MATH_COMPONENT"] = identity(task)
    command = [sys.executable, str(ROOT / "verification/run-isolated.py"), str(script),
               "--heap", "2G", "--seconds", "180", "--detect-vacuity"]
    if sys.platform == "darwin":
        command.append("--keep-awake")
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    with LOCK:
        ACTIVE.add(process)
    try:
        if STOP.is_set():
            process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=210)
    finally:
        with LOCK:
            ACTIVE.discard(process)
    if process.returncode:
        raise RuntimeError(f"Failed {identity(task)}:\n{output}")
    log = Path(re.search(r"^Log: (.+)$", output, re.MULTILINE).group(1))
    report = log.with_suffix(".json")
    record = json.loads(report.read_text())
    node = {"status": "passed", "task": task, "input_digest": fingerprint, "premises": premises,
            "script": str(script.relative_to(ROOT)), "script_sha256": digest(script),
            "report": str(report.relative_to(ROOT)), "report_sha256": digest(report),
            "log": str(log.relative_to(ROOT)), "log_sha256": digest(log),
            "wall_seconds": record["wall_elapsed_seconds"], "rss_bytes": record["child_max_rss_bytes"],
            "exports": {str(path.relative_to(ROOT)): digest(path) for path in outputs(task, fingerprint)}}
    validate(task, node, fingerprint, premises)
    write(node_path, json.dumps(node, indent=2) + "\n")
    print(f"Passed {identity(task)}: {node['wall_seconds']:.1f}s", flush=True)
    return node


def node_digest(node):
    return hashlib.sha256(json.dumps(node, sort_keys=True).encode()).hexdigest()


def negative_controls(nodes, fingerprint):
    controls = {}
    mutations = {"wrong_parameters": lambda n: n["task"].update(q=17),
                 "wrong_transcript_hash": lambda n: n.update(log_sha256="0" * 64),
                 "wrong_entry_hash": lambda n: n.update(script_sha256="0" * 64),
                 "unproved_premise": lambda n: n.update(premises={"unproved": "0" * 64}),
                 "changed_export": lambda n: n["exports"].update({next(iter(n["exports"])): "0" * 64})}
    for name, mutate in mutations.items():
        changed = copy.deepcopy(nodes[0])
        mutate(changed)
        try:
            validate(nodes[0]["task"], changed, fingerprint, {})
        except ValueError as error:
            controls[name] = str(error)
        else:
            raise ValueError(f"Accepted negative control: {name}")
    for name, altered in [("missing_block", nodes[1:]), ("duplicate_block", nodes + [nodes[0]])]:
        if [n["task"] for n in altered] == tasks():
            raise ValueError(f"Accepted negative control: {name}")
        controls[name] = "Rejected incomplete or duplicate task coverage"
    return controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--negative-controls", action="store_true")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    before = sources()
    fingerprint = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    result_path = TARGET / "bridge-report.json"
    if not args.check:
        write(result_path, json.dumps({"status": "running", "input_digest": fingerprint}) + "\n")
    started = time.monotonic()
    jobs, nodes = tasks(), []
    pool = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = [pool.submit(run, task, fingerprint, {}, args.check) for task in jobs if task["kind"] == "block"]
        for future in as_completed(futures):
            nodes.append(future.result())
    except BaseException:
        STOP.set()
        for future in futures:
            future.cancel()
        with LOCK:
            for process in ACTIVE:
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    for task in jobs:
        if task["kind"] == "block":
            continue
        predecessors = [n for n in nodes if n["task"]["case"] == task["case"] and
                        n["task"]["kind"] == ("block" if task["kind"] == "coverage" else "coverage")]
        premises = {identity(n["task"]): node_digest(n) for n in sorted(predecessors, key=lambda n: identity(n["task"]))}
        nodes.append(run(task, fingerprint, premises, args.check))
    nodes.sort(key=lambda node: jobs.index(node["task"]))
    if [n["task"] for n in nodes] != jobs or before != sources():
        raise ValueError("Incomplete coverage or changed proof sources")
    if args.check:
        saved = json.loads(result_path.read_text())
        if (saved["status"] != "passed" or saved["nodes"] != nodes or
                saved["source_sha256"] != before or saved["input_digest"] != fingerprint):
            raise ValueError("Aggregate checkpoint does not match the validated graph")
    else:
        write(result_path, json.dumps({"status": "passed", "input_digest": fingerprint,
              "scope": "mathematical bridge; actual whole-consumer Rust call composition remains open",
              "source_sha256": before, "nodes": nodes, "closed_blocks": 80,
              "output_coefficients": 2560, "coverage_implications": 3, "normalization_implications": 3,
              "elapsed_seconds": round(time.monotonic() - started, 3)}, indent=2) + "\n")
    if args.negative_controls:
        controls = negative_controls(nodes, fingerprint)
        write(TARGET / "checker-controls.json", json.dumps(controls, indent=2) + "\n")
    print(f"Validated all three complete signed-input consumer bridges: {result_path}")


if __name__ == "__main__":
    main()
