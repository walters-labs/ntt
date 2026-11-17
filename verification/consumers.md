# Consumer inventory and verification targets

This inventory reads the three repositories at the revisions below. It describes
their source-level calls, not a verification of those crates or their published
packages. All three declare `ntt = "0.1.9"`; the proofs in this repository apply
to the current checkout, which has unpublished changes.

| Repository | Inspected revision |
| --- | --- |
| mlkem-fips203 | [6e5536514671c119d6f6e0049be0119a7a340520](https://github.com/walters-labs/mlkem-fips203/tree/6e5536514671c119d6f6e0049be0119a7a340520) |
| module-lwe | [6fd32d3f70e8a0d9154f3edd1726267cbec9b3ff](https://github.com/walters-labs/module-lwe/tree/6fd32d3f70e8a0d9154f3edd1726267cbec9b3ff) |
| ring-lwe | [555b26a579779f265bce237d9c2d3d5c91090372](https://github.com/walters-labs/ring-lwe/tree/555b26a579779f265bce237d9c2d3d5c91090372) |

The inspected repositories do not contain Cargo lockfiles. Module-LWE declares
`ring-lwe = "0.1.6"`; its actual resolved dependency must be recorded before an
end-to-end consumer proof. The adapter described here is the inspected ring-LWE
revision, whose package version is 0.1.8.

## Actual calls and parameters

Distinguish the ring degree `d` from the length `N` passed to `ntt`.

| Consumer/configuration | Ring degree and modulus | Use of this crate | Default full-length NTT target |
| --- | --- | --- | --- |
| ML-KEM-512, -768, -1024 | `d=256`, `q=3329`, `x^256+1` | `mod_exp(17, bit_reverse(i,7), 3329)`, for `i=0..127` | No call to this crate's transform; 128 modular-power evaluations |
| Module-LWE default | `d=512`, `q=12289`, `x^512+1`, rank 8 | `omega(q,2*d)` and ring-LWE's multiplication adapter | `N=1024`, root `10302` |
| Ring-LWE default | `d=1024`, `q=12289`, `x^1024+1` | `omega(q,2*d)` and `polymul_ntt` | `N=2048`, root `1945` |
| Ring-LWE homomorphic-product test | `d=1024`, `q=12289^2=151019521` | Recomputes `omega(q,2*d)` before key generation/encryption | `N=2048`, root `51689479` |
| Ring-LWE small example/test/benchmark | Four coefficients per input, `q=17` | Pads and calls `polymul_ntt` | `N=8`, root `9` |

The numeric roots above were checked using this checkout's `omega` and the
independent product tests in `tests/consumer_contracts.rs`. Formal transform
proofs now cover all three fixed tuples; the consumers' root-generation calls
remain a separate obligation.

Source anchors:

- [ML-KEM parameter constructors](https://github.com/walters-labs/mlkem-fips203/blob/6e5536514671c119d6f6e0049be0119a7a340520/src/parameters.rs#L31): all three variants use the same 128 powers; the names 512/768/1024 do not change the polynomial length.
- [ML-KEM's own transform and multiplication](https://github.com/walters-labs/mlkem-fips203/blob/6e5536514671c119d6f6e0049be0119a7a340520/src/utils.rs#L973): seven stages ending at width 2, inverse scaling by `128^-1`, and quadratic base multiplication. These functions are outside this crate's proofs.
- [Module-LWE defaults and multiplication calls](https://github.com/walters-labs/module-lwe/blob/6fd32d3f70e8a0d9154f3edd1726267cbec9b3ff/src/utils.rs#L25).
- [Ring-LWE defaults](https://github.com/walters-labs/ring-lwe/blob/555b26a579779f265bce237d9c2d3d5c91090372/src/utils.rs#L22), [multiplication adapter](https://github.com/walters-labs/ring-lwe/blob/555b26a579779f265bce237d9c2d3d5c91090372/src/utils.rs#L124), and [squared-modulus test](https://github.com/walters-labs/ring-lwe/blob/555b26a579779f265bce237d9c2d3d5c91090372/src/test.rs#L55).

## The cyclic-to-negacyclic connection

The ring-LWE adapter chooses
`N = 2 * next_power_of_two(max(x.coeffs().len(), y.coeffs().len()))`, pads both
inputs to `N`, calls the cyclic product, and reduces the result modulo `f`.
Its coefficient normalization returns centered representatives, whereas `ntt`
returns canonical representatives in `0..q`.

For inputs of degree less than `d`, padding to `2*d` prevents cyclic wraparound
of their ordinary product. Reduction modulo `x^d+1` then gives
`result[i] = (product[i] - product[i+d]) mod q`. The independent tests compare
this composition with direct negacyclic schoolbook multiplication, including
signed extrema. A formal proof of the consumer's actual padding, polynomial
representation, reduction, and centering code is still required.

## Parameter-consistency findings

1. **A stored root can disagree with an input-dependent transform length.**
   Defaults store a root of order `2*d`, but the adapter selects `N` from the
   coefficient lengths. Short or zero polynomials can therefore select a smaller
   transform with the old root. For example, three coefficients select `N=8`;
   neither default root above has order 8. The current `PreparedNtt::new`
   correctly rejects these combinations. The adapter should either use a fixed
   transform length derived from the ring parameters or obtain a suitable root
   for each chosen length. This needs a consumer-side change and proof.

2. **CLI overrides retain the old root.**
   Both [module-LWE](https://github.com/walters-labs/module-lwe/blob/6fd32d3f70e8a0d9154f3edd1726267cbec9b3ff/src/main.rs#L197)
   and [ring-LWE](https://github.com/walters-labs/ring-lwe/blob/555b26a579779f265bce237d9c2d3d5c91090372/src/main.rs#L202)
   update `n`, `q`, and `f` when all three optional parameters are supplied, but
   retain the default `omega`. The tests reproduce rejection for the documented
   module-LWE `(d=256,q=7681)` example and ring-LWE `(d=512,q=12289)` override.
   Recomputing the root resolves the NTT parameter mismatch. Partial overrides
   are ignored by these builders; their supported CLI contract also needs review.

These are findings about the pinned source and this checkout's NTT contract.
The consumer repositories have not been modified or rebuilt as part of this audit.
No whole-cryptosystem correctness or security claim follows from the NTT proofs.

## Completion targets

1. **Completed in the foundation suite:** prove scalar normalization, addition, subtraction, and both multiplication
   branches for arbitrary valid `i64` moduli, rather than repeating fixed-modulus
   arithmetic proofs for every consumer configuration.
2. **Completed in the foundation suite:** verify all modular-power calls actually used to construct ML-KEM's twiddle
   table. Its own transform needs a separate specification and implementation proof.
3. **Partially completed:** establish parameter-validation contracts. Length-one
   validation and acceptance of the three larger consumer tuples are proved;
   general validation and the consumers' actual root-generation calls remain.
4. **Completed:** forward, inverse, and cyclic-multiplication proofs passed for
   all signed coefficients at `(1024,12289,10302)`, `(2048,12289,1945)`, and
   `(2048,151019521,51689479)`. The 2048-point gates connect closed mathematical,
   transform-model, and Rust proofs to the exact source and MIR build.
5. Resolve the consumer parameter findings and prove the actual negacyclic
   adapters. Record exact dependency versions and repeat verification against
   the code that is released.

The 256-point proof remains a valid earlier milestone. The full default consumer
transform targets are 1024 and 2048 points; none is covered by that proof alone.
