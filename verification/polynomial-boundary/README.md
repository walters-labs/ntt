# Polynomial construction and consumer padding

This checkpoint verifies the actual `polynomial-ring` 0.5.1 constructor and
Ring-LWE's private padding helper for ring degrees 512 and 1024. Padding is
independent of the modulus, so these two degrees cover all three fixed consumer
tuples. Coefficients range over every signed `i64` value.

## Contracts

For each degree `d`, `Polynomial::<i64>::new` receives an arbitrary `d`-word
vector and any valid capacity at least `d`. Its contract preserves the backing
coefficients, pointer, and capacity, returns a length at most `d`, removes only
trailing zeros, and leaves a nonzero last coefficient whenever the result is
nonempty. Together these properties characterize the canonical polynomial
representation, including the zero polynomial.

For each logical input length `c=0..d`, the actual consumer helper
`ring_lwe::utils::ntt_padding::padded` returns exactly `2*d` coefficients:
the original `c` words followed by zeros. It preserves the input coefficients.
The contract allows every valid capacity at least `c`, including capacity zero
for the empty input, and does not require a nonzero last coefficient. The
exhaustive length cases therefore include every trimmed polynomial of degree
less than `d`, without assuming a full-degree backing allocation.

The suite has 2 constructor contracts and 1,538 padding contracts, for a total
of 1,540 MIR checks. Each uses vacuity checking. No constructor or padding
contract is admitted or replaced by an unproved override.

The complete 52-task run passed on November 17, together with four native
adapter/vector regressions. It took 1,325.659 seconds (22.1 minutes) with two
workers; maximum child RSS was 0.637 GiB. The heap ceiling is per SAW process,
and this RSS figure is the largest child, rather than aggregate memory use.

| Proof | Contracts | Sum of batch wall seconds | Maximum child RSS |
| --- | ---: | ---: | ---: |
| Constructor, 512 words | 1 | 66.168 | 0.47 GiB |
| Constructor, 1024 words | 1 | 233.784 | 0.61 GiB |
| Padding, all lengths 0..512 | 513 | 561.365 | 0.62 GiB |
| Padding, all lengths 0..1024 | 1025 | 1737.985 | 0.64 GiB |

The batch times overlap because two workers run concurrently. A deliberately
incorrect specification requiring a leading one for the padded empty input
was rejected by an output-equality postcondition with a counterexample.
Patch application, idempotency, and changed-source rejection passed. Both
existing 2048-point NTT provenance gates were rechecked successfully.

## Consumer change and patch order

`padding.rs` is copied unchanged into Ring-LWE as the private `ntt_padding`
module. It allocates a zeroed buffer at the fixed transform length and copies
the input slice into its prefix. The adapter uses this helper for both inputs.
The public signatures and padded coefficient values are unchanged.

Apply the root-selection, parameter-consistency, and reduction patches first,
as described in `../consumer-adapter/README.md`, then:

```sh
python3 verification/polynomial-boundary/apply.py /path/to/ring-lwe
python3 verification/polynomial-boundary/apply.py /path/to/ring-lwe --check
```

The helper validates before/after hashes and stages the patch before writing.
Module-LWE uses the Ring-LWE adapter and needs no additional patch here.
These patches are prepared against the pinned consumer revisions in
`consumers.json`; they still need application in the release repositories.

## Replay and cached validation

Load the pinned toolchain environment, then run from the NTT repository root.
The runner's consumer checkouts must be inside this repository so its source
records use repository-relative paths. The example below uses copies under
`target/consumer-checkouts/`; the existing development copies are under
`target/verification-polynomial-boundary/checkouts/`.

```sh
python3 verification/polynomial-boundary/run.py \
  --ring-lwe target/consumer-checkouts/ring-lwe \
  --module-lwe target/consumer-checkouts/module-lwe
```

The runner builds the actual patched consumer, preserves its exact linked MIR
by SHA-256, and runs batches of 32 concrete input lengths with two workers.
Each SAW process has a 2 GiB heap ceiling. Constructor processes have an
external limit of 660 seconds; padding batches have 300 seconds, with an
additional 30-second bound on each length. `--workers 1` runs sequentially.
Completed batches are cached against their source and MIR hashes, including
proof scripts, dependencies, lockfiles, and the isolated runner. Interrupting
the driver retains completed batches. Source changes invalidate the cache.
Cargo defaults to offline mode; use `CARGO_NET_OFFLINE=false` if fetching the
pinned dependencies is necessary.

After a successful run, validate the saved checkpoint without rerunning SAW:

```sh
python3 verification/check-polynomial-boundary.py \
  target/verification-polynomial-boundary/boundary-report.json \
  --negative-controls \
  --output target/verification-polynomial-boundary/checkpoint-check.json
```

This checks exact coverage, source/build/MIR hashes, every proof report,
transcript and entry script, and the four-test native regression log. Its
negative controls reject missing/duplicate batches, wrong degrees, and changed
artifact hashes. `run.py` also accepts `--check` with both consumer paths.
The aggregate checker additionally validates the recorded native log hash.
Both cached checks completed in less than a second on the development Mac.
The full evidence snapshot, including exact MIR, scripts, source, transcripts,
lockfiles, controls, and file manifest, is retained in
`../results/2026-11-17-polynomial-boundary.tar.gz`.

## Proof engineering and remaining scope

Bulk constructor assertions avoid retranslating hundreds of nearly identical
per-coefficient goals. Enumerating logical input lengths avoids a symbolic-sized
allocation and symbolic prefix update, while still covering the entire bounded
input domain. The explicit Vec setup in `vec-layout.saw` follows the pinned
SAW/MIR standard-library representation; it is specific to that toolchain.

The earlier pause snapshot and exploratory probes are historical records in
`PAUSED.md` and `../results/2026-11-17-boundary-paused.tar.gz`. They are separate
from this actual-consumer proof suite.

The subsequent [consumer-call checkpoint](../consumer-call/README.md) now
connects these component contracts through three actual Rust entry paths,
including validation, padding, NTT allocation, folding, output truncation,
and result construction. Its checker discharges cached MIR contract imports
against the existing proofs and reachable MIR graph identity. See that
checkpoint for input-representation limits and the extended trusted boundary.
The NTT library's production Rust remains unchanged.
