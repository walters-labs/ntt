# Fixed consumer root selection

The three fixed cases now have a small root selector and six successful SAW/MIR
contracts: selection of the expected root and acceptance by the actual NTT
validator for each case. The expected `(q,N,root)` values come directly from
`Ntt1024.cry`, `Ntt2048.cry`, and `Ntt2048_151019521.cry`, the instances used by
the completed transform proofs.

| Consumer case | Modulus | Transform length | Selected root |
| --- | ---: | ---: | ---: |
| Module-LWE default | 12289 | 1024 | 10302 |
| Ring-LWE default | 12289 | 2048 | 1945 |
| Ring-LWE squared-modulus test | 151019521 | 2048 | 51689479 |

`roots.rs` is the exact source added as `src/ntt_roots.rs` by both consumer
patches. The proof crate compiles it against this repository's NTT library.
`harness.rs` only keeps the existing validator reachable in the linked MIR.
There is no new public API in the `ntt` crate, and its Rust sources are unchanged.

The patches replace the two default constructors' root-generation calls and the
squared-modulus test's recomputation. They are based on the exact revisions in
`consumers.json`. They have been applied to local copies under
`target/verification-root-selection/checkouts/`; both patched libraries compile,
and a native test of their actual default constructors passes. The tracked
patches must still be applied in the consumer repositories before release.
ML-KEM does not call this root generator and needs no patch for this step.

## Proof scope and the generator fallback

The selector uses constants for the three fixed pairs and calls `ntt::omega`
for every other pair. Each formal selection contract executes a concrete fixed
pair with no overrides, admitted lemmas, or assumptions about `omega`'s return.
The fallback is outside the formal target. Native regression tests compare all
three constants with the existing generator, and exercise four fallback pairs.

A bounded direct proof of `omega(12289,1024)` stopped in 2.146 seconds at an
unsupported `u64`-to-`f64` cast in Reikna's prime sieve, reached through
factorization. This is a translation limitation, not a counterexample or a
successful generator proof. The fixed branches avoid that dependency entirely.

The formal claim is about the selector component and validator, not the full
consumer constructors or cryptosystems. The consumer padding/length mismatch,
CLI overrides, negacyclic reduction, and coefficient representation remain the
next integration obligations in `../consumers.md`.

Follow-up: `../consumer-parameters/` now contains tested fixes for the length
mismatch and CLI overrides, applied after these patches. Its actual adapter
still needs the formal integration proof.

## Reproduce

With the pinned SAW/MIR toolchain on `PATH` and `SAW_RUST_LIBRARY_PATH` set, run
from the NTT repository root:

```sh
python3 verification/consumer-roots/run.py
```

The controller builds a separate proof crate, preserves its exact MIR by hash,
runs six contracts with vacuity checking under a 2 GiB heap / 120-second limit,
and runs the two native regression tests. It records the source, patch, lockfile,
MIR, report, and transcript hashes in
`target/verification-root-selection/root-selection-report.json`. It defaults to
offline Cargo operation; the pinned toolchain and Reikna dependency must already
be installed. Proofs take about four seconds and 0.56 GiB maximum child RSS on
the development Mac; the entire cached workflow takes several seconds.

Apply a patch to its pinned consumer checkout with:

```sh
python3 verification/consumer-roots/apply.py module-lwe /path/to/module-lwe
python3 verification/consumer-roots/apply.py ring-lwe /path/to/ring-lwe
```

The helper checks the exact original file hashes, validates the staged patch
before writing, accepts an already-applied patch, and refuses other source
versions. Add `--check` to require the verified patched files without writing.
The archive URLs and revisions are in `consumers.json`.

To compile the patched libraries and test their actual defaults:

```sh
python3 verification/consumer-roots/check-consumers.py \
  --module-lwe /path/to/module-lwe --ring-lwe /path/to/ring-lwe
```

This native smoke test links both local consumers to this checkout's NTT and
links Module-LWE to the inspected Ring-LWE checkout. It records all compiled
consumer source hashes and the resolved Cargo lockfile; it is not an end-to-end
formal proof or a check of their published dependency resolutions. Missing
dependencies can be fetched by setting `CARGO_NET_OFFLINE=false` for this command.

Results and exact source versions are retained separately in
`../results/2026-11-17-roots.tar.gz`, leaving the completed transform archives
unchanged. Negative controls reject an incorrect expected root and changed
consumer source. Both existing 2048-point provenance gates were also rechecked.
