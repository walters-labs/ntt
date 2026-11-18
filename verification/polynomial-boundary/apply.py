#!/usr/bin/env python3
"""Apply the polynomial padding patch after the consumer parameter fixes."""

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
    entry = json.loads((here / "consumers.json").read_text())["ring-lwe"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    if digest(checkout / "src/ntt_roots.rs") != entry["selector_sha256"]:
        raise SystemExit("Expected the unchanged verified root selector")
    if digest(here / "padding.rs") != entry["files"]["src/ntt_padding.rs"]["after_sha256"]:
        raise SystemExit("Padding source does not match the consumer patch")
    files = entry["files"]
    if all(digest(checkout / name) == item["after_sha256"] for name, item in files.items()):
        print("ring-lwe: polynomial padding patch already applied")
        return
    if args.check:
        raise SystemExit("Consumer files do not match the adapter checkpoint")
    for name, item in files.items():
        if digest(checkout / name) != item["before_sha256"]:
            raise SystemExit(f"Changed source: {name}; apply {entry['requires']} first")
    with tempfile.TemporaryDirectory(prefix="ntt-polynomial-boundary-") as temporary:
        staged = Path(temporary)
        for name in files:
            (staged / name).parent.mkdir(parents=True, exist_ok=True)
            if (checkout / name).is_file():
                shutil.copyfile(checkout / name, staged / name)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(here / entry["patch"])],
                       cwd=staged, capture_output=True, check=True)
        for name, item in files.items():
            if digest(staged / name) != item["after_sha256"]:
                raise SystemExit(f"Patch output mismatch: {name}")
        for name in files:
            shutil.copyfile(staged / name, checkout / name)
    print("ring-lwe: applied polynomial padding patch")


if __name__ == "__main__":
    main()
