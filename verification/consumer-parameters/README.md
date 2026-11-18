# Consumer parameter-consistency fixes

This checkpoint fixes both parameter findings from `../consumers.md` in
revision-bound consumer patches. It follows the root-selector patches in
`../consumer-roots/`. The NTT library and the completed formal-proof sources are
unchanged. This is a native regression milestone, not a formal adapter proof.

## Behavior

Ring-LWE's `polymul_fast` now derives its transform length from the polynomial
modulus: `N = 2*d` for `f = x^d + 1`. Empty polynomials, constants, and trimmed
coefficient vectors therefore use the same length and root as full ring
elements. The adapter checks the polynomial modulus and requires inputs of
degree less than `d`, preventing accidental truncation while padding.

The small example, test, and benchmark now supply `x^4 + 1` with their
order-eight root modulo 17. The fixed consumer cases retain their already
verified roots at lengths 1024 and 2048.

Both CLI parameter builders now honor each optional override independently,
recompute the root for the final degree and modulus, and rebuild `x^d + 1`.
Invalid degrees and length overflow are rejected before allocating the
polynomial modulus. Unsupported modulus/length combinations are rejected by
the existing generator. This does not add a general formal claim about the
generator or about other cryptosystem parameter constraints.

## Source and patch order

`consumers.json` records the pinned revisions and exact before/after hashes of
every changed file. The parameter patches apply on top of the root-selector
patches, and require that selector's unchanged source. For each pinned checkout:

```sh
python3 verification/consumer-roots/apply.py ring-lwe /path/to/ring-lwe
python3 verification/consumer-parameters/apply.py ring-lwe /path/to/ring-lwe

python3 verification/consumer-roots/apply.py module-lwe /path/to/module-lwe
python3 verification/consumer-parameters/apply.py module-lwe /path/to/module-lwe
```

The parameter helper stages and validates changes before writing. Reapplying
it is harmless; `--check` verifies the final files without writing. It rejects
unrecognized source. Once the second patch is applied, use its check command:
the first patch's helper intentionally recognizes only its earlier checkpoint.

The final patched copies used here are under
`target/verification-consumer-parameters/checkouts/`. The earlier root-selection
copies and evidence archive are preserved separately. The tracked patches
still need applying in the consumers' release repositories.

## Checks and replay

```sh
python3 verification/consumer-parameters/run.py \
  --module-lwe /path/to/module-lwe --ring-lwe /path/to/ring-lwe
```

| Check | Result |
| --- | --- |
| Actual adapter and module-vector regressions | 4 tests passed |
| Actual Module-LWE CLI builder | 2 tests passed |
| Actual Ring-LWE CLI builder | 2 tests passed |
| Ring-LWE documentation examples | 7 tests passed |
| Ring-LWE benchmarks | Compilation passed |

The independent schoolbook reference uses wide accumulators and centered
representatives. The adapter tests cover all three fixed tuples with empty,
short, trimmed, wrapping, and full-length inputs, including signed extrema.
They also exercise malformed moduli, oversized inputs, and mismatched roots.
CLI tests cover defaults, complete overrides, individual overrides, invalid
degrees, overflow, and incompatible moduli.

The first isolated run took 34.852 seconds, including native compilation.
The runner uses distinct Cargo build directories for each positive test target;
old-source controls use a separate directory. Sharing a directory between
different local source copies caused a stale-executable collision in an earlier
attempt, which was discarded and replaced by the isolated run.

The runner defaults to offline Cargo operation and preserves existing lockfiles.
Missing dependencies can be fetched by setting `CARGO_NET_OFFLINE=false` on the
first run. Reports bind the actual source, patches, lockfiles, and transcripts
by SHA-256 in `target/verification-consumer-parameters/`.

Negative controls reproduce root-mismatch failures in the original adapter and
both original CLI builders using the new regression tests. Patch controls check
application, idempotency, and rejection of changed source. Exact source versions,
locked dependencies, logs, and control scripts are retained in
`../results/2026-11-17-parameters.tar.gz`.

The next formal obligation is the actual consumer adapter: connect its padding,
polynomial representation, negacyclic reduction, and centering to the completed
NTT contracts. Passing these native tests does not discharge that obligation.

Follow-up: `../consumer-adapter/` adds the next Ring-LWE patch and formal proofs
of the actual coefficient-folding and centering helpers for all three fixed
tuples. Apply that patch after this checkpoint. Padding, polynomial representation,
and full adapter composition remain open.
