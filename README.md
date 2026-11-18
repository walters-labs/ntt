# ntt

![CI](https://github.com/walters-labs/ntt/actions/workflows/ci.yml/badge.svg)
![MIT License](https://img.shields.io/badge/License-MIT-brightgreen)
[![crates.io](https://img.shields.io/crates/v/ntt.svg)](https://crates.io/crates/ntt)

A radix-2 number theoretic transform in Rust, with prime, prime-power, and
composite coefficient moduli. The arithmetic core uses coefficient slices;
no polynomial object or `polynomial-ring` dependency is required.

## Repeated transforms

Build a transform once to validate the parameters and precompute forward and inverse
twiddle factors. Each in-place transform then reuses those tables and allocates
no memory. A transform stores `n` twiddle coefficients in total when `n > 1`.

```rust
use ntt::PreparedNtt;

let transform = PreparedNtt::new(8, 17, ntt::omega(17, 8));
let mut a = [1, 2, 3, 4, 0, 0, 0, 0];
let original = a;
transform.forward_in_place(&mut a);
transform.inverse_in_place(&mut a);
assert_eq!(a, original);

let b = [5, 6, 7, 8, 0, 0, 0, 0];
let product = transform.multiply(&a, &b);
assert_eq!(product, [5, 16, 0, 9, 10, 1, 15, 0]);
```

The allocating `ntt`, `intt`, and `polymul_ntt` functions remain available with
their existing signatures. They construct a fresh transform for each call; reuse a
transform when the parameters stay fixed. `polymul` now accepts slices, including
ordinary `&Vec<i64>` arguments through coercion.

## Mathematical contract

- The transform length `n` is a nonzero power of two and fits in `i64`.
- Input slices have exactly `n` coefficients.
- The modulus `q` is greater than one and is odd for `n > 1`.
- The supplied root satisfies `omega^n = 1` and, for `n > 1`,
  `omega^(n/2) = -1 (mod q)`. For `n = 1`, the root is `1`.
- Coefficients may be any `i64`, including negative values. Outputs are
  canonical residues in `0..q`. Intermediate arithmetic avoids signed overflow,
  using `i128` multiplication when `(q - 1)^2` would exceed `i64::MAX`.

The forward transform returns the DFT in bit-reversed order. The inverse accepts
that order and returns the normalized coefficients. Constructor and length
checks panic on invalid inputs; they do not silently pad or truncate.

Both multiplication functions compute **cyclic** convolution, modulo `x^n - 1`.
For an ordinary polynomial product, zero-pad to a power-of-two length at least
`a.len() + b.len() - 1` and choose a root for that padded length. To obtain a
product modulo `x^d + 1`, subsequently reduce the ordinary product by that
polynomial; a length-`d` cyclic transform alone does not compute that product.

`omega(q, n)` generates roots for odd moduli. For radix-2 lengths, `n` must divide
`phi(p^e)` for every prime-power factor of `q`. `PreparedNtt::new` accepts a supplied
root and does not need to factor `q`. General parameter generation remains
separate from the transform loops.

## Validation and performance

```text
cargo test
cargo test --release
cargo clippy --all-targets -- -D warnings
cargo bench --bench transform
```

Tests compare against independent DFT and schoolbook-convolution references,
including composite moduli, signed extremes, large moduli, invalid parameters,
and a prime-power root-lifting regression. The benchmark reports the median of
seven batches for both fresh and reused transforms, including buffer handling.

## Formal verification

Archived proof audits are tied to commit `1cf40e1` and their retained build
artifacts. Restore that snapshot and its archived artifacts for cached audits;
see `verification/publication/README.md`. The production Rust and dependency
lockfile in `main` match the published `0.1.10` release.

Cryptol/SAW proofs check the production Rust forward transform, inverse transform,
and cyclic multiplication for **all signed `i64` inputs**, including both extrema:

| Length | Modulus | Root |
| --- | --- | --- |
| 8 | 17 | 9 |
| 16 | 17 | 3 |
| 8 | 289 | 110 |
| 256 | 12289 | 8340 |
| 1024 | 12289 | 10302 |
| 2048 | 12289 | 1945 |
| 2048 | 151019521 | 51689479 |

The specifications use direct DFT and convolution formulas. The proofs include
normalization, parameter construction, and MIR safety obligations.
The larger cases compose verified butterflies, stages, and slice kernels;
a separate recursive proof connects spectral multiplication to cyclic convolution.
The 1024-point case uses two successful SAW processes connected through the
same spectral-product definition, with matching source and build provenance.
The 2048-point cases check Rust, transform-model equivalence, and convolution
in separate proof layers, with checked propositions and matching provenance.

See [verification/README.md](verification/README.md) for the pinned toolchain,
scope, and `bash verification/run.sh` command, which runs the four smaller cases.
Use the documented split workflows for the larger consumer configurations.
The separate `bash verification/run-foundations.sh` suite proves scalar arithmetic and both butterflies
for every valid positive `i64` modulus, including the `i128` multiplication path,
and checks additional parameter and ML-KEM modular-power contracts.
The [consumer inventory](verification/consumers.md) records the actual 1024- and
2048-point targets and the integration work needed for the consuming crates.
The [verification roadmap](verification/roadmap.md) tracks the work needed for
those three fixed parameter sets and their consumer integration.
Transform coverage is limited to the table above. The implementation does not
claim constant-time execution or side-channel resistance.
