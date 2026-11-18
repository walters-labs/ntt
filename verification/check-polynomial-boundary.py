#!/usr/bin/env python3
"""Check the complete polynomial-boundary checkpoint without rerunning SAW."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "verification/polynomial-boundary/run.py"
spec = importlib.util.spec_from_file_location("polynomial_boundary", RUNNER)
boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boundary)


def check(report):
    if report.get("status") != "passed":
        raise ValueError("The boundary proof suite has not passed")
    sources = report["source_sha256"]
    if not sources or any(boundary.digest(ROOT / name) != sha for name, sha in sources.items()):
        raise ValueError("Source changed since the proof build")
    build_path = ROOT / report["build_report"]
    if boundary.digest(build_path) != report["build_report_sha256"]:
        raise ValueError("Changed build report")
    build = json.loads(build_path.read_text())
    source_key = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    if build_path.stem != source_key or build["source_sha256"] != sources:
        raise ValueError("Build does not bind the current sources")
    mir_hash = report["mir_sha256"]
    if (build["mir_sha256"] != mir_hash or build["mir_path"] != report["mir_path"] or
            boundary.digest(ROOT / report["mir_path"]) != mir_hash):
        raise ValueError("Changed linked MIR artifact")
    fingerprint = hashlib.sha256((source_key + mir_hash).encode()).hexdigest()
    if report["input_digest"] != fingerprint:
        raise ValueError("Wrong source/MIR fingerprint")
    nodes = report["nodes"]
    boundary.coverage(nodes)
    for task, node in zip(boundary.tasks(), nodes):
        boundary.validate(task, node, fingerprint, mir_hash)
        record = json.loads((ROOT / node["report"]).read_text())
        if (record["runner_sha256"] != boundary.digest(ROOT / "verification/run-isolated.py") or
                record["log"] != node["log"] or record["wall_elapsed_seconds"] != node["wall_seconds"] or
                record["child_max_rss_bytes"] != node["rss_bytes"]):
            raise ValueError("Proof metadata does not match its transcript or runner")
    contracts = sum(1 if n["task"]["kind"] == "constructor" else n["task"]["count"] for n in nodes)
    if contracts != 1540 or report["mir_contracts"] != contracts or report["native_tests"] != 4:
        raise ValueError("Wrong contract or regression count")
    native_log = ROOT / "target/verification-polynomial-boundary/boundary-native.log"
    if (boundary.digest(native_log) != report["native_log_sha256"] or
            "4 passed; 0 failed" not in native_log.read_text()):
        raise ValueError("Changed or unsuccessful native regression log")
    return {"status": "passed", "tasks": len(nodes), "mir_contracts": contracts,
            "padding_lengths": contracts - 2,
            "maximum_child_rss_bytes": max(n["rss_bytes"] for n in nodes)}


def negative_controls(report):
    controls = {}
    mutations = {
        "missing_batch": lambda r: r["nodes"].pop(),
        "duplicate_batch": lambda r: r["nodes"].append(copy.deepcopy(r["nodes"][-1])),
        "wrong_degree": lambda r: r["nodes"][-1]["task"].update(degree=512),
        "wrong_entry_hash": lambda r: r["nodes"][0].update(script_sha256="0" * 64),
        "wrong_transcript_hash": lambda r: r["nodes"][0].update(log_sha256="0" * 64),
        "wrong_native_log_hash": lambda r: r.update(native_log_sha256="0" * 64),
        "wrong_mir_hash": lambda r: r.update(mir_sha256="0" * 64),
    }
    for name, mutate in mutations.items():
        changed = copy.deepcopy(report)
        mutate(changed)
        try:
            check(changed)
        except ValueError as error:
            controls[name] = {"status": "rejected", "reason": str(error)}
        else:
            raise ValueError(f"Accepted negative control: {name}")
    return controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--negative-controls", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    result = check(report)
    result.update(report_sha256=boundary.digest(args.report), checker_sha256=boundary.digest(Path(__file__)))
    if args.negative_controls:
        result["negative_controls"] = negative_controls(report)
    if args.output:
        boundary.write(args.output, json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
