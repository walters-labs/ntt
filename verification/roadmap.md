# Verification roadmap: three fixed parameter sets

The verification target comprises these three fixed parameter sets. Input
coefficients remain arbitrary signed `i64` values at each tuple. Other lengths,
moduli, and roots accepted by the generic API are outside this target.

| Length | Modulus | Root | Consumer |
| --- | --- | --- | --- |
| 1024 | 12289 | 10302 | Module-LWE default |
| 2048 | 12289 | 1945 | Ring-LWE default |
| 2048 | 151019521 | 51689479 | Ring-LWE squared-modulus test |

## Next step

Complete the 1024-point cyclic multiplication proof against the independent
convolution formula within the runner's memory budget. The forward and inverse
public-operation proofs have already passed against the independent DFT formulas.
The script is `ntt-1024-12289.saw`. Arithmetic and individual stages alone are
not enough: the mathematical model, full kernels, constructor/twiddle tables,
and all three public-operation contracts must also pass.

The 1024-point stages, direct-DFT models, slice kernels, and public forward and
inverse operations have passed. Cyclic multiplication remains in progress and
requires completion of the mathematical convolution theorem and its connection
to the public multiplication API.

The large interactive session timed out on a convolution identity and reached
about 29 GiB; it has been closed. An isolated proof of that identity succeeded,
but this does not establish the complete multiplication claim. The runner now
defaults to a 6 GiB SAW heap limit. Before attempting either 2048-point case,
complete the remaining 1024-point proof with separately retained lemmas and
validate the full batch run under a stated memory budget.

## Following steps, one at a time

1. Complete the two 2048-point transform cases using the same proof structure.
2. Cover parameter generation at the exact calls used by the consumers, if they
   continue to compute roots rather than use the proved constants. This does
   not require a claim about all possible calls to `omega`.
3. Resolve the consumer parameter mismatches and verify the actual padding,
   negacyclic reduction, and coefficient representation described in
   `consumers.md`. Pin the resolved dependencies for integration proofs.
4. Record source/toolchain/dependency versions and automate the required proof
   runs against the exact code to be released.

## Already established

- All-modulus scalar arithmetic and butterflies: six general MIR contracts.
- General length-one validator acceptance and three larger concrete parameter
  tuples: five contracts, including the supporting standard-library contract.
- All 128 modular-power calls used by ML-KEM's twiddle construction.
- Forward, inverse, and cyclic multiplication for all signed coefficients at
  the four previously completed tuples, through length 256.

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
