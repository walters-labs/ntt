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

## Next steps, one at a time

1. Cover parameter generation at the exact calls used by the consumers, if they
   continue to compute roots rather than use the proved constants. This does
   not require a claim about all possible calls to `omega`.
2. Resolve the consumer parameter mismatches and verify the actual padding,
   negacyclic reduction, and coefficient representation described in
   `consumers.md`. Pin the resolved dependencies for integration proofs.
3. Record source/toolchain/dependency versions and automate the required proof
   runs against the exact code to be released.

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
