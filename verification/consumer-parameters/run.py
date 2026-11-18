#!/usr/bin/env python3
"""Run native regression tests for the actual patched consumer code."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-lwe", type=Path, required=True)
    parser.add_argument("--ring-lwe", type=Path, required=True)
    args = parser.parse_args()
    checkouts = {"module-lwe": args.module_lwe.resolve(), "ring-lwe": args.ring_lwe.resolve()}
    for name, path in checkouts.items():
        subprocess.run([sys.executable, str(here / "apply.py"), name, str(path), "--check"], check=True)
    target = root / "target/verification-consumer-parameters"
    smoke = target / "smoke"
    (smoke / "src").mkdir(parents=True, exist_ok=True)
    paths = {name: json.dumps(str(path)) for name, path in checkouts.items()}
    (smoke / "Cargo.toml").write_text(f'''[package]
name = "consumer-parameter-regressions"
version = "0.0.0"
edition = "2021"
publish = false

[dependencies]
polynomial-ring = "=0.5.1"
module-lwe = {{ path = {paths["module-lwe"]} }}
ring-lwe = {{ path = {paths["ring-lwe"]} }}

[patch.crates-io]
ntt = {{ path = {json.dumps(str(root))} }}
ring-lwe = {{ path = {paths["ring-lwe"]} }}
''')
    (smoke / "src/lib.rs").write_bytes((here / "smoke.rs").read_bytes())
    env = os.environ.copy()
    env.setdefault("CARGO_NET_OFFLINE", "true")
    def build_directory(name):
        # Root packages in different source checkouts can otherwise reuse a
        # binary with the same Cargo artifact name. Isolate each consumer too.
        return ["--target-dir", str(target / "native" / name)]
    patches = ["--config", f"patch.crates-io.ntt.path={json.dumps(str(root))}",
               "--config", f"patch.crates-io.ring-lwe.path={paths['ring-lwe']}"]
    for path in [smoke, *checkouts.values()]:
        if not (path / "Cargo.lock").exists():
            subprocess.run(["cargo", "generate-lockfile", *patches], cwd=path, env=env, check=True, timeout=120)
    sources = list((root / "src").rglob("*.rs")) + [root / "Cargo.toml"]
    for checkout in checkouts.values():
        sources += list((checkout / "src").rglob("*.rs")) + list((checkout / "benches").rglob("*.rs"))
        sources += [checkout / "Cargo.toml", checkout / "Cargo.lock"]
    sources += [p for p in here.rglob("*") if p.is_file() and p.suffix in {".py", ".rs", ".json", ".patch"}]
    sources += [smoke / "Cargo.toml", smoke / "Cargo.lock", smoke / "src/lib.rs"]
    before = {str(p): digest(p) for p in sources}
    jobs = [("adapter-regressions", smoke, ["cargo", "test", "--locked", *build_directory("adapter")])]
    for name, path in checkouts.items():
        jobs += [(name + "-cli", path, ["cargo", "test", "--locked", "--bin", name,
                  "parameter_consistency_tests", *build_directory(name), *patches])]
    # Exercise the corrected toy example and compile its benchmark too.
    jobs += [("ring-lwe-doctests", checkouts["ring-lwe"], ["cargo", "test", "--locked", "--doc", *build_directory("ring-lwe"), *patches]),
             ("ring-lwe-benches", checkouts["ring-lwe"], ["cargo", "check", "--locked", "--benches", *build_directory("ring-lwe"), *patches])]
    results = []
    started = time.monotonic()
    for name, cwd, command in jobs:
        log = target / (name + ".log")
        begin = time.monotonic()
        print(f"Running {name}", flush=True)
        with log.open("w") as output:
            run = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=180)
        if run.returncode:
            print(log.read_text())
            raise SystemExit(run.returncode)
        results.append({"name": name, "command": command, "cwd": str(cwd), "status": "passed",
                        "seconds": round(time.monotonic() - begin, 3),
                        "log": str(log.relative_to(root)), "log_sha256": digest(log)})
    for name, sha in before.items():
        if digest(Path(name)) != sha:
            raise SystemExit(f"Source changed during regression tests: {name}")
    report = {"status": "passed", "scope": "native parameter and adapter regressions; no new formal adapter proof",
              "elapsed_seconds": round(time.monotonic() - started, 3), "source_sha256": before, "jobs": results}
    output = target / "parameter-regression-report.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Consumer parameter regressions passed: {output}")


if __name__ == "__main__":
    main()
