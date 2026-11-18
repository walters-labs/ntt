#!/usr/bin/env python3
"""Build and verify the three consumer root selections with exact provenance."""

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
    target = root / "target/verification-root-selection"
    target.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("CARGO_NET_OFFLINE", "true")
    if not (here / "Cargo.lock").exists():
        subprocess.run(["cargo", "+nightly-2026-03-21", "generate-lockfile"],
                       cwd=here, env=env, check=True, timeout=120)
    sources = sorted((root / "src").rglob("*.rs"))
    sources += [root / "verification/harness.rs", root / "Cargo.toml",
                root / "verification/consumer-roots.saw", root / "verification/run-isolated.py"]
    if (root / "Cargo.lock").exists():
        sources.append(root / "Cargo.lock")
    sources += sorted((root / "verification").glob("*.cry"))
    sources += sorted(p for p in here.rglob("*") if p.is_file() and
                      (p.suffix in {".rs", ".py", ".json", ".patch"} or
                       p.name in {"Cargo.toml", "Cargo.lock"}))
    before = {str(p.relative_to(root)): digest(p) for p in sources}
    started = time.monotonic()
    command = ["cargo", "+nightly-2026-03-21", "saw-build", "--lib", "--target-dir",
               str(target / "build"), "--message-format=json"]
    with (target / "build-artifacts.jsonl").open("w") as output:
        subprocess.run(command, cwd=here, env=env, stdout=output, check=True, timeout=180)
    artifacts = []
    for line in (target / "build-artifacts.jsonl").read_text().splitlines():
        event = json.loads(line)
        if (event.get("reason") == "compiler-artifact" and
                event.get("target", {}).get("name") == "ntt_consumer_roots_proof" and
                "lib" in event.get("target", {}).get("kind", []) and
                event.get("profile", {}).get("test") and event.get("executable")):
            artifacts.append(Path(event["executable"] + ".linked-mir.json"))
    if len(artifacts) != 1 or not artifacts[0].is_file():
        raise SystemExit("Expected exactly one proof-library MIR artifact")
    mir_hash = digest(artifacts[0])
    mir = target / "artifacts" / f"{mir_hash}.linked-mir.json"
    mir.parent.mkdir(exist_ok=True)
    if not mir.exists():
        shutil.copyfile(artifacts[0], mir)
    if digest(mir) != mir_hash:
        raise SystemExit("MIR artifact hash mismatch")
    run = subprocess.run([sys.executable, "verification/run-isolated.py", "verification/consumer-roots.saw",
                          "--mir", str(mir), "--heap", "2G", "--seconds", "120", "--detect-vacuity"],
                         cwd=root, env=env, capture_output=True, text=True)
    print(run.stdout, end="")
    if run.returncode:
        print(run.stderr, file=sys.stderr)
        raise SystemExit(run.returncode)
    log = Path(re.search(r"^Log: (.+)$", run.stdout, re.MULTILINE).group(1))
    report_path = log.with_suffix(".json")
    report = json.loads(report_path.read_text())
    transcript = log.read_text()
    if (report["status"] != "passed" or report["mir_sha256"] != mir_hash or
            transcript.count("Proof succeeded!") != 6 or
            "Verified root selection and validator acceptance for all three fixed configurations" not in transcript):
        raise SystemExit("Incomplete root-selection proof")
    subprocess.run(["cargo", "+nightly-2026-03-21", "test", "--target-dir", str(target / "native")],
                   cwd=here, env=env, check=True, timeout=120)
    for name, sha in before.items():
        if digest(root / name) != sha:
            raise SystemExit(f"Source changed during verification: {name}")
    if digest(mir) != mir_hash:
        raise SystemExit("MIR changed during verification")
    result = {
        "status": "passed", "scope": "three fixed root selections and validator acceptance; generic fallback excluded",
        "source_sha256": before, "build_command": command,
        "mir_path": str(mir.relative_to(root)), "mir_sha256": mir_hash,
        "proof_report": str(report_path.relative_to(root)), "proof_report_sha256": digest(report_path),
        "proof_log": str(log.relative_to(root)), "proof_log_sha256": digest(log),
        "mir_contracts": 6, "native_tests": 2,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "proof_wall_seconds": report["wall_elapsed_seconds"],
        "proof_child_max_rss_bytes": report["child_max_rss_bytes"],
    }
    output = target / "root-selection-report.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Root-selection milestone passed: {output}")


if __name__ == "__main__":
    main()
