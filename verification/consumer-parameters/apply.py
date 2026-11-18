#!/usr/bin/env python3
"""Apply the parameter-consistency fix after the fixed root-selector patch."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    here = Path(__file__).resolve().parent
    consumers = json.loads((here / "consumers.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consumer", choices=consumers)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    entry = consumers[args.consumer]
    if (digest(checkout / "src/ntt_roots.rs") != entry["selector_sha256"] or
            digest(here.parent / "consumer-roots/roots.rs") != entry["selector_sha256"]):
        raise SystemExit("Expected the unchanged, verified root-selector source")
    files = entry["files"]
    if all(digest(checkout / name) == item["after_sha256"] for name, item in files.items()):
        print(f"{args.consumer}: parameter-consistency patch already applied")
        return
    if args.check:
        raise SystemExit("Consumer files do not match the parameter-consistency checkpoint")
    for name, item in files.items():
        if digest(checkout / name) != item["before_sha256"]:
            raise SystemExit(f"Unrecognized or changed source: {name}; apply {entry['requires']} first")
    with tempfile.TemporaryDirectory(prefix="ntt-consumer-parameters-") as temporary:
        staged = Path(temporary)
        for name in files:
            (staged / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checkout / name, staged / name)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(here / entry["patch"])],
                       cwd=staged, check=True, capture_output=True)
        for name, item in files.items():
            if digest(staged / name) != item["after_sha256"]:
                raise SystemExit(f"Patch output mismatch: {name}")
        for name in files:
            shutil.copyfile(staged / name, checkout / name)
    print(f"{args.consumer}: applied parameter-consistency patch")


if __name__ == "__main__":
    main()
