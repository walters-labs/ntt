# Complete Rust consumer entry paths

This checkpoint composes the actual patched Ring-LWE `polymul_fast` call,
including its parameter checks, polynomial construction, padding, allocating
NTT call, folding/centering, truncation, and returned polynomial metadata.
Module-LWE uses this same Ring-LWE adapter. The production NTT Rust is unchanged.

| Transform length | Ring degree | Modulus | Root |
| ---: | ---: | ---: | ---: |
| 1024 | 512 | 12289 | 10302 |
| 2048 | 1024 | 12289 | 1945 |
| 2048 | 1024 | 151019521 | 51689479 |

Each function in `harness.rs` accepts two arbitrary signed `i64` arrays of
the stated ring degree. It builds real `Polynomial` values and the modulus
`x^d + 1`, then calls the public consumer function. This covers every logical
input polynomial with at most `d` coefficients, including short and zero
polynomials, through that particular construction path. It does not prove
direct calls on every independently allocated `Polynomial` heap representation.
The inputs initially have `d` initialized backing words; construction may trim
their logical lengths. No coefficient-range restriction is imposed.

The returned backing coefficients equal the independent centered negacyclic
product of the normalized inputs in `consumer-composition/ConsumerProduct.cry`.
The returned logical length is at most `d`; every discarded coefficient is
zero, and the last retained coefficient is nonzero for a nonempty result.
Capacity bounds and generated MIR safety obligations are also checked.

All 13 proof jobs passed, including 72 new MIR contract checks, two padding
consequence witnesses, and three mathematical composition implications.
Ten proposition boundaries match exactly. The complete call proofs took
60.2 / 161.9 / 162.2 seconds. The sum of all new job times is 24.2 minutes;
some jobs overlapped. Maximum child RSS was 4.42 GiB. A replay of just these
new layers should be budgeted roughly 20–30 minutes on the development Mac;
replaying their historical dependencies takes longer. The runner is sequential
and retains each completed job.

Load the existing pinned toolchain environment, then audit the saved evidence:

```sh
source ~/.zprofile
python3 verification/consumer-call/run.py --check --negative-controls
```

This does not run SAW or rebuild Rust. It checks every prior required proof
gate, the source/build/dependency bindings, exact contract fragments, complete
reachable MIR graphs, successful reports/transcripts, and proposition exports.
It rejects `Not convertible`, missing matches, and extra matches even if SAW
exited successfully. Nine controls exercise missing jobs/consequences, wrong
tuples, changed transcripts, changed MIR opcodes/constants/layouts, identifier
collisions, and changed import contracts.

To run missing new proof jobs and reuse unchanged completed jobs:

```sh
python3 verification/consumer-call/run.py --negative-controls
```

This checkpoint expects the retained consumer checkouts and dependency proof
artifacts under `target/`, as recorded in `recipe.json`. It is an exact
checkpoint runner, not a general consumer checkout generator. The harness
manifest and lockfile are retained in the result archive. The build uses
`nightly-2026-03-21`, the pinned SAW/mir-json installation, and the existing
Cargo offline cache. It remaps only the NTT `src/` prefix. The linker can
reorder declarations between identical builds, so all three complete entry
graphs are compared to the proof artifact in addition to checking file hashes.
Changed implementation semantics require a new checkpoint, not adoption of an
old proof. The initial `--adopt-evidence` facility was used only to freeze the
already completed runs and their reviewed dependency bindings; ordinary replay
must use the frozen proof records instead.

The proof dependency chain is:

1. Previously proved transform kernels feed fresh allocating-NTT API proofs.
2. Previously proved constructors and fresh symbolic-length padding proofs
   feed the consumer calls. The constructor's zero-tail fact permits replacing
   the padding mask by the original backing vector. `padding-equality.saw`
   proves that consequence for both degrees, with allocation/frame fields
   unchanged.
3. Each call freshly proves the literal modulus constructor, scalar centering,
   every folding block, and the full fold before checking the actual entry.
4. `model-link.saw` connects the returned transform model to the already
   proved signed-input negacyclic formula. Its premises are checked exports of
   the existing convolution, transform-model, and consumer-bridge graphs.

SAW 1.6 cannot serialize MIR MethodSpecs. The small import files therefore
use `mir_unsafe_assume_spec`. **Their discharge is enforced by `run.py` and
`mir_identity.py`; these Python checkers extend the trusted proof boundary.**
Each import needs a successful previous proof of the identical contract and
parameter/spec instance. The checker compares the complete reachable MIR
declaration graphs, including callees, constants, types, layouts, intrinsics,
and language-item bindings. It permits bijective identifier renaming and
ignores only source-position metadata. A standalone SAW process using these
imports is a conditional proof; its exit status alone is insufficient.
The retained logs are audit evidence, not independently checkable proof
certificates. The usual SAW/MIR frontend, solvers, standard-library model, and
compiler trust assumptions also remain.

`../results/2026-11-17-consumer-call.tar.gz` preserves the new checkpoint. Its
`manifest.json` hashes every member. It depends on the earlier November 16 NTT,
November 17 NTT, polynomial-boundary, and consumer-bridge checkpoints. Restore
their `target/` members at the original repository location before the new
archive's `target/` members when recovering the cached audit; absolute paths in
historical runs remain significant. Source snapshots in the new archive are
under `source/2026-11-17-consumer-call/` and do not overwrite working sources.

The prepared patches still need applying in the release repositories, followed
by checking the exact released source and dependency versions. Arbitrary
generic API parameters, ML-KEM's separate transform, constant-time behavior,
and whole-cryptosystem security are outside this checkpoint.
