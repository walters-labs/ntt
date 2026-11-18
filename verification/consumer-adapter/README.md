# Consumer reduction and centering proofs

The consumer's actual in-place reduction helper is now verified at all three
fixed transform tuples. Given a canonical length-`2*d` NTT result `c`, it writes
the centered representative of `c[i] - c[i+d]` into each lower-half position
and preserves every upper-half word. This is the coefficient reduction modulo
`x^d + 1` needed by the consumer adapter.

The input condition is `0 <= c[i] < q`, the canonical output domain of the
completed NTT proofs. The reduction proof includes the generated overflow and
memory-safety obligations. It does not restrict the original signed polynomial
coefficients beyond the existing NTT contracts.

| Transform length | Modulus | MIR contracts | Wall seconds | Maximum child RSS |
| --- | ---: | ---: | ---: | ---: |
| 1024 | 12289 | 11 | 39.640 | 1.24 GiB |
| 2048 | 12289 | 19 | 81.228 | 2.11 GiB |
| 2048 | 151019521 | 19 | 81.806 | 2.03 GiB |

Two additional contracts verify Euclidean normalization and a one-coefficient
wrapper around the consumer's existing `mod_coeffs` function, through the real
`Polynomial` constructor. That wrapper is proved for every signed `i64` input
and every modulus from 2 through `i64::MAX`; zero/trimmed output is included.
That run took 4.514 seconds and 0.49 GiB maximum child RSS.

## Implementation and proof structure

The patch adds private `ntt_adapter` helpers to Ring-LWE. The multiplication
adapter folds and centers its NTT result in the same buffer, truncates it to
the ring degree, and constructs the result polynomial once. This removes
intermediate polynomial construction, a coefficient-vector clone, and the
separate normalization output buffer. The public function signature is unchanged.
Other callers of `polyrem` and `mod_coeffs` retain those existing functions.

`adapter.rs` is copied unchanged to the consumer's `src/ntt_adapter.rs`.
SAW verifies the functions in the actual compiled consumer dependency:

1. Verify the scalar difference/centering formula against exact integer arithmetic.
2. Verify every 64-coefficient block, including preservation of all other words.
   Only the block's inputs need to be canonical; already-processed positions
   may contain negative centered values.
3. Verify the actual outer loop against the complete array specification, using
   only the block contracts proved in that same SAW process.

There are 51 successful MIR contract checks in the complete run, including
repeated supporting standard-library and scalar proofs in separate processes.
No block contract or NTT result is admitted or imported as an unproved override.
The NTT computation is outside these reduction proofs; its result is the
canonical symbolic input specified by their precondition.

The proof crate's `multiplication_entry` keeps the private helper reachable in
the linked MIR. That product entry is not itself proved. `AdapterSpec.cry` uses
exact integers and the same three concrete parameter instances as the transform
proofs. `cases.json` binds their exact file hashes.

## Patch order and replay

Apply the root-selector and parameter-consistency patches first, as described
in `../consumer-parameters/README.md`. Then apply this Ring-LWE-only patch:

```sh
python3 verification/consumer-adapter/apply.py /path/to/ring-lwe
```

The helper validates all before/after hashes and the unchanged root selector,
stages the patch before writing, and accepts reapplication. Add `--check` to
require the final files without writing. Module-LWE uses Ring-LWE's adapter
and needs no further source change for this checkpoint.

With the pinned SAW/MIR toolchain installed:

```sh
python3 verification/consumer-adapter/run.py \
  --ring-lwe /path/to/ring-lwe --module-lwe /path/to/module-lwe
```

The runner builds the actual patched dependency into a separate MIR artifact,
preserves that artifact by hash, and checks the scalar wrapper and three full
reduction cases sequentially with vacuity checking. It uses 2 GiB heaps for the
smaller jobs and 3 GiB for the 2048-point jobs, with ten-minute external limits
per process. The heap ceiling is not an aggregate process-memory limit.
On macOS it keeps the machine awake during each proof.

The complete run took 215.734 seconds, including compilation and four native
adapter/vector regressions against the independent schoolbook reference from
the previous checkpoint. Allow about four minutes on this development Mac.
The runner defaults to offline Cargo operation and preserves its lockfiles;
set `CARGO_NET_OFFLINE=false` on the first run if dependencies are missing.

The report is `target/verification-consumer-adapter/adapter-report.json`. It
binds source, parameter instances, consumer patches, lockfiles, MIR, and each
successful proof transcript/report by SHA-256. The saved checkpoint is
`../results/2026-11-17-adapter-reduction.tar.gz`. The tracked patch still needs
application in the consumer's release repository.

## Controls, limits, and remaining work

A deliberately incorrect addition formula was rejected with a genuine return
postcondition counterexample. Patch application, idempotency, and changed-source
rejection passed. Both completed 2048-point NTT provenance gates were rechecked;
the NTT library and its existing proof sources were not modified.

The first direct consumer probe encountered a symbolic-sized allocation after
polynomial trimming. The in-place tail avoids that allocation. Separate bounded
probes showed that the large scalar loop also needed compositional proofs;
the final block workflow stays within the measured memory figures above.
Constructor-related proofs use path-satisfiability checking to exclude impossible
paths; see the [SAW verification manual](https://galoisinc.github.io/saw-script/master/saw-user-manual/verifying-code.html).

**The full consumer adapter remains open.** The subsequent
[polynomial boundary checkpoint](../polynomial-boundary/README.md) now proves
the constructor and all bounded input-padding lengths. Connect the complete
consumer call to those contracts, the existing NTT, and these reduction contracts.
At this earlier checkpoint, a bounded full-size padding
probe failed after 91 seconds with a solver-protocol error near its internal
deadline; it was not counted as successful. The native tests of
the complete adapter remain regression coverage, not that formal composition.
