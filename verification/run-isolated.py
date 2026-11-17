#!/usr/bin/env python3
"""Run one SAW script with a heap ceiling, wall deadline, and saved results."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time


class StopRun(Exception):
    def __init__(self, signum):
        self.signum = signum


def stop_run(signum, _frame):
    raise StopRun(signum)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--heap", default="6G")
    parser.add_argument("--compact", action="store_true", help="use GHC's in-place compaction for the oldest generation")
    parser.add_argument("--nursery", help="GHC allocation area size, for example 32M; default is unchanged")
    parser.add_argument("--mir", type=Path, help="MIR artifact passed as the first SAW script argument")
    parser.add_argument("--detect-vacuity", action="store_true")
    parser.add_argument("--keep-awake", action="store_true", help="prevent idle system sleep during this run (macOS)")
    args = parser.parse_args()
    if args.seconds <= 0 or not re.fullmatch(r"[1-9][0-9]*[MG]", args.heap):
        parser.error("use a positive timeout and heap size such as 6G or 4096M")
    if args.nursery is not None and not re.fullmatch(r"[1-9][0-9]*[MG]", args.nursery):
        parser.error("use an allocation area size such as 32M")
    script = args.script.resolve()
    if not script.is_file() or script.suffix != ".saw":
        parser.error("script must be an existing .saw file")
    if args.mir is not None and not args.mir.is_file():
        parser.error("MIR artifact must be an existing file")
    if args.keep_awake and (sys.platform != "darwin" or not shutil.which("caffeinate")):
        parser.error("--keep-awake requires macOS caffeinate")

    root = Path(__file__).resolve().parent.parent
    output = root / "target" / "verification-isolated"
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    # Concurrent processes can receive the same microsecond timestamp. Reserve
    # the filename atomically so neither transcript nor report is overwritten.
    log_fd, log_name = tempfile.mkstemp(prefix=f"{script.stem}-{stamp}-", suffix=".log", dir=output)
    os.close(log_fd)
    log_path = Path(log_name)
    stem = log_path.with_suffix("")
    command = ["saw", "+RTS", f"-M{args.heap}", "-s"]
    if args.compact:
        command.append("-c")
    if args.nursery is not None:
        command.append(f"-A{args.nursery}")
    command.extend(["-RTS", "--timestamping"])
    if args.detect_vacuity:
        command.append("--detect-vacuity")
    command.append(str(script))
    if args.mir is not None:
        command.append(str(args.mir.resolve()))
    env = os.environ.copy()
    env["SBV_CVC5_OPTIONS"] = "--lang smt --incremental --nl-cov --solve-bv-as-int=sum"
    sources = sorted((root / "verification").glob("*.saw"))
    sources += sorted((root / "verification").glob("*.cry"))
    if args.mir is not None:
        sources += sorted((root / "src").rglob("*.rs"))
        sources += [root / "verification/harness.rs", root / "Cargo.toml", root / "Cargo.lock"]
    hashes = {str(p.relative_to(root)): file_hash(p)
              for p in sources}
    entry_hash = file_hash(script)
    runner_hash = file_hash(Path(__file__).resolve())
    mir_hash = file_hash(args.mir.resolve()) if args.mir is not None else None
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, stop_run)
    print(f"Running {script.name}: {args.heap} SAW heap, {args.seconds}s deadline", flush=True)
    print(f"Log: {log_path}", flush=True)
    start = time.monotonic()
    wall_start = time.time()
    deadline = wall_start + args.seconds
    status = "failed"
    awake = None
    with log_path.open("w") as log:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            if args.keep_awake:
                awake = subprocess.Popen(["caffeinate", "-i", "-w", str(process.pid)],
                                         stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True)
            # A Mac's monotonic clock can exclude sleep. Use wall time for the
            # external deadline, and report both clocks to expose interruptions.
            while process.poll() is None:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, args.seconds)
                try:
                    process.wait(timeout=min(remaining, 1.0))
                except subprocess.TimeoutExpired:
                    pass
            code = process.returncode
            status = "passed" if code == 0 else "failed"
        except subprocess.TimeoutExpired:
            status = "timeout"
            code = 124
        except KeyboardInterrupt:
            status = "interrupted"
            code = 130
        except StopRun as stop:
            status = "interrupted"
            code = 128 + stop.signum
        finally:
            # Also stop lingering solver children in this dedicated process group.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if awake is not None:
                # -w releases the assertion when the SAW PID exits. Allow the
                # system utility to exit normally instead of signalling it.
                awake.wait(timeout=5)

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak_rss = usage.ru_maxrss
    if sys.platform != "darwin":
        peak_rss *= 1024
    result = {
        "status": status, "exit_code": code,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "wall_elapsed_seconds": round(time.time() - wall_start, 3),
        "child_cpu_seconds": round(usage.ru_utime + usage.ru_stime, 3),
        "wall_limit_seconds": args.seconds, "saw_heap_limit": args.heap,
        "compact_gc": args.compact, "nursery": args.nursery,
        "keep_awake": args.keep_awake,
        "child_max_rss_bytes": peak_rss,
        "command": command, "log": str(log_path.relative_to(root)),
        "entry_script_sha256": entry_hash, "runner_sha256": runner_hash,
        "source_sha256": hashes,
    }
    if "NTT_MATH_OUTPUT" in env:
        result["math_context"] = {
            "output": env["NTT_MATH_OUTPUT"],
            "component": env.get("NTT_MATH_COMPONENT"),
        }
    if "NTT_MODEL_SLICE_OFFSET" in env:
        result["model_slice"] = {"offset": env["NTT_MODEL_SLICE_OFFSET"],
                                 "count": env.get("NTT_MODEL_SLICE_COUNT")}
    if "NTT_MODEL_COVERAGE_SIZE" in env:
        result["model_coverage"] = {"size": env["NTT_MODEL_COVERAGE_SIZE"]}
    if "NTT_HALF_GRAPH_CORE" in env:
        result["half_graph_context"] = env["NTT_HALF_GRAPH_CORE"]
    if args.mir is not None:
        result["mir_path"] = str(args.mir.resolve())
        result["mir_sha256"] = mir_hash
    stem.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{status}: {result['elapsed_seconds']}s; max child RSS {peak_rss / 2**30:.2f} GiB",
          flush=True)
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    sys.exit(main())
