#!/usr/bin/env python3
"""Build the current Rust library for SAW and record its exact MIR provenance."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-dir", type=Path, default=root / "target/verification-split")
    args = parser.parse_args()
    target = args.target_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    sources = sorted((root / "src").rglob("*.rs"))
    sources += [root / "verification/harness.rs", root / "Cargo.toml"]
    if (root / "Cargo.lock").exists():
        sources.append(root / "Cargo.lock")
    before = {str(p.relative_to(root)): digest(p) for p in sources}
    command = ["cargo", "+nightly-2026-03-21", "saw-build", "--lib",
               "--target-dir", str(target), "--message-format=json"]
    env = os.environ.copy()
    env.setdefault("CARGO_NET_OFFLINE", "true")
    artifact_log = target / "artifacts.jsonl"
    with artifact_log.open("w") as output:
        subprocess.run(command, cwd=root, env=env, stdout=output, check=True)
    for name, sha in before.items():
        if digest(root / name) != sha:
            raise SystemExit(f"Build input changed during compilation: {name}")
    before["Cargo.lock"] = digest(root / "Cargo.lock")
    artifacts = []
    for line in artifact_log.read_text().splitlines():
        event = json.loads(line)
        if (event.get("reason") == "compiler-artifact"
                and event.get("target", {}).get("name") == "ntt"
                and "lib" in event.get("target", {}).get("kind", [])
                and event.get("profile", {}).get("test") and event.get("executable")):
            artifacts.append(Path(event["executable"] + ".linked-mir.json"))
    if len(artifacts) != 1 or not artifacts[0].is_file():
        raise SystemExit("Expected exactly one current NTT library MIR artifact")
    built_mir = artifacts[0].resolve()
    mir_hash = digest(built_mir)
    # Rebuilds can change MIR bytes even for unchanged Rust sources. Preserve
    # the exact verified artifact instead of letting a later build overwrite it.
    mir = target / "artifacts" / f"{mir_hash}.linked-mir.json"
    mir.parent.mkdir(parents=True, exist_ok=True)
    if not mir.exists():
        shutil.copyfile(built_mir, mir)
    if digest(mir) != mir_hash:
        raise SystemExit("Stored MIR artifact failed its hash check")
    report = {"status": "passed", "command": command, "source_sha256": before,
              "mir_path": str(mir), "mir_sha256": mir_hash}
    (target / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(mir)


if __name__ == "__main__":
    main()
