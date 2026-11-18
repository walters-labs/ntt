#!/usr/bin/env python3
"""Verify polynomial construction and every bounded consumer padding length."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TARGET = ROOT / "target/verification-polynomial-boundary"
ACTIVE = set()
LOCK = threading.Lock()
STOP = threading.Event()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != value:
        path.write_text(value)


def tasks():
    result = []
    for degree in (512, 1024):
        result.append({"kind": "constructor", "degree": degree})
    for degree in (512, 1024):
        for first in range(0, degree + 1, 32):
            result.append({"kind": "padding", "degree": degree, "first": first,
                           "count": min(32, degree + 1 - first)})
    return result


def entry(task):
    text = f"let d = {task['degree']};\n"
    if task["kind"] == "constructor":
        text += 'let constructor_timeout = 600000;\n'
        text += f'include "{HERE / "constructor.saw"}";\n'
    else:
        text += f"let first = {task['first']};\nlet count = {task['count']};\n"
        text += f'include "{HERE / "padding.saw"}";\n'
    return text


def task_id(task):
    return f"{task['kind']}-{task['degree']}-" + str(task.get("first", "all"))


def validate(task, node, fingerprint, mir_hash):
    if node.get("status") != "passed" or node.get("task") != task or node.get("input_digest") != fingerprint:
        raise ValueError("Stale or incomplete proof node")
    report = ROOT / node["report"]
    log = ROOT / node["log"]
    script = ROOT / node["script"]
    if (digest(report) != node["report_sha256"] or digest(log) != node["log_sha256"] or
            script.read_text() != entry(task) or digest(script) != node["script_sha256"]):
        raise ValueError("Changed proof artifact")
    record = json.loads(report.read_text())
    transcript = log.read_text()
    count = 1 if task["kind"] == "constructor" else task["count"]
    if (record["status"] != "passed" or record["exit_code"] != 0 or record["mir_sha256"] != mir_hash or
            record["entry_script_sha256"] != digest(script) or "--detect-vacuity" not in record["command"] or
            transcript.count("Proof succeeded!") != count):
        raise ValueError("Missing successful MIR contracts")
    if task["kind"] == "padding":
        actual = list(map(int, re.findall(r"Verified padding input length (\d+)", transcript)))
        expected = list(range(task["first"], task["first"] + task["count"]))
        degrees = list(map(int, re.findall(r"Verified padding degree (\d+)", transcript)))
        if actual != expected or degrees != [task["degree"]]:
            raise ValueError("Missing, duplicated, or wrong padding lengths")
    elif list(map(int, re.findall(r"Verified constructor coefficient count (\d+)", transcript))) != [task["degree"]]:
        raise ValueError("Wrong constructor degree")


def coverage(nodes):
    if [n["task"] for n in nodes] != tasks():
        raise ValueError("Incomplete or reordered task coverage")
    for degree in (512, 1024):
        lengths = [i for n in nodes if n["task"]["kind"] == "padding" and n["task"]["degree"] == degree
                   for i in range(n["task"]["first"], n["task"]["first"] + n["task"]["count"])]
        if lengths != list(range(degree + 1)):
            raise ValueError("Missing or duplicated lengths")


def run_node(task, fingerprint, mir, mir_hash, check_only):
    node_path = TARGET / "nodes" / fingerprint / (task_id(task) + ".json")
    if node_path.exists():
        node = json.loads(node_path.read_text())
        validate(task, node, fingerprint, mir_hash)
        return node
    if check_only:
        raise ValueError(f"Missing proof: {task_id(task)}")
    if STOP.is_set():
        raise RuntimeError("Run interrupted")
    script = TARGET / "entries" / fingerprint / (task_id(task) + ".saw")
    write(script, entry(task))
    seconds = 660 if task["kind"] == "constructor" else 300
    command = [sys.executable, str(ROOT / "verification/run-isolated.py"), str(script),
               "--mir", str(mir), "--heap", "2G", "--seconds", str(seconds), "--detect-vacuity"]
    if sys.platform == "darwin":
        command.append("--keep-awake")
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=True)
    with LOCK:
        ACTIVE.add(process)
    try:
        if STOP.is_set():
            process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=seconds + 30)
    finally:
        with LOCK:
            ACTIVE.discard(process)
    if process.returncode:
        raise RuntimeError(f"{task_id(task)} failed:\n{output}")
    log = Path(re.search(r"^Log: (.+)$", output, re.MULTILINE).group(1))
    report = log.with_suffix(".json")
    record = json.loads(report.read_text())
    node = {"status": "passed", "task": task, "input_digest": fingerprint,
            "script": str(script.relative_to(ROOT)), "script_sha256": digest(script),
            "report": str(report.relative_to(ROOT)), "report_sha256": digest(report),
            "log": str(log.relative_to(ROOT)), "log_sha256": digest(log),
            "wall_seconds": record["wall_elapsed_seconds"], "rss_bytes": record["child_max_rss_bytes"]}
    validate(task, node, fingerprint, mir_hash)
    write(node_path, json.dumps(node, indent=2) + "\n")
    print(f"Passed {task_id(task)}: {node['wall_seconds']:.1f}s", flush=True)
    return node


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ring-lwe", type=Path, required=True)
    parser.add_argument("--module-lwe", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="validate cached proofs without running SAW")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    ring, module = args.ring_lwe.resolve(), args.module_lwe.resolve()
    TARGET.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(HERE / "apply.py"), str(ring), "--check"], check=True)
    subprocess.run([sys.executable, str(ROOT / "verification/consumer-parameters/apply.py"),
                    "module-lwe", str(module), "--check"], check=True)
    env = os.environ.copy()
    env.setdefault("CARGO_NET_OFFLINE", "true")
    os.environ.setdefault("CARGO_NET_OFFLINE", "true")
    harness, native = TARGET / "final-harness", TARGET / "native-harness"
    for path in (harness, native):
        path.mkdir(exist_ok=True)
    write(harness / "harness.rs", (HERE / "harness.rs").read_text())
    write(native / "harness.rs", (ROOT / "verification/consumer-parameters/smoke.rs").read_text())
    for path, name, with_module in [(harness, "ntt-polynomial-boundary-proof", False),
                                     (native, "ntt-polynomial-boundary-regressions", True)]:
        manifest = f'''[package]
name = "{name}"
version = "0.0.0"
edition = "2021"
publish = false
[lib]
path = "harness.rs"
[dependencies]
polynomial-ring = "=0.5.1"
ring-lwe = {{ path = {json.dumps(str(ring))} }}
''' + (f'module-lwe = {{ path = {json.dumps(str(module))} }}\n' if with_module else '') + f'''
[patch.crates-io]
ntt = {{ path = {json.dumps(str(ROOT))} }}
ring-lwe = {{ path = {json.dumps(str(ring))} }}
'''
        write(path / "Cargo.toml", manifest)
        if not (path / "Cargo.lock").exists():
            subprocess.run(["cargo", "+nightly-2026-03-21", "generate-lockfile"], cwd=path, env=env,
                           check=True, timeout=120)
    paths = list((ROOT / "src").rglob("*.rs")) + [ROOT / "Cargo.toml", ROOT / "verification/harness.rs"]
    for path in (ring, module):
        paths += list((path / "src").rglob("*.rs")) + [path / "Cargo.toml"]
    paths += [p for p in HERE.iterdir() if p.is_file() and p.suffix in {".saw", ".rs", ".py", ".json"}]
    paths += [ROOT / "verification/run-isolated.py", ROOT / "verification/consumer-parameters/smoke.rs",
              ROOT / "verification/consumer-parameters/apply.py", ROOT / "verification/consumer-parameters/consumers.json"]
    for path in (harness, native):
        paths += [path / "Cargo.toml", path / "Cargo.lock", path / "harness.rs"]
    sources = {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(paths))}
    source_key = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    build_path = TARGET / "build-reports" / (source_key + ".json")
    started = time.monotonic()
    if build_path.exists():
        build = json.loads(build_path.read_text())
    else:
        if args.check:
            raise ValueError("Missing build provenance")
        command = ["cargo", "+nightly-2026-03-21", "saw-build", "--lib", "--target-dir",
                   str(TARGET / "final-build"), "--message-format=json"]
        artifact_log = TARGET / "final-build-artifacts.jsonl"
        with artifact_log.open("w") as log:
            subprocess.run(command, cwd=harness, env=env, stdout=log, check=True, timeout=180)
        artifacts = []
        for line in artifact_log.read_text().splitlines():
            event = json.loads(line)
            if (event.get("reason") == "compiler-artifact" and event.get("target", {}).get("name") ==
                    "ntt_polynomial_boundary_proof" and event.get("profile", {}).get("test") and event.get("executable")):
                artifacts.append(Path(event["executable"] + ".linked-mir.json"))
        if len(artifacts) != 1 or not artifacts[0].is_file():
            raise ValueError("Expected exactly one current boundary MIR artifact")
        mir_hash = digest(artifacts[0])
        mir = TARGET / "artifacts" / (mir_hash + ".linked-mir.json")
        if not mir.exists():
            shutil.copyfile(artifacts[0], mir)
        build = {"source_sha256": sources, "mir_path": str(mir.relative_to(ROOT)),
                 "mir_sha256": mir_hash, "command": command}
        write(build_path, json.dumps(build, indent=2) + "\n")
    mir, mir_hash = ROOT / build["mir_path"], build["mir_sha256"]
    if build["source_sha256"] != sources or digest(mir) != mir_hash:
        raise ValueError("Changed build provenance or MIR")
    fingerprint = hashlib.sha256((source_key + mir_hash).encode()).hexdigest()
    output = TARGET / "boundary-report.json"
    if not args.check:
        write(output, json.dumps({"status": "running", "input_digest": fingerprint}) + "\n")
    pool = ThreadPoolExecutor(max_workers=args.workers)
    nodes = []
    try:
        futures = [pool.submit(run_node, task, fingerprint, mir, mir_hash, args.check) for task in tasks()]
        for future in as_completed(futures):
            nodes.append(future.result())
    except BaseException:
        STOP.set()
        for future in futures:
            future.cancel()
        with LOCK:
            active = list(ACTIVE)
        for process in active:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    nodes.sort(key=lambda node: tasks().index(node["task"]))
    coverage(nodes)
    native_log = TARGET / "boundary-native.log"
    if not args.check:
        with native_log.open("w") as log:
            subprocess.run(["cargo", "test", "--locked", "--target-dir", str(TARGET / "native-build")],
                           cwd=native, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    if "4 passed; 0 failed" not in native_log.read_text():
        raise ValueError("Missing native regressions")
    for name, sha in sources.items():
        if digest(ROOT / name) != sha:
            raise ValueError(f"Source changed during verification: {name}")
    result = {"status": "passed", "scope": "constructors and all bounded consumer padding input lengths",
              "source_sha256": sources, "input_digest": fingerprint,
              "build_report": str(build_path.relative_to(ROOT)), "build_report_sha256": digest(build_path),
              "mir_path": str(mir.relative_to(ROOT)), "mir_sha256": mir_hash,
              "nodes": nodes, "mir_contracts": 1540, "native_tests": 4,
              "native_log_sha256": digest(native_log), "elapsed_seconds": round(time.monotonic() - started, 3)}
    if not args.check:
        write(output, json.dumps(result, indent=2) + "\n")
    print(f"Validated both constructors and all 1538 padding lengths: {output}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted; completed proof batches remain cached.", file=sys.stderr)
        sys.exit(130)
