"""Run and validate independent transform-model proofs and their product bridge."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading

from math_proof import ROOT, CASES, digest, inside, relative, successful_run


METHOD = "SAW transform-model proofs with checked staged-product bridge"
ORDER = ["forward", "inverse", "bridge"]
PROCESSES = set()
PROCESS_LOCK = threading.Lock()
STOPPING = threading.Event()


def family_order(family):
    return (["forward", "inverse", "linearity", "shift", "recurrence", "sums", "diffs"]
            if family == "math" else ORDER)


def slice_marker(family, label):
    return f"Verified standalone {'mathematical' if family == 'math' else 'model'} slice: {label}"


def coverage_marker(family, node):
    return f"Verified covered {'mathematical component' if family == 'math' else 'transform model'}: {node}"


def merge_hashes(target, checked):
    for name in target.keys() & checked.keys():
        if target[name] != checked[name]:
            raise ValueError(f"Model proofs used different {name}")
    target.update(checked)


def freeze_core(core, output):
    sha = digest(core)
    artifact = output / "artifacts" / f"{sha}.core"
    artifact.parent.mkdir(exist_ok=True)
    if not artifact.exists():
        shutil.copyfile(core, artifact)
    return {"path": relative(artifact), "sha256": sha}


def checked_job(record, entry, marker, case, output, selector):
    path = inside(record["report"])
    if digest(path) != record["report_sha256"]:
        raise ValueError("Changed model run report")
    report, hashes = successful_run(path, entry, CASES[case], marker)
    if report.get("math_context") != {"output": str(output), "component": selector}:
        raise ValueError("Wrong model selector or output directory")
    for export in record["exports"].values():
        if digest(inside(export["path"])) != export["sha256"]:
            raise ValueError("Changed model proposition export")
    return report, hashes


def validate_sliced(case, node, record, output, family="model"):
    if record.get("family", "model") != family:
        raise ValueError("Wrong proof-partition family")
    size = record["size"]
    n = int(case.split("-")[0])
    if not isinstance(size, int) or size <= 0 or n % size:
        raise ValueError("Invalid model partition size")
    offsets = list(range(0, n, size))
    parts = record["parts"]
    if [part["offset"] for part in parts] != offsets:
        raise ValueError("Model partition has missing, duplicate, or reordered outputs")
    hashes, inputs = {}, {}
    selector = str(family_order(family).index(node))
    for part in parts:
        offset = part["offset"]
        label = f"{node}-{offset}-{size}"
        report, checked = checked_job(part, f"{family}-slice-{case}.saw",
            slice_marker(family, label), case, output, selector)
        if report.get("model_slice") != {"offset": str(offset), "count": str(size)}:
            raise ValueError("Wrong model output partition selector")
        if set(part["exports"]) != {f"{label}.core"}:
            raise ValueError("Wrong partition proposition export")
        inputs[f"{label}.core"] = part["exports"][f"{label}.core"]["sha256"]
        merge_hashes(hashes, checked)
    coverage = record["coverage"]
    report, checked = checked_job(coverage, f"{family}-coverage-{case}.saw",
        coverage_marker(family, node), case, output, selector)
    if report.get("model_coverage") != {"size": str(size)} or coverage["inputs"] != inputs:
        raise ValueError("Unmatched model partition coverage premises")
    if set(coverage["exports"]) != {f"{node}.core", f"{node}-coverage.core"}:
        raise ValueError("Incomplete model coverage exports")
    if record["output"] != coverage["exports"][f"{node}.core"] or record["inputs"]:
        raise ValueError("Unmatched covered model proposition")
    merge_hashes(hashes, checked)
    return hashes


def blueprint(case, node):
    if node == "bridge":
        return (f"model-bridge-{case}.saw",
                "Verified conditional staged-product bridge with both matched model premises")
    return f"model-component-{case}.saw", f"Verified standalone transform model: {node}"


def inputs_for(node, nodes):
    if node != "bridge":
        return {}
    return {f"{name}.core": nodes[name]["output"]["sha256"] for name in ORDER[:2]}


def validate_node(case, node, record, output, nodes):
    if record.get("kind") == "sliced":
        if node not in ORDER[:2]:
            raise ValueError("Only transform models may use output partitions")
        return validate_sliced(case, node, record, output)
    entry, marker = blueprint(case, node)
    path = inside(record["report"])
    if digest(path) != record["report_sha256"]:
        raise ValueError(f"Changed model run report: {node}")
    report, hashes = successful_run(path, entry, CASES[case], marker)
    selector = str(ORDER.index(node)) if node != "bridge" else None
    if report.get("math_context") != {"output": str(output), "component": selector}:
        raise ValueError(f"Wrong model selector or output directory: {node}")
    if digest(inside(record["output"]["path"])) != record["output"]["sha256"]:
        raise ValueError(f"Changed model proposition export: {node}")
    if record["inputs"] != inputs_for(node, nodes):
        raise ValueError("Unmatched transform-model premise")
    return hashes


def validate_graph(path, case):
    result = json.loads(inside(path).read_text())
    if result.get("method") != METHOD or result.get("case") != case or result.get("status") != "passed":
        raise ValueError("Not a completed model proof graph for this case")
    nodes = result["nodes"]
    if set(nodes) != set(ORDER):
        raise ValueError("Transform-model proof graph is incomplete")
    hashes = {}
    for node in ORDER:
        checked = validate_node(case, node, nodes[node], inside(result["output"]), nodes)
        for name in hashes.keys() & checked.keys():
            if hashes[name] != checked[name]:
                raise ValueError(f"Model proofs used different {name}")
        hashes.update(checked)
    required = {"verification/multiplication-spec.saw", "verification/staged-product.saw"}
    if not required.issubset(hashes) or hashes != result["source_sha256"]:
        raise ValueError("Model proof source inventory or shared product boundary differs")
    return result, hashes


def save_record(case, node, report_path, output, nodes):
    entry, marker = blueprint(case, node)
    successful_run(report_path, entry, CASES[case], marker)
    return {"report": relative(report_path), "report_sha256": digest(report_path),
            "inputs": inputs_for(node, nodes),
            "output": freeze_core(output / f"{node}.core", output)}


def run_node(case, node, output, nodes, args):
    inputs = inputs_for(node, nodes)
    for name, sha in inputs.items():
        if digest(output / name) != sha:
            raise ValueError(f"Changed model premise: {name}")
    entry, _ = blueprint(case, node)
    env = os.environ.copy()
    env["NTT_MATH_OUTPUT"] = str(output)
    env.pop("NTT_MATH_COMPONENT", None)
    if node != "bridge":
        env["NTT_MATH_COMPONENT"] = str(ORDER.index(node))
    small = case == "8-17" or node == "bridge"
    command = [sys.executable, str(ROOT / "verification/run-isolated.py"),
               str(ROOT / "verification" / entry), "--seconds", "300" if small else "3700",
               "--heap", "2G" if small else args.heap]
    if args.keep_awake:
        command.append("--keep-awake")
    if args.compact:
        command.append("--compact")
    if args.nursery:
        command.extend(["--nursery", args.nursery])
    print(f"Starting model {case}: {node}", flush=True)
    report = execute(command, env)
    for name, sha in inputs.items():
        if digest(output / name) != sha:
            raise ValueError(f"Model premise changed while proving {node}")
    return save_record(case, node, report, output, nodes)


def execute(command, env):
    log = None
    with PROCESS_LOCK:
        if STOPPING.is_set():
            raise RuntimeError("Model worker canceled")
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1,
                                   start_new_session=True)
        PROCESSES.add(process)
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            if line.startswith("Log: "):
                log = Path(line.removeprefix("Log: ").strip())
        code = process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=30)
        with PROCESS_LOCK:
            PROCESSES.discard(process)
    if code or log is None:
        raise RuntimeError(f"Model job failed (exit {code}); completed nodes remain cached")
    return log.with_suffix(".json")


def run_partition_job(case, node, output, args, offset=None, inputs=None, family="model"):
    env = os.environ.copy()
    for key in ("NTT_MODEL_SLICE_OFFSET", "NTT_MODEL_SLICE_COUNT", "NTT_MODEL_COVERAGE_SIZE"):
        env.pop(key, None)
    env["NTT_MATH_OUTPUT"] = str(output)
    env["NTT_MATH_COMPONENT"] = str(family_order(family).index(node))
    if offset is None:
        entry = f"{family}-coverage-{case}.saw"
        env["NTT_MODEL_COVERAGE_SIZE"] = str(args.slice_size)
        names = [f"{node}.core", f"{node}-coverage.core"]
    else:
        entry = f"{family}-slice-{case}.saw"
        env["NTT_MODEL_SLICE_OFFSET"] = str(offset)
        env["NTT_MODEL_SLICE_COUNT"] = str(args.slice_size)
        names = [f"{node}-{offset}-{args.slice_size}.core"]
    command = [sys.executable, str(ROOT / "verification/run-isolated.py"),
               str(ROOT / "verification" / entry), "--seconds", "700",
               "--heap", args.slice_heap, "--nursery", args.nursery or "32M"]
    if args.keep_awake:
        command.append("--keep-awake")
    if args.compact:
        command.append("--compact")
    for name, sha in (inputs or {}).items():
        if digest(output / name) != sha:
            raise ValueError(f"Changed partition premise: {name}")
    report = execute(command, env)
    for name, sha in (inputs or {}).items():
        if digest(output / name) != sha:
            raise ValueError(f"Partition premise changed while proving: {name}")
    record = {"report": relative(report), "report_sha256": digest(report),
              "exports": {name: freeze_core(output / name, output) for name in names}}
    if offset is None:
        record["inputs"] = inputs
    else:
        record["offset"] = offset
    return record


def run_sliced(case, node, output, args, family="model"):
    n = int(case.split("-")[0])
    if args.slice_size <= 0 or n % args.slice_size:
        raise ValueError("--slice-size must be positive and divide the transform length")
    part_cache = output / f"{node}-parts-{args.slice_size}.json"
    parts = json.loads(part_cache.read_text()) if part_cache.exists() else {}
    pending = []
    for offset in range(0, n, args.slice_size):
        label = f"{node}-{offset}-{args.slice_size}"
        try:
            part = parts[str(offset)]
            report, _ = checked_job(part, f"{family}-slice-{case}.saw",
                slice_marker(family, label), case, output, str(family_order(family).index(node)))
            if (part["offset"] != offset or set(part["exports"]) != {f"{label}.core"}
                    or report.get("model_slice") != {"offset": str(offset), "count": str(args.slice_size)}):
                raise ValueError("Wrong cached partition")
            print(f"Reusing checked model partition: {label}", flush=True)
        except (ValueError, KeyError, OSError):
            pending.append(offset)
    executor = ThreadPoolExecutor(max_workers=args.workers)
    futures = {}
    completed = False
    try:
        futures = {executor.submit(run_partition_job, case, node, output, args, offset, None, family): offset
                   for offset in pending}
        for future in as_completed(futures):
            offset = futures[future]
            parts[str(offset)] = future.result()
            part_cache.write_text(json.dumps(parts, indent=2) + "\n")
            print(f"Saved model partition {node}: {offset}/{n}", flush=True)
        completed = True
    finally:
        if not completed:
            STOPPING.set()
        for future in futures:
            future.cancel()
        with PROCESS_LOCK:
            for process in PROCESSES:
                if process.poll() is None:
                    process.terminate()
        executor.shutdown(wait=True, cancel_futures=True)
    selected = [parts[str(offset)] for offset in range(0, n, args.slice_size)]
    inputs = {}
    for part in selected:
        for name, artifact in part["exports"].items():
            shutil.copyfile(inside(artifact["path"]), output / name)
            inputs[name] = artifact["sha256"]
    coverage = run_partition_job(case, node, output, args, inputs=inputs, family=family)
    return {"kind": "sliced", "family": family, "size": args.slice_size, "parts": selected,
            "coverage": coverage, "inputs": {}, "output": coverage["exports"][f"{node}.core"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=["8-17", "2048-12289", "2048-151019521"])
    parser.add_argument("--heap", default="10G")
    parser.add_argument("--nursery")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--keep-awake", action="store_true")
    parser.add_argument("--slice-size", type=int, help="prove models in blocks of output coefficients")
    parser.add_argument("--slice-heap", default="2G")
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--only", nargs="+", choices=ORDER)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--forward-report", type=Path, help="adopt an already successful standalone forward-model run")
    parser.add_argument("--inverse-report", type=Path, help="adopt an already successful standalone inverse-model run")
    args = parser.parse_args()
    controller_hash = digest(Path(__file__))
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        if args.check:
            validate_graph(args.check, args.case)
            print(f"Validated complete transform-model proof graph: {args.check}")
            return
        output = inside(args.output_dir) if args.output_dir else ROOT / "target/verification-models" / args.case
        output.mkdir(parents=True, exist_ok=True)
        cache = output / "nodes.json"
        nodes = json.loads(cache.read_text()) if cache.exists() else {}
        if args.keep_awake:
            if sys.platform != "darwin" or not shutil.which("caffeinate"):
                parser.error("--keep-awake requires macOS caffeinate")
            subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for node in ORDER:
            if args.only and node not in args.only:
                continue
            supplied = args.forward_report if node == "forward" else (
                args.inverse_report if node == "inverse" else None)
            if supplied:
                nodes[node] = save_record(args.case, node, inside(supplied), output, nodes)
            else:
                try:
                    validate_node(args.case, node, nodes[node], output, nodes)
                    print(f"Reusing checked model {args.case}: {node}", flush=True)
                except (ValueError, KeyError, OSError):
                    if args.slice_size and node in ORDER[:2]:
                        nodes[node] = run_sliced(args.case, node, output, args)
                    else:
                        nodes[node] = run_node(args.case, node, output, nodes, args)
            validate_node(args.case, node, nodes[node], output, nodes)
            cache.write_text(json.dumps(nodes, indent=2) + "\n")
            shutil.copyfile(inside(nodes[node]["output"]["path"]), output / f"{node}.core")
        if set(nodes) != set(ORDER):
            print("Saved checked model nodes; remaining: " + ", ".join(n for n in ORDER if n not in nodes))
            return
        hashes = {}
        for node in ORDER:
            hashes.update(validate_node(args.case, node, nodes[node], output, nodes))
        result = {"status": "passed", "method": METHOD, "case": args.case,
                  "output": relative(output), "nodes": nodes,
                  "source_sha256": hashes, "controller_sha256": controller_hash}
        result_path = output / "model-result.json"
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        validate_graph(result_path, args.case)
        print(f"Verified complete transform-model proof graph: {result_path}", flush=True)
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Model controller interrupted; completed nodes remain cached.\n")


if __name__ == "__main__":
    main()
