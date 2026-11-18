#!/usr/bin/env python3
"""Audit the archived 1024-point proof against current implementation/specs.

Later changes to proof tactics do not change an already proved statement.
Require the complete original proof-source snapshot, while requiring today's
implementation and mathematical interface to match the original run. The old
proof harness must be preserved with only the six known 2048 wrappers appended.
This validates retained evidence; it does not replay SAW or import a theorem.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile


ROOT = Path(__file__).resolve().parent.parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def audit(archive):
    with tarfile.open(archive) as saved:
        files = {m.name: saved.extractfile(m).read() for m in saved.getmembers() if m.isfile()}
    manifest = json.loads(files["manifest.json"])
    if set(files) != set(manifest) | {"manifest.json"}:
        raise ValueError("Archive manifest does not cover every saved file")
    for name, expected in manifest.items():
        if sha(files[name]) != expected:
            raise ValueError(f"Changed archive member: {name}")
    prefix = "source/2026-11-16/"
    pair_name = "target/verification-isolated/paired-1024-12289-20261116T235742904639Z.json"
    pair = json.loads(files[pair_name])
    if pair["status"] != "passed" or pair["case"] != "1024-12289":
        raise ValueError("Missing successful original proof gate")
    if sha(files[prefix + "verification/check-split.py"]) != pair["checker_sha256"]:
        raise ValueError("Changed original validator")
    original_root = Path(pair["math_report"]).parents[2]

    def relative(name):
        path = Path(name)
        return str(path.relative_to(original_root)) if path.is_absolute() else str(path)

    records = {}
    for kind in ("math", "rust", "build"):
        name = relative(pair[kind + "_report"])
        if sha(files[name]) != pair[kind + "_report_sha256"]:
            raise ValueError(f"Changed original {kind} report")
        records[kind] = json.loads(files[name])
    bindings = {}
    for kind, entry, marker in [
        ("math", "convolution-1024.saw", "Verified complete 1024-point convolution theorem and multiplication specification bridge"),
        ("rust", "spectral-1024-12289.saw", "Verified Rust multiplication against shared spectral product for all i64 inputs: 1024_12289"),
    ]:
        report = records[kind]
        if report["status"] != "passed" or report["exit_code"] != 0:
            raise ValueError("Original proof did not pass")
        source = "verification/" + entry
        if (str(original_root / source) not in report["command"] or
                sha(files[prefix + source]) != report["entry_script_sha256"]):
            raise ValueError("Changed original proof entry")
        transcript = files[report["log"]].decode()
        if marker not in transcript:
            raise ValueError("Incomplete original proof transcript")
        loaded = {relative(name) for name in re.findall(r'^Loading file "([^"]+)"', transcript, re.MULTILINE)}
        if not {source, "verification/multiplication-spec.saw"}.issubset(loaded):
            raise ValueError("Missing shared product definition")
        loaded |= {"verification/NttSpec.cry", "verification/Ntt1024.cry"}
        if kind == "rust":
            if "--detect-vacuity" not in report["command"]:
                raise ValueError("Original MIR run did not check vacuity")
            loaded |= {name[len(prefix):] for name in files if name.startswith(prefix + "src/") and name.endswith(".rs")}
            loaded |= {"Cargo.toml", "Cargo.lock", "verification/harness.rs"}
        for name in loaded:
            expected = report["source_sha256"].get(name)
            if expected is None or sha(files[prefix + name]) != expected:
                raise ValueError(f"Changed original proof dependency: {name}")
            if name in bindings and bindings[name] != expected:
                raise ValueError("Original proof layers used different source versions")
            bindings[name] = expected
    build, rust = records["build"], records["rust"]
    if build["status"] != "passed" or build["mir_sha256"] != rust["mir_sha256"] or pair["mir_sha256"] != rust["mir_sha256"]:
        raise ValueError("Original build and MIR proof disagree")
    mir_member = "target/verification-split/artifacts/" + rust["mir_sha256"] + ".linked-mir.json"
    if sha(files[mir_member]) != rust["mir_sha256"]:
        raise ValueError("Changed original linked MIR")
    if any(bindings.get(name) != expected for name, expected in build["source_sha256"].items()):
        raise ValueError("Original build inputs disagree with the MIR proof")
    harness_name = "verification/harness.rs"
    original_harness = files[prefix + harness_name]
    current_harness = (ROOT / harness_name).read_bytes()
    added = []
    for modulus, root in [(12289, 1945), (151019521, 51689479)]:
        for operation, function in [("forward", "ntt"), ("inverse", "intt"), ("multiply", "polymul_ntt")]:
            parameters = "a: [i64; 2048]" + (", b: [i64; 2048]" if operation == "multiply" else "")
            arguments = f"&a, &b, 2048, {modulus}, {root}" if operation == "multiply" else f"&a, {root}, 2048, {modulus}"
            added.append(f'''#[allow(dead_code)]
pub fn {operation}_2048_{modulus}({parameters}) -> [i64; 2048] {{
    let result = crate::{function}({arguments});
    let mut out = [0; 2048];
    out.copy_from_slice(&result);
    out
}}''')
    expected_harness = original_harness + ("\n" + "\n\n".join(added) + "\n").encode()
    if current_harness not in (original_harness, expected_harness):
        raise ValueError("Current harness changes the archived wrappers or adds unexpected code")
    current_names = (set(build["source_sha256"]) - {harness_name}) | {
        "verification/NttSpec.cry", "verification/Ntt1024.cry", "verification/multiplication-spec.saw"}
    current = {name: sha((ROOT / name).read_bytes()) for name in sorted(current_names)}
    if any(value != bindings[name] for name, value in current.items()):
        raise ValueError("Current implementation or mathematical interface differs from the proved version")
    changed_tactics = sorted(name for name, expected in bindings.items()
                             if name.endswith(".saw") and sha((ROOT / name).read_bytes()) != expected)
    return {"status": "passed", "scope": "Historical proof evidence with unchanged current implementation and mathematical interface",
            "archive": str(archive.relative_to(ROOT)), "archive_sha256": sha(archive.read_bytes()),
            "manifest_members": len(manifest), "current_source_sha256": current,
            "harness": {"archived_sha256": sha(original_harness), "current_sha256": sha(current_harness),
                        "extension": "Only the six known 2048-point wrappers may be appended"},
            "historical_proof_dependencies": bindings, "later_changed_proof_scripts": changed_tactics,
            "mir_sha256": rust["mir_sha256"], "checker_sha256": sha(Path(__file__).read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(ROOT / "verification/results/2026-11-16.tar.gz")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Audited archived 1024-point proof against current implementation: {args.output}")


if __name__ == "__main__":
    main()
