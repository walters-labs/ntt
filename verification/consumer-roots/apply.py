#!/usr/bin/env python3
"""Apply a root-selector patch only to the recorded consumer source version."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    here = Path(__file__).resolve().parent
    consumers = json.loads((here / "consumers.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consumer", choices=consumers)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--check", action="store_true", help="require the patch to be already applied")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    entry = consumers[args.consumer]
    files = entry["files"]
    if files["src/ntt_roots.rs"]["after_sha256"] != sha(here / "roots.rs"):
        raise SystemExit("Consumer selector does not match the proof source")
    if all(sha(checkout / name) == item["after_sha256"] for name, item in files.items()):
        print(f"{args.consumer}: verified patch already applied ({entry['revision']})")
        return
    if args.check:
        raise SystemExit("Consumer source does not match the verified patched version")
    for name, item in files.items():
        if sha(checkout / name) != item["before_sha256"]:
            raise SystemExit(f"Refusing to overwrite changed or unrecognized source: {name}")
    # Apply and validate in a temporary directory before writing any user file.
    with tempfile.TemporaryDirectory(prefix="ntt-consumer-roots-") as temporary:
        staged = Path(temporary)
        for name in files:
            source = checkout / name
            if source.is_file():
                (staged / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, staged / name)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(here / entry["patch"])],
                       cwd=staged, check=True, capture_output=True)
        for name, item in files.items():
            if sha(staged / name) != item["after_sha256"]:
                raise SystemExit(f"Patch did not produce the verified source: {name}")
        for name in files:
            shutil.copyfile(staged / name, checkout / name)
    print(f"{args.consumer}: applied verified root selector ({entry['revision']})")


if __name__ == "__main__":
    main()
