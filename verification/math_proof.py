"""Run and validate a graph of SAW mathematical proofs with explicit premises.

Core files contain propositions, never imported proof objects. SAW proves each
leaf, checks definitional equality at every edge, and proves the two closed
implications. The graph checker requires every premise's successful proof.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent.parent
METHOD = "SAW component proofs with checked conditional composition and spectral bridge"
CASES = {"8-17": "Ntt8.cry", "2048-12289": "Ntt2048.cry",
         "1024-151019521": "Ntt1024_151019521.cry",
         "2048-151019521": "Ntt2048_151019521.cry"}
COMPONENTS = ["forward", "inverse", "linearity", "shift", "recurrence", "sums", "diffs"]
ORDER = ["half", *COMPONENTS, "compose", "bridge"]


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def inside(path):
    path = (ROOT / path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Proof artifact outside repository: {path}")
    return path


def relative(path):
    return str(inside(path).relative_to(ROOT))


def blueprint(case, node, legacy=False, graph_half=False):
    if graph_half:
        return ("math-adapt-half-2048-151019521.saw",
                "Matched exported half-size theorem to the complete 1024-point proof graph", ["half.core"])
    if legacy == "half":
        return ("math-adapt-half-2048.saw",
                "Matched exported half-size theorem to the verified 1024-point checkpoint", ["half.core"])
    if legacy:
        return ("math-adapt-recurrence-2048.saw",
                "Matched exported recurrence to the previously proved predicate", ["recurrence.core"])
    if node in COMPONENTS:
        return (f"math-component-{case}.saw",
                f"Verified exported mathematical component: {node}", [f"{node}.core"])
    return {
        "half": (f"math-half-{case}.saw", "Verified exported half-size convolution theorem", ["half.core"]),
        "compose": (f"math-compose-{case}.saw",
                    "Verified conditional convolution composition with all eight matched premises",
                    ["composition.core", "convolution.core"]),
        "bridge": (f"math-bridge-{case}.saw",
                   "Verified conditional spectral bridge with matched convolution premise",
                   ["bridge.core", "spectral-identity.core"]),
    }[node]


def check_instance_binding(source_texts, cryptol):
    # A common template hash does not identify its concrete parameter instance.
    # Require the expected unqualified Ntt import throughout the loaded closure;
    # qualified imports (for example `as Old`) are checked at explicit edges.
    instances = {name for source in source_texts for name in re.findall(
        r'^\s*import\s+"(Ntt[^"\n]+\.cry)"\s*;', source, re.MULTILINE)}
    if instances != {cryptol}:
        raise ValueError(f"Proof parameter instances {sorted(instances)} differ from {cryptol}")


def successful_run(path, entry, cryptol, marker, extra_sources=()):
    path = inside(path)
    report = json.loads(path.read_text())
    script = ROOT / "verification" / entry
    if report["status"] != "passed" or report["exit_code"] != 0:
        raise ValueError(f"Unsuccessful SAW run: {path}")
    if str(script) not in report["command"] or digest(script) != report["entry_script_sha256"]:
        raise ValueError(f"Changed proof entry: {entry}")
    log = inside(report["log"]).read_text()
    if marker not in log:
        raise ValueError(f"Missing proof completion marker: {path}")
    loaded = {relative(name) for name in re.findall(r'^Loading file "([^"]+)"', log, re.MULTILINE)}
    loaded.update([f"verification/{entry}", f"verification/{cryptol}", "verification/NttSpec.cry"])
    loaded.update(extra_sources)
    check_instance_binding((inside(name).read_text() for name in loaded if name.endswith(".saw")), cryptol)
    hashes = {}
    for name in sorted(loaded):
        sha = report["source_sha256"].get(name)
        if sha is None or digest(inside(name)) != sha:
            raise ValueError(f"Changed mathematical proof dependency: {name}")
        hashes[name] = sha
    return report, hashes


def legacy_expression(path, pattern):
    matches = re.findall(pattern, Path(path).read_text(), re.DOTALL)
    if len(matches) != 1:
        raise ValueError(f"Unexpected legacy recurrence entry structure: {path}")
    return re.sub(r"\s+", "", matches[0])


def validate_legacy(path):
    report, hashes = successful_run(path, "recurrence-2048.saw", CASES["2048-12289"],
                                   "Verified 2048-point schoolbook convolution recurrence")
    old = legacy_expression(ROOT / "verification/recurrence-2048.saw",
        r"recurrence_verified <- prove_vector 64 n 2 \(math_formula\s*\{\{(.*?)\}\}\);")
    new = legacy_expression(ROOT / "verification/math-adapt-recurrence-2048.saw",
        r"let legacy_recurrence_statement = math_formula\s*\{\{(.*?)\}\};")
    if old != new:
        raise ValueError("The recurrence adapter differs from the previously proved predicate")
    return report, hashes


def validate_half_checkpoint(path, archive_path):
    """Validate the historical proof against its retained source, not new tactics.

    Its mathematical definitions and convolution factory must still match the
    current ones. The separate SAW adapter checks the exact cross-instance
    proposition; changed historical implementation files remain inside the
    hash-pinned archive rather than masquerading as current source files.
    """
    path, archive_path = inside(path), inside(archive_path)
    report_bytes = path.read_bytes()
    report = json.loads(report_bytes)
    with tarfile.open(archive_path, "r:gz") as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        def read(name):
            data = archive.extractfile(name).read()
            if hashlib.sha256(data).hexdigest() != manifest[name]:
                raise ValueError(f"Changed historical archive member: {name}")
            return data
        archived_report = str(Path(report["log"]).with_suffix(".json"))
        if read(archived_report) != report_bytes:
            raise ValueError("Half-size checkpoint differs from its archived successful report")
        if report["status"] != "passed" or report["exit_code"] != 0:
            raise ValueError("Half-size checkpoint was not successful")
        entry = "verification/convolution-1024.saw"
        if (str(ROOT / entry) not in report["command"]
                or digest(ROOT / entry) != report["entry_script_sha256"]):
            raise ValueError("Unexpected historical half-size proof entry")
        log = read(report["log"]).decode()
        if ("Verified cyclic convolution theorem at length 1024" not in log
                or "Verified complete 1024-point convolution theorem and multiplication specification bridge" not in log):
            raise ValueError("Historical checkpoint did not finish the required theorem")
        loaded = {relative(name) for name in re.findall(r'^Loading file "([^"]+)"', log, re.MULTILINE)}
        loaded.update([entry, "verification/Ntt1024.cry", "verification/NttSpec.cry"])
        instance_sources = []
        for name in loaded:
            data = read("source/2026-11-16/" + name)
            if hashlib.sha256(data).hexdigest() != report["source_sha256"].get(name):
                raise ValueError(f"Historical proof source differs from its report: {name}")
            if name.endswith(".saw"):
                instance_sources.append(data.decode())
        check_instance_binding(instance_sources, "Ntt1024.cry")
        hashes = {relative(archive_path): digest(archive_path)}
        for name in [entry, "verification/convolution.saw", "verification/Ntt1024.cry", "verification/NttSpec.cry"]:
            if digest(ROOT / name) != report["source_sha256"].get(name):
                raise ValueError(f"Historical half-size theorem definition changed: {name}")
            hashes[name] = digest(ROOT / name)
    return report, hashes


def inputs_for(node, nodes):
    if node == "compose":
        return {f"{name}.core": nodes[name]["outputs"][f"{name}.core"]["sha256"]
                for name in ["half", *COMPONENTS]}
    if node == "bridge":
        return {"convolution.core": nodes["compose"]["outputs"]["convolution.core"]["sha256"]}
    return {}


def validate_node(case, name, record, output, nodes):
    if record.get("kind") == "sliced":
        if name not in ("forward", "inverse", "recurrence") or record.get("legacy"):
            raise ValueError("Unsupported partitioned mathematical node")
        if record.get("outputs") != {f"{name}.core": record["output"]}:
            raise ValueError("Unmatched partitioned mathematical export")
        from model_proof import validate_sliced
        return validate_sliced(case, name, record, output, family="math")
    legacy = record.get("legacy")
    half_graph = record.get("half_graph")
    if half_graph and (case != "2048-151019521" or name != "half" or legacy):
        raise ValueError("Nested half-size graph used at an unsupported node")
    legacy_kind = legacy.get("kind", "recurrence") if legacy else None
    if legacy and (case != "2048-12289" or legacy_kind not in ("half", "recurrence")
                   or name != legacy_kind):
        raise ValueError("Historical proof used at an unsupported graph node")
    entry, marker, outputs = blueprint(case, name, legacy_kind, bool(half_graph))
    report_path = inside(record["report"])
    if digest(report_path) != record["report_sha256"]:
        raise ValueError(f"Changed run report for {name}")
    extra_sources = ["verification/Ntt1024.cry"] if legacy_kind == "half" else []
    if half_graph:
        extra_sources.append("verification/Ntt1024_151019521.cry")
    report, hashes = successful_run(report_path, entry, CASES[case], marker, extra_sources)
    expected_component = str(COMPONENTS.index(name)) if name in COMPONENTS else None
    if report.get("math_context") != {"output": str(output), "component": expected_component}:
        raise ValueError(f"Wrong proof selector or output directory for {name}")
    if set(record["outputs"]) != set(outputs):
        raise ValueError(f"Missing or unexpected proposition exports for {name}")
    for artifact in record["outputs"].values():
        if digest(inside(artifact["path"])) != artifact["sha256"]:
            raise ValueError(f"Changed exported proposition for {name}")
    if record["inputs"] != inputs_for(name, nodes):
        raise ValueError(f"Unmatched premise at {name}")
    if half_graph:
        nested_path = inside(half_graph["report"])
        if digest(nested_path) != half_graph["report_sha256"]:
            raise ValueError("Changed half-size proof graph")
        nested, checked = validate_graph(nested_path, "1024-151019521")
        core = nested["nodes"]["compose"]["outputs"]["convolution.core"]
        if report.get("half_graph_context") != str(inside(core["path"])):
            raise ValueError("Unmatched nested half-size convolution proposition")
        for source in hashes.keys() & checked.keys():
            if hashes[source] != checked[source]:
                raise ValueError(f"Half-size graph used different {source}")
        hashes.update(checked)
    if legacy:
        if digest(inside(legacy["report"])) != legacy["report_sha256"]:
            raise ValueError("Changed legacy recurrence report")
        if legacy_kind == "half":
            if digest(inside(legacy["archive"])) != legacy["archive_sha256"]:
                raise ValueError("Changed historical proof archive")
            _, legacy_hashes = validate_half_checkpoint(legacy["report"], legacy["archive"])
        else:
            _, legacy_hashes = validate_legacy(legacy["report"])
        for source in hashes.keys() & legacy_hashes.keys():
            if hashes[source] != legacy_hashes[source]:
                raise ValueError(f"Legacy recurrence used a different {source}")
        hashes.update(legacy_hashes)
    return hashes


def validate_graph(path, case):
    result = json.loads(inside(path).read_text())
    if result.get("method") != METHOD or result.get("case") != case or result.get("status") != "passed":
        raise ValueError("Not a completed mathematical proof graph for this case")
    output = inside(result["output"])
    nodes = result["nodes"]
    if set(nodes) != set(ORDER):
        raise ValueError("The mathematical proof graph is incomplete")
    hashes = {}
    for name in ORDER:
        source_hashes = validate_node(case, name, nodes[name], output, nodes)
        for source in hashes.keys() & source_hashes.keys():
            if hashes[source] != source_hashes[source]:
                raise ValueError(f"Graph nodes used different {source}")
        hashes.update(source_hashes)
    if hashes != result["source_sha256"]:
        raise ValueError("Mathematical source inventory does not match the checked graph")
    return result, hashes


def run_node(case, node, output, nodes, args):
    if args.slice_size and node in ("forward", "inverse", "recurrence"):
        from model_proof import run_sliced
        record = run_sliced(case, node, output, args, family="math")
        record["outputs"] = {f"{node}.core": record["output"]}
        return record
    half_graph = inside(args.reuse_half_graph) if node == "half" and args.reuse_half_graph else None
    if half_graph:
        nested, _ = validate_graph(half_graph, "1024-151019521")
    legacy = args.reuse_recurrence if node == "recurrence" else (
        args.reuse_half if node == "half" else None)
    if legacy:
        if node == "half":
            validate_half_checkpoint(legacy, args.half_archive)
        else:
            validate_legacy(legacy)
    entry, marker, files = blueprint(case, node, node if legacy else None, bool(half_graph))
    inputs = inputs_for(node, nodes)
    for name, sha in inputs.items():
        if digest(output / name) != sha:
            raise ValueError(f"Changed input proposition: {name}")
    env = os.environ.copy()
    env["NTT_MATH_OUTPUT"] = str(output)
    env.pop("NTT_MATH_COMPONENT", None)
    env.pop("NTT_HALF_GRAPH_CORE", None)
    if half_graph:
        env["NTT_HALF_GRAPH_CORE"] = str(inside(nested["nodes"]["compose"]["outputs"]["convolution.core"]["path"]))
    if node in COMPONENTS:
        env["NTT_MATH_COMPONENT"] = str(COMPONENTS.index(node))
    small = case == "8-17"
    half_seconds = 5400 if case == "2048-151019521" else 2400
    seconds = (300 if half_graph else 120 if small else half_seconds if node == "half"
               else 3700 if node in COMPONENTS and not legacy else 300)
    heap = "2G" if small or node in ("compose", "bridge") or legacy or half_graph else args.heap
    command = [sys.executable, str(ROOT / "verification/run-isolated.py"),
               str(ROOT / "verification" / entry), "--seconds", str(seconds), "--heap", heap]
    if args.keep_awake:
        command.append("--keep-awake")
    if args.compact:
        command.append("--compact")
    if args.nursery is not None:
        command.extend(["--nursery", args.nursery])
    print(f"Starting {case}: {node}", flush=True)
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1,
                               start_new_session=True)
    log = None
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            if line.startswith("Log: "):
                log = Path(line.removeprefix("Log: ").strip())
        code = process.wait()
    finally:
        if process.poll() is None:
            # The isolated runner handles TERM by stopping its SAW/solver group
            # and writing an interrupted result. Do not leave it orphaned when
            # this controller is interrupted or its output stream fails.
            process.terminate()
            process.wait(timeout=30)
    if code or log is None:
        raise RuntimeError(f"Mathematical node {node} failed (exit {code}); prior successful nodes remain cached")
    report_path = log.with_suffix(".json")
    successful_run(report_path, entry, CASES[case], marker)
    for name, sha in inputs.items():
        if digest(output / name) != sha:
            raise ValueError(f"Premise changed while proving {node}: {name}")
    exports = {}
    for name in files:
        sha = digest(output / name)
        artifact = output / "artifacts" / f"{sha}.core"
        artifact.parent.mkdir(exist_ok=True)
        if not artifact.exists():
            shutil.copyfile(output / name, artifact)
        exports[name] = {"path": relative(artifact), "sha256": sha}
    record = {"report": relative(report_path), "report_sha256": digest(report_path),
              "inputs": inputs, "outputs": exports}
    if half_graph:
        sha = digest(half_graph)
        saved = output / "artifacts" / f"{sha}.json"
        if not saved.exists():
            shutil.copyfile(half_graph, saved)
        record["half_graph"] = {"report": relative(saved), "report_sha256": sha}
    if legacy:
        sha = digest(legacy)
        saved_report = output / "artifacts" / f"{sha}.json"
        if not saved_report.exists():
            shutil.copyfile(legacy, saved_report)
        record["legacy"] = {"kind": node, "report": relative(saved_report), "report_sha256": sha}
        if node == "half":
            record["legacy"].update({"archive": relative(args.half_archive),
                                     "archive_sha256": digest(args.half_archive)})
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--heap", default="10G")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--nursery")
    parser.add_argument("--keep-awake", action="store_true")
    parser.add_argument("--slice-size", type=int, help="partition top-level forward, inverse, and recurrence outputs")
    parser.add_argument("--slice-heap", default="2G")
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--reuse-recurrence", type=Path)
    parser.add_argument("--reuse-half", type=Path)
    parser.add_argument("--reuse-half-graph", type=Path, help="use a completed 1024-151019521 mathematical graph as the squared-modulus half premise")
    parser.add_argument("--half-archive", type=Path, default=ROOT / "verification/results/2026-11-16.tar.gz")
    parser.add_argument("--only", nargs="+", choices=ORDER, help="run selected nodes and retain the checked cache")
    parser.add_argument("--check", type=Path, help="validate an existing completed graph without running SAW")
    args = parser.parse_args()
    controller_hash = digest(Path(__file__))
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        if args.check:
            validate_graph(args.check, args.case)
            print(f"Validated complete mathematical proof graph: {args.check}")
            return
        if args.reuse_recurrence and args.case != "2048-12289":
            parser.error("--reuse-recurrence supports only the original 2048-12289 diagnostic")
        if args.reuse_half and args.case != "2048-12289":
            parser.error("--reuse-half supports only the archived 1024-point modulus-12289 theorem")
        if args.reuse_half_graph and args.case != "2048-151019521":
            parser.error("--reuse-half-graph supports only the squared-modulus 2048-point case")
        output = inside(args.output_dir) if args.output_dir else ROOT / "target/verification-math" / args.case
        output.mkdir(parents=True, exist_ok=True)
        cache = output / "nodes.json"
        nodes = json.loads(cache.read_text()) if cache.exists() else {}
        if args.keep_awake:
            if sys.platform != "darwin" or not shutil.which("caffeinate"):
                parser.error("--keep-awake requires macOS caffeinate")
            # This watcher exits when the controller exits, covering gaps between jobs.
            subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for name in ORDER:
            if args.only and name not in args.only:
                continue
            try:
                source_hashes = validate_node(args.case, name, nodes[name], output, nodes)
                print(f"Reusing checked {args.case}: {name}", flush=True)
            except (KeyError, ValueError, OSError):
                nodes[name] = run_node(args.case, name, output, nodes, args)
                cache.write_text(json.dumps(nodes, indent=2) + "\n")
                source_hashes = validate_node(args.case, name, nodes[name], output, nodes)
            for filename, artifact in nodes[name]["outputs"].items():
                shutil.copyfile(inside(artifact["path"]), output / filename)
        if set(nodes) != set(ORDER):
            print("Saved checked nodes; remaining: " + ", ".join(name for name in ORDER if name not in nodes))
            return
        hashes = {}
        for name in ORDER:
            hashes.update(validate_node(args.case, name, nodes[name], output, nodes))
        result = {"status": "passed", "method": METHOD, "case": args.case,
                  "output": relative(output), "nodes": {name: nodes[name] for name in ORDER},
                  "source_sha256": hashes, "controller_sha256": controller_hash}
        result_path = output / "math-result.json"
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        validate_graph(result_path, args.case)
        print(f"Verified complete mathematical proof graph: {result_path}", flush=True)
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Mathematical controller interrupted; completed nodes remain cached.\n")


if __name__ == "__main__":
    main()
