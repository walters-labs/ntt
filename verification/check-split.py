#!/usr/bin/env python3
"""Check the provenance and shared boundaries of successful SAW proof layers.

This records their logical connection; it does not import logs as SAW theorems
or replace any proof. Each conditional composition requires successful proofs
of all its premises, checked by the corresponding dependency-graph validator.
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re

from math_proof import METHOD as MATH_GRAPH_METHOD, check_instance_binding, validate_graph
from model_proof import validate_graph as validate_model_graph


ROOT = Path(__file__).resolve().parent.parent
CASES = {
    "8-17": (8, 17, "Ntt8.cry", "convolution-8-17.saw"),
    "1024-12289": (1024, 12289, "Ntt1024.cry", "convolution-1024.saw"),
    "2048-12289": (2048, 12289, "Ntt2048.cry", "convolution-2048-12289.saw"),
    "2048-151019521": (2048, 151019521, "Ntt2048_151019521.cry", "convolution-2048-151019521.saw"),
}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def freeze_report(path):
    # A later build or cache refresh may replace its convenient report path.
    # Validate immutable copies so completed pairs keep their exact evidence.
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    frozen = ROOT / "target/verification-isolated/reports" / f"{sha}.json"
    frozen.parent.mkdir(parents=True, exist_ok=True)
    if not frozen.exists():
        frozen.write_bytes(data)
    if digest(frozen) != sha:
        raise ValueError("Stored report failed its hash check")
    return frozen


def check_run(path, entry, cryptol, marker, rust=False, shared_spec="multiplication-spec.saw"):
    report = json.loads(path.read_text())
    if report["status"] != "passed" or report["exit_code"] != 0:
        raise ValueError(f"Not a successful proof run: {path}")
    script = ROOT / "verification" / entry
    if str(script) not in report["command"] or digest(script) != report["entry_script_sha256"]:
        raise ValueError(f"Entry script differs from the proved script: {entry}")
    log_path = (ROOT / report["log"]).resolve()
    if not log_path.is_relative_to(ROOT):
        raise ValueError("Proof log must be inside this repository")
    log = log_path.read_text()
    if marker not in log:
        raise ValueError(f"Missing completion marker in {log_path}")
    # SAW prints the files actually loaded. Ignore unrelated proof scripts in
    # the runner's broader source inventory; editing them need not force reruns.
    loaded = set()
    for name in re.findall(r'^Loading file "([^"]+)"', log, re.MULTILINE):
        source = (ROOT / name).resolve()
        loaded.add(str(source.relative_to(ROOT)))
    required = {f"verification/{entry}", f"verification/{shared_spec}"}
    if not required.issubset(loaded):
        raise ValueError("The shared multiplication specification was not loaded")
    check_instance_binding(((ROOT / name).read_text() for name in loaded if name.endswith(".saw")), cryptol)
    loaded.update([f"verification/{cryptol}", "verification/NttSpec.cry"])
    if rust:
        if "--detect-vacuity" not in report["command"]:
            raise ValueError("Rust verification must enable vacuity checking")
        loaded.update(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.rs"))
        loaded.update(["verification/harness.rs", "Cargo.toml", "Cargo.lock"])
        if digest(Path(report["mir_path"])) != report["mir_sha256"]:
            raise ValueError("The verified MIR artifact has changed")
    hashes = {}
    for name in sorted(loaded):
        expected = report["source_sha256"].get(name)
        if expected is None or digest(ROOT / name) != expected:
            raise ValueError(f"Proof dependency changed: {name}")
        hashes[name] = expected
    return report, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("math_report", type=Path)
    parser.add_argument("rust_report", type=Path)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--model-report", type=Path, help="required for Rust proofs against the staged operational model")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    n, q, cryptol, math_entry = CASES[args.case]
    try:
        args.math_report = freeze_report(args.math_report)
        args.rust_report = freeze_report(args.rust_report)
        args.build_report = freeze_report(args.build_report)
        if args.model_report:
            args.model_report = freeze_report(args.model_report)
        math_kind = json.loads(args.math_report.read_text()).get("method")
        if math_kind == MATH_GRAPH_METHOD:
            math, math_hashes = validate_graph(args.math_report, args.case)
        else:
            math, math_hashes = check_run(args.math_report, math_entry, cryptol,
                f"Verified complete {n}-point convolution theorem and multiplication specification bridge")
        model_hashes = {}
        if args.model_report:
            _, model_hashes = validate_model_graph(args.model_report, args.case)
            rust, rust_hashes = check_run(args.rust_report, f"staged-{args.case}.saw", cryptol,
                f"Verified Rust multiplication against staged product for all i64 inputs: {n}_{q}",
                rust=True, shared_spec="staged-product.saw")
        else:
            rust, rust_hashes = check_run(args.rust_report, f"spectral-{args.case}.saw", cryptol,
                f"Verified Rust multiplication against shared spectral product for all i64 inputs: {n}_{q}", rust=True)
        build = json.loads(args.build_report.read_text())
        if build["status"] != "passed" or build["mir_sha256"] != rust["mir_sha256"]:
            raise ValueError("Build provenance does not match the verified MIR")
        for name, sha in build["source_sha256"].items():
            if rust_hashes.get(name) != sha:
                raise ValueError(f"Verified Rust source differs from the build input: {name}")
        combined_hashes = {}
        for hashes in [math_hashes, model_hashes, rust_hashes]:
            for name in combined_hashes.keys() & hashes.keys():
                if combined_hashes[name] != hashes[name]:
                    raise ValueError(f"The proof layers used different versions of {name}")
            combined_hashes.update(hashes)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "target/verification-isolated" / f"paired-{args.case}-{stamp}.json"
    result = {
        "status": "passed", "case": args.case,
        "method": ("Checked convolution, transform-model, and Rust proofs connected by shared definitions"
                   if args.model_report else
                   "Checked mathematical and Rust proofs connected by the same spectral-product definition"),
        "math_report": str(args.math_report.resolve()), "math_report_sha256": digest(args.math_report),
        "rust_report": str(args.rust_report.resolve()), "rust_report_sha256": digest(args.rust_report),
        "build_report": str(args.build_report.resolve()), "build_report_sha256": digest(args.build_report),
        "checker_sha256": digest(Path(__file__).resolve()),
        "shared_spec_sha256": math_hashes["verification/multiplication-spec.saw"],
        "source_sha256": combined_hashes, "mir_sha256": rust["mir_sha256"],
        "validator_sha256": {name: digest(ROOT / name) for name in
            ["verification/check-split.py", "verification/math_proof.py", "verification/model_proof.py"]},
    }
    if args.model_report:
        result.update({"model_report": str(args.model_report),
                       "model_report_sha256": digest(args.model_report)})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Validated split proof for {args.case}: {output}")


if __name__ == "__main__":
    main()
