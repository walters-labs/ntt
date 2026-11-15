#!/usr/bin/env bash
set -euo pipefail

ntt_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ntt_root"

cases=("$@")
if [ "${#cases[@]}" -eq 0 ]; then
    cases=(8-17 16-17 8-289 256-12289)
fi
for case_id in "${cases[@]}"; do
    case "$case_id" in
        8-17|16-17|8-289|256-12289|1024-12289) ;;
        *)
            printf 'Unknown verification case: %s\nUsage: bash verification/run.sh [8-17] [16-17] [8-289] [256-12289] [1024-12289]\n' "$case_id" >&2
            exit 2
            ;;
    esac
done
ntt_saw_max_heap="${NTT_SAW_MAX_HEAP:-6G}"
if [[ ! "$ntt_saw_max_heap" =~ ^[1-9][0-9]*[MG]$ ]]; then
    printf 'NTT_SAW_MAX_HEAP must be a positive size in M or G, for example 6G.\n' >&2
    exit 2
fi
: "${SAW_RUST_LIBRARY_PATH:?Set SAW_RUST_LIBRARY_PATH to the translated mir-json rlibs directory}"

# Exact bit-vector-to-integer translation makes the representation proofs
# tractable. This also supplies SBV's normal CVC5 options explicitly.
export SBV_CVC5_OPTIONS='--lang smt --incremental --nl-cov --solve-bv-as-int=sum'

ntt_target_dir="${NTT_VERIFICATION_TARGET_DIR:-target/verification}"
mkdir -p "$ntt_target_dir"
cargo +nightly-2026-03-21 saw-build --lib \
    --target-dir "$ntt_target_dir" --message-format=json \
    > "$ntt_target_dir/artifacts.jsonl"

# Use Cargo's current artifact, not a glob that might select an older build.
ntt_mir_file="$(python3 - "$ntt_target_dir/artifacts.jsonl" <<'PY'
import json
import sys
from pathlib import Path

artifacts = []
for line in Path(sys.argv[1]).read_text().splitlines():
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
    saw +RTS "-M${ntt_saw_max_heap}" -RTS \
        --detect-vacuity --timestamping "verification/ntt-$case_id.saw" "$ntt_mir_file" 2>&1 \
        | tee "$ntt_target_dir/ntt-$case_id.log"
done
