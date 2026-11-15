use ntt::{crt, intt, mod_exp, ntt, omega, polymul, polymul_ntt, primitive_root, PreparedNtt};

// Independent arithmetic references: do not call the crate's modular helpers.
fn product_reference(a: &[i64], b: &[i64], n: usize, q: i64) -> Vec<i64> {
    let q = q as i128;
    let mut c = vec![0i128; n];
    for (i, &x) in a.iter().enumerate() {
        for (j, &y) in b.iter().enumerate() {
            let term = (x as i128).rem_euclid(q) * (y as i128).rem_euclid(q) % q;
            c[(i + j) % n] = (c[(i + j) % n] + term) % q;
        }
    }
    c.into_iter().map(|x| x as i64).collect()
}

fn dft_reference(a: &[i64], w: i64, q: i64) -> Vec<i64> {
    let q = q as i128;
    let mut root_k = 1;
    (0..a.len())
        .map(|_| {
            let mut power = 1;
            let mut sum = 0;
            for &a_j in a {
                sum = (sum + (a_j as i128).rem_euclid(q) * power % q) % q;
                power = power * root_k % q;
            }
            root_k = root_k * w as i128 % q;
            sum as i64
        })
        .collect()
}

fn bit_reverse(k: usize, n: usize) -> usize {
    if n == 1 {
        0
    } else {
        k.reverse_bits() >> (usize::BITS - n.trailing_zeros())
    }
}

fn check_case(a: &[i64], b: &[i64], q: i64, w: i64) {
    let n = a.len();
    let transform = PreparedNtt::new(n, q, w);
    assert_eq!(transform.size(), n);
    assert_eq!(transform.modulus(), q);
    let mut transformed = a.to_vec();
    transform.forward_in_place(&mut transformed);
    let expected_dft = dft_reference(a, w, q);
    for k in 0..n {
        assert_eq!(
            transformed[bit_reverse(k, n)],
            expected_dft[k],
            "DFT: n={n}, q={q}, k={k}"
        );
    }
    assert_eq!(ntt(a, w, n, q), transformed);
    let expected_input: Vec<_> = a.iter().map(|x| x.rem_euclid(q)).collect();
    assert_eq!(intt(&transformed, w, n, q), expected_input);
    transform.inverse_in_place(&mut transformed);
    assert_eq!(transformed, expected_input);
    let expected_product = product_reference(a, b, n, q);
    assert_eq!(transform.multiply(a, b), expected_product);
    assert_eq!(polymul_ntt(a, b, n, q, w), expected_product);
    assert_eq!(polymul(a, b, n as i64, q), expected_product);
}

#[test]
fn transforms_match_independent_dft_and_convolution() {
    let mut state = 0x7b91_4f03_e26d_051au64;
    for (q, max_n) in [
        (17, 16),
        (17 * 17, 16),
        (17 * 41, 8),
        (17 * 41 * 73, 8),
        (17i64.pow(4), 16),
    ] {
        for n in [1, 2, 4, 8, 16].into_iter().filter(|n| *n <= max_n) {
            let w = omega(q, n);
            for _ in 0..12 {
                let mut next = || {
                    state ^= state << 13;
                    state ^= state >> 7;
                    state ^= state << 17;
                    state as i64
                };
                let a: Vec<_> = (0..n).map(|_| next()).collect();
                let b: Vec<_> = (0..n).map(|_| next()).collect();
                check_case(&a, &b, q, w);
            }
        }
    }
}

#[test]
fn exhaustive_two_coefficient_products() {
    let transform = PreparedNtt::new(2, 5, 4);
    for a0 in 0..5 {
        for a1 in 0..5 {
            for b0 in 0..5 {
                for b1 in 0..5 {
                    let (a, b) = ([a0, a1], [b0, b1]);
                    assert_eq!(transform.multiply(&a, &b), product_reference(&a, &b, 2, 5));
                }
            }
        }
    }
}

#[test]
fn signed_extremes_and_large_moduli() {
    // Exercise both multiplication widths at the exact dispatch boundary.
    for q in [3_037_000_499, 3_037_000_501, i64::MAX] {
        check_case(&[i64::MIN, q - 1], &[i64::MAX, -1], q, q - 1);
    }
    let q = 5i64.pow(27);
    let w = mod_exp(2, 5i64.pow(26), q);
    check_case(
        &[q - 1, q - 2, i64::MIN, i64::MAX],
        &[1, -1, q - 1, q - 2],
        q,
        w,
    );
    check_case(&[i64::MIN], &[i64::MAX], 2, 1);
    assert_eq!(mod_exp(i64::MIN, 2, i64::MAX), 1);
    assert_eq!(mod_exp(3_037_000_499, 2, 3_037_000_500), 1);
    assert_eq!(mod_exp(-2, 3, 17), 9);
    assert_eq!(mod_exp(0, 0, 17), 1);
}

#[test]
fn application_sized_products() {
    for (n, q) in [(256, 3329), (1024, 12289), (1024, 12289 * 12289)] {
        let a: Vec<i64> = (0..n).map(|i| (i as i64 * 7919 + 13) % q).collect();
        let b: Vec<_> = a.iter().rev().copied().collect();
        let expected = product_reference(&a, &b, n, q);
        assert_eq!(polymul_ntt(&a, &b, n, q, omega(q, n)), expected);
    }
}

#[test]
fn cyclic_wraparound_is_not_negacyclic() {
    let a = [0, 0, 0, 1];
    let b = [0, 1, 0, 0];
    assert_eq!(polymul_ntt(&a, &b, 4, 17, omega(17, 4)), [1, 0, 0, 0]);
    assert_eq!(
        polymul(&[1, 2, 3, 4, 5], &[2, -1, 0], 2, 17),
        product_reference(&[1, 2, 3, 4, 5], &[2, -1, 0], 2, 17)
    );
}

#[test]
fn invalid_parameters_are_rejected() {
    // 2 has order 4 modulo 15, but it is not a principal fourth root.
    for (n, q, w) in [
        (0, 17, 1),
        (3, 17, 1),
        (8, 17, 1),
        (4, 15, 2),
        (2, 4, 3),
        (1, 17, 2),
        (1, 0, 1),
        (1, 1, 1),
        (1, -17, 1),
    ] {
        assert!(std::panic::catch_unwind(|| PreparedNtt::new(n, q, w)).is_err());
    }
    assert!(std::panic::catch_unwind(|| mod_exp(2, -1, 17)).is_err());
    assert!(std::panic::catch_unwind(|| polymul(&[], &[], 0, 17)).is_err());
    assert!(std::panic::catch_unwind(|| omega(17, 0)).is_err());
    assert!(std::panic::catch_unwind(|| omega(17, 32)).is_err());
}

#[test]
fn mismatched_lengths_are_rejected_before_mutation() {
    let w = omega(17, 8);
    let transform = PreparedNtt::new(8, 17, w);
    for n in [0, 7, 9] {
        let mut a = vec![-1; n];
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(
            || transform.forward_in_place(&mut a)
        ))
        .is_err());
        assert_eq!(a, vec![-1; n]);
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(
            || transform.inverse_in_place(&mut a)
        ))
        .is_err());
        assert_eq!(a, vec![-1; n]);
        assert!(std::panic::catch_unwind(|| ntt(&a, w, 8, 17)).is_err());
        assert!(std::panic::catch_unwind(|| intt(&a, w, 8, 17)).is_err());
        assert!(std::panic::catch_unwind(|| polymul_ntt(&[0; 8], &a, 8, 17, w)).is_err());
    }
}

#[test]
fn crt_avoids_large_intermediate_overflow() {
    for (a, b, m, n) in [
        (i64::MAX, i64::MIN, 2_147_483_647, 2_147_483_629),
        (-1, 4, 17, 41),
        (0, 3, 1, 7),
        (3, 0, 7, 1),
    ] {
        let x = crt(a, m, b, n);
        assert!(0 <= x && x < m * n);
        assert_eq!(x % m, a.rem_euclid(m));
        assert_eq!(x % n, b.rem_euclid(n));
    }
    assert!(std::panic::catch_unwind(|| crt(0, 6, 1, 9)).is_err());
    assert!(std::panic::catch_unwind(|| crt(0, i64::MAX, 1, 2)).is_err());
}

#[test]
fn primitive_root_lifting_checks_the_square() {
    // The least primitive root 5 modulo 40487 fails to generate modulo p^2.
    let p = 40487i64;
    let modulus = p.pow(3);
    let phi = (p - 1) * p * p;
    let g = primitive_root(p, 3);
    assert_eq!(mod_exp(g, phi, modulus), 1);
    for factor in [2, 31, 653, p] {
        assert_ne!(mod_exp(g, phi / factor, modulus), 1);
    }
    assert_eq!(primitive_root(2, 1), 1);
    assert_eq!(primitive_root(2, 2), 3);
    assert!(std::panic::catch_unwind(|| primitive_root(2, 3)).is_err());
    assert!(std::panic::catch_unwind(|| primitive_root(17, 0)).is_err());
}
