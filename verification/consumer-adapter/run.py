#!/usr/bin/env python3
"""Verify the consumer's actual folding helper, then run adapter regressions."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ring-lwe", type=Path, required=True)
    parser.add_argument("--module-lwe", type=Path, required=True)
    args = parser.parse_args()
    ring, module = args.ring_lwe.resolve(), args.module_lwe.resolve()
    target = root / "target/verification-consumer-adapter"
    target.mkdir(parents=True, exist_ok=True)
    output = target / "adapter-report.json"
    output.write_text('{"status":"running"}\n')
    subprocess.run([sys.executable, str(here / "apply.py"), str(ring), "--check"], check=True)
    subprocess.run([sys.executable, str(here.parent / "consumer-parameters/apply.py"),
                    "module-lwe", str(module), "--check"], check=True)
    cases = json.loads((here / "cases.json").read_text())
    for case in cases:
        if digest(root / case["instance"]) != case["instance_sha256"]:
            raise SystemExit(f"Changed transform parameter instance: {case['instance']}")
    env = os.environ.copy()
    env.setdefault("CARGO_NET_OFFLINE", "true")
    harness, native = target / "harness", target / "native-harness"
    for path in (harness, native):
        path.mkdir(exist_ok=True)
    (harness / "harness.rs").write_bytes((here / "harness.rs").read_bytes())
    (native / "harness.rs").write_bytes((here.parent / "consumer-parameters/smoke.rs").read_bytes())
    def manifest(name, include_module):
        return f'''[package]
name = "{name}"
version = "0.0.0"
edition = "2021"
publish = false
[lib]
path = "harness.rs"
[dependencies]
polynomial-ring = "=0.5.1"
ring-lwe = {{ path = {json.dumps(str(ring))} }}
''' + (f'module-lwe = {{ path = {json.dumps(str(module))} }}\n' if include_module else '') + f'''
[patch.crates-io]
ntt = {{ path = {json.dumps(str(root))} }}
ring-lwe = {{ path = {json.dumps(str(ring))} }}
'''
    (harness / "Cargo.toml").write_text(manifest("ntt-consumer-adapter-proof", False))
    (native / "Cargo.toml").write_text(manifest("ntt-consumer-adapter-regressions", True))
    for path in (harness, native):
        if not (path / "Cargo.lock").exists():
            subprocess.run(["cargo", "+nightly-2026-03-21", "generate-lockfile"],
                           cwd=path, env=env, check=True, timeout=120)
    sources = list((root / "src").rglob("*.rs")) + [root / "Cargo.toml", root / "verification/harness.rs"]
    for path in (ring, module):
        sources += list((path / "src").rglob("*.rs")) + [path / "Cargo.toml"]
    sources += list((root / "verification").glob("*.cry"))
    sources += list((root / "verification").glob("adapter-*.saw"))
    sources += [root / "verification/run-isolated.py", here.parent / "consumer-parameters/smoke.rs",
                here.parent / "consumer-parameters/apply.py", here.parent / "consumer-parameters/consumers.json"]
    sources += [p for p in here.rglob("*") if p.is_file() and p.suffix in {".rs", ".py", ".json", ".patch"}]
    for path in (harness, native):
        sources += [path / "Cargo.toml", path / "Cargo.lock", path / "harness.rs"]
    before = {str(p.relative_to(root)): digest(p) for p in sources}
    started = time.monotonic()
    command = ["cargo", "+nightly-2026-03-21", "saw-build", "--lib", "--target-dir",
               str(target / "final-build"), "--message-format=json"]
    artifact_log = target / "final-build-artifacts.jsonl"
    with artifact_log.open("w") as log:
        subprocess.run(command, cwd=harness, env=env, stdout=log, check=True, timeout=180)
    artifacts = []
    for line in artifact_log.read_text().splitlines():
        event = json.loads(line)
        if (event.get("reason") == "compiler-artifact" and
                event.get("target", {}).get("name") == "ntt_consumer_adapter_proof" and
                "lib" in event.get("target", {}).get("kind", []) and
                event.get("profile", {}).get("test") and event.get("executable")):
            artifacts.append(Path(event["executable"] + ".linked-mir.json"))
    if len(artifacts) != 1 or not artifacts[0].is_file():
        raise SystemExit("Expected exactly one current proof-library MIR artifact")
    mir_hash = digest(artifacts[0])
    mir = target / "artifacts" / f"{mir_hash}.linked-mir.json"
    mir.parent.mkdir(exist_ok=True)
    if not mir.exists():
        shutil.copyfile(artifacts[0], mir)
    if digest(mir) != mir_hash:
        raise SystemExit("MIR hash mismatch")
    jobs = [{"case": "scalar-centering", "script": "verification/adapter-centering.saw",
             "contracts": 2, "heap": "2G"}, *cases]
    results = []
    for case in jobs:
        print(f"Checking {case['case']}", flush=True)
        cmd = [sys.executable, "verification/run-isolated.py", case["script"], "--mir", str(mir),
               "--heap", case["heap"], "--seconds", "600", "--detect-vacuity"]
        if sys.platform == "darwin":
            cmd.append("--keep-awake")
        run = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
        print(run.stdout, end="", flush=True)
        if run.returncode:
            print(run.stderr, file=sys.stderr)
            raise SystemExit(run.returncode)
        log = Path(re.search(r"^Log: (.+)$", run.stdout, re.MULTILINE).group(1))
        report = log.with_suffix(".json")
        record = json.loads(report.read_text())
        if (record["status"] != "passed" or record["mir_sha256"] != mir_hash or
                log.read_text().count("Proof succeeded!") != case["contracts"]):
            raise SystemExit(f"Incomplete proof: {case['case']}")
        results.append({"case": case["case"], "contracts": case["contracts"],
                        "report": str(report.relative_to(root)), "report_sha256": digest(report),
                        "log": str(log.relative_to(root)), "log_sha256": digest(log),
                        "wall_seconds": record["wall_elapsed_seconds"],
                        "max_child_rss_bytes": record["child_max_rss_bytes"]})
    native_command = ["cargo", "test", "--locked", "--target-dir", str(target / "native-build")]
    native_log = target / "native-regressions.log"
    with native_log.open("w") as log:
        native_run = subprocess.run(native_command, cwd=native, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=180)
    if native_run.returncode:
        print(native_log.read_text())
        raise SystemExit(native_run.returncode)
    for name, sha in before.items():
        if digest(root / name) != sha:
            raise SystemExit(f"Source changed during verification: {name}")
    if digest(mir) != mir_hash:
        raise SystemExit("MIR changed during verification")
    result = {"status": "passed", "scope": "consumer fold/centering components; full adapter composition remains open",
              "source_sha256": before, "build_command": command,
              "mir_path": str(mir.relative_to(root)), "mir_sha256": mir_hash,
              "proofs": results, "mir_contracts": sum(c["contracts"] for c in jobs),
              "native_tests": 4, "native_command": native_command,
              "native_log_sha256": digest(native_log),
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Adapter reduction checkpoint passed: {output}")


if __name__ == "__main__":
    main()
