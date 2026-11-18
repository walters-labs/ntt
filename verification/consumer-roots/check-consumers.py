#!/usr/bin/env python3
"""Compile the patched consumer libraries and test their actual default roots."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


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
    target = root / "target/verification-root-selection"
    smoke = target / "smoke"
    (smoke / "src").mkdir(parents=True, exist_ok=True)
    # JSON strings are also valid TOML basic strings for these local paths.
    quoted = {name: json.dumps(str(path)) for name, path in checkouts.items()}
    (smoke / "Cargo.toml").write_text(f'''[package]
name = "consumer-root-smoke"
version = "0.0.0"
edition = "2021"
publish = false

[dependencies]
ntt = {{ path = {json.dumps(str(root))} }}
module-lwe = {{ path = {quoted["module-lwe"]} }}
ring-lwe = {{ path = {quoted["ring-lwe"]} }}

[patch.crates-io]
ntt = {{ path = {json.dumps(str(root))} }}
ring-lwe = {{ path = {quoted["ring-lwe"]} }}
''')
    (smoke / "src/lib.rs").write_bytes((here / "smoke.rs").read_bytes())
    env = os.environ.copy()
    env.setdefault("CARGO_NET_OFFLINE", "true")
    subprocess.run(["cargo", "generate-lockfile"], cwd=smoke, env=env, check=True, timeout=120)
    sources = list((root / "src").rglob("*.rs")) + [root / "Cargo.toml"]
    for checkout in checkouts.values():
        sources += list((checkout / "src").rglob("*.rs")) + [checkout / "Cargo.toml"]
    sources += [here / "apply.py", here / "consumers.json", here / "roots.rs", here / "smoke.rs",
                Path(__file__).resolve(), smoke / "Cargo.toml", smoke / "Cargo.lock", smoke / "src/lib.rs"]
    before = {str(p): digest(p) for p in sources}
    command = ["cargo", "test", "--locked", "--target-dir", str(target / "consumer-native")]
    log = target / "consumer-smoke.log"
    with log.open("w") as output:
        subprocess.run(command, cwd=smoke, env=env, stdout=output, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    for name, sha in before.items():
        if digest(Path(name)) != sha:
            raise SystemExit(f"Source changed during smoke test: {name}")
    result = {"status": "passed", "scope": "native test of two actual default constructors; not a consumer proof",
              "command": command, "source_sha256": before, "log_sha256": digest(log)}
    (target / "consumer-smoke-report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(log.read_text())


if __name__ == "__main__":
    main()
