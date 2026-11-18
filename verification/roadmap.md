# Verification roadmap: three fixed parameter sets

The verification target comprises these three fixed parameter sets. Input
coefficients remain arbitrary signed `i64` values at each tuple. Other lengths,
moduli, and roots accepted by the generic API are outside this target.

| Length | Modulus | Root | Consumer | Transform status |
| --- | --- | --- | --- | --- |
| 1024 | 12289 | 10302 | Module-LWE default | Forward, inverse, cyclic multiplication verified |
| 2048 | 12289 | 1945 | Ring-LWE default | Forward, inverse, cyclic multiplication verified |
| 2048 | 151019521 | 51689479 | Ring-LWE squared-modulus test | Forward, inverse, cyclic multiplication verified |

## Completed 1024-point milestone

Use the split workflow in `README.md`: prove the full mathematical convolution
identity and verify Rust against `multiplication-spec.saw` in separate processes,
then validate the common source and build provenance with `check-split.py`.
The complete workflow passed at 8 and 1024 points. A 10 GiB heap was sufficient
for the 1024-point runs on the 16 GiB development Mac. Use `--keep-awake`: power logs
confirmed that system sleep caused a separate timeout despite little CPU work.

The complete 1024-point mathematical convolution theorem and spectral-product
bridge passed on November 16 in 1,473.838 wall seconds with 6.53 GiB maximum
child RSS, under a 10 GiB heap and 1,800-second deadline. The machine stayed
awake; monotonic elapsed time was 1,473.860 seconds and child CPU time was
1,458.831 seconds.

`spectral-1024-12289.saw` also passed: 31 MIR contracts covering arithmetic,
butterflies, all 20 stages, full kernels, and the three public operations,
along with the direct-DFT model proofs. It took 2,095.494 wall seconds and
5.99 GiB maximum child RSS, with vacuity checking, a 10 GiB heap, and a
3,600-second deadline. `check-split.py` validated both runs' actual dependencies,
shared definition, Rust source, and exact MIR build. This establishes forward,
inverse, and cyclic multiplication at the 1024-point tuple for every signed input.

The runner's default remains 6 GiB; the split runs explicitly request 10 GiB.
The earlier failures and memory experiments are retained in
[the saved results](results/README.md).

## Completed 2048-point milestone

Both 2048-point tuples passed all 33 MIR contracts with vacuity checking, plus
their complete transform-model and convolution graphs. The Rust runs took
8,687.053 / 9,259.766 wall seconds and reached 4.45 / 6.44 GiB maximum child RSS.
The final gates checked the current Rust source, exact MIR, parameter-instance
imports, every closed dependency, and the explicit proposition connections.

Mathematical forward/inverse decomposition, recurrence, and transform models
can be proved as closed output blocks. Proved coverage implications restore the
original full statements. The squared-modulus graph uses a separately closed
1024-point mathematical graph as its half-size premise. These are auxiliary
proof dependencies for the three fixed targets.

Results, transcripts, exact MIR, toolchain records, and source versions are
retained in `results/2026-11-17.tar.gz`. See `results/README.md` for timings and
the unsuccessful attempts that led to the bounded workflow.

## Completed fixed root-selection milestone

`consumer-roots/` contains a selector that returns the verified constant for
each of the three fixed `(modulus,length)` pairs and preserves `omega` as the
fallback for other pairs. Six SAW/MIR contracts prove the three selections
against the existing Cryptol instances and the actual validator's acceptance.
They take about four seconds and 0.56 GiB maximum child RSS. The NTT library's
Rust sources are unchanged; both existing 2048-point proof gates still pass.

Revision-bound patches update the consumers' default constructors and the
squared-modulus test. They were applied to local source copies, and a native
test of both actual defaults passed after compiling the patched libraries.
The patches still need to be applied in the consumer repositories before
release. The formal claim is about the shared selector component; the full
consumer adapters remain outside it. See `consumer-roots/README.md` for scope,
commands, and the separate evidence archive.

A direct proof of `omega` hit an unsupported integer-to-float cast in its
factorization dependency. No generator result was assumed. The fixed branches
remove that dependency from these three cases; other generator calls remain
outside the verification target.

## Next steps, one at a time

The parameter mismatches now have prepared fixes and native regression
coverage in `consumer-parameters/`: the adapter uses a ring-derived fixed
length, and both CLI builders refresh roots after honoring individual overrides.
The actual adapter passes independent schoolbook comparisons at all three fixed
tuples, and both CLI builders pass their regressions. Fifteen tests passed,
including documentation examples; benchmarks compile. This adds no formal
adapter claim and does not modify the NTT library or its existing proof sources.

The next reduction checkpoint is now complete: `consumer-adapter/` contains
an in-place folding/centering implementation and 51 successful MIR contract
checks, including supporting scalar/library contracts. The complete lower-half
formula and preservation of the upper half are proved at all three fixed tuples.
The full run, including native regressions, took about 3.6 minutes and reached
2.11 GiB maximum child RSS.

The polynomial boundary checkpoint is also complete. The actual constructor
preserves and canonically trims 512/1024-word input vectors, and the consumer's
private fixed-buffer helper pads every input length 0..512 and 0..1024 correctly,
with arbitrary signed coefficients and valid capacities. All 1,540 MIR checks
and four native regressions passed in 22.1 minutes with two workers and 0.64 GiB
maximum child RSS. Cached validation takes less than a second. See
`polynomial-boundary/README.md` for exact contracts, patch order, and replay.

The mathematical composition is now complete in `consumer-composition/`.
Eighty closed blocks cover all 2,560 output positions across the three tuples.
Checked coverage and normalization implications establish the centered
negacyclic-product formula for arbitrary signed input vectors. All 83
proposition connections passed the strict acceptance gate. The run took
23.1 minutes with two workers and 0.96 GiB maximum child RSS; cached validation
takes less than a second.

The actual Rust consumer-call composition is now complete for the three
fixed-array entries in `consumer-call/`. All 72 new MIR contracts, the padding
consequence witnesses, and ten exact proposition boundaries passed. The three
complete entry proofs took 60.2, 161.9, and 162.2 seconds; all new jobs sum to
24.2 minutes, with 4.42 GiB maximum child RSS. The import checker validates
previous closed proofs, identical contracts, and complete reachable MIR graphs
before accepting cached MethodSpecs. See `consumer-call/README.md` for the
precise input representation and extended trusted boundary.

The release-integration checkpoint in `consumer-release/` applies the patches
to local release branches and prepares NTT 0.1.10, Ring-LWE 0.1.9, and Module-LWE
0.1.6. Their exact crate sources are tested and all three rebuilt consumer
entry graphs match the successful composed proof. The original NTT proof
checkout remains intact; its version bump lives in a separate release worktree.

1. Review and commit the prepared source and evidence. Publish NTT, Ring-LWE,
   then Module-LWE in dependency order, repeating package verification against
   the registry as each prerequisite becomes available.
2. Retain the resulting final package hashes and keep the checked proof graphs
   and cached audits in the release workflow. Direct calls on arbitrary
   independently allocated `Polynomial` heap layouts remain outside this
   fixed-array entry checkpoint, as do other generic API parameter tuples and
   whole-cryptosystem verification.

## Already established

- All-modulus scalar arithmetic and butterflies: six general MIR contracts.
- General length-one validator acceptance and three larger concrete parameter
  tuples: five contracts, including the supporting standard-library contract.
- All 128 modular-power calls used by ML-KEM's twiddle construction.
- Forward, inverse, and cyclic multiplication for all signed coefficients at
  the four smaller tuples through length 256 and at all three consumer tuples.

The foundation suite contains 139 successful MIR contracts. Those general
helper proofs remain useful even though the transform parameter scope is fixed.
ML-KEM has a separate transform implementation; its modular-power coverage does
not verify that implementation or the whole cryptosystem.

## Scope and tools

Cryptol and SAW/MIR remain the proof tools for these fixed configurations.
An arbitrary-length loop proof and verification of the entire generic API are
outside this scope.

The claims are functional MIR-level correctness under the stated contracts,
including generated safety obligations. They do not establish constant-time
execution, compiler correctness, or whole-cryptosystem security.
