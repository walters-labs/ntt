#!/usr/bin/env python3
"""Strictly validate all closed consumer-bridge proofs and proposition links.

SAW 1.6 check_convertible prints a result and returns unit even on mismatch.
Successful process exit alone does not validate those proposition boundaries.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("consumer_bridge", ROOT / "verification/consumer-composition/run.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def conversions(transcript, expected):
    matches = re.findall(r"(?m)^(?:\[[^\]\n]*\]\s*)?(Not convertible|Convertible)\s*$", transcript)
    if matches != ["Convertible"] * expected:
        raise ValueError(f"Proposition matches differ: expected {expected} Convertible results, found {matches}")


def check(report):
    sources = bridge.sources()
    fingerprint = bridge.hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    if (report.get("status") != "passed" or report.get("source_sha256") != sources or
            report.get("input_digest") != fingerprint):
        raise ValueError("Incomplete checkpoint or changed proof inputs")
    nodes = report["nodes"]
    if [n["task"] for n in nodes] != bridge.tasks():
        raise ValueError("Missing, duplicated, or reordered proof tasks")
    completed, match_count = [], 0
    for task, node in zip(bridge.tasks(), nodes):
        predecessor_kind = "block" if task["kind"] == "coverage" else "coverage"
        predecessors = [] if task["kind"] == "block" else [
            n for n in completed if n["task"]["case"] == task["case"] and n["task"]["kind"] == predecessor_kind]
        premises = {bridge.identity(n["task"]): bridge.node_digest(n)
                    for n in sorted(predecessors, key=lambda n: bridge.identity(n["task"]))}
        bridge.validate(task, node, fingerprint, premises)
        expected = task["n"] // 64 if task["kind"] == "coverage" else 1 if task["kind"] == "normalized" else 0
        conversions((ROOT / node["log"]).read_text(), expected)
        match_count += expected
        completed.append(node)
    if (report["closed_blocks"] != 80 or report["output_coefficients"] != 2560 or
            report["coverage_implications"] != 3 or report["normalization_implications"] != 3):
        raise ValueError("Wrong proof coverage counts")
    return {"status": "passed", "closed_blocks": 80, "output_coefficients": 2560,
            "matched_proposition_boundaries": match_count,
            "maximum_child_rss_bytes": max(n["rss_bytes"] for n in nodes),
            "checker_sha256": bridge.digest(Path(__file__))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=bridge.TARGET / "bridge-report.json")
    parser.add_argument("--output", type=Path, default=bridge.TARGET / "strict-check.json")
    parser.add_argument("--negative-controls", action="store_true")
    parser.add_argument("--conversion-log", type=Path, help="check only a transcript's proposition-match results")
    parser.add_argument("--expected-checks", type=int)
    args = parser.parse_args()
    try:
        if args.conversion_log:
            if args.expected_checks is None or args.expected_checks < 0:
                parser.error("--conversion-log requires nonnegative --expected-checks")
            conversions(args.conversion_log.read_text(), args.expected_checks)
            print("Validated exact proposition matches")
            return
        report = json.loads(args.report.read_text())
        result = check(report)
        result["report_sha256"] = bridge.digest(args.report)
        if args.negative_controls:
            result["metadata_controls"] = bridge.negative_controls(report["nodes"], report["input_digest"])
            controls = {}
            for name, text, count in [("missing_match", "", 1),
                                      ("wrong_proposition", "[00:00:00.000] Not convertible\n", 1),
                                      ("extra_match", "Convertible\nConvertible\n", 1)]:
                try:
                    conversions(text, count)
                except ValueError as error:
                    controls[name] = str(error)
                else:
                    raise ValueError(f"Accepted proposition-match negative control: {name}")
            result["proposition_controls"] = controls
        bridge.write(args.output, json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
