#!/usr/bin/env bash
set -euo pipefail

ntt_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ntt_root"

cases=("$@")
if [ "${#cases[@]}" -eq 0 ]; then
    cases=(arithmetic-general parameters mlkem-powers)
fi
for case_id in "${cases[@]}"; do
    case "$case_id" in
        arithmetic-general|parameters|mlkem-powers) ;;
        *)
            printf 'Unknown foundation case: %s\nUsage: bash verification/run-foundations.sh [arithmetic-general] [parameters] [mlkem-powers]\n' "$case_id" >&2
            exit 2
            ;;
    esac
done
: "${SAW_RUST_LIBRARY_PATH:?Set SAW_RUST_LIBRARY_PATH to the translated mir-json rlibs directory}"
export SBV_CVC5_OPTIONS='--lang smt --incremental --nl-cov --solve-bv-as-int=sum'

# Keep these artifacts and logs separate from the longer transform proof suite.
mkdir -p target/verification-foundations
cargo +nightly-2026-03-21 saw-build --lib \
    --target-dir target/verification-foundations --message-format=json \
    > target/verification-foundations/artifacts.jsonl

ntt_mir_file="$(python3 - <<'PY'
import json
from pathlib import Path

artifacts = []
for line in Path('target/verification-foundations/artifacts.jsonl').read_text().splitlines():
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    if (event.get('reason') == 'compiler-artifact'
            and event.get('target', {}).get('name') == 'ntt'
            and 'lib' in event.get('target', {}).get('kind', [])
            and event.get('profile', {}).get('test')
            and event.get('executable')):
        artifacts.append(Path(event['executable'] + '.linked-mir.json'))
if len(artifacts) != 1 or not artifacts[0].is_file():
    raise SystemExit('Expected exactly one current NTT library MIR artifact')
print(artifacts[0].resolve())
PY
)"

for case_id in "${cases[@]}"; do
    saw --detect-vacuity --timestamping "verification/$case_id.saw" "$ntt_mir_file" 2>&1 \
        | tee "target/verification-foundations/$case_id.log"
done
