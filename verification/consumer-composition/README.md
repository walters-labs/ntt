# Consumer cyclic-to-negacyclic mathematical bridge

This checkpoint connects the existing NTT convolution specification to the
consumer's centered product modulo `x^d + 1`, at all three fixed tuples:

| Ring degree `d` | Transform length | Modulus |
| ---: | ---: | ---: |
| 512 | 1024 | 12289 |
| 1024 | 2048 | 12289 |
| 1024 | 2048 | 151019521 |

All three cases passed on November 17. The complete two-worker run took
1,384.907 seconds (23.1 minutes), with 0.963 GiB maximum child RSS. Cached
graph validation took 0.096 seconds; the strict final gate also passed all
83 proposition boundaries and its integrity controls.

| Transform length and modulus | Closed coefficient blocks | Sum of job wall seconds | Maximum child RSS |
| --- | ---: | ---: | ---: |
| 1024, 12289 | 16 | 301.705 | 0.60 GiB |
| 2048, 12289 | 32 | 1220.391 | 0.96 GiB |
| 2048, 151019521 | 32 | 1220.673 | 0.95 GiB |

Job times overlap across the two workers and include each case's final
composition steps. RSS is the maximum child process, not aggregate memory.
The saved evidence is `../results/2026-11-17-consumer-bridge.tar.gz`.

Let `A` and `B` be the coefficient-wise Euclidean normalizations of arbitrary
signed `i64` input vectors. Pad each degree-`d` vector with `d` zero words and
take its cyclic convolution at length `2*d`. Folding and centering that result
produces, at every position `k < d`,

```text
centered_q(sum over j=0..d-1 of
  (if j <= k then +1 else -1) * A[j] * B[(k+d-j) mod d])
```

`ConsumerProduct.cry` specifies this independent single-sum negacyclic formula
using exact integer multiplication and addition. The theorem uses the actual
`NttSpec.convolution`, `NttSpec.normalizePoly`, and `AdapterSpec.foldCenter`
definitions from the preceding checkpoints. Input coefficients have no range
restriction. Zero and short polynomials are represented by zero-extending
their coefficient vectors to degree `d`; the preceding padding proofs cover
every actual shorter input length and valid capacity.

## Proof structure

Each independent output block contains 32 coefficients. The full run has 80
closed block proofs: 16 at degree 512 and 32 for each degree-1024 modulus.
Together they cover all 2,560 output positions across the three cases.

Every block first proves the scalar representation and modular-subtraction
lemmas it uses. The proof separates the final centered representation from
the exact integer coefficient-sum identity. The centering function is kept
opaque only after proving its definition; no arithmetic result is assumed.

`coverage.saw` proves that the conjunction of the block propositions implies
the original complete vector identity. `normalized.saw` proves that
normalization commutes with zero padding and that the complete vector identity
implies the signed-input theorem needed by the NTT boundary. These six
composition implications are themselves closed proofs.

**Serialized `.core` files contain propositions, not proof certificates.**
The coverage process checks that each loaded proposition is definitionally
equal to its expected block statement. The controller requires a successful
closed proof for every block and binds each composition node to the exact
successful reports of all its premises. Merely writing proposition files or
proving one of the conditional composition statements cannot complete the gate.

## Replay

With the pinned SAW/Cryptol toolchain environment loaded, run from the NTT
repository root:

```sh
python3 verification/consumer-composition/run.py
python3 verification/check-consumer-bridge.py --negative-controls
```

The runner uses two workers by default, a 2 GiB heap ceiling for each SAW
process, a 120-second internal block deadline, and a 180-second external
deadline. It keeps the Mac awake during each proof. Use `--workers 1` to run
sequentially. Proof blocks are cached against all maintained proof source
hashes, shared specification hashes, and exact parameter instances. An
interruption retains completed blocks.

The report is `target/verification-consumer-composition/bridge-report.json`.
After completion, validate the full cached graph and its integrity controls:

```sh
python3 verification/consumer-composition/run.py --check --negative-controls
python3 verification/check-consumer-bridge.py --negative-controls
```

This checks exact task coverage, proof and entry-script hashes, successful
transcripts, proposition exports, and the proved dependency graph. Controls
reject missing/duplicate blocks, wrong parameters, changed logs/scripts/exports,
and an unproved dependency.

The second command is the required final acceptance gate. In SAW 1.6,
`check_convertible` prints `Not convertible` on a mismatch but still returns
successfully. The strict checker therefore requires exactly the expected
successful `Convertible` results: 80 block-to-vector boundaries and three
vector-to-signed-input boundaries. A wrong-modulus control demonstrated the
SAW behavior and was rejected by this strict gate. All 678 recorded proposition
matches in the earlier NTT evidence archives were audited successfully.

The earlier 1024-point transform checkpoint uses its archived proof-script
versions. Its current production Rust and shared mathematical definitions are
unchanged; the old harness is preserved with only six known 2048-point wrappers
appended. Audit that retained evidence with:

```sh
python3 verification/check-archived-1024.py \
  --output target/verification-consumer-composition/rechecked-1024-12289.json
```

This validates the archive's complete file manifest, successful proof/build
records, original loaded dependencies, exact MIR, and current implementation
and mathematical interface. It does not replay the later versions of the
proof tactics. The existing 2048-point gates validate their current sources.

## Implementation connection

The subsequent [consumer-call checkpoint](../consumer-call/README.md) now
verifies three fixed-array entry paths through the complete patched Rust
`polymul_fast` call. Explicit implications and ten checked proposition matches
connect its returned coefficient model to this signed-input negacyclic formula.
The call proof includes validation, padding, the allocating NTT API, folding,
truncation, and constructor metadata. Its separate import checker extends
the trusted proof boundary; an individual SAW invocation is conditional on
its imported MIR contracts. Consumer release integration still remains.
